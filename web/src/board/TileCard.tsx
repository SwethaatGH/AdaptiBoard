import { motion } from "framer-motion";
import {
  ArrowRight, Clock, CircleHelp, Dices, Ear, Footprints, Heart, History, MapPin, Palette,
  MessageSquareText, PersonStanding, Shapes, Siren, Sparkles, Type, Users, UtensilsCrossed, BellRing,
} from "lucide-react";
import { useState } from "react";
import { tileColor } from "../lib/colors";
import type { Tile } from "../lib/types";

export function FocusRing() {
  return (
    <motion.div
      layoutId="focus-ring"
      className="focus-ring"
      transition={{ type: "spring", stiffness: 520, damping: 38, mass: 0.7 }}
    />
  );
}

/** ARASAAC pictogram. If it can't load, a quiet line icon (big tiles) or nothing (sentence chips). */
export function Picto({ label, size = "lg" }: { label: string; emoji?: string; size?: "lg" | "sm" }) {
  const [failed, setFailed] = useState(false);
  const src = `/api/icon/${encodeURIComponent(label.replace(/[?!.]/g, ""))}`;
  if (failed) return size === "lg" ? <MessageSquareText className="picto-fallback" strokeWidth={1.6} aria-hidden /> : null;
  return <img className={`picto ${size}`} src={src} alt="" draggable={false} onError={() => setFailed(true)} />;
}

const SOURCE_BADGE: Record<string, { icon: JSX.Element; title: string } | undefined> = {
  context: { icon: <Ear size={13} />, title: "Heard in the conversation" },
  ai: { icon: <Sparkles size={13} />, title: "Suggested by AI" },
  history: { icon: <History size={13} />, title: "You often choose this" },
};

export const CATEGORY_ICONS: Record<string, JSX.Element> = {
  people: <Users />, actions: <Footprints />, feelings: <Heart />, food: <UtensilsCrossed />,
  places: <MapPin />, things: <Shapes />, questions: <CircleHelp />, describe: <Palette />,
  body: <PersonStanding />, time: <Clock />, activities: <Dices />, little: <Type />,
};

interface Props {
  tile: Tile;
  index: number;
  focused: boolean;
  dim?: boolean;
  pulse: boolean;
  wide?: boolean; // Smart Board columns: picture left, word right
  onClick: () => void;
}

export function TileCard({ tile, index, focused, dim, pulse, wide, onClick }: Props) {
  const badge = SOURCE_BADGE[tile.source];
  const isMore = tile.kind === "more";
  const isCat = tile.kind === "category";
  const level = tile.need?.level;
  const long = !tile.picto && tile.label.length > 14;

  let art: JSX.Element;
  if (isMore) art = <ArrowRight className="more-arrow" strokeWidth={2.5} />;
  else if (isCat) art = <span className="cat-icon">{CATEGORY_ICONS[tile.target ?? ""] ?? <Shapes />}</span>;
  else if (tile.kind === "need") art = <Picto label={tile.icon || tile.label} />;
  else if (tile.picto) art = <Picto label={tile.icon || tile.label} />;
  else art = <span className={`tile-glyph ${long ? "is-long" : ""}`}>{tile.label}</span>;

  const showLabel = tile.picto || isMore || isCat || tile.kind === "need";

  return (
    <motion.button
      type="button"
      className={[
        "tile",
        focused && "is-focused",
        dim && "is-dim",
        isMore && "is-more",
        isCat && "is-cat",
        wide && "is-wide",
        level && `need-${level}`,
      ].filter(Boolean).join(" ")}
      style={{ "--tile": tileColor(tile.pos) } as React.CSSProperties}
      initial={{ opacity: 0, y: 12, scale: 0.95 }}
      animate={pulse ? { opacity: 1, y: 0, scale: [1, 1.06, 1] } : { opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.12 } }}
      transition={{ delay: pulse ? 0 : index * 0.018, type: "spring", stiffness: 380, damping: 28 }}
      onClick={onClick}
      aria-label={tile.label}
    >
      {focused && <FocusRing />}
      {badge && (
        <span className="tile-badge" title={badge.title}>
          {badge.icon}
        </span>
      )}
      {level && level !== "normal" && (
        <span className="need-badge" title={level === "emergency" ? "Emergency alert" : "Alerts the caregiver"}>
          {level === "emergency" ? <Siren size={14} /> : <BellRing size={13} />}
        </span>
      )}
      <span className="tile-art">{art}</span>
      {showLabel && <span className="tile-label">{tile.label}</span>}
    </motion.button>
  );
}

export function SkeletonTile({ index }: { index: number }) {
  return <div className="tile skeleton" style={{ animationDelay: `${index * 40}ms` }} />;
}
