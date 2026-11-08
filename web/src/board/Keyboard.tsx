import { Check, Delete, Keyboard as KbIcon, Space, X } from "lucide-react";
import type { Focus } from "./nav";
import { FocusRing } from "./TileCard";

export type KeyKind = "suggest" | "letter" | "add" | "space" | "backspace" | "clear";
export interface KeyDef {
  id: string;
  label: string;
  kind: KeyKind;
}

const LETTERS = ["QWERTYUIOP", "ASDFGHJKL'", "ZXCVBNM?"];

/** Row 0 = word suggestions for what is typed (hidden when empty), rows 1-3 letters, row 4 controls. */
export function buildKeyRows(suggestions: string[], typed: string): KeyDef[][] {
  const suggest = typed.trim()
    ? suggestions.slice(0, 6).map((s) => ({ id: `s:${s}`, label: s, kind: "suggest" as const }))
    : [];
  const letters = LETTERS.map((row) => row.split("").map((ch) => ({ id: `k:${ch}`, label: ch, kind: "letter" as const })));
  const controls: KeyDef[] = [
    { id: "add", label: "Add word", kind: "add" },
    { id: "space", label: "Space", kind: "space" },
    { id: "backspace", label: "Delete letter", kind: "backspace" },
    { id: "clear", label: "Clear typing", kind: "clear" },
  ];
  return [suggest, ...letters, controls];
}

const CONTROL_ICON: Partial<Record<KeyKind, JSX.Element>> = {
  add: <Check size={18} />, space: <Space size={18} />, backspace: <Delete size={18} />, clear: <X size={18} />,
};

interface Props {
  rows: KeyDef[][];
  typed: string;
  focus: Focus;
  onKey: (row: number, col: number) => void;
}

export function Keyboard({ rows, typed, focus, onKey }: Props) {
  const inKeys = focus.zone === "keys";
  return (
    <div className={`keyboard ${inKeys || focus.zone === "krows" ? "has-focus" : ""}`}>
      {rows.map((row, r) => {
        const rowFocused = focus.zone === "krows" && focus.row === r;
        const active = inKeys && focus.row === r;
        return (
          <div
            key={r}
            className={`kb-row kb-row-${r} ${rowFocused ? "is-focused" : ""} ${inKeys && !active ? "is-dim" : ""}`}
          >
            {rowFocused && <FocusRing />}
            {r === 0 && (
              <div className={`kb-typed ${typed ? "" : "is-empty"}`}>
                <KbIcon size={18} />
                <span>{typed || "Type a word…"}</span>
                {typed && <i className="caret" />}
              </div>
            )}
            {row.map((k, c) => {
              const focused = inKeys && focus.row === r && focus.col === c;
              return (
                <button
                  key={k.id}
                  type="button"
                  className={`key-btn kind-${k.kind} ${focused ? "is-focused" : ""}`}
                  onClick={() => onKey(r, c)}
                >
                  {focused && <FocusRing />}
                  {CONTROL_ICON[k.kind]}
                  <span>{k.label}</span>
                </button>
              );
            })}
            {r === 0 && row.length === 0 && typed && <span className="kb-none">no matches · Add word to use it as typed</span>}
          </div>
        );
      })}
    </div>
  );
}

/** The Keyboard page (its own item in the side menu). */
export function KeyboardPage({ subtitle, ...props }: Props & { subtitle: string }) {
  return (
    <section className="kb-page">
      <header className="grid-head">
        <h2>Keyboard</h2>
        <span className="grid-sub">{subtitle}</span>
      </header>
      <Keyboard {...props} />
    </section>
  );
}
