"""
llm.py - optional language-model layer (next tiles, sentence completion, context words).

Pick ONE provider by setting environment variables (or server/.env):

    OPENAI_API_KEY=...      (model: OPENAI_MODEL, default gpt-4o-mini)
    GROQ_API_KEY=...        free tier; (GROQ_MODEL, default llama-3.3-70b-versatile)
    GEMINI_API_KEY=...      free for NC State; (GEMINI_MODEL, default gemini-2.5-flash)
    OLLAMA_MODEL=llama3.2   local + open source; needs `ollama serve` running
    LLM_PROVIDER=openai|groq|gemini|ollama|off   (optional; otherwise first key found wins)
    LLM_TIMEOUT=4           seconds before the board falls back to offline predictions

With nothing set, AdaptiBoard runs fully offline (predictor.py).
"""
import json
import os
import re
import time

import httpx

ALLOWED_POS = {"pronoun", "verb", "noun", "place", "describe", "question", "social",
               "yes", "no", "little"}
CATEGORIES = ["people", "actions", "feelings", "food", "places", "things", "describe",
              "questions", "body", "time", "activities", "chat"]
COLUMN_IDS = ["questions", "people", "actions", "things"]


def provider():
    forced = os.getenv("LLM_PROVIDER", "").strip().lower()
    if forced == "off":
        return None
    if forced:
        return forced
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("OLLAMA_MODEL"):
        return "ollama"
    return None


def model_name(p=None):
    p = p or provider()
    return {
        "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "groq": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "ollama": os.getenv("OLLAMA_MODEL", "llama3.2"),
    }.get(p, "")


def timeout():
    try:
        return float(os.getenv("LLM_TIMEOUT", "4"))
    except ValueError:
        return 4.0


async def _chat_json(system, user, max_tokens=700):
    """Send one prompt, return parsed JSON (or raise)."""
    p = provider()
    if not p:
        raise RuntimeError("no LLM provider configured")
    model = model_name(p)
    async with httpx.AsyncClient(timeout=timeout()) as client:
        if p in ("openai", "groq"):
            base = "https://api.openai.com/v1" if p == "openai" else "https://api.groq.com/openai/v1"
            key = os.getenv("OPENAI_API_KEY" if p == "openai" else "GROQ_API_KEY")
            r = await client.post(f"{base}/chat/completions",
                                  headers={"Authorization": f"Bearer {key}"},
                                  json={"model": model, "temperature": 0.3,
                                        "max_tokens": max_tokens,
                                        "response_format": {"type": "json_object"},
                                        "messages": [{"role": "system", "content": system},
                                                     {"role": "user", "content": user}]})
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
        elif p == "gemini":
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": user}]}],
                      "generationConfig": {"responseMimeType": "application/json",
                                           "temperature": 0.3, "maxOutputTokens": max_tokens,
                                           "thinkingConfig": {"thinkingBudget": 0}}})
            if r.status_code == 400 and "thinking" in r.text.lower():
                # older models don't accept thinkingConfig - retry without it
                body = json.loads(r.request.content)
                body["generationConfig"].pop("thinkingConfig", None)
                r = await client.post(r.request.url, headers={"x-goog-api-key": key}, json=body)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        elif p == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
            r = await client.post(f"{host}/api/chat",
                                  json={"model": model, "stream": False, "format": "json",
                                        "options": {"temperature": 0.3},
                                        "messages": [{"role": "system", "content": system},
                                                     {"role": "user", "content": user}]})
            r.raise_for_status()
            text = r.json()["message"]["content"]
        else:
            raise RuntimeError(f"unknown LLM_PROVIDER {p}")
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)  # tolerate ```json fences
    return json.loads(m.group(0) if m else text)


def _conversation(lines, now=None, limit=12):
    now = now or time.time()
    recent = [(t, s) for t, s in lines if now - t < 180][-limit:]
    if not recent:
        return "(nothing heard recently)"
    return "\n".join(f"[{int(now - t)}s ago] {s}" for t, s in recent)


def _profile_text(profile):
    if not profile:
        return "(no profile)"
    parts = []
    if profile.get("name"):
        parts.append(f"User's name: {profile['name']}")
    if profile.get("family"):
        parts.append("People in their life: " + ", ".join(profile["family"]))
    if profile.get("likes"):
        parts.append("Likes: " + ", ".join(profile["likes"]))
    if profile.get("notes"):
        parts.append("Notes: " + profile["notes"])
    return "\n".join(parts) or "(no profile)"


def clean_tiles(raw, limit=16):
    out, seen = [], set()
    for t in raw or []:
        if isinstance(t, str):
            t = {"label": t}
        label = str(t.get("label", "")).strip().strip(".")
        if not label or len(label) > 26 or len(label.split()) > 4:
            continue
        if label.lower() in seen:
            continue
        pos = str(t.get("pos", "")).lower()
        out.append({"label": label, "pos": pos if pos in ALLOWED_POS else None,
                    "emoji": str(t.get("emoji", ""))[:8],
                    "category": t.get("category") if t.get("category") in CATEGORIES else None})
        seen.add(label.lower())
        if len(out) >= limit:
            break
    return out


SYSTEM_PREDICT = """You are the word-prediction engine inside AdaptiBoard, an AAC \
(augmentative and alternative communication) board. The user cannot speak and builds \
sentences one tile at a time with a brain-computer interface, so every selection costs \
them several seconds. Predict what they will choose NEXT.

The Smart Board has 4 columns of 4 tiles. Sentences are usually built left to right:
- "questions": question words / short questions (what, where, can I, do you...). If someone \
just asked the user something, put direct REPLIES here instead (yes, no, maybe...).
- "people": pronouns and names (I, you, Mom, Grandma, it, that).
- "actions": verbs, feelings and describing words (want, go, eat, tired, happy, more).
- "things": food, drinks, objects and places (water, pizza, TV, park, bathroom).

Rules:
- Up to 4 tiles per column, most likely first. Each tile 1-3 words.
- Tiles CONTINUE the message (never repeat words already chosen). Empty message = starters.
- PERSONALISE: the user's habits are listed - strongly prefer words and sentences they \
actually use, words they choose at this time of day, and people/things from their profile.
- Use names and things from the recent conversation when relevant.
- First-person point of view, simple everyday words, never offensive, no medical advice.
- "emoji": one emoji that pictures the tile. "pos": pronoun|verb|noun|place|describe|question|social|yes|no
- "completion": if the message has 2+ words, ONE short grammatical sentence the user most \
likely means, keeping ALL of their words in order (you may add small words like to/the/a \
and fix verb forms). Otherwise "".
Reply with JSON only:
{"questions":[{"label":"...","emoji":"...","pos":"..."}],"people":[...],"actions":[...],"things":[...],"completion":"..."}"""


def _keep_words(completion, message):
    """Drop completions that change or drop the user's own words."""
    if not completion or len(message) < 2:
        return ""
    low, pos = completion.lower(), 0
    for w in " ".join(message).lower().split():
        i = low.find(w.strip("?.!"), pos)
        if i < 0:
            return ""
        pos = i + len(w)
    return completion


async def predict(message, lines, profile, habits, offline_cols):
    """AI tiles per Smart Board column + an optional whole-sentence completion."""
    offline = "; ".join(f"{c}: {', '.join(t['label'] for t in offline_cols.get(c, []))}"
                        for c in COLUMN_IDS)
    user = (f"Message so far: {json.dumps(' '.join(message)) if message else '(empty)'}\n"
            f"Time of day: {time.strftime('%A %H:%M')}\n"
            f"Recent conversation around the user:\n{_conversation(lines)}\n"
            f"User profile:\n{_profile_text(profile)}\n"
            f"User habits (learned from their past selections):\n{habits}\n"
            f"Offline predictor's guesses (use or improve): {offline}")
    data = await _chat_json(SYSTEM_PREDICT, user)
    cols = {c: clean_tiles(data.get(c), limit=4) for c in COLUMN_IDS}
    completion = _keep_words(str(data.get("completion") or "").strip(), message)
    return {"columns": cols, "completion": completion}


SYSTEM_POLISH = """You fix the grammar of sentences built on an AAC board (the user cannot \
speak and picks one word tile at a time, so the words come out in base form, e.g. \
"I was walk", "he want go park", "me hungry").
Rewrite them into ONE short, natural, grammatical sentence that means exactly the same thing:
- keep every one of the user's words, in the same order (you may change their form: \
walk -> walking/walked, want -> wants, I -> me),
- you may add only small words (to, the, a, am, is, are, of, for, at, it) and punctuation,
- never add new ideas, people or things; first-person stays first-person,
- end with "?" for questions, otherwise ".".
Reply with JSON only: {"text":"..."}"""


async def polish(words):
    data = await _chat_json(SYSTEM_POLISH, f"Words: {json.dumps(' '.join(words))}", max_tokens=80)
    return str(data.get("text") or "").strip()


SYSTEM_CONTEXT = """You listen to the conversation happening around an AAC user (a person \
who cannot speak) and pick out what they may want to say about it.
Return JSON only:
{"topic":"2-4 words","question_to_user":true|false,
 "answers":["up to 4 short replies the user could give, 1-4 words each"],
 "items":[{"label":"1-3 words","pos":"pronoun|verb|noun|place|describe|question|social|yes|no",
           "emoji":"one emoji",
           "category":"people|actions|feelings|food|places|things|describe|questions|body|time|activities"}]}
items: up to 8 words/names/things from the conversation that the user would likely use in a \
reply (people's names, foods, places, activities, feelings). Most relevant first.
question_to_user: true only if the most recent speech asks the user something."""


async def extract_context(lines, profile):
    user = (f"Conversation (oldest first):\n{_conversation(lines, limit=16)}\n"
            f"User profile:\n{_profile_text(profile)}")
    data = await _chat_json(SYSTEM_CONTEXT, user, max_tokens=500)
    answers = [str(a).strip() for a in (data.get("answers") or []) if str(a).strip()][:4]
    return {"topic": str(data.get("topic") or "")[:40],
            "question_to_user": bool(data.get("question_to_user")),
            "answers": [a for a in answers if len(a) <= 30],
            "items": clean_tiles(data.get("items"), limit=8)}
