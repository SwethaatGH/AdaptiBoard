/**
 * Speech output. Uses the server's neural voices (edge-tts, cached) for natural,
 * accurate speech; falls back to the browser's own voice if the server can't.
 * Also tracks "the app is talking" so the microphone ignores the app's own voice.
 */
const cache = new Map<string, Promise<string | null>>(); // text -> object URL
let voice = "en-US-AriaNeural";
let current: HTMLAudioElement | null = null;
let speakingUntil = 0;
let serverOk = true;
const listeners = new Set<(on: boolean) => void>();

export function setVoice(v: string) {
  if (v !== voice) cache.clear();
  voice = v;
}

/** True while the app is speaking (plus a short tail for echo). */
export function isSpeaking() {
  return Date.now() < speakingUntil;
}

export function onSpeaking(fn: (on: boolean) => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(on: boolean) {
  listeners.forEach((fn) => fn(on));
}

function fetchAudio(text: string): Promise<string | null> {
  const key = text.trim().toLowerCase();
  if (!cache.has(key)) {
    const p = fetch(`/api/tts?voice=${encodeURIComponent(voice)}&text=${encodeURIComponent(text)}`)
      .then(async (r) => (r.ok ? URL.createObjectURL(await r.blob()) : null))
      .catch(() => null);
    cache.set(key, p);
    p.then((u) => !u && cache.delete(key));
  }
  return cache.get(key)!;
}

/** Warm the cache so tiles speak instantly when chosen. */
export function prefetch(texts: string[]) {
  if (!serverOk) return;
  texts.filter(Boolean).slice(0, 20).forEach((t) => fetchAudio(t));
}

export function stop() {
  current?.pause();
  current = null;
  window.speechSynthesis?.cancel();
}

export async function speak(text: string) {
  text = text.trim();
  if (!text) return;
  stop();
  speakingUntil = Date.now() + 1500 + text.length * 90; // provisional, fixed below
  emit(true);
  const url = serverOk ? await fetchAudio(text) : null;
  if (url) {
    const audio = new Audio(url);
    current = audio;
    audio.onloadedmetadata = () => {
      speakingUntil = Date.now() + audio.duration * 1000 + 700;
    };
    const done = () => {
      speakingUntil = Date.now() + 600;
      setTimeout(() => emit(false), 600);
    };
    audio.onended = done;
    audio.onerror = done;
    try {
      await audio.play();
      return;
    } catch {
      /* autoplay blocked or decode error -> browser voice */
    }
  } else {
    serverOk = false;
    setTimeout(() => (serverOk = true), 30000); // try the server again later
  }
  browserSpeak(text);
}

function browserSpeak(text: string) {
  const synth = window.speechSynthesis;
  if (!synth) return;
  const u = new SpeechSynthesisUtterance(text);
  const voices = synth.getVoices();
  const prefer = ["Google US English", "Samantha", "Aria", "Jenny", "Natural", "Daniel"];
  u.voice =
    prefer.map((n) => voices.find((v) => v.name.includes(n) && v.lang.startsWith("en"))).find(Boolean) ??
    voices.find((v) => v.lang.startsWith("en")) ??
    null;
  u.rate = 0.95;
  u.onend = () => {
    speakingUntil = Date.now() + 600;
    setTimeout(() => emit(false), 600);
  };
  synth.speak(u);
}

/** Must run inside a click: browsers block audio until the user interacts once. */
export function unlockAudio() {
  try {
    const a = new Audio(
      "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=",
    );
    a.play().catch(() => {});
    window.speechSynthesis?.getVoices();
  } catch {
    /* ignore */
  }
}

/** Resolves once the app has finished speaking. */
export function speechDone(): Promise<void> {
  return new Promise((resolve) => {
    const t = window.setInterval(() => {
      if (!isSpeaking()) {
        clearInterval(t);
        resolve();
      }
    }, 150);
  });
}
