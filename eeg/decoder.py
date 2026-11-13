"""
decoder.py - turns NeuroPawn EEG into the 5 AdaptiBoard commands (up/down/left/right/ok).

The controller screen flickers five keys at different frequencies. Looking at one makes
your visual cortex oscillate at that frequency (SSVEP). Every 0.5 s this script takes the
last few seconds of EEG, scores each frequency with filter-bank CCA (fbcca.py - no training
needed) and, once one key clearly wins, sends that command to the AdaptiBoard server.

It reads the flicker frequencies and on/off state from the controller (through the server),
so the two can never disagree, and it only decides while the keys are actually flickering.

Run (close the NeuroPawn EXG Visualizer first - only one program can use the headset):
    python eeg/decoder.py --server http://localhost:8000 --port /dev/cu.usbserial-XXXX
    python eeg/decoder.py --server http://192.168.1.23:8000 --port COM3          (Windows)
    python eeg/decoder.py --server ... --port ... --imu                          (IMU board)
    python eeg/decoder.py --server ... --port ... --clench-model switch.joblib   (jaw clench = OK too)

Test without a headset:
    python eeg/decoder.py --server http://localhost:8000 --simulate
        then type u / d / l / r / o + Enter to "look" at a key, or just Enter to look away.
    python eeg/decoder.py --server http://localhost:8000 --synthetic   (BrainFlow's fake board)

Electrodes: SSVEP is strongest over the back of the head. 8 channels: O1, Oz, O2, PO3, POz, PO4, PO7, PO8.
Put as many channels as you can there; use conductive paste.
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fbcca import FBCCA, Decider, preprocess  # noqa: E402

DIRS = ["up", "left", "ok", "right", "down"]
DEFAULT_FREQS = {"up": 6.0, "down": 8.0, "left": 10.0, "right": 12.0, "ok": 15.0}


# ---------------------------------------------------------------- EEG sources
class HeadsetSource:
    """The real NeuroPawn Knight board through BrainFlow (or BrainFlow's synthetic board)."""

    def __init__(self, args):
        from eeg_bci import connect

        self.board, self.fs, self.eeg_ch, self.ts_ch = connect(args)
        self.lock = threading.Lock()

    def latest(self, n):
        with self.lock:
            d = self.board.get_current_board_data(n)
        return d[self.eeg_ch]

    def raw(self, n):
        with self.lock:
            return self.board.get_current_board_data(n)

    def close(self):
        from eeg_bci import release

        with self.lock:
            release(self.board)


class SimSource:
    """Fake EEG for testing everything without a headset.

    Background noise + a little alpha, plus an SSVEP at the frequency of the key you're
    "looking" at (type u/d/l/r/o + Enter in this terminal).
    """

    def __init__(self, fs=125, n_ch=8, amp=2.2):
        self.fs, self.n_ch, self.amp = fs, n_ch, amp
        self.freqs = dict(DEFAULT_FREQS)
        self.target = None
        self.rng = np.random.default_rng(0)
        self.phase = self.rng.uniform(0, 2 * np.pi, n_ch)
        self.gain = self.rng.uniform(0.4, 1.0, n_ch)
        threading.Thread(target=self._keys, daemon=True).start()

    def _keys(self):
        keys = {"u": "up", "d": "down", "l": "left", "r": "right", "o": "ok", "k": "ok"}
        print("[sim] type u/d/l/r/o + Enter to look at a key; Enter alone = look away")
        for line in sys.stdin:
            c = line.strip().lower()[:1]
            self.target = keys.get(c)
            print(f"[sim] looking at: {self.target or 'nothing'}")

    def latest(self, n):
        t = time.time() - np.arange(n)[::-1] / self.fs
        x = self.rng.normal(0, 6.0, (self.n_ch, n))
        x += 3.0 * np.sin(2 * np.pi * 10.3 * t + self.phase[:, None] * 0.3)  # alpha
        x += 25 * np.sin(2 * np.pi * 0.4 * t)[None]  # slow drift (filtered out)
        if self.target:
            f = self.freqs[self.target]
            s = np.sin(2 * np.pi * f * t[None] + self.phase[:, None]) \
                + 0.4 * np.sin(2 * np.pi * 2 * f * t[None] + 2 * self.phase[:, None])
            x += self.amp * self.gain[:, None] * s
        return x

    def close(self):
        pass


# ---------------------------------------------------------------- server connection
class Hub:
    """WebSocket link to the AdaptiBoard server. Reconnects automatically."""

    def __init__(self, server, room=""):
        u = urlparse(server if "://" in server else f"http://{server}")
        scheme = "wss" if u.scheme == "https" else "ws"
        self.url = f"{scheme}://{u.netloc}/ws?role=decoder" + (f"&room={room}" if room else "")
        self.ws = None
        self.lock = threading.Lock()
        self.stimulus = {"on": False, "freqs": dict(DEFAULT_FREQS)}
        self.connected = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        from websockets.sync.client import connect

        while True:
            try:
                with connect(self.url, open_timeout=5) as ws:
                    self.ws = ws
                    self.connected.set()
                    print(f"[hub] connected to {self.url}")
                    for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "status" and "stimulus" in msg:
                            st = msg["stimulus"]
                            if st != self.stimulus:
                                self.stimulus = {"on": bool(st.get("on")),
                                                 "freqs": {**DEFAULT_FREQS, **(st.get("freqs") or {})}}
                                print(f"[hub] flicker {'ON' if self.stimulus['on'] else 'off'} "
                                      f"{self.stimulus['freqs']}")
            except Exception as e:
                if self.connected.is_set():
                    print(f"[hub] disconnected ({e}); retrying...")
                else:
                    print(f"[hub] can't reach {self.url} ({e}); retrying...")
            self.ws = None
            self.connected.clear()
            time.sleep(2)

    def send(self, msg):
        ws = self.ws
        if not ws:
            return False
        try:
            with self.lock:
                ws.send(json.dumps(msg))
            return True
        except Exception:
            return False


# ---------------------------------------------------------------- SSVEP loop
def ssvep_loop(src, hub, args, stop):
    fs = src.fs if hasattr(src, "fs") else 125
    n = int(args.window * fs)
    need = n + 2 * fs  # extra so filter edges stay outside the window
    model, decider, key, was_on = None, None, None, False
    ok_locked, ok_time = False, 0.0
    step = 0.5
    while not stop.is_set():
        time.sleep(step)
        st = hub.stimulus
        on = st["on"] or args.always
        if not on:
            if was_on:
                hub.send({"type": "lean", "direction": None, "conf": 0})
            was_on = False
            continue
        freqs = [float(st["freqs"][d]) for d in DIRS]
        if isinstance(src, SimSource):
            src.freqs = dict(zip(DIRS, freqs))
        if model is None or key != tuple(freqs) or not was_on:
            model = FBCCA(freqs, fs, n)
            decider = Decider(5, z=args.z, strict={DIRS.index("ok"): args.ok_strict})
            decider.cool = int(args.window / step)  # wait for a full window of flicker
            key, was_on = tuple(freqs), True
            print(f"[ssvep] deciding between {dict(zip(DIRS, freqs))} Hz, {args.window}s window")
        d = src.latest(need)
        if d.shape[1] < need:
            continue
        x = preprocess(d, fs, notch=args.notch)[:, -n:]
        dec, lead, conf = decider.update(model.scores(x))
        hub.send({"type": "lean", "direction": DIRS[lead], "conf": round(conf, 3)})
        if args.verbose:
            print(f"  lean {DIRS[lead]:5s} {conf:4.0%}")
        # Arrows may repeat while you keep looking (hold → to keep moving), but OK must
        # re-arm: after an OK, look away from OK before another OK can fire.
        if ok_locked and (DIRS[lead] != "ok" or time.time() - ok_time > args.ok_rearm):
            ok_locked = False
        if dec is not None and DIRS[dec] == "ok":
            if ok_locked:
                continue
            ok_locked, ok_time = True, time.time()
        if dec is not None:
            print(f"[ssvep] -> {DIRS[dec].upper()} ({freqs[dec]} Hz)")
            hub.send({"type": "command", "direction": DIRS[dec], "source": "eeg", "conf": 1.0})


def clench_loop(src, hub, args, stop):
    """Optional: a jaw-clench model from eeg_bci.py acts as a second OK button."""
    import joblib
    from eeg_bci import features
    from eeg_bci import preprocess as pre

    bundle = joblib.load(args.clench_model)
    model, labels = bundle["model"], bundle["labels"]
    k = labels.index(args.clench_label)
    fs = src.fs
    rows = src.eeg_ch[:bundle["n_channels"]]
    need, win = int(fs * (bundle["win"] + 2)), int(fs * bundle["win"])
    smooth = np.ones(len(labels)) / len(labels)
    armed, last = True, 0.0
    print(f"[clench] '{args.clench_label}' = OK")
    while not stop.is_set():
        time.sleep(0.1)
        d = src.raw(need)
        if d.shape[1] < need:
            continue
        x = pre(d[rows], fs, bundle["notch"], bundle.get("car", False))[:, -win:]
        p = model.predict_proba(features(x, fs)[None])[0]
        smooth = 0.5 * smooth + 0.5 * p
        now = time.time()
        if smooth[k] >= 0.7 and armed and now - last >= 1.0:
            print(f"[clench] -> OK (p={smooth[k]:.2f})")
            hub.send({"type": "command", "direction": "ok", "source": "eeg-clench"})
            armed, last = False, now
        elif smooth[k] < 0.42:
            armed = True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://localhost:8000", help="AdaptiBoard server address")
    ap.add_argument("--room", default="", help="private room id on a hosted server (open the board with ?room=<id>)")
    ap.add_argument("--port", default="COM3", help="headset serial port (Mac: /dev/cu.usbserial-XXXX)")
    ap.add_argument("--simulate", action="store_true", help="fake EEG, steer it from the keyboard")
    ap.add_argument("--synthetic", action="store_true", help="BrainFlow synthetic board")
    ap.add_argument("--imu", action="store_true", help="the box says IMU")
    ap.add_argument("--n-channels", type=int, default=8)
    ap.add_argument("--gain", type=int, default=12)
    ap.add_argument("--notch", type=float, default=60.0, help="mains frequency (60 US, 50 EU/India)")
    ap.add_argument("--window", type=float, default=4.0, help="seconds of EEG per decision")
    ap.add_argument("--z", type=float, default=3.0, help="evidence needed: higher = fewer mistakes, slower")
    ap.add_argument("--ok-strict", type=float, default=1.3, help="OK needs this much more evidence")
    ap.add_argument("--ok-rearm", type=float, default=8.0,
                    help="after OK, seconds of steady gaze on OK before it can fire again")
    ap.add_argument("--always", action="store_true", help="decide even when the controller isn't flickering")
    ap.add_argument("--clench-model", help="joblib model from eeg_bci.py train (jaw clench = OK)")
    ap.add_argument("--clench-label", default="clench")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.simulate:
        src = SimSource()
    else:
        print("Connecting to the headset (channel setup takes ~20 s)...")
        src = HeadsetSource(args)
    hub = Hub(args.server, args.room)
    stop = threading.Event()
    threads = [threading.Thread(target=ssvep_loop, args=(src, hub, args, stop), daemon=True)]
    if args.clench_model and not args.simulate:
        threads.append(threading.Thread(target=clench_loop, args=(src, hub, args, stop), daemon=True))
    for t in threads:
        t.start()
    print("Decoder running. Start the flicker on the controller screen. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        time.sleep(0.6)
        src.close()


if __name__ == "__main__":
    main()
