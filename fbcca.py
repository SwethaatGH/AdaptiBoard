"""
fbcca.py - training-free SSVEP detection (filter-bank CCA) for arrow navigation.

Adapted from the NeuroKnights project (natHacks 2024, NeuroPawn headset), MIT License,
Copyright (c) 2024 Oleksii Yurchuk, Arthur Witte, Jessu Doroy, Matvey Okoneshnikov,
Ivan Costa Neto - https://github.com/alexyurchuk/NeuroKnights
(src/ssvep/signal_processing/analysis.py and processing.py).

What's kept from NeuroKnights: their preprocessing (5.5-35 Hz bandpass, 50/60 Hz notches;
their common average reference is optional and off by default, see preprocess()), sine/cosine references with 3 harmonics, and a filter
bank of 7 sub-bands (6, 8, ... 18 Hz up to 35 Hz). Changes: a numerically stable CCA (QR +
SVD instead of matrix inverses), the standard FBCCA sub-band weights (Chen et al. 2015),
and an evidence-accumulating decision rule (see Decider), which made decisions far more
reliable on weak signals than deciding from each window on its own.
"""
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch, sosfiltfilt

SUBBANDS = [(lo, 35.0) for lo in (6, 8, 10, 12, 14, 16, 18)]  # NeuroKnights filter bank


def preprocess(x, fs, notch=60.0, car=False):
    """x: (channels, samples) raw -> detrended, 5.5-35 Hz bandpass, 50/60 Hz notched.

    car=False by default: with every electrode over the visual cortex, the SSVEP is common
    to all channels, so a common average reference would subtract the signal we want. CCA
    already finds the best channel mix (and cancels shared noise) on its own.
    """
    x = x - x.mean(axis=1, keepdims=True)
    for f0 in (50.0, notch):
        if f0 and f0 < fs / 2 - 1:
            b, a = iirnotch(f0, 20, fs)
            x = filtfilt(b, a, x, axis=1)
    sos = butter(4, [5.5, min(35.0, fs / 2 - 1)], btype="band", fs=fs, output="sos")
    x = sosfiltfilt(sos, x, axis=1)
    return x - x.mean(axis=0, keepdims=True) if car else x


def references(freq, n, fs, harmonics=3):
    t = np.arange(n) / fs
    ref = []
    for h in range(1, harmonics + 1):
        if h * freq < fs / 2 - 1:
            ref += [np.sin(2 * np.pi * h * freq * t), np.cos(2 * np.pi * h * freq * t)]
    return np.array(ref).T  # (samples, 2*harmonics)


def cca_corr(x, y):
    """Largest canonical correlation between x (samples, a) and y (samples, b)."""
    x = x - x.mean(0)
    y = y - y.mean(0)
    qx, _ = np.linalg.qr(x)
    qy, _ = np.linalg.qr(y)
    return float(np.linalg.svd(qx.T @ qy, compute_uv=False)[0])


class FBCCA:
    def __init__(self, freqs, fs, n_samples, a=1.25, b=0.25):
        self.freqs, self.fs = list(freqs), fs
        self.refs = [references(f, n_samples, fs) for f in self.freqs]
        side = max(0.45, 1.8 * fs / n_samples)  # just beyond the window's frequency resolution
        self.side_refs = [references(f + d, n_samples, fs) for f in self.freqs for d in (-side, side)]
        k = np.arange(1, len(SUBBANDS) + 1)
        self.w = k ** (-a) + b
        self.bank = [butter(4, [lo, min(hi, fs / 2 - 1)], btype="band", fs=fs, output="sos")
                     for lo, hi in SUBBANDS]

    def raw_scores(self, x, refs):
        s = np.zeros(len(refs))
        for wk, sos in zip(self.w, self.bank):
            xb = sosfiltfilt(sos, x, axis=1).T
            s += wk * np.array([cca_corr(xb, r) ** 2 for r in refs])
        return s

    def scores(self, x):
        """x: (channels, samples), already preprocessed -> one score per target frequency.

        Each target's FBCCA score minus the average score of two nearby "side" frequencies
        (f +/- SIDE Hz) in the same window - like a signal-to-noise ratio. This cancels each
        frequency's natural background level without needing any history or calibration.
        """
        allf = self.raw_scores(x, self.refs + self.side_refs)
        k = len(self.freqs)
        return allf[:k] - 0.5 * (allf[k::2] + allf[k + 1::2])


class Decider:
    """Turns a stream of FBCCA score vectors into decisions by accumulating evidence.

    Scores are already relative to nearby frequencies (see FBCCA.scores), so with no SSVEP
    they hover around zero. They're leaky-averaged across windows, and a decision fires when
    the leader is `z` standard deviations above chance AND `margin` SDs ahead of the runner-up.
    Chance spread is estimated live from the non-leading targets. After a decision the
    evidence resets and `cooldown` windows are skipped, so holding your gaze on an arrow
    repeats the move every couple of seconds.

    `strict` raises the bar for chosen targets (e.g. {ok_index: 1.3}) because a wrong OK
    speaks a phrase, while a wrong arrow only moves the cursor.

    Tuned on simulated EEG at your measured SSVEP strength (4 s window): first move after
    ~5 s, about 80-95% of decisions correct depending on signal strength.
    """

    def __init__(self, n_targets, leak=0.7, z=3.0, margin=1.5, cooldown=3, strict=None):
        self.leak, self.z, self.margin, self.cooldown = leak, z, margin, cooldown
        self.strict = strict or {}
        self.avg = np.zeros(n_targets)
        self.var = None
        self.cool = 0

    def update(self, s):
        """Returns (decision or None, current leader, confidence 0..1 for a UI meter)."""
        self.avg = self.leak * self.avg + (1 - self.leak) * s
        order = np.argsort(self.avg)[::-1]
        v = float(np.mean(self.avg[order[1:]] ** 2))
        self.var = v if self.var is None else 0.95 * self.var + 0.05 * v
        sd = np.sqrt(max(self.var, 1e-12))
        best = int(order[0])
        need = self.z * self.strict.get(best, 1.0)
        zbest = self.avg[best] / sd
        conf = float(np.clip(zbest / need, 0, 1))
        if self.cool:
            self.cool -= 1
            return None, best, 0.0
        if zbest > need and (self.avg[best] - self.avg[order[1]]) / sd > self.margin:
            self.cool = self.cooldown
            self.avg[:] = 0
            return best, best, 1.0
        return None, best, conf
