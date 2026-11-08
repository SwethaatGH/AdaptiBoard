"""
board_server.py - connects the Knight headset (via BrainFlow) to board.html.

How it fits together:
    headset --BrainFlow--> this server --Server-Sent Events--> board.html (in Chrome)
      - clench switch: your eeg_bci.py model, fires "select" events
      - SSVEP "look to select": NeuroPawn's TRCA pipeline (github.com/NeuroPawn/ssvep)
      - SSVEP arrow navigation: training-free FBCCA adapted from NeuroKnights (fbcca.py),
        driven by a separate control screen at http://localhost:8000/control

Setup (close the EXG Visualizer first - only one program can use the headset):
    git clone https://github.com/NeuroPawn/ssvep neuropawn-ssvep     # once, inside this folder
    pip install meegkit pandas

Run:
    python board_server.py                                             # board only (Space key)
    python board_server.py --model switch.joblib --port COM3           # clench switch
    python board_server.py --ssvep --port COM3                         # SSVEP only
    python board_server.py --ssvep --model switch.joblib --port COM3   # both (hybrid)
    python board_server.py --nav --port COM3                           # arrows + OK screen
    python board_server.py --nav --model switch.joblib --port COM3     # arrows, clench = OK too
Then open http://localhost:8000 in Chrome.

The board's SSVEP flicker uses NeuroPawn's frequencies and timing (read from their
config.py), and training data is saved in their CSV format, so their evaluate tools
understand it. Train on the board itself ("Train SSVEP" button): TRCA learns your
response to THIS screen's flicker, so training and use must happen on the same board.
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

HERE = Path(__file__).resolve().parent
clients, clients_lock = [], threading.Lock()
status = {"type": "status", "eeg": False, "switch": False, "ssvep": False, "nav": False,
          "msg": "Headset not connected (Space key works)"}
stop = threading.Event()
headset = None  # Headset, once connected
ssvep = None    # SSVEPEngine, once ready
nav = None      # NavEngine, once ready


def broadcast(msg):
    data = json.dumps(msg)
    with clients_lock:
        for q in clients:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass


def set_status(msg, **flags):
    status.update(msg=msg, **flags)
    broadcast(status)
    print(f"[status] {msg}")


# ---------------------------------------------------------------- shared headset session
class Headset:
    """One BrainFlow session shared by the clench switch and SSVEP."""

    def __init__(self, args):
        from eeg_bci import connect

        self.board, self.fs, self.eeg_ch, self.ts_ch = connect(args)
        self.lock = threading.Lock()

    def latest(self, n):
        with self.lock:
            return self.board.get_current_board_data(n)

    def release(self):
        from eeg_bci import release

        with self.lock:
            release(self.board)


# ---------------------------------------------------------------- SSVEP (NeuroPawn TRCA)
class SSVEPEngine:
    """Capture / train / predict using NeuroPawn's ssvep package (imported, not copied)."""

    def __init__(self, repo, data_dir, hs):
        repo = Path(repo).resolve()
        if not (repo / "ssvep" / "trca_model.py").exists():
            raise FileNotFoundError(
                f"NeuroPawn SSVEP repo not found at {repo}. Run:\n"
                "  git clone https://github.com/NeuroPawn/ssvep neuropawn-ssvep")
        sys.path.insert(0, str(repo))
        from ssvep import config as cfg
        from ssvep.preprocessing import crop_indices, extract_channel_matrix, filter_eeg
        from ssvep.trca_model import build_model, load_training_data

        self.cfg, self.hs, self.data_dir = cfg, hs, str(data_dir)
        self._filter, self._extract, self._crop = filter_eeg, extract_channel_matrix, crop_indices
        self._load, self._build = load_training_data, build_model
        self.model, self.accuracy, self.lock = None, None, threading.Lock()
        if hs.fs != cfg.SAMPLING_RATE:
            print(f"[ssvep] warning: board runs at {hs.fs} Hz but NeuroPawn config expects "
                  f"{cfg.SAMPLING_RATE} Hz")
        os.makedirs(self.data_dir, exist_ok=True)
        if self.blocks() >= 1:
            try:
                self.train()
            except Exception as e:
                print(f"[ssvep] could not train on existing data: {e}")

    def info(self):
        c = self.cfg
        return {"available": True, "freqs": list(c.STIMULUS_FREQUENCIES),
                "cue": c.CUE_DURATION, "flicker": c.FLICKER_DURATION, "rest": c.INTER_TRIAL_INTERVAL,
                "blocks": self.blocks(), "trained": self.model is not None, "accuracy": self.accuracy}

    def blocks(self):
        """Number of complete blocks (every target recorded); a cancelled block doesn't count."""
        b = 0
        while all(os.path.exists(os.path.join(self.data_dir, f"block_{b + 1}_{t}.csv"))
                  for t in range(1, self.cfg.N_TARGETS + 1)):
            b += 1
        return b

    def capture(self, t_end):
        """The flicker window that ended at t_end (server time), filtered NeuroPawn's way.

        Returns a (samples, channels) array, the same shape NeuroPawn saves and predicts on.
        """
        n = self.cfg.CAPTURE_SAMPLES
        hs = self.hs
        deadline = time.time() + 0.8
        while True:  # wait for samples up to t_end to arrive over USB
            d = hs.latest(n + 2 * hs.fs)
            ts = d[hs.ts_ch]
            if (ts.size and ts[-1] >= t_end) or time.time() > deadline:
                break
            time.sleep(0.02)
        if d.shape[1] < n:
            return None
        if ts.size and abs(ts[-1] - t_end) < 3:  # timestamps usable: anchor to flicker end
            k = int(np.searchsorted(ts, t_end, side="right"))
        else:  # fall back to NeuroPawn's behaviour: the latest samples
            k = d.shape[1]
        if k < n:
            return None
        win = np.ascontiguousarray(d[:, k - n:k])
        self._filter(win, hs.eeg_ch, hs.fs)
        return self._extract(win, hs.eeg_ch)

    def save(self, window, block, target):
        path = os.path.join(self.data_dir, f"block_{block}_{target + 1}.csv")
        header = ",".join(self.cfg.ELECTRODE_LABELS[:window.shape[1]])
        np.savetxt(path, window, delimiter=",", header=header, comments="", fmt="%.7f")
        return os.path.basename(path)

    def train(self):
        """Fit TRCA on all blocks; leave-one-block-out accuracy when there are 2+ blocks."""
        nb = self.blocks()
        if nb == 0:
            raise ValueError("No SSVEP training data yet")
        nt = self.cfg.N_TARGETS
        eeg, labels = self._load(self.data_dir, nb)
        accs = []
        if nb >= 2:
            for i in range(nb):
                tr = np.concatenate((eeg[..., :i * nt], eeg[..., (i + 1) * nt:]), axis=2)
                ytr = np.concatenate((labels[:i * nt], labels[(i + 1) * nt:]))
                m = self._build()
                m.fit(tr, ytr)
                accs.append(float(np.mean(m.predict(eeg[..., i * nt:(i + 1) * nt])
                                          == labels[i * nt:(i + 1) * nt])))
        model = self._build()
        model.fit(eeg, labels)
        with self.lock:
            self.model = model
            self.accuracy = float(np.mean(accs)) if accs else None
        acc = f"{self.accuracy:.0%}" if self.accuracy is not None else "n/a (need 2+ blocks)"
        print(f"[ssvep] TRCA trained on {nb} blocks, cross-validated accuracy {acc}")
        return {"blocks": nb, "accuracy": self.accuracy, "per_block": accs}

    def predict(self, window):
        with self.lock:
            if self.model is None:
                return None
            trial = np.expand_dims(window, axis=2)[self._crop()]
            return int(self.model.predict(trial)[0])


# ---------------------------------------------------------------- arrow navigation (FBCCA)
class NavEngine:
    """Continuously decides which control-screen arrow you're looking at. No training needed.

    The control page flickers 5 targets non-stop; every `step` seconds this takes the last
    `window` seconds of EEG, scores each frequency with filter-bank CCA (fbcca.py, adapted
    from NeuroKnights) and accumulates evidence until one target clearly wins.
    """
    ACTIONS = ["up", "left", "ok", "right", "down"]
    # 60 Hz screen: 9, 8, 5, 7, 6 frames per cycle. 10 Hz sits on "down" (harmless) because
    # relaxed alpha rhythm is also ~10 Hz; OK gets 12 Hz, the clearest in your tests.
    DEFAULT_FREQS = [6.67, 7.5, 12.0, 8.57, 10.0]

    def __init__(self, hs, args):
        from fbcca import FBCCA, Decider, preprocess

        self.hs, self.preprocess, self.Decider = hs, preprocess, Decider
        self.freqs = args.nav_freqs or self.DEFAULT_FREQS
        if len(self.freqs) != 5:
            raise ValueError("--nav-freqs needs 5 values: up left ok right down")
        self.win, self.step, self.z = args.nav_window, 0.5, args.nav_z
        self.n = int(self.win * hs.fs)
        self.model = FBCCA(self.freqs, hs.fs, self.n)
        self.enabled = threading.Event()
        self.decider = self.new_decider()

    def new_decider(self):  # OK needs 30% more evidence than an arrow
        return self.Decider(5, z=self.z, strict={self.ACTIONS.index("ok"): 1.3})

    def set_enabled(self, on):
        if on and not self.enabled.is_set():
            self.decider = self.new_decider()
            self.decider.cool = int(self.win / self.step)  # let a full window of flicker arrive
        (self.enabled.set if on else self.enabled.clear)()
        print(f"[nav] {'started' if on else 'paused'}")

    def run(self):
        need = self.n + 2 * self.hs.fs  # extra so filter edges stay outside the window
        while not stop.is_set():
            if not self.enabled.wait(0.2):
                continue
            time.sleep(self.step)
            d = self.hs.latest(need)
            if d.shape[1] < need:
                continue
            x = self.preprocess(d[self.hs.eeg_ch], self.hs.fs)[:, -self.n:]
            dec, lead, conf = self.decider.update(self.model.scores(x))
            broadcast({"type": "navlean", "action": self.ACTIONS[lead], "conf": conf})
            if dec is not None and self.enabled.is_set():
                print(f"[nav] {self.ACTIONS[dec]} ({self.freqs[dec]} Hz)")
                broadcast({"type": "nav", "action": self.ACTIONS[dec]})


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = (HERE / "board.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = queue.Queue(maxsize=200)
            with clients_lock:
                clients.append(q)
            try:
                self.wfile.write(f"data: {json.dumps(status)}\n\n".encode())
                self.wfile.flush()
                while not stop.is_set():
                    try:
                        self.wfile.write(f"data: {q.get(timeout=10)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")  # keeps the connection alive
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            finally:
                with clients_lock:
                    clients.remove(q)
        elif path == "/control":
            body = (HERE / "control.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/nav/config":
            self._json({"available": nav is not None, "actions": NavEngine.ACTIONS,
                        "freqs": nav.freqs if nav else NavEngine.DEFAULT_FREQS})
        elif path == "/ssvep/status":
            self._json(ssvep.info() if ssvep else {"available": False})
        elif path == "/select":  # test hook: open http://localhost:8000/select in another tab
            broadcast({"type": "select"})
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self):
        t_recv = time.time()  # the board posts the instant the flicker ends
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/alert":
            # Help was confirmed on the board. Put your automation here
            # (text a caregiver with Twilio, post to Discord, etc.). Never dial 911 in a demo.
            print(f"[ALERT] Help confirmed at {time.strftime('%H:%M:%S')}")
            self.send_response(204)
            self.end_headers()
        elif url.path == "/ssvep/capture":
            if not ssvep:
                return self._json({"error": "SSVEP not running (start with --ssvep)"}, 503)
            window = ssvep.capture(t_recv)
            if window is None:
                return self._json({"error": "not enough data yet"}, 503)
            if q.get("mode") == "train":
                name = ssvep.save(window, int(q["block"]), int(q["target"]))
                print(f"[ssvep] saved {name}")
                return self._json({"saved": name})
            target = ssvep.predict(window)
            if target is None:
                return self._json({"error": "SSVEP not trained yet"}, 409)
            print(f"[ssvep] looking at target {target} ({ssvep.cfg.STIMULUS_FREQUENCIES[target]} Hz)")
            return self._json({"target": target})
        elif url.path == "/nav/enable":
            if nav:
                nav.set_enabled(q.get("on") == "1")
            self._json({"enabled": bool(nav and nav.enabled.is_set())})
        elif url.path == "/ssvep/train":
            if not ssvep:
                return self._json({"error": "SSVEP not running"}, 503)
            try:
                return self._json(ssvep.train())
            except Exception as e:
                return self._json({"error": str(e)}, 400)
        else:
            self.send_error(404)


# ---------------------------------------------------------------- headset thread
def headset_thread(args):
    global headset, ssvep, nav
    bundle = None
    if args.model:
        import joblib

        bundle = joblib.load(args.model)
        if args.switch_label not in bundle["labels"]:
            set_status(f"--switch-label must be one of {bundle['labels']}")
            return
        args.n_channels = max(args.n_channels if args.ssvep else 0, bundle["n_channels"])

    set_status("Connecting to headset (channel setup takes ~20 s)...")
    try:
        headset = Headset(args)
    except Exception as e:
        set_status(f"Headset connection failed: {e}")
        return

    parts = []
    if args.ssvep:
        try:
            ssvep = SSVEPEngine(args.ssvep_repo, args.ssvep_data, headset)
            parts.append("SSVEP ready" + ("" if ssvep.model else " (train it on the board)"))
        except Exception as e:
            print(f"[ssvep] disabled: {e}")
            parts.append(f"SSVEP failed: {e}")
    if args.nav:
        try:
            nav = NavEngine(headset, args)
            threading.Thread(target=nav.run, daemon=True).start()
            parts.append("arrow screen ready (open /control)")
        except Exception as e:
            print(f"[nav] disabled: {e}")
            parts.append(f"arrows failed: {e}")
    if bundle:
        parts.append(f"'{args.switch_label}' selects")
    set_status("Headset connected - " + ", ".join(parts or ["streaming"]),
               eeg=True, switch=bundle is not None, ssvep=ssvep is not None, nav=nav is not None)

    try:
        if bundle:
            clench_loop(args, bundle)
        else:
            stop.wait()
    except Exception as e:
        set_status(f"Headset error: {e}", eeg=False)
    finally:
        headset.release()


def clench_loop(args, bundle):
    """Runs the clench model ~10x/s and sends one 'select' per clench."""
    from eeg_bci import features, preprocess

    model, labels = bundle["model"], bundle["labels"]
    k_sw = labels.index(args.switch_label)
    fs = headset.fs
    rows = headset.eeg_ch[:bundle["n_channels"]]
    need, win = int(fs * (bundle["win"] + 2)), int(fs * bundle["win"])
    smooth = np.ones(len(labels)) / len(labels)
    armed, last = True, 0.0
    while not stop.is_set():
        time.sleep(0.1)
        d = headset.latest(need)
        if d.shape[1] < need:
            continue
        x = preprocess(d[rows], fs, bundle["notch"], bundle.get("car", False))[:, -win:]
        p = model.predict_proba(features(x, fs)[None])[0]
        smooth = 0.5 * smooth + 0.5 * p
        p_sw = float(smooth[k_sw])
        broadcast({"type": "probs", "label": args.switch_label, "p": p_sw})
        now = time.time()  # one press per clench: rising edge, re-arm once the signal drops
        if p_sw >= args.threshold and armed and now - last >= args.refractory:
            broadcast({"type": "select"})
            print(f"[select] p={p_sw:.2f}")
            armed, last = False, now
        elif p_sw < args.threshold * 0.6:
            armed = True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--model", help="clench model from eeg_bci.py train")
    ap.add_argument("--switch-label", default="clench")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--refractory", type=float, default=1.0)
    ap.add_argument("--ssvep", action="store_true", help="enable SSVEP look-to-select")
    ap.add_argument("--ssvep-repo", default=str(HERE / "neuropawn-ssvep"),
                    help="path to your clone of github.com/NeuroPawn/ssvep")
    ap.add_argument("--ssvep-data", default=str(HERE / "ssvep_training"),
                    help="where board SSVEP training blocks are saved")
    ap.add_argument("--nav", action="store_true", help="enable the arrows + OK control screen")
    ap.add_argument("--nav-window", type=float, default=4.0, help="seconds of EEG per decision")
    ap.add_argument("--nav-z", type=float, default=3.0,
                    help="evidence needed per move: higher = fewer mistakes, slower moves")
    ap.add_argument("--nav-freqs", type=float, nargs=5, metavar="HZ",
                    help="flicker Hz for up left ok right down (default 6.67 7.5 12 8.57 10)")
    ap.add_argument("--port", default="COM3", help="headset serial port")
    ap.add_argument("--n-channels", type=int, default=8)
    ap.add_argument("--gain", type=int, default=12)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--imu", action="store_true")
    args = ap.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    server.daemon_threads = True
    th = None
    if args.model or args.ssvep or args.nav:
        th = threading.Thread(target=headset_thread, args=(args,), daemon=True)
        th.start()
    print(f"Board running at http://localhost:{args.http_port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if th:
            th.join(timeout=3)  # lets the headset session close cleanly
        server.server_close()


if __name__ == "__main__":
    main()