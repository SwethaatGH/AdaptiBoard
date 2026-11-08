import { isSpeaking } from "./tts";

/**
 * Listens to the conversation around the user and reports what was said.
 *
 *  auto    - server if it has speech-to-text (Groq / OpenAI / local Whisper), else browser
 *  browser - Chrome/Edge built-in speech recognition (free, no key, live words; needs
 *            Google's servers - if that fails it switches to server mode by itself)
 *  server  - records each spoken sentence (cut at the pause after it) and sends it
 *            to the server (local Whisper / Groq / OpenAI)
 *  off     - microphone off
 *
 * Words heard while the app itself is speaking are ignored, so the board's own voice
 * never becomes "context". Audio is never stored.
 */
export type SttMode = "auto" | "browser" | "server" | "off";

export interface ListenCallbacks {
  onFinal: (text: string) => void;
  onInterim: (text: string) => void;
  onError: (msg: string) => void;
  onLevel: (level: number) => void; // 0..1 mic loudness, for the meter
  onFallback?: () => boolean; // browser STT failed: return true if server mode can take over
}

export function browserSttSupported() {
  return !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

export class Listener {
  private active = false;
  private rec: any = null;
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private raf = 0;
  private recorder: MediaRecorder | null = null;
  private level = 0;
  private timer = 0;

  constructor(private cb: ListenCallbacks) {}

  async start(mode: Exclude<SttMode, "auto">) {
    this.stop();
    if (mode === "off") return;
    this.active = true;
    if (!window.isSecureContext) {
      this.cb.onError("Microphone needs http://localhost (open the board on the server laptop).");
      return;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      this.cb.onError("Microphone permission denied.");
      this.active = false;
      return;
    }
    this.meter(this.stream);
    console.info(`[stt] listening in ${mode} mode`);
    if (mode === "browser") this.startBrowser();
    else this.startServer(this.stream);
  }

  stop() {
    this.active = false;
    try {
      this.rec?.stop();
    } catch {
      /* already stopped */
    }
    this.rec = null;
    try {
      if (this.recorder?.state === "recording") this.recorder.stop();
    } catch {
      /* ignore */
    }
    this.recorder = null;
    clearInterval(this.timer);
    cancelAnimationFrame(this.raf);
    this.ctx?.close().catch(() => {});
    this.ctx = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.cb.onLevel(0);
  }

  private meter(stream: MediaStream) {
    this.ctx = new AudioContext();
    this.ctx.resume().catch(() => {}); // a context made after an await can start suspended
    const src = this.ctx.createMediaStreamSource(stream);
    const an = this.ctx.createAnalyser();
    an.fftSize = 512;
    src.connect(an);
    const buf = new Uint8Array(an.fftSize);
    let last = 0;
    const tick = (t: number) => {
      if (!this.active) return;
      if (t - last > 80) {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        this.level = Math.min(1, Math.sqrt(sum / buf.length) * 4);
        this.cb.onLevel(this.level);
        last = t;
      }
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  private startBrowser() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      this.cb.onError("This browser has no built-in speech recognition. Use Chrome, or Server mode.");
      return;
    }
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const text = r[0].transcript.trim();
        if (r.isFinal) {
          if (text && !isSpeaking()) this.cb.onFinal(text);
        } else interim += text + " ";
      }
      this.cb.onInterim(isSpeaking() ? "" : interim.trim());
    };
    let failures = 0;
    rec.onresult = ((orig) => (e: any) => {
      failures = 0;
      orig(e);
    })(rec.onresult);
    rec.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") return; // normal: silence / restart
      console.warn("[stt] browser speech recognition error:", e.error);
      // network / service-not-allowed / not-allowed / audio-capture: Chrome's service isn't usable
      failures += e.error === "network" ? 1 : 3;
      if (failures >= 2) {
        this.active = false;
        try {
          rec.stop();
        } catch {
          /* ignore */
        }
        if (this.cb.onFallback?.()) return; // the board restarts us in server mode
        this.cb.onError(
          e.error === "network"
            ? "Chrome speech recognition can't reach Google. Add a GROQ_API_KEY and use Server mode."
            : `Chrome speech recognition failed (${e.error}). Check mic permission or use Server mode.`,
        );
      }
    };
    rec.onend = () => {
      if (this.active) setTimeout(() => this.active && this.safeStart(rec), 250);
    };
    this.rec = rec;
    this.safeStart(rec);
  }

  private safeStart(rec: any) {
    try {
      rec.start();
    } catch {
      /* already running */
    }
  }

  /**
   * Server mode: keep recording; when someone speaks and then pauses (~0.8 s), send that
   * sentence for transcription and start a fresh recording. Silence is never sent, so
   * Whisper can't "hear" things in it and no API calls are wasted.
   */
  private startServer(stream: MediaStream) {
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((m) =>
      MediaRecorder.isTypeSupported(m),
    );
    let floor = 0.03; // background noise level, learned as we go
    const next = () => {
      if (!this.active || !this.stream) return;
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      this.recorder = rec;
      const chunks: Blob[] = [];
      const t0 = Date.now();
      let voicedMs = 0;
      let lastVoice = 0;
      let spokeDuring = isSpeaking();
      let send = false;
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = async () => {
        if (this.active) next(); // the next sentence starts recording straight away
        if (!send || spokeDuring || !chunks.length) return;
        const blob = new Blob(chunks, { type: rec.mimeType });
        this.cb.onInterim("…transcribing");
        try {
          const r = await fetch("/api/transcribe", {
            method: "POST",
            headers: { "Content-Type": rec.mimeType },
            body: blob,
          });
          const d = await r.json();
          this.cb.onInterim("");
          if (!r.ok) this.cb.onError(d.error || "Server speech-to-text failed");
          else if (d.text) this.cb.onFinal(d.text);
        } catch {
          this.cb.onInterim("");
          this.cb.onError("Server speech-to-text unreachable");
        }
      };
      rec.start(250);
      clearInterval(this.timer);
      this.timer = window.setInterval(() => {
        if (rec.state !== "recording") return;
        const now = Date.now();
        const th = Math.max(0.06, floor * 2.5);
        if ((window as any).__sttDebug) console.info(`[stt] level ${this.level.toFixed(3)} th ${th.toFixed(3)}`);
        spokeDuring ||= isSpeaking();
        if (this.level > th) {
          voicedMs += 100;
          lastVoice = now;
        } else floor = floor * 0.97 + this.level * 0.03;
        const talking = voicedMs >= 300;
        if (talking && !spokeDuring) this.cb.onInterim(now - lastVoice < 400 ? "…hearing speech" : "…");
        const ended = talking && now - lastVoice > 800; // a pause after speech
        const tooLong = now - t0 > 15000;
        const idle = !talking && now - t0 > 8000 && now - lastVoice > 1000; // nothing said: recycle
        if (ended || tooLong || idle) {
          send = talking;
          clearInterval(this.timer);
          rec.stop();
        }
      }, 100);
    };
    next();
  }
}
