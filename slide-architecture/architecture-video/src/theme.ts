import { loadFont } from "@remotion/google-fonts/Inter";
import { Easing } from "remotion";

// Same palette as marketing-video (mirrors triage-explorer/src/index.css).
export const { fontFamily } = loadFont("normal", {
  weights: ["400", "500", "600", "700", "800"],
  subsets: ["latin"],
});

// Dark navy palette of the Team 8 logo (ai-support-agent-logo-compact.svg), shared with start + end screens.
export const C = {
  surface0: "#0A0F2A",
  surface1: "#141B3F",
  surface2: "#1E2752",
  border: "rgba(142,155,214,.28)",
  wire: "#34407A",
  text: "#FFFFFF",
  text2: "#B7C0EA",
  muted: "#8E9BD6",
  accent: "#7CF3FF",
  coral: "#00E5FF",
  plum: "#C04DFF",
  good: "#7CFFD6",
  goodBg: "rgba(0,214,154,.18)",
};

export const GRADIENT = "linear-gradient(135deg, #00E5FF, #6C7BFF, #C04DFF)";

export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
