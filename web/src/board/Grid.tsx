import { AnimatePresence } from "framer-motion";
import type { Tile } from "../lib/types";
import type { Focus } from "./nav";
import { FocusRing, SkeletonTile, TileCard } from "./TileCard";

export const COLS = 4;
export const ROWS = 4;

interface Props {
  tiles: Tile[];
  loading: boolean;
  focus: Focus;
  pageKey: string;
  pulseId: string | null;
  title: string;
  subtitle: string;
  onTileClick: (row: number, col: number) => void;
}

export function rowsOf(tiles: Tile[]): Tile[][] {
  return Array.from({ length: ROWS }, (_, r) => tiles.slice(r * COLS, r * COLS + COLS));
}

export function Grid({ tiles, loading, focus, pageKey, pulseId, title, subtitle, onTileClick }: Props) {
  const rows = rowsOf(tiles);
  const inTiles = focus.zone === "tiles";
  return (
    <section className={`grid-panel ${loading ? "is-loading" : ""}`}>
      <header className="grid-head">
        <h2>{title}</h2>
        <span className="grid-sub">{subtitle}</span>
      </header>
      <div className="grid">
        {rows.map((row, r) => {
          const rowFocused = focus.zone === "rows" && focus.row === r;
          const activeRow = inTiles && focus.row === r;
          return (
            <div
              key={r}
              className={`grid-row ${rowFocused ? "is-focused" : ""} ${activeRow ? "is-active" : ""} ${
                inTiles && !activeRow ? "is-dim" : ""
              }`}
            >
              {rowFocused && <FocusRing />}
              {loading
                ? Array.from({ length: COLS }, (_, c) => <SkeletonTile key={c} index={r * COLS + c} />)
                : (
                  <AnimatePresence mode="popLayout" initial>
                    {Array.from({ length: COLS }, (_, c) => {
                      const t = row[c];
                      if (!t) return <div key={`${pageKey}-empty-${c}`} className="tile is-empty" />;
                      return (
                        <TileCard
                          key={`${pageKey}-${t.id}`}
                          tile={t}
                          index={r * COLS + c}
                          focused={inTiles && focus.row === r && focus.col === c}
                          dim={false}
                          pulse={pulseId === t.id}
                          onClick={() => onTileClick(r, c)}
                        />
                      );
                    })}
                  </AnimatePresence>
                )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
