import { motion } from "framer-motion";
import { Send, Trash2, Volume2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { postJSON } from "../lib/hub";
import { browserSttSupported, type SttMode } from "../lib/stt";
import { speak } from "../lib/tts";
import type { HubStatus } from "../lib/types";
import type { Settings } from "./settings";

interface Props {
  settings: Settings;
  update: (p: Partial<Settings>) => void;
  voices: { id: string; label: string }[];
  status: HubStatus | null;
  onClose: () => void;
}

const SAMPLES = [
  "Hey, do you want pizza or pasta for dinner tonight?",
  "Grandma is coming over this afternoon, are you excited?",
  "Should we go to the park or watch a movie?",
  "Are you feeling okay? You look a little tired.",
];

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export function SettingsDrawer({ settings, update, voices, status, onClose }: Props) {
  const [said, setSaid] = useState("");
  const [phrases, setPhrases] = useState<{ text: string; n: number }[]>([]);
  const p = settings.profile;
  const loadPhrases = () =>
    fetch("/api/phrases").then((r) => r.json()).then((d) => setPhrases(d.phrases)).catch(() => {});
  useEffect(() => {
    loadPhrases();
  }, []);
  const removePhrase = async (text: string) => {
    await postJSON("/api/phrases/delete", { text });
    loadPhrases();
  };
  const sendHeard = async (text: string) => {
    if (!text.trim()) return;
    await postJSON("/api/heard", { text });
    setSaid("");
  };
  return (
    <>
      <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.aside
        className="drawer"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 34 }}
      >
        <header>
          <h3>Caregiver settings</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <X />
          </button>
        </header>

        <h4>Voice</h4>
        <div className="row">
          <select value={settings.voice} onChange={(e) => update({ voice: e.target.value })}>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>{v.label}</option>
            ))}
          </select>
          <button type="button" className="btn" onClick={() => speak("Hi! This is my voice.")}>
            <Volume2 size={16} /> Test
          </button>
        </div>
        <label className="check">
          <input type="checkbox" checked={settings.speakOnSelect} onChange={(e) => update({ speakOnSelect: e.target.checked })} />
          Speak each tile when it is chosen
        </label>
        {!status?.tts && <p className="note">Neural voice unavailable on the server; using the browser voice.</p>}

        <h4>Listening (conversation context)</h4>
        <select value={settings.sttMode} onChange={(e) => update({ sttMode: e.target.value as SttMode })}>
          <option value="auto">Auto ({status?.stt ? `server · ${status.stt}` : "browser"})</option>
          <option value="browser" disabled={!browserSttSupported()}>Browser speech recognition (Chrome · free · live)</option>
          <option value="server" disabled={!status?.stt}>Server Whisper ({status?.stt ?? "not configured"})</option>
          <option value="off">Off</option>
        </select>
        <p className="note">Audio is never saved. Words heard while the board is speaking are ignored.</p>

        <h4>Simulate the conversation</h4>
        <p className="note">For demos in noisy rooms: type what someone said to the user.</p>
        <div className="row">
          <input value={said} placeholder="e.g. Do you want tea or coffee?" onChange={(e) => setSaid(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendHeard(said)} />
          <button type="button" className="btn" onClick={() => sendHeard(said)} aria-label="Send">
            <Send size={16} />
          </button>
        </div>
        <div className="samples">
          {SAMPLES.map((s) => (
            <button type="button" key={s} className="sample" onClick={() => sendHeard(s)}>{s}</button>
          ))}
        </div>
        <button type="button" className="btn ghost" onClick={() => postJSON("/api/transcript/clear", {})}>
          <Trash2 size={16} /> Clear conversation context
        </button>

        <h4>About the user (helps predictions)</h4>
        <label>Name<input value={p.name} onChange={(e) => update({ profile: { ...p, name: e.target.value } })} /></label>
        <label>People in their life (comma separated)
          <input defaultValue={p.family.join(", ")} placeholder="Mom, Alex, Grandma"
            onBlur={(e) => update({ profile: { ...p, family: list(e.target.value) } })} />
        </label>
        <label>Things they like
          <input defaultValue={p.likes.join(", ")} placeholder="soccer, mango juice, Taylor Swift"
            onBlur={(e) => update({ profile: { ...p, likes: list(e.target.value) } })} />
        </label>
        <label>Notes
          <textarea value={p.notes} rows={2} placeholder="e.g. vegetarian, loves the beach"
            onChange={(e) => update({ profile: { ...p, notes: e.target.value } })} />
        </label>

        <h4>Saved sentences (Chat page)</h4>
        <p className="note">Every sentence the user Speaks is saved and ranked by how often they use it.</p>
        <div className="phrases">
          {phrases.length === 0 && <p className="note">Nothing saved yet.</p>}
          {phrases.slice(0, 30).map((ph) => (
            <div key={ph.text} className="phrase-row">
              <span>{ph.text}</span>
              <small>×{ph.n}</small>
              <button type="button" className="icon-btn sm" onClick={() => removePhrase(ph.text)} aria-label="Remove">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        <h4>Needs alerts</h4>
        <p className="note">
          Red Needs tiles sound an alarm, speak "call nine one one" and show a full-screen alert. To also get a push
          on the caregiver's phone, set <code>NTFY_TOPIC</code> in <code>server/.env</code> and subscribe to it in the free
          ntfy app. AdaptiBoard never dials 911 itself.
        </p>

        <h4>Keyboard (testing without EEG)</h4>
        <p className="note">Arrow keys move · Enter / Space = OK. Letter keys type into the on-screen keyboard (Enter adds the word). The controller screen sends the same five commands.</p>
        <p className="note">
          AI: <b>{status?.llm ? `${status.llm} (${status.llmModel})` : "offline predictor"}</b> · set a key in <code>server/.env</code>
        </p>
      </motion.aside>
    </>
  );
}
