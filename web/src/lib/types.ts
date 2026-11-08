export type Direction = "up" | "down" | "left" | "right" | "ok";
export const DIRECTIONS: Direction[] = ["up", "left", "ok", "right", "down"];

export type Pos =
  | "pronoun" | "verb" | "noun" | "place" | "describe"
  | "question" | "social" | "yes" | "no" | "little";

export interface Tile {
  id: string;
  label: string;
  speak: string;
  pos: Pos;
  emoji: string;
  kind: "word" | "phrase" | "more" | "category" | "need";
  source: string; // predict | history | context | ai | vocab | nav
  picto: boolean;
  page?: number; // "more" tiles: the page they open
  target?: string; // "category" tiles: the category they open
  icon?: string | null; // pictogram word, if different from the label
  need?: { level: "emergency" | "urgent" | "normal"; say: string };
}

/** One column of the Smart Board. */
export interface Column {
  id: string;
  title: string;
  tiles: Tile[];
}

export interface Alert {
  level: "emergency" | "urgent";
  label: string;
  say: string;
  t: number;
}

/** One chosen tile in the message bar. */
export interface MessageItem {
  label: string; // used for prediction
  text: string; // shown + spoken
  pos: Pos;
  emoji: string;
  picto: boolean;
}

export interface Category {
  id: string;
  label: string;
  emoji: string;
}

export interface HubStatus {
  clients: { board: number; controller: number; decoder: number };
  stimulus: { on: boolean; freqs: Record<Direction, number> };
  llm: string | null;
  llmModel: string;
  stt: string | null;
  tts: boolean;
}

export interface ContextInfo {
  version: number;
  lines: { t: number; text: string }[];
  keywords: string[];
  question: boolean;
  options: string[];
  topic: string;
  answers: string[];
  items: string[];
  llmUpdate?: boolean;
}

export interface Profile {
  name: string;
  family: string[];
  likes: string[];
  notes: string;
}
