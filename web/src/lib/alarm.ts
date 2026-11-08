/**
 * Alert sounds for the Needs page, made with Web Audio (no files to load).
 *   siren(seconds)  two-tone emergency siren
 *   chime()         gentle three-note "please come" chime for urgent needs
 */
let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  try {
    ctx = ctx ?? new (window.AudioContext || (window as any).webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

function tone(freq: number, start: number, dur: number, type: OscillatorType = "sine", vol = 0.25) {
  const a = audio();
  if (!a) return;
  const o = a.createOscillator();
  const g = a.createGain();
  o.type = type;
  o.frequency.value = freq;
  g.gain.setValueAtTime(0, a.currentTime + start);
  g.gain.linearRampToValueAtTime(vol, a.currentTime + start + 0.02);
  g.gain.setValueAtTime(vol, a.currentTime + start + dur - 0.04);
  g.gain.linearRampToValueAtTime(0, a.currentTime + start + dur);
  o.connect(g).connect(a.destination);
  o.start(a.currentTime + start);
  o.stop(a.currentTime + start + dur + 0.05);
}

/** Returns a promise that resolves when the siren ends. */
export function siren(seconds = 2): Promise<void> {
  const step = 0.36;
  for (let i = 0; i * step < seconds; i++) tone(i % 2 ? 660 : 880, i * step, step, "square", 0.12);
  return new Promise((r) => setTimeout(r, seconds * 1000));
}

export function chime(): Promise<void> {
  [659, 784, 1047].forEach((f, i) => tone(f, i * 0.22, 0.42, "sine", 0.3));
  return new Promise((r) => setTimeout(r, 900));
}

export function unlockAlarm() {
  audio();
}
