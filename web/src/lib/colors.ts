import type { Pos } from "./types";

/**
 * AAC colour coding (modified Fitzgerald key). The first six are the team's palette;
 * blue/purple/slate extend it for describing words, questions and little grammar words.
 */
export const POS_COLORS: Record<Pos, { bg: string; name: string }> = {
  pronoun: { bg: "#FFF0B3", name: "People" },
  verb: { bg: "#B3E6B3", name: "Actions" },
  noun: { bg: "#FFD9B3", name: "Things" },
  place: { bg: "#FFD9B3", name: "Places" },
  social: { bg: "#FFB3D9", name: "Social" },
  no: { bg: "#FF9999", name: "No / Stop" },
  yes: { bg: "#99CC99", name: "Yes / Go" },
  describe: { bg: "#B3D9FF", name: "Describe" },
  question: { bg: "#D9C2FF", name: "Questions" },
  little: { bg: "#E2E8F0", name: "Little words" },
};

export const LEGEND: Pos[] = ["pronoun", "verb", "noun", "describe", "question", "social", "yes", "no"];

export function tileColor(pos: Pos): string {
  return (POS_COLORS[pos] ?? POS_COLORS.noun).bg;
}
