import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Brain, CircleDot, Maximize, Monitor,
  Pause, Play, Settings as Gear, Siren, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useHub } from "../lib/hub";
import type { Direction } from "../lib/types";

/**
 * Controller screen (second laptop). Five keys flicker at different frequencies; the EEG
 * decoder works out which one the user is looking at (SSVEP) and sends that command.
 * Each key face shows its own bright colour when sin(2*pi*f*t) >= 0 and black otherwise,
 * updated once per screen frame - the same frame-locked method as NeuroPawn's stimulus.py.
 * (Strong light/dark contrast is what drives the SSVEP; the colours just make keys easy to tell apart.)
 */
const KEYS: { dir: Direction; icon: JSX.Element; accent: string; label: string }[] = [
  { dir: "up", icon: <ArrowUp />, accent: "#FFD43B", label: "Up" }, // yellow
  { dir: "left", icon: <ArrowLeft />, accent: "#4DABF7", label: "Left" }, // blue
  { dir: "ok", icon: <CircleDot />, accent: "#00FF9D", label: "OK / Select" }, // mint
  { dir: "right", icon: <ArrowRight />, accent: "#FF6B9D", label: "Right" }, // pink
  { dir: "down", icon: <ArrowDown />, accent: "#B197FC", label: "Down" }, // purple
];
const DEFAULT_FREQS: Record<Direction, number> = { up: 6, down: 8, left: 10, right: 12, ok: 15 };
const FKEY = "adaptiboard-freqs-v2"; // v2: 6/8/10/12/15 Hz defaults

function loadFreqs(): Record<Direction, number> {
  try {
    return { ...DEFAULT_FREQS, ...JSON.parse(localStorage.getItem(FKEY) || "{}") };
  } catch {
    return DEFAULT_FREQS;
  }
}

export default function Controller() {
  const [freqs, setFreqs] = useState(loadFreqs);
  const [running, setRunning] = useState(false);
  const [setup, setSetup] = useState(true);
  const [showLean, setShowLean] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [lean, setLean] = useState<{ dir: Direction; conf: number } | null>(null);
  const [fired, setFired] = useState<{ dir: Direction; n: number } | null>(null);
  const [hz, setHz] = useState<number | null>(null);
  const [mouseIdle, setMouseIdle] = useState(false);
  const [alert, setAlert] = useState<{ level: string; label: string; say: string } | null>(null);
  const faces = useRef<Partial<Record<Direction, HTMLDivElement | null>>>({});
  const runRef = useRef(false);
  const freqRef = useRef(freqs);
  freqRef.current = freqs;
  const n = useRef(0);

  const { connected, status, send } = useHub("controller", (msg) => {
    if (msg.type === "lean") setLean({ dir: msg.direction, conf: msg.conf });
    else if (msg.type === "command") setFired({ dir: msg.direction, n: ++n.current });
    else if (msg.type === "alert") setAlert(msg.clear ? null : msg);
  });

  useEffect(() => {
    try {
      localStorage.setItem(FKEY, JSON.stringify(freqs));
    } catch {
      /* ignore */
    }
  }, [freqs]);

  // tell the server (and so the decoder) when flicker is on and at which frequencies
  useEffect(() => {
    if (connected) send({ type: "stimulus", on: running, freqs });
  }, [running, freqs, connected]); // eslint-disable-line react-hooks/exhaustive-deps

  // frame-locked flicker loop
  useEffect(() => {
    runRef.current = running;
    let raf = 0;
    let t0: number | null = null;
    const frame = (now: number) => {
      if (runRef.current) {
        if (t0 === null) t0 = now;
        const t = (now - t0) / 1000;
        for (const k of KEYS) {
          const el = faces.current[k.dir];
          if (el) el.style.background = Math.sin(2 * Math.PI * freqRef.current[k.dir] * t) >= 0 ? k.accent : "#000000";
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    if (!running) for (const k of KEYS) faces.current[k.dir]?.style.removeProperty("background");
    return () => cancelAnimationFrame(raf);
  }, [running]);

  // measure the refresh rate (default frequencies assume 60 Hz)
  useEffect(() => {
    let frames = 0;
    let t0: number | null = null;
    let raf = 0;
    const f = (t: number) => {
      if (t0 === null) t0 = t;
      frames++;
      if (t - t0 < 1500) raf = requestAnimationFrame(f);
      else setHz(Math.round((frames * 1000) / (t - t0)));
    };
    raf = requestAnimationFrame(f);
    return () => cancelAnimationFrame(raf);
  }, []);

  // stop flashing if the tab is hidden (safety)
  useEffect(() => {
    const vis = () => document.hidden && setRunning(false);
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, []);

  const press = (dir: Direction, source: string) => send({ type: "command", direction: dir, source });

  const startFlicker = () => {
    let ok = false;
    try {
      ok = sessionStorage.getItem("flicker-ok") === "1";
    } catch {
      /* ignore */
    }
    if (!ok) {
      ok = confirm(
        "This screen flashes. Do not use it with anyone who has photosensitive epilepsy or gets headaches from flicker. Continue?",
      );
      if (!ok) return;
      try {
        sessionStorage.setItem("flicker-ok", "1");
      } catch {
        /* ignore */
      }
    }
    setRunning(true);
    setSetup(false);
  };

  // keyboard: arrows/Enter send commands; Space toggles flicker; Esc = stop + setup
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "Escape") {
        setRunning(false);
        setSetup(true);
        return;
      }
      if (e.key === " ") {
        e.preventDefault();
        running ? setRunning(false) : startFlicker();
        return;
      }
      const map: Record<string, Direction> = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "ok" };
      if (map[e.key]) {
        e.preventDefault();
        if (!e.repeat) press(map[e.key], "controller-keyboard");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // hide the cursor and gear while the user is looking at the keys
  useEffect(() => {
    let timer = 0;
    const move = () => {
      setMouseIdle(false);
      clearTimeout(timer);
      timer = window.setTimeout(() => setMouseIdle(true), 2500);
    };
    window.addEventListener("mousemove", move);
    move();
    return () => {
      window.removeEventListener("mousemove", move);
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!fired) return;
    const t = setTimeout(() => setFired(null), 550);
    return () => clearTimeout(t);
  }, [fired]);

  const decoders = status?.clients.decoder ?? 0;
  const boards = status?.clients.board ?? 0;

  return (
    <div className={`ctl ${running ? "is-running" : ""} ${mouseIdle && !setup ? "hide-cursor" : ""}`}>
      <div className="pad">
        {KEYS.map((k) => {
          const leaning = showLean && lean && lean.dir === k.dir && lean.conf > 0.05;
          return (
            <div key={k.dir} className={`key key-${k.dir}`} style={{ "--accent": k.accent } as React.CSSProperties}>
              <button
                type="button"
                className={`face ${fired?.dir === k.dir ? "is-fired" : ""}`}
                ref={(el) => (faces.current[k.dir] = el as unknown as HTMLDivElement)}
                onClick={() => press(k.dir, "controller-click")}
                aria-label={k.label}
              >
                <span className="key-icon">{k.icon}</span>
              </button>
              {showLean && (
                <span className="lean">
                  <i style={{ width: `${leaning ? Math.round(lean!.conf * 100) : 0}%` }} />
                </span>
              )}
              {showLabels && <span className="key-label">{k.label}</span>}
            </div>
          );
        })}
      </div>

      <AnimatePresence>
        {alert && (
          <motion.div
            className={`ctl-alert ${alert.level === "emergency" ? "is-emergency" : ""}`}
            initial={{ y: -80 }}
            animate={{ y: 0 }}
            exit={{ y: -80 }}
          >
            <Siren size={22} />
            <b>{alert.level === "emergency" ? `EMERGENCY · Call 911 · ${alert.label}` : `Needs help · ${alert.label}`}</b>
            <span>“{alert.say}”</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className={`ctl-corner ${mouseIdle && !setup ? "is-hidden" : ""}`}>
        <span className={`dot ${connected && boards ? "ok" : connected ? "warn" : "bad"}`} />
        <button type="button" className="icon-btn" onClick={() => (running ? setRunning(false) : startFlicker())} aria-label={running ? "Pause" : "Start"}>
          {running ? <Pause size={18} /> : <Play size={18} />}
        </button>
        <button type="button" className="icon-btn" onClick={() => setSetup(true)} aria-label="Setup">
          <Gear size={18} />
        </button>
      </div>

      <AnimatePresence>
        {setup && (
          <motion.div className="ctl-setup" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="ctl-card" initial={{ y: 24, scale: 0.97 }} animate={{ y: 0, scale: 1 }} exit={{ y: 24, scale: 0.97 }}>
              <header>
                <div>
                  <h2>AdaptiBoard Controller</h2>
                  <p>Look at a key to move the highlight on the board. Look at OK to choose.</p>
                </div>
                <button type="button" className="icon-btn" onClick={() => setSetup(false)} aria-label="Close setup">
                  <X />
                </button>
              </header>

              <div className="conn">
                <span className={`pill ${connected ? "ok" : "bad"}`}>{connected ? "Server connected" : "Connecting to server…"}</span>
                <span className={`pill ${boards ? "ok" : ""}`}><Monitor size={14} /> Board {boards ? "connected" : "not open"}</span>
                <span className={`pill ${decoders ? "ok" : ""}`}><Brain size={14} /> EEG decoder {decoders ? "connected" : "not running"}</span>
                <span className={`pill ${hz && Math.abs(hz - 60) > 3 ? "bad" : "ok"}`}>Screen {hz ?? "…"} Hz</span>
              </div>
              {hz && Math.abs(hz - 60) > 3 && (
                <p className="warn">The default frequencies assume a 60 Hz display. Set this screen to 60 Hz, or retune the frequencies.</p>
              )}

              <h4>Flicker frequencies (Hz)</h4>
              <div className="freqs">
                {KEYS.map((k) => (
                  <label key={k.dir}>
                    <span style={{ color: k.accent }}>{k.label}</span>
                    <input
                      type="number"
                      step="0.01"
                      min={4}
                      max={30}
                      value={freqs[k.dir]}
                      onChange={(e) => setFreqs({ ...freqs, [k.dir]: Number(e.target.value) || DEFAULT_FREQS[k.dir] })}
                    />
                  </label>
                ))}
              </div>
              <p className="note">
                Defaults: Up 6 · Down 8 · Left 10 · Right 12 · OK 15 Hz (6, 10, 12, 15 divide 60 Hz evenly). Use the same values the decoder was tested with.{" "}
                <button type="button" className="link" onClick={() => setFreqs(DEFAULT_FREQS)}>Reset</button>
              </p>

              <div className="toggles">
                <label className="check"><input type="checkbox" checked={showLean} onChange={(e) => setShowLean(e.target.checked)} /> Show decoder feedback bar</label>
                <label className="check"><input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} /> Show key labels</label>
              </div>

              <div className="ctl-actions">
                <button type="button" className="btn primary" onClick={startFlicker}><Play size={18} /> Start flicker</button>
                <button type="button" className="btn" onClick={() => { setSetup(false); setRunning(false); }}>Keys only (click to test)</button>
                <button type="button" className="btn ghost" onClick={() => document.documentElement.requestFullscreen?.()}><Maximize size={16} /> Full screen</button>
              </div>
              <p className="note">
                Keyboard: arrows + Enter send commands · Space starts/stops flicker · Esc stops and opens this panel.
                Flicker stops automatically if this tab is hidden.
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
