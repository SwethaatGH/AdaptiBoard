import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Brain, CircleDot, Cpu, Gamepad2 } from "lucide-react";
import { LEGEND, POS_COLORS } from "../lib/colors";
import type { Direction, HubStatus } from "../lib/types";
import { HINTS, type Focus } from "./nav";

const DIR_ICON: Record<Direction, JSX.Element> = {
  up: <ArrowUp size={16} />, down: <ArrowDown size={16} />, left: <ArrowLeft size={16} />,
  right: <ArrowRight size={16} />, ok: <CircleDot size={16} />,
};

interface Props {
  focus: Focus;
  lastCmd: { dir: Direction; n: number; source: string } | null;
  status: HubStatus | null;
  connected: boolean;
}

export function HintBar({ focus, lastCmd, status, connected }: Props) {
  const c = status?.clients;
  return (
    <footer className="hintbar">
      <div className="hints">
        {HINTS[focus.zone].map(([k, v]) => (
          <span key={k} className="hint">
            <kbd>{k}</kbd> {v}
          </span>
        ))}
      </div>
      <AnimatePresence>
        {lastCmd && (
          <motion.span
            key={lastCmd.n}
            className="last-cmd"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 500, damping: 25 }}
            title={`from ${lastCmd.source}`}
          >
            {DIR_ICON[lastCmd.dir]} {lastCmd.dir.toUpperCase()}
            <small>{lastCmd.source}</small>
          </motion.span>
        )}
      </AnimatePresence>
      <div className="legend">
        {LEGEND.map((p) => (
          <span key={p}>
            <i style={{ background: POS_COLORS[p].bg }} />
            {POS_COLORS[p].name}
          </span>
        ))}
      </div>
      <div className="status-pills">
        <span className={`pill ${connected ? "ok" : "bad"}`} title="Server connection">
          <Cpu size={14} /> {connected ? "Server" : "Offline"}
        </span>
        <span className={`pill ${c && c.controller > 0 ? "ok" : ""}`} title="Controller screen connected">
          <Gamepad2 size={14} /> Controller
        </span>
        <span className={`pill ${c && c.decoder > 0 ? "ok" : ""} ${status?.stimulus.on ? "live" : ""}`} title="EEG decoder connected">
          <Brain size={14} /> EEG
        </span>
        <span className={`pill ${status?.llm ? "ai" : ""}`} title={status?.llm ? `${status.llm} · ${status.llmModel}` : "Offline predictor (no API key)"}>
          {status?.llm ?? "offline"}
        </span>
      </div>
    </footer>
  );
}
