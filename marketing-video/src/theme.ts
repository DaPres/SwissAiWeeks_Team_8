import { loadFont } from "@remotion/google-fonts/Inter";
import { Easing } from "remotion";

// Mirrors triage-explorer/src/index.css so the video matches the running app.
export const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "600", "700", "800"],
  subsets: ["latin"],
});

export const C = {
  surface0: "#f8f4f8",
  surface1: "#ffffff",
  surface2: "#fbf0f7",
  border: "#eadce8",
  grid: "#f0e7ef",
  text: "#2c1732",
  text2: "#685a6d",
  muted: "#837389",
  accent: "#9e258a",
  coral: "#ff6266",
  coralSoft: "#ff9a9e",
  plum: "#421449",
  goodBg: "#e6f5ef",
  goodInk: "#17614d",
  warnBg: "#fff0e6",
  warnInk: "#8a441c",
  critBg: "#ffe7eb",
  critInk: "#a52f4b",
  seq: ["#fbe0ef", "#f3afd6", "#d963ad", "#a83096", "#642274"],
};

export const GRADIENT = "linear-gradient(135deg, #ff6266, #ae2a99)";

export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);

export type Level = "highest" | "high" | "medium" | "low" | "lowest";
export const LEVELS: Level[] = ["highest", "high", "medium", "low", "lowest"];

// MATRIX[urgency][impact] -> priority (backend/app/catalog.py)
export const MATRIX: Record<Level, Level[]> = {
  highest: ["highest", "highest", "high", "medium", "medium"],
  high: ["highest", "high", "high", "medium", "low"],
  medium: ["high", "high", "medium", "low", "low"],
  low: ["medium", "medium", "low", "low", "lowest"],
  lowest: ["medium", "low", "low", "lowest", "lowest"],
};

export const PRIORITY_STYLE: Record<Level, { bg: string; fg: string }> = {
  lowest: { bg: C.seq[0], fg: "#642274" },
  low: { bg: C.seq[1], fg: "#642274" },
  medium: { bg: C.seq[2], fg: "#451d52" },
  high: { bg: C.seq[3], fg: "#ffffff" },
  highest: { bg: C.seq[4], fg: "#ffffff" },
};
