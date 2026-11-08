import type { Direction } from "../lib/types";

/**
 * Where the highlight is. The board works like a TV remote with 5 buttons.
 *
 * Everywhere:
 *   actions  top bar: Speak / Use sentence / Delete / Clear      (← → move, ↓ back down)
 *   nav      left menu: Back, Smart Board, More words, Keyboard, Chat, Needs
 *                                            (↑ ↓ move, → back to the page)
 *
 * Smart Board (column-wise):
 *   cols     a whole COLUMN is highlighted   (← → choose column, OK = enter it)
 *   ctiles   a tile inside that column       (↑ ↓ choose tile, OK = say it, ← → leave column)
 *
 * Keyboard page:
 *   krows    a keyboard row                  (↑ ↓ choose row, OK = enter it)
 *   keys     a key inside that row           (← → choose key, OK = type it, ↑ ↓ leave row)
 *
 * Chat, Needs, More words, category pages (row-wise):
 *   rows     a whole ROW is highlighted      (↑ ↓ choose row, OK = enter it, ← menu)
 *   tiles    a tile inside that row          (← → choose tile, OK = choose it, ↑ ↓ leave row)
 */
export type Focus =
  | { zone: "actions"; index: number }
  | { zone: "nav"; index: number }
  | { zone: "rows"; row: number }
  | { zone: "tiles"; row: number; col: number }
  | { zone: "cols"; col: number }
  | { zone: "ctiles"; col: number; row: number }
  | { zone: "krows"; row: number }
  | { zone: "keys"; row: number; col: number };

export interface Layout {
  mode: "smart" | "rows" | "keys";
  actions: number; // buttons in the top bar
  nav: number; // menu items
  navActive: number; // menu item of the page being shown
  rowLens: number[]; // rows mode: tiles in each row
  colLens: number[]; // smart mode: tiles in each column
  keyRows: number[]; // keys mode: keys in each keyboard row (0 = row hidden)
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** The page's own starting point (where ↓ from the top bar or → from the menu lands). */
export function home(L: Layout): Focus {
  if (L.mode === "smart") return { zone: "cols", col: 0 };
  if (L.mode === "keys") return { zone: "krows", row: keyRow(0, 1, L) ?? 1 };
  return { zone: "rows", row: 0 };
}

function keyRow(from: number, step: 1 | -1, L: Layout): number | null {
  for (let r = from; r >= 0 && r < L.keyRows.length; r += step) if (L.keyRows[r] > 0) return r;
  return null;
}

export function move(f: Focus, dir: Exclude<Direction, "ok">, L: Layout): Focus {
  const rows = L.rowLens.filter((n) => n > 0).length;
  const cols = L.colLens.length;
  switch (f.zone) {
    // ---------------------------------------------------- shared
    case "actions":
      if (dir === "left") return f.index > 0 ? { zone: "actions", index: f.index - 1 } : { zone: "nav", index: L.navActive };
      if (dir === "right") return { zone: "actions", index: clamp(f.index + 1, 0, L.actions - 1) };
      if (dir === "down") return home(L);
      return f;
    case "nav":
      if (dir === "up") return f.index > 0 ? { zone: "nav", index: f.index - 1 } : { zone: "actions", index: 0 };
      if (dir === "down") return { zone: "nav", index: clamp(f.index + 1, 0, L.nav - 1) };
      if (dir === "right") return home(L);
      return f;

    // ---------------------------------------------------- rows pages
    case "rows":
      if (dir === "up") return f.row > 0 ? { zone: "rows", row: f.row - 1 } : { zone: "actions", index: 0 };
      if (dir === "down") return { zone: "rows", row: clamp(f.row + 1, 0, Math.max(0, rows - 1)) };
      if (dir === "left") return { zone: "nav", index: L.navActive };
      return f;
    case "tiles": {
      const len = L.rowLens[f.row] ?? 0;
      if (dir === "left") return f.col > 0 ? { ...f, col: f.col - 1 } : { zone: "rows", row: f.row };
      if (dir === "right") return { ...f, col: clamp(f.col + 1, 0, Math.max(0, len - 1)) };
      return move({ zone: "rows", row: f.row }, dir, L); // ↑ ↓ leave the row and move
    }

    // ---------------------------------------------------- Smart Board
    case "cols":
      if (dir === "left") return f.col > 0 ? { zone: "cols", col: f.col - 1 } : { zone: "nav", index: L.navActive };
      if (dir === "right") return { zone: "cols", col: clamp(f.col + 1, 0, cols - 1) };
      if (dir === "up") return { zone: "actions", index: 0 };
      return f;
    case "ctiles": {
      const len = L.colLens[f.col] ?? 0;
      if (dir === "up") return f.row > 0 ? { ...f, row: f.row - 1 } : { zone: "cols", col: f.col };
      if (dir === "down") return { ...f, row: clamp(f.row + 1, 0, Math.max(0, len - 1)) };
      return move({ zone: "cols", col: f.col }, dir, L); // ← → leave the column and move
    }
    case "krows": {
      if (dir === "up") {
        const r = keyRow(f.row - 1, -1, L);
        return r === null ? { zone: "actions", index: 0 } : { zone: "krows", row: r };
      }
      if (dir === "down") {
        const r = keyRow(f.row + 1, 1, L);
        return r === null ? f : { zone: "krows", row: r };
      }
      if (dir === "left") return { zone: "nav", index: L.navActive };
      return f;
    }
    case "keys": {
      const len = L.keyRows[f.row] ?? 0;
      if (dir === "left") return f.col > 0 ? { ...f, col: f.col - 1 } : { zone: "krows", row: f.row };
      if (dir === "right") return { ...f, col: clamp(f.col + 1, 0, Math.max(0, len - 1)) };
      return move({ zone: "krows", row: f.row }, dir, L);
    }
  }
}

const MODE_ZONES: Record<Layout["mode"], Set<string>> = {
  smart: new Set(["cols", "ctiles"]),
  rows: new Set(["rows", "tiles"]),
  keys: new Set(["krows", "keys"]),
};

/** Keeps focus valid when the page or its contents change. */
export function fit(f: Focus, L: Layout): Focus {
  if (f.zone !== "actions" && f.zone !== "nav" && !MODE_ZONES[L.mode].has(f.zone)) return home(L);
  const rows = L.rowLens.filter((n) => n > 0).length;
  switch (f.zone) {
    case "rows":
      return { zone: "rows", row: clamp(f.row, 0, Math.max(0, rows - 1)) };
    case "tiles": {
      const len = L.rowLens[f.row] ?? 0;
      return len ? { ...f, col: clamp(f.col, 0, len - 1) } : { zone: "rows", row: 0 };
    }
    case "cols":
      return { zone: "cols", col: clamp(f.col, 0, Math.max(0, L.colLens.length - 1)) };
    case "ctiles": {
      const len = L.colLens[f.col] ?? 0;
      return len ? { ...f, row: clamp(f.row, 0, len - 1) } : { zone: "cols", col: f.col };
    }
    case "krows":
      return L.keyRows[f.row] ? f : { zone: "krows", row: keyRow(0, 1, L) ?? 1 };
    case "keys": {
      const len = L.keyRows[f.row] ?? 0;
      return len ? { ...f, col: clamp(f.col, 0, len - 1) } : { zone: "krows", row: keyRow(0, 1, L) ?? 1 };
    }
    case "actions":
      return { zone: "actions", index: clamp(f.index, 0, L.actions - 1) };
    case "nav":
      return { zone: "nav", index: clamp(f.index, 0, L.nav - 1) };
    default:
      return f;
  }
}

export const HINTS: Record<Focus["zone"], [string, string][]> = {
  cols: [["← →", "choose a column"], ["OK", "open the column"], ["←", "menu"]],
  ctiles: [["↑ ↓", "choose a tile"], ["OK", "say it"], ["← →", "other columns"]],
  krows: [["↑ ↓", "choose a row"], ["OK", "open the row"], ["←", "menu"]],
  keys: [["← →", "choose a key"], ["OK", "type it"], ["↑ ↓", "other rows"]],
  rows: [["↑ ↓", "choose a row"], ["OK", "open the row"], ["←", "menu"]],
  tiles: [["← →", "choose a tile"], ["OK", "choose it"], ["↑ ↓", "back to rows"]],
  nav: [["↑ ↓", "choose a page"], ["OK", "open it"], ["→", "back to the page"]],
  actions: [["← →", "choose"], ["OK", "do it"], ["↓", "back to the page"]],
};
