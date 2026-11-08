import { AnimatePresence } from "framer-motion";
import type { Column } from "../lib/types";
import type { Focus } from "./nav";
import { FocusRing, SkeletonTile, TileCard } from "./TileCard";

export const PER_COLUMN = 4;

interface Props {
  columns: Column[];
  loading: boolean;
  focus: Focus;
  pageKey: string;
  pulseId: string | null;
  subtitle: string;
  onTile: (col: number, row: number) => void;
}

const COL_CLASS = ["col-questions", "col-people", "col-actions", "col-things"];

/**
 * The Smart Board: 4 columns, chosen column by column (Questions → People →
 * Actions & Feelings → Food & Things). Columns are colour-coded, no labels.
 */
export function SmartBoard({ columns, loading, focus, pageKey, pulseId, subtitle, onTile }: Props) {
  const inCol = focus.zone === "ctiles";
  return (
    <section className="smart">
      <header className="grid-head">
        <h2>Smart Board</h2>
        <span className="grid-sub">{subtitle}</span>
      </header>

      <div className="columns">
        {Array.from({ length: 4 }, (_, c) => {
          const col = columns[c];
          const colFocused = focus.zone === "cols" && focus.col === c;
          const active = inCol && focus.col === c;
          return (
            <div
              key={c}
              title={col?.title}
              className={`column ${COL_CLASS[c]} ${colFocused ? "is-focused" : ""} ${active ? "is-active" : ""} ${
                inCol && !active ? "is-dim" : ""
              }`}
            >
              {colFocused && <FocusRing />}
              <div className="column-tiles">
                {loading || !col ? (
                  Array.from({ length: PER_COLUMN }, (_, r) => <SkeletonTile key={r} index={c * PER_COLUMN + r} />)
                ) : (
                  <AnimatePresence mode="popLayout" initial>
                    {Array.from({ length: PER_COLUMN }, (_, r) => {
                      const t = col.tiles[r];
                      if (!t) return <div key={`${pageKey}-e-${c}-${r}`} className="tile is-empty" />;
                      return (
                        <TileCard
                          key={`${pageKey}-${t.id}`}
                          tile={t}
                          index={c * PER_COLUMN + r}
                          wide
                          focused={inCol && focus.col === c && focus.row === r}
                          pulse={pulseId === t.id}
                          onClick={() => onTile(c, r)}
                        />
                      );
                    })}
                  </AnimatePresence>
                )}
              </div>
            </div>
          );
        })}
      </div>

    </section>
  );
}
