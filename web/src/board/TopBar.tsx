import { AnimatePresence, motion } from "framer-motion";
import { Check, Delete, SpellCheck, Sparkles, Trash2, Volume2 } from "lucide-react";
import { tileColor } from "../lib/colors";
import type { MessageItem } from "../lib/types";
import type { Focus } from "./nav";
import { FocusRing, Picto } from "./TileCard";

export type ActionId = "speak" | "complete" | "delete" | "clear";

interface Props {
  message: MessageItem[];
  polished: { text: string; source: string } | null; // grammar-fixed sentence (shown + spoken)
  spoken: boolean;
  completion: string;
  actions: ActionId[];
  focus: Focus;
  onAction: (id: ActionId) => void;
}

const META: Record<ActionId, { label: string; icon: JSX.Element; cls: string }> = {
  speak: { label: "Speak", icon: <Volume2 size={30} />, cls: "act-speak" },
  complete: { label: "Use sentence", icon: <Sparkles size={22} />, cls: "act-complete" },
  delete: { label: "Delete", icon: <Delete size={28} />, cls: "act-delete" },
  clear: { label: "Clear", icon: <Trash2 size={26} />, cls: "act-clear" },
};

export function TopBar({ message, polished, spoken, completion, actions, focus, onAction }: Props) {
  const btn = (id: ActionId) => {
    const i = actions.indexOf(id);
    if (i < 0) return null;
    const focused = focus.zone === "actions" && focus.index === i;
    const m = META[id];
    return (
      <motion.button
        layout
        key={id}
        type="button"
        className={`action ${m.cls} ${focused ? "is-focused" : ""}`}
        onClick={() => onAction(id)}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
      >
        {focused && <FocusRing />}
        {m.icon}
        {id === "complete" ? (
          <span className="complete-text">
            <small>Use sentence</small>
            {completion}
          </span>
        ) : (
          <span>{m.label}</span>
        )}
      </motion.button>
    );
  };

  return (
    <header className="topbar">
      {btn("speak")}
      <div className={`message ${spoken ? "is-spoken" : ""} ${polished ? "has-polish" : ""}`}>
        {polished && (
          <motion.div
            key={polished.text}
            className="polished"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            title={polished.source === "ai" ? "Grammar fixed by AI" : "Grammar fixed"}
          >
            <SpellCheck size={20} />
            <span>{polished.text}</span>
          </motion.div>
        )}
        {message.length === 0 ? (
          <span className="message-hint">Look at the arrows to choose words…</span>
        ) : (
          <div className="message-chips">
            <AnimatePresence initial={false}>
              {message.map((m, i) => (
                <motion.span
                  key={`${i}-${m.text}`}
                  className="chip"
                  style={{ "--tile": tileColor(m.pos) } as React.CSSProperties}
                  initial={{ opacity: 0, y: 10, scale: 0.8 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.6, transition: { duration: 0.15 } }}
                  layout
                >
                  {m.picto && <Picto label={m.label} emoji={m.emoji} size="sm" />}
                  {m.text}
                </motion.span>
              ))}
            </AnimatePresence>
          </div>
        )}
        {spoken && (
          <span className="spoken-badge">
            <Check size={14} /> spoken
          </span>
        )}
      </div>
      <AnimatePresence>{btn("complete")}</AnimatePresence>
      {btn("delete")}
      {btn("clear")}
    </header>
  );
}
