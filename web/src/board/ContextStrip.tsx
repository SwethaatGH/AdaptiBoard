import { AnimatePresence, motion } from "framer-motion";
import { Ear, MicOff, RefreshCw, Settings as Gear } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ContextInfo } from "../lib/types";

/** Five little bars that bounce with the microphone level. */
function MicMeter({ levelRef }: { levelRef: React.MutableRefObject<number> }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const el = ref.current;
      if (el) {
        const l = levelRef.current;
        el.querySelectorAll("i").forEach((bar, i) => {
          const h = 0.18 + Math.min(1, l * (0.6 + ((i * 37) % 5) / 6)) * 0.82;
          (bar as HTMLElement).style.transform = `scaleY(${h})`;
        });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [levelRef]);
  return (
    <span className="mic-meter" ref={ref} aria-hidden>
      <i /><i /><i /><i /><i />
    </span>
  );
}

interface Props {
  ctx: ContextInfo | null;
  interim: string;
  micOn: boolean;
  micError: string;
  levelRef: React.MutableRefObject<number>;
  pending: boolean;
  onSettings: () => void;
}

export function ContextStrip({ ctx, interim, micOn, micError, levelRef, pending, onSettings }: Props) {
  const last = ctx?.lines[ctx.lines.length - 1]?.text;
  const chips = [...new Set([...(ctx?.options ?? []), ...(ctx?.items ?? []), ...(ctx?.keywords ?? [])])].slice(0, 6);
  return (
    <section className="context">
      <div className={`mic-pill ${micOn && !micError ? "is-on" : ""}`} title={micError || "Listening to the conversation"}>
        {micOn && !micError ? <MicMeter levelRef={levelRef} /> : <MicOff size={16} />}
        <span>{micError ? "Mic off" : micOn ? "Listening" : "Mic off"}</span>
      </div>

      <div className="heard">
        <Ear size={16} className="heard-icon" />
        <AnimatePresence mode="wait">
          <motion.span
            key={interim ? "interim" : last ?? "none"}
            className={`heard-text ${interim ? "is-interim" : ""}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
          >
            {micError || interim || (last ? `“${last}”` : "Conversation context will appear here")}
          </motion.span>
        </AnimatePresence>
        {ctx?.topic && <span className="topic">{ctx.topic}</span>}
        <div className="kw">
          {chips.map((k) => (
            <span key={k} className="kw-chip">{k}</span>
          ))}
        </div>
        {pending && (
          <span className="pending" title="New conversation context. It is applied after your next choice so tiles never move while you navigate.">
            <RefreshCw size={13} /> new context
          </span>
        )}
      </div>

      <div className="status-pills">
        <button type="button" className="pill gear" onClick={onSettings} aria-label="Settings">
          <Gear size={16} />
        </button>
      </div>
    </section>
  );
}
