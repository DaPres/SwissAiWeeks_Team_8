import React from "react";
import { Interactive, interpolate, useCurrentFrame } from "remotion";
import { C, clamp, EASE_OUT, fontFamily } from "./theme";
import { DURATION, s, STEPS } from "./timing";

/** Step caption above the diagram; swaps with the storyboard in timing.ts. */
export const Header: React.FC = () => {
  const frame = useCurrentFrame();
  const index = STEPS.filter((st) => frame >= s(st.from)).length - 1;
  const step = STEPS[Math.max(0, index)];
  const start = s(step.from);
  const end = s(STEPS[index + 1]?.from ?? DURATION);
  const local = frame - start;
  const out = index === STEPS.length - 1 ? 1 : interpolate(frame, [end - 8, end], [1, 0], clamp);
  const enter = (delay: number) => ({
    opacity: interpolate(local, [delay, delay + 14], [0, 1], clamp) * out,
    translate: `0px ${interpolate(local, [delay, delay + 18], [24, 0], { ...clamp, easing: EASE_OUT })}px`,
  });

  return (
    <div style={{ position: "absolute", left: 70, right: 70, top: 58, fontFamily }}>
      <Interactive.Div
        name="Eyebrow"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          color: C.accent,
          fontSize: 22,
          fontWeight: 800,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          ...enter(0),
        }}
      >
        <span style={{ width: 11, height: 11, borderRadius: "50%", background: C.coral, boxShadow: "0 0 0 7px rgba(0,229,255,.18)" }} />
        {step.eyebrow}
      </Interactive.Div>
      <Interactive.Div
        name="Title"
        style={{ marginTop: 12, color: C.text, fontSize: 54, lineHeight: 1.05, fontWeight: 780, letterSpacing: "-0.045em", ...enter(4) }}
      >
        {step.title}
      </Interactive.Div>
      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        {step.chips.map((chip, i) => (
          <span
            key={chip}
            style={{
              padding: "6px 15px",
              borderRadius: 999,
              background: C.surface2,
              border: `1.5px solid ${C.border}`,
              color: "#C9D0FF",
              fontSize: 19,
              fontWeight: 650,
              ...enter(12 + i * 5),
            }}
          >
            {chip}
          </span>
        ))}
      </div>
    </div>
  );
};
