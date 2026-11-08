import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, CircleDot } from "lucide-react";
import { LEGEND, POS_COLORS } from "../lib/colors";
import type { Direction } from "../lib/types";
import { HINTS, type Focus } from "./nav";

const DIR_ICON: Record<Direction, JSX.Element> = {
  up: <ArrowUp size={16} />, down: <ArrowDown size={16} />, left: <ArrowLeft size={16} />,
  right: <ArrowRight size={16} />, ok: <CircleDot size={16} />,
};

export function HintBar({ focus, lastCmd }: { focus: Focus; lastCmd: { dir: Direction; n: number; source: string } | null }) {
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
      <span className="credit">
        Pictograms: Sergio Palao · ARASAAC (CC BY-NC-SA)
      </span>
    </footer>
  );
}
