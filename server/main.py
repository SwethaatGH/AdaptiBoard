"""
AdaptiBoard server - the hub between the board, the controller and the EEG decoder.

    Board laptop:      python server/main.py         (serves everything on port 8000)
    Board screen:      http://localhost:8000/
    Controller screen: http://<board-laptop-IP>:8000/controller
    EEG decoder:       python eeg/decoder.py --server http://<board-laptop-IP>:8000 ...

WebSocket /ws?role=board|controller|decoder carries:
    command   {direction: up|down|left|right|ok, source}  controller/decoder -> board
    lean      {direction, conf}                            decoder -> controller (feedback)
    stimulus  {on, freqs}                                  controller -> decoder
    heard     {text}                                       board mic -> server (context)
    alert     {level, label, say} / {clear: true}          server -> board + controller (Needs)
"""
import argparse
import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _load_env():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import grammar  # noqa: E402
import icons  # noqa: E402
import llm  # noqa: E402
import predictor  # noqa: E402
import needs  # noqa: E402
import speech  # noqa: E402
from vocab import CATEGORIES, CATEGORY_WORDS, MORE_CATEGORIES, WORDS  # noqa: E402

DIST = HERE.parent / "web" / "dist"
DATA = HERE / "data"
DIRECTIONS = {"up", "down", "left", "right", "ok"}
DEFAULT_FREQS = {"up": 6.0, "down": 8.0, "left": 10.0, "right": 12.0, "ok": 15.0}

from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    words = [it["label"] for items in CATEGORY_WORDS.values() for it in items if it["pos"] != "little"]
    words += [w for w in WORDS if WORDS[w]["pos"] != "little"]
    words += [t["icon"] for t in needs.need_tiles() if t["icon"]]
    task = asyncio.create_task(icons.prefetch(sorted(set(words))))  # pictograms, in background
    yield
    task.cancel()


app = FastAPI(title="AdaptiBoard", lifespan=lifespan)
usage = predictor.Usage(DATA / "usage.json")


class State:
    def __init__(self):
        self.clients: dict[WebSocket, str] = {}
        self.lines: list[tuple[float, str]] = []  # what was heard: (time, text)
        self.version = 0
        self.ctx_llm: dict | None = None
        self.ctx_task: asyncio.Task | None = None
        self.stimulus = {"on": False, "freqs": DEFAULT_FREQS}
        self.profile: dict = {}
        self.last_command = None
        self.alert: dict | None = None


S = State()


# ---------------------------------------------------------------- websocket hub
async def send(ws, msg):
    try:
        await ws.send_text(json.dumps(msg))
    except Exception:
        pass


async def broadcast(msg, roles=None):
    for ws, role in list(S.clients.items()):
        if roles is None or role in roles:
            await send(ws, msg)


def status_msg():
    counts = {"board": 0, "controller": 0, "decoder": 0}
    for r in S.clients.values():
        counts[r] = counts.get(r, 0) + 1
    return {"type": "status", "clients": counts, "stimulus": S.stimulus,
            "llm": llm.provider(), "llmModel": llm.model_name(), "stt": speech.stt_provider(),
            "tts": speech.TTS_AVAILABLE}


async def handle_command(direction, source="unknown", conf=None):
    if direction not in DIRECTIONS:
        return False
    S.last_command = {"direction": direction, "source": source, "t": time.time()}
    print(f"[command] {direction:5s} from {source}" + (f" (conf {conf:.2f})" if conf else ""))
    await broadcast({"type": "command", "direction": direction, "source": source,
                     "ts": time.time()}, roles={"board", "controller"})
    return True


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    role = ws.query_params.get("role", "board")
    await ws.accept()
    S.clients[ws] = role
    print(f"[ws] {role} connected ({len(S.clients)} clients)")
    await broadcast(status_msg())
    if role == "board":
        await send(ws, context_msg())
    if S.alert and role in ("board", "controller"):
        await send(ws, {"type": "alert", **S.alert})
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            t = msg.get("type")
            if t == "command":
                await handle_command(msg.get("direction"), msg.get("source", role), msg.get("conf"))
            elif t == "lean":
                await broadcast({"type": "lean", "direction": msg.get("direction"),
                                 "conf": msg.get("conf", 0)}, roles={"controller"})
            elif t == "stimulus":
                freqs = {k: float(v) for k, v in (msg.get("freqs") or {}).items() if k in DIRECTIONS}
                S.stimulus = {"on": bool(msg.get("on")),
                              "freqs": freqs if len(freqs) == 5 else S.stimulus["freqs"]}
                print(f"[stimulus] {'ON' if S.stimulus['on'] else 'off'} {S.stimulus['freqs']}")
                await broadcast(status_msg())
            elif t == "heard":
                await add_heard(msg.get("text", ""))
            elif t == "profile":
                S.profile = msg.get("profile") or {}
            elif t == "ping":
                await send(ws, {"type": "pong"})
    except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
        pass
    finally:
        S.clients.pop(ws, None)
        print(f"[ws] {role} disconnected")
        await broadcast(status_msg())


# ---------------------------------------------------------------- conversation context
def context_msg():
    ctx = current_context()
    return {"type": "context", "version": S.version,
            "lines": [{"t": t, "text": s} for t, s in S.lines[-8:]],
            "keywords": list(ctx["keywords"].keys())[:8], "question": ctx["question"],
            "options": ctx["options"], "topic": (S.ctx_llm or {}).get("topic", ""),
            "answers": ctx.get("answers", []),
            "items": [i["label"] for i in ctx.get("items", [])]}


def current_context():
    ctx = predictor.extract_context(S.lines)
    c = S.ctx_llm
    if c and time.time() - c["time"] < 150:
        ctx["items"] = c["items"]
        ctx["topic"] = c["topic"]
        if c["question_to_user"] and time.time() - c["time"] < 45:
            ctx["question"] = True
            ctx["answers"] = c["answers"]
    return ctx


async def add_heard(text):
    text = " ".join(str(text).split())[:400]
    if not text:
        return
    S.lines.append((time.time(), text))
    S.lines = S.lines[-60:]
    S.version += 1
    print(f"[heard] {text}")
    await broadcast(context_msg(), roles={"board"})
    if llm.provider():
        if S.ctx_task and not S.ctx_task.done():
            S.ctx_task.cancel()
        S.ctx_task = asyncio.create_task(refresh_llm_context(S.version))


async def refresh_llm_context(version):
    await asyncio.sleep(1.0)  # wait for the speaker to finish their sentence
    try:
        c = await llm.extract_context(S.lines, S.profile)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[llm] context failed: {e}")
        return
    c["time"] = time.time()
    S.ctx_llm = c
    print(f"[llm] context: topic={c['topic']!r} items={[i['label'] for i in c['items']]} "
          f"answers={c['answers']}")
    if version == S.version:
        await broadcast({**context_msg(), "llmUpdate": True}, roles={"board"})


# ---------------------------------------------------------------- HTTP API
@app.get("/api/config")
async def config():
    lexicon = {}
    for items in CATEGORY_WORDS.values():
        for it in items:
            if " " not in it["label"] and it["label"].lower() not in lexicon:
                lexicon[it["label"].lower()] = {"label": it["label"], "pos": it["pos"], "n": 0}
    for w, n in usage.unigrams.items():  # words this user has used (incl. typed ones)
        e = lexicon.setdefault(w, {"label": WORDS.get(w, {}).get("label", w),
                                   "pos": predictor.guess_pos(w), "n": 0})
        e["n"] = n
    return {"categories": [{"id": c, "label": l, "emoji": e} for c, l, e in CATEGORIES],
            "columns": [{"id": c, "title": t} for c, t in predictor.COLUMNS],
            "voices": [{"id": v, "label": l} for v, l in speech.VOICES],
            "defaultVoice": speech.DEFAULT_VOICE, "freqs": S.stimulus["freqs"],
            "lexicon": list(lexicon.values()), **status_msg()}


def _with_heard(tiles, ctx, category, page_index):
    """Category pages: words heard in the conversation go first."""
    heard = [i for i in ctx.get("items", []) if i.get("category") == category]
    if not heard or page_index:
        return tiles
    have = {t["label"].lower() for t in tiles}
    extra = [predictor.make_tile(i["label"], "context", i["pos"], i["emoji"])
             for i in heard if i["label"].lower() not in have][:4]
    if not extra:
        return tiles
    keep = [t for t in tiles if t["kind"] != "more"][:predictor.SLOTS - len(extra) - 1]
    more = [t for t in tiles if t["kind"] == "more"]
    return (extra + keep + more)[:predictor.SLOTS]


@app.post("/api/predict")
async def predict(req: Request):
    body = await req.json()
    message = [str(w) for w in body.get("message", [])][-12:]
    page = body.get("page", "smart")
    page_index = int(body.get("pageIndex", 0))
    profile = body.get("profile") or S.profile
    S.profile = profile or S.profile
    ctx = current_context()
    base = {"completion": "", "source": "vocab", "contextVersion": S.version}

    if page == "keyboard":
        return {**base, "tiles": []}
    if page == "more":
        return {**base, "tiles": predictor.more_page(MORE_CATEGORIES)}
    if page == "chat":
        return {**base, "tiles": predictor.chat_page(page_index, usage)}
    if page == "needs":
        return {**base, "tiles": needs.need_tiles()}
    if page != "smart":
        tiles = predictor.category_page(page, page_index, ctx, usage, profile)
        return {**base, "tiles": _with_heard(tiles, ctx, page, page_index)}

    # Smart Board: 4 columns
    offline = predictor.predict_columns(message, ctx, usage, profile)
    cols, completion, source = offline, "", "offline"
    if llm.provider():
        try:
            res = await asyncio.wait_for(
                llm.predict(message, S.lines, profile, usage.summary(message), offline),
                timeout=llm.timeout() + 0.5)
            cols = predictor.predict_columns(message, ctx, usage, profile, ai=res["columns"])
            completion, source = res["completion"], "ai"
        except Exception as e:
            print(f"[llm] predict fell back to offline: {type(e).__name__}: {e}")
    columns = [{"id": c, "title": t, "tiles": cols[c]} for c, t in predictor.COLUMNS]
    return {"columns": columns, "tiles": [t for c in columns for t in c["tiles"]],
            "completion": completion, "source": source, "contextVersion": S.version}


_polished = {}  # words -> sentence (so the same words never cost two GPT calls)


@app.post("/api/polish")
async def polish(req: Request):
    """Chosen words -> a grammatical sentence for the message bar (GPT, else offline rules)."""
    words = [str(w) for w in (await req.json()).get("words", []) if str(w).strip()][-16:]
    if len(words) < 2:
        return {"text": "", "source": "none"}
    key = " ".join(words).lower()
    if key in _polished:
        return _polished[key]
    res = {"text": grammar.offline(words), "source": "offline"}
    if llm.provider():
        try:
            text = await asyncio.wait_for(llm.polish(words), timeout=llm.timeout() + 0.5)
            if text and grammar.keeps_words(text, words):
                res = {"text": text, "source": "ai"}
            else:
                print(f"[llm] polish rejected (changed the words): {text!r}")
        except Exception as e:
            print(f"[llm] polish fell back to offline: {type(e).__name__}: {e}")
    if res["source"] == "ai" or not llm.provider():
        _polished[key] = res
        if len(_polished) > 500:
            _polished.pop(next(iter(_polished)))
    return res


@app.post("/api/select")
async def select(req: Request):
    """The user chose a word: learn it (pairs, triples, time of day)."""
    body = await req.json()
    word = str(body.get("word", "")).strip()
    if word:
        usage.add(body.get("prev"), word, body.get("prev2"))
    return {"ok": True}


@app.post("/api/spoken")
async def spoken(req: Request):
    """A whole sentence was spoken: save it for the Chat page."""
    usage.add_phrase(str((await req.json()).get("text", "")))
    return {"ok": True}


@app.get("/api/phrases")
async def phrases():
    return {"phrases": [{"text": p, **usage.phrases[p]} for p in usage.top_phrases(200)]}


@app.post("/api/phrases/delete")
async def delete_phrase(req: Request):
    usage.remove_phrase(str((await req.json()).get("text", "")))
    return {"ok": True}


async def notify_caregiver(level, label, say):
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        return
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=6) as client:
            await client.post(f"{server}/{topic}", content=say.encode(),
                              headers={"Title": f"AdaptiBoard: {label}",
                                       "Priority": "urgent" if level == "emergency" else "high",
                                       "Tags": "rotating_light" if level == "emergency" else "bell"})
        print(f"[need] caregiver notified via {server}/{topic}")
    except Exception as e:
        print(f"[need] caregiver notification failed: {e}")


@app.post("/api/need")
async def need(req: Request):
    """A Needs tile was chosen. Emergencies/urgent needs alert everyone + the caregiver's phone."""
    body = await req.json()
    level, label, say = body.get("level", "normal"), str(body.get("label", "")), str(body.get("say", ""))
    print(f"[need] {level.upper()}: {label} -> {say!r}")
    if level in ("emergency", "urgent"):
        S.alert = {"level": level, "label": label, "say": say, "t": time.time()}
        await broadcast({"type": "alert", **S.alert}, roles={"board", "controller"})
        asyncio.create_task(notify_caregiver(level, label, say))
    return {"ok": True, "notify": bool(os.getenv("NTFY_TOPIC"))}


@app.post("/api/alert/clear")
async def clear_alert():
    S.alert = None
    await broadcast({"type": "alert", "clear": True}, roles={"board", "controller"})
    return {"ok": True}


@app.post("/api/heard")
async def heard(req: Request):
    await add_heard((await req.json()).get("text", ""))
    return {"ok": True, "version": S.version}


@app.post("/api/transcript/clear")
async def clear_transcript():
    S.lines, S.ctx_llm = [], None
    S.version += 1
    await broadcast(context_msg(), roles={"board"})
    return {"ok": True}


@app.post("/api/transcribe")
async def transcribe(req: Request):
    audio = await req.body()
    if len(audio) < 2000:
        return {"text": ""}
    try:
        text = await speech.transcribe(audio, req.headers.get("content-type", "audio/webm"))
    except Exception as e:
        return JSONResponse({"error": str(e)}, 503)
    if text and req.query_params.get("append") == "1":
        await add_heard(text)
    return {"text": text}


@app.get("/api/tts")
async def tts(text: str, voice: str = speech.DEFAULT_VOICE, rate: str = "+0%"):
    audio = await speech.tts(text[:300], voice, rate)
    if not audio:
        return JSONResponse({"error": "tts unavailable"}, 503)
    return Response(audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "public, max-age=31536000"})


@app.get("/api/icon/{word}")
async def icon(word: str):
    p = await icons.icon_path(word)
    if not p:
        return Response(status_code=404)
    return FileResponse(p, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.post("/api/command")
async def command(req: Request):
    """For decoders that prefer plain HTTP:  POST {"direction": "left"}"""
    body = await req.json()
    ok = await handle_command(str(body.get("direction", "")).lower(), body.get("source", "http"))
    return JSONResponse({"ok": ok}, 200 if ok else 400)


@app.get("/api/status")
async def status():
    return {**status_msg(), "lastCommand": S.last_command}


# ---------------------------------------------------------------- web app
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
async def spa(path: str):
    f = DIST / path
    if path and f.is_file():
        return FileResponse(f)
    index = DIST / "index.html"
    if not index.exists():
        return Response("Web app not built yet. Run:  cd web && npm install && npm run build",
                        media_type="text/plain", status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main():
    ap = argparse.ArgumentParser(description="AdaptiBoard server")
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 lets the controller laptop connect")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print("\n  AdaptiBoard")
    print(f"  Board (this laptop):  http://localhost:{args.port}/")
    for ip in lan_ips():
        print(f"  Controller laptop:    http://{ip}:{args.port}/controller")
        print(f"  EEG decoder:          python eeg/decoder.py --server http://{ip}:{args.port} ...")
    print(f"  LLM: {llm.provider() or 'offline predictor'} {llm.model_name()}"
          f" | STT (server): {speech.stt_provider() or 'browser only'}"
          f" | TTS: {'edge neural voices' if speech.TTS_AVAILABLE else 'browser voice'}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
