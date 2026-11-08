import {
  CircleHelp, Footprints, Heart, Keyboard, LayoutGrid, LifeBuoy, MapPin, MessageCircle, Palette, Shapes,
  Sparkles, Undo2, Users, UtensilsCrossed,
} from "lucide-react";
import type { Category } from "../lib/types";
import type { Focus } from "./nav";
import { FocusRing } from "./TileCard";

const ICONS: Record<string, JSX.Element> = {
  back: <Undo2 />, smart: <Sparkles />, more: <LayoutGrid />, keyboard: <Keyboard />, people: <Users />, actions: <Footprints />,
  feelings: <Heart />, food: <UtensilsCrossed />, places: <MapPin />, things: <Shapes />,
  describe: <Palette />, questions: <CircleHelp />, chat: <MessageCircle />, needs: <LifeBuoy />,
};

interface Props {
  items: Category[]; // includes the Back item first
  activeId: string;
  focus: Focus;
  onPick: (index: number) => void;
}

export function NavBar({ items, activeId, focus, onPick }: Props) {
  return (
    <nav className={`navbar ${focus.zone === "nav" ? "has-focus" : ""}`}>
      {items.map((c, i) => {
        const focused = focus.zone === "nav" && focus.index === i;
        return (
          <button
            key={c.id}
            type="button"
            className={`nav-item nav-${c.id} ${activeId === c.id ? "is-active" : ""} ${focused ? "is-focused" : ""}`}
            onClick={() => onPick(i)}
          >
            {focused && <FocusRing />}
            <span className="nav-icon">{ICONS[c.id] ?? <Sparkles />}</span>
            <span className="nav-label">{c.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
