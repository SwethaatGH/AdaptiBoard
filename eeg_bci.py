"""
eeg_bci.py - record labeled EEG from a NeuroPawn Knight board, train a classifier, run it live.

Setup (close the EXG Visualizer first - only one program can hold the serial port):
    pip install brainflow numpy scipy scikit-learn joblib

Commands:
    python eeg_bci.py check  --port COM3                       # per-channel signal quality
    python eeg_bci.py spectrum --port COM3 --freqs 6.67 8.57 10 12   # Hz per channel
    python eeg_bci.py record --port COM3 --labels open closed --trials 10 --trial-sec 8 --out s1.npz
    python eeg_bci.py train  --data s1.npz s2.npz --model model.joblib
    python eeg_bci.py live   --port COM3 --model model.joblib

    AAC switch mode (Grid 3 / TD Snap on the same laptop; needs `pip install pynput`):
    python eeg_bci.py record --port COM3 --labels rest clench --trials 15 --trial-sec 3 --out sw1.npz
    python eeg_bci.py train  --data sw1.npz --win 1 --model switch.joblib
    python eeg_bci.py live   --port COM3 --model switch.joblib --switch-label clench --switch-key space

    Add --synthetic to check/record/live to test the whole pipeline without the headset.
    Add --imu if your box says IMU.
    Ports: Windows "COM3", Mac "/dev/cu.usbserial-XXXX" (use the cu. one), Linux "/dev/ttyUSB0".
"""
import argparse
import random
import sys
import time

import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt, welch

BANDS = {"delta": (1, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 45)}


# ---------------------------------------------------------------- hardware
def connect(args):
    from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams

    params = BrainFlowInputParams()
    if args.synthetic:
        board_id = BoardIds.SYNTHETIC_BOARD.value
    else:
        name = "NEUROPAWN_KNIGHT_BOARD_IMU" if args.imu else "NEUROPAWN_KNIGHT_BOARD"
        if not hasattr(BoardIds, name):
            sys.exit(f"Your brainflow has no BoardIds.{name}. Run: pip install -U brainflow")
        board_id = getattr(BoardIds, name).value
        params.serial_port = args.port
        params.other_info = '{"gain": %d}' % args.gain

    board = BoardShim(board_id, params)
    board.prepare_session()
    board.start_stream(450000)
    time.sleep(2)
    if not args.synthetic:
        # same as clicking "Active" + "Route RLD" for each channel in the visualizer
        # (timing matches NeuroPawn's example: 0.5s, chon, 1s, rldadd, 0.5s)
        print("Configuring channels (Active + Route RLD)...")
        for ch in range(1, args.n_channels + 1):
            time.sleep(0.5)
            board.config_board(f"chon_{ch}_{args.gain}")
            time.sleep(1.0)
            board.config_board(f"rldadd_{ch}")
            time.sleep(0.5)
            print(f"  ch{ch}: active (gain {args.gain}) + RLD on")
        time.sleep(1.0)
        board.get_board_data()  # discard samples recorded before RLD was active
    fs = BoardShim.get_sampling_rate(board_id)
    eeg_ch = BoardShim.get_exg_channels(board_id)[: args.n_channels]
    ts_ch = BoardShim.get_timestamp_channel(board_id)
    print(f"Connected. fs={fs} Hz, channels={eeg_ch}")
    return board, fs, eeg_ch, ts_ch


def release(board):
    try:
        board.stop_stream()
    except Exception:
        pass
    board.release_session()


# ---------------------------------------------------------------- signal processing
def preprocess(x, fs, notch=60.0, car=False):
    """x: (n_channels, n_samples) raw microvolts -> detrended, notched, 1-45 Hz bandpassed.

    car=True removes noise shared by all channels (bad ground, cables, mains) by subtracting
    the median across channels at each sample. Median, not mean, so one bad electrode
    doesn't leak its noise into the others.
    """
    x = x - x.mean(axis=1, keepdims=True)
    if notch and notch < fs / 2 - 1:
        b, a = iirnotch(notch, 30, fs)
        x = filtfilt(b, a, x, axis=1)
    sos = butter(4, [1, min(45, fs / 2 - 1)], btype="band", fs=fs, output="sos")
    x = sosfiltfilt(sos, x, axis=1)
    if car and x.shape[0] >= 3:
        x = x - np.median(x, axis=0, keepdims=True)
    return x


def features(win, fs):
    """win: (n_channels, n_samples) filtered -> 1D feature vector."""
    f, p = welch(win, fs=fs, nperseg=min(win.shape[1], int(fs)), axis=1)
    total = p[:, (f >= 1) & (f <= 45)].sum(axis=1) + 1e-12
    feats = []
    for lo, hi in BANDS.values():
        bp = p[:, (f >= lo) & (f < hi)].sum(axis=1)
        feats.append(np.log(bp + 1e-12))  # absolute band power
        feats.append(bp / total)  # relative band power
    feats.append(np.log(win.std(axis=1) + 1e-12))  # amplitude: catches blinks / jaw clench
    feats.append(np.log(np.abs(win).max(axis=1) + 1e-12))
    return np.concatenate(feats)


# ---------------------------------------------------------------- commands
def cmd_check(args):
    board, fs, eeg_ch, ts_ch = connect(args)
    print("Live channel quality (std of 1-45 Hz signal, uV). Ctrl+C to stop.")
    print("  ~5-50 = plausible EEG | ~0 = dead/not connected | huge = loose contact or railed")
    print(f"  shared-noise removal (--car): {'ON' if args.car else 'off'}\n")
    last_ts, stalled = None, 0
    try:
        while True:
            time.sleep(1)
            d = board.get_current_board_data(int(fs * 3))
            if d.shape[1] < fs * 2:
                continue
            ts = d[ts_ch][-1]
            if ts == last_ts:
                stalled += 1
                print(f"  !! no new data for {stalled}s - stream stopped. Check the USB cable; "
                      "Ctrl+C, unplug/replug, and restart.")
                continue
            last_ts, stalled = ts, 0
            x = preprocess(d[eeg_ch], fs, args.notch, args.car)[:, int(fs):]
            print("  ".join(f"ch{i + 1}:{s:7.1f}" for i, s in enumerate(x.std(axis=1))))
    except KeyboardInterrupt:
        pass
    finally:
        release(board)


def spectrum_table(x, fs, freqs=()):
    """Per-channel frequency summary of filtered EEG x (channels, samples).

    Returns rows of: peak frequency (Hz, searched 3-45 Hz so slow drift doesn't always win;
    None when no frequency clearly stands out),
    % of 1-45 Hz power in each band, and SNR at each requested frequency (power there vs.
    neighbouring frequencies; > 6 is a clear peak, ~1 means nothing special).
    """
    f, p = welch(x, fs=fs, nperseg=min(x.shape[1], int(fs * 2)), noverlap=int(fs * 1.5), axis=1)
    total = p[:, (f >= 1) & (f <= 45)].sum(axis=1) + 1e-12
    search = (f >= 3) & (f <= 45)
    rows = []
    for c in range(x.shape[0]):
        ps = p[c, search]
        # only call it a peak if it clearly stands above this channel's typical power
        peak = f[search][np.argmax(ps)] if ps.max() > 4 * np.median(ps) else None
        bands = [100 * p[c, (f >= lo) & (f < hi)].sum() / total[c] for lo, hi in BANDS.values()]
        snrs = []
        for hz in freqs:
            k = int(np.argmin(np.abs(f - hz)))
            nb = [i for i in range(k - 7, k + 8) if 0 <= i < len(f) and abs(i - k) > 1]
            snrs.append(p[c, k] / (p[c, nb].mean() + 1e-12))
        rows.append((peak, bands, snrs))
    return rows


def cmd_spectrum(args):
    board, fs, eeg_ch, ts_ch = connect(args)
    freqs = args.freqs or []
    head = "       peak Hz" + "".join(f"{b:>7}" for b in BANDS) + "".join(f"  {hz:>5}Hz" for hz in freqs)
    print("Strongest frequency and band power per channel (last 4 s). Ctrl+C to stop.")
    print("  delta 1-4 Hz | theta 4-8 | alpha 8-13 (eyes closed, relaxed) | beta 13-30 (focus) | "
          "gamma 30-45 (often muscle)")
    if freqs:
        print("  Hz columns = SNR at that frequency: > 6 means a clear peak (e.g. an SSVEP you're looking at)")
    last_ts = None
    try:
        while True:
            time.sleep(1)
            d = board.get_current_board_data(int(fs * 5))
            if d.shape[1] < fs * 5:
                continue
            if d[ts_ch][-1] == last_ts:
                print("  !! no new data - stream stopped. Check the USB cable and restart.")
                continue
            last_ts = d[ts_ch][-1]
            x = preprocess(d[eeg_ch], fs, args.notch, args.car)[:, int(fs):]
            print("\n" + head)
            for i, (peak, bands, snrs) in enumerate(spectrum_table(x, fs, freqs)):
                pk = f"{peak:7.1f}" if peak is not None else "   none"
                print(f"  ch{i + 1}  {pk}" + "".join(f"{b:6.0f}%" for b in bands)
                      + "".join(f"  {s:7.1f}" for s in snrs))
    except KeyboardInterrupt:
        pass
    finally:
        release(board)


def cmd_record(args):
    board, fs, eeg_ch, ts_ch = connect(args)
    trials = [i for i in range(len(args.labels)) for _ in range(args.trials)]
    random.shuffle(trials)
    events = []
    print(f"\n{len(trials)} trials of {args.trial_sec}s. Settling for 5s - sit still...")
    time.sleep(5)
    try:
        for n, lab in enumerate(trials, 1):
            print(f"\n[{n}/{len(trials)}] Get ready:  >>> {args.labels[lab].upper()} <<<")
            time.sleep(2)
            print("   GO")
            t0 = time.time()
            time.sleep(args.trial_sec)
            t1 = time.time()
            print("   stop - relax")
            events.append((t0, t1, lab))
            time.sleep(args.rest_sec)
        time.sleep(0.5)
        data = board.get_board_data()
    except KeyboardInterrupt:
        print("\nStopped early - saving what was recorded.")
        data = board.get_board_data()
    finally:
        release(board)

    np.savez(args.out, eeg=data[eeg_ch], ts=data[ts_ch], events=np.array(events),
             labels=np.array(args.labels), fs=fs)
    print(f"Saved {args.out}: {data.shape[1] / fs:.0f}s of data, {len(events)} trials")


def build_dataset(files, win_sec, step_sec, notch, skip_sec=0.5, car=False):
    X, y, groups, labels, fs0 = [], [], [], None, None
    for fi, path in enumerate(files):
        d = np.load(path, allow_pickle=True)
        fs, labs = int(d["fs"]), list(d["labels"])
        if labels is None:
            labels, fs0 = labs, fs
        if labs != labels or fs != fs0:
            sys.exit(f"{path} has different labels/fs than the first file")
        eeg = preprocess(d["eeg"], fs, notch, car)
        ts = d["ts"]
        win, step = int(win_sec * fs), int(step_sec * fs)
        for ti, (t0, t1, lab) in enumerate(d["events"]):
            idx = np.where((ts >= t0 + skip_sec) & (ts <= t1))[0]
            if len(idx) < win:
                continue
            seg = eeg[:, idx[0]: idx[-1] + 1]
            for s in range(0, seg.shape[1] - win + 1, step):
                X.append(features(seg[:, s: s + win], fs))
                y.append(int(lab))
                groups.append(fi * 10000 + ti)  # one group per trial: no leakage in CV
    return np.array(X), np.array(y), np.array(groups), labels, fs0


def cmd_train(args):
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import GroupKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, y, groups, labels, fs = build_dataset(args.data, args.win, args.step, args.notch, car=args.car)
    n_ch = X.shape[1] // (2 * len(BANDS) + 2)
    print(f"{len(X)} windows, {X.shape[1]} features, {len(set(groups))} trials, classes={labels}")
    if len(set(groups)) < 4:
        sys.exit("Need more trials - record at least 2 per class.")

    models = {
        "logreg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5)),
        "forest": make_pipeline(StandardScaler(), RandomForestClassifier(300, min_samples_leaf=3, random_state=0)),
    }
    cv = GroupKFold(n_splits=min(5, len(set(groups))))
    best, best_acc = None, -1
    for name, m in models.items():
        pred = cross_val_predict(m, X, y, groups=groups, cv=cv)
        acc = (pred == y).mean()
        print(f"\n== {name}: cross-validated accuracy {acc:.1%} (chance ~{1 / len(labels):.0%})")
        print(confusion_matrix(y, pred))
        print(classification_report(y, pred, target_names=labels, zero_division=0))
        if acc > best_acc:
            best, best_acc = name, acc

    model = models[best].fit(X, y)
    joblib.dump({"model": model, "labels": labels, "fs": fs, "n_channels": n_ch,
                 "win": args.win, "notch": args.notch, "car": args.car}, args.model)
    print(f"Saved {best} model -> {args.model}")


class SwitchEmulator:
    """Turns predictions into switch presses for AAC apps (Grid 3, TD Snap, ...).

    Fires one key press when `trigger` label is detected above `threshold`, then waits
    until the signal returns to another label AND `refractory` seconds pass before it can
    fire again - so one clench = one press, not a stream of presses.
    """

    def __init__(self, trigger, key, threshold=0.7, refractory=1.0):
        from pynput.keyboard import Controller, Key

        self.kb = Controller()
        self.key = getattr(Key, key) if hasattr(Key, key) else key  # "space", "enter", "f1", or "1"
        self.trigger, self.threshold, self.refractory = trigger, threshold, refractory
        self.armed, self.last = True, 0.0

    def __call__(self, label, prob):
        now = time.time()
        if label == self.trigger and prob >= self.threshold:
            if self.armed and now - self.last >= self.refractory:
                self.kb.press(self.key)
                self.kb.release(self.key)
                self.last, self.armed = now, False
                print(f"\n  >> SWITCH PRESS ({self.trigger}, p={prob:.2f})")
        elif label != self.trigger:
            self.armed = True


def on_prediction(label, prob):
    """Hook your app here: move a game character, send a keypress, post to a websocket, etc."""
    pass


def cmd_live(args):
    import joblib

    bundle = joblib.load(args.model)
    model, labels = bundle["model"], bundle["labels"]
    args.n_channels = bundle["n_channels"]
    board, fs, eeg_ch, _ = connect(args)
    if fs != bundle["fs"]:
        print(f"Warning: model trained at {bundle['fs']} Hz, board is {fs} Hz")
    need = int(fs * (bundle["win"] + 2))  # extra 2s so filter edges don't hit the window
    win = int(fs * bundle["win"])
    smooth = np.ones(len(labels)) / len(labels)
    hook = on_prediction
    if args.switch_label:
        if args.switch_label not in labels:
            sys.exit(f"--switch-label must be one of {labels}")
        hook = SwitchEmulator(args.switch_label, args.switch_key, args.threshold, args.refractory)
        print(f"Switch mode: '{args.switch_label}' presses '{args.switch_key}'. "
              "Click into your AAC app window so it receives the key.")
    print("Running. Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(0.25)
            d = board.get_current_board_data(need)
            if d.shape[1] < need:
                continue
            x = preprocess(d[eeg_ch], fs, bundle["notch"], bundle.get("car", False))[:, -win:]
            p = model.predict_proba(features(x, fs)[None])[0]
            smooth = 0.6 * smooth + 0.4 * p  # simple smoothing so output doesn't flicker
            k = int(smooth.argmax())
            bars = "  ".join(f"{l}:{'#' * int(s * 20):<20}" for l, s in zip(labels, smooth))
            print(f"\r{bars}  -> {labels[k]:<10}", end="", flush=True)
            hook(labels[k], float(smooth[k]))
    except KeyboardInterrupt:
        print()
    finally:
        release(board)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def hw(p):
        p.add_argument("--port", default="COM3")
        p.add_argument("--n-channels", type=int, default=8)
        p.add_argument("--gain", type=int, default=12)
        p.add_argument("--synthetic", action="store_true")
        p.add_argument("--imu", action="store_true")
        p.add_argument("--notch", type=float, default=60.0)  # US mains
        p.add_argument("--car", action="store_true", help="remove noise shared by all channels")

    p = sub.add_parser("check"); hw(p)
    p = sub.add_parser("spectrum"); hw(p)
    p.add_argument("--freqs", type=float, nargs="*", help="also show SNR at these Hz, e.g. 6.67 8.57 10 12")
    p = sub.add_parser("record"); hw(p)
    p.add_argument("--labels", nargs="+", required=True)
    p.add_argument("--trials", type=int, default=10, help="trials per label")
    p.add_argument("--trial-sec", type=float, default=8)
    p.add_argument("--rest-sec", type=float, default=2)
    p.add_argument("--out", required=True)
    p = sub.add_parser("train")
    p.add_argument("--data", nargs="+", required=True)
    p.add_argument("--model", default="model.joblib")
    p.add_argument("--win", type=float, default=2.0)
    p.add_argument("--step", type=float, default=0.25)
    p.add_argument("--notch", type=float, default=60.0)
    p.add_argument("--car", action="store_true", help="remove noise shared by all channels")
    p = sub.add_parser("live"); hw(p)
    p.add_argument("--model", default="model.joblib")
    p.add_argument("--switch-label", help="label that acts as a switch press, e.g. clench")
    p.add_argument("--switch-key", default="space", help="key to send: space, enter, f1, 1, ...")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--refractory", type=float, default=1.0, help="min seconds between presses")

    args = ap.parse_args()
    {"check": cmd_check, "spectrum": cmd_spectrum, "record": cmd_record, "train": cmd_train, "live": cmd_live}[args.cmd](args)


if __name__ == "__main__":
    main()