import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { NodeDef } from "./layout";
import { C, clamp, EASE_OUT, fontFamily, GRADIENT } from "./theme";
import { s, USER } from "./timing";

const INK = "#2c1732";

/** mood: 0 = worried, 1 = happy. */
const Face: React.FC<{ mood: number }> = ({ mood }) => {
  const mouth = interpolate(mood, [0, 1], [-5, 8]);
  const brow = interpolate(mood, [0, 1], [5, 0]);
  return (
    <svg width={124} height={124} viewBox="0 0 120 120">
      <defs>
        <clipPath id="avatarClip">
          <circle cx={60} cy={60} r={57} />
        </clipPath>
      </defs>
      <circle cx={60} cy={60} r={57} fill={C.surface2} />
      <g clipPath="url(#avatarClip)">
        {/* long hair behind the head */}
        <rect x={33} y={42} width={54} height={50} rx={18} fill="#5b3326" />
        <ellipse cx={60} cy={122} rx={40} ry={32} fill={C.accent} />
        <rect x={53} y={74} width={14} height={14} rx={5} fill="#eeb99b" />
        <circle cx={60} cy={56} r={23} fill="#f6cfb5" />
        <path d="M36 56 C36 36 50 30 60 30 C72 30 86 38 84 58 C78 46 68 40 56 42 C48 43 40 48 36 56 Z" fill="#5b3326" />
        {/* eyes: dots when worried, happy arcs when solved */}
        <g opacity={1 - mood}>
          <circle cx={51} cy={57} r={2.8} fill={INK} />
          <circle cx={69} cy={57} r={2.8} fill={INK} />
        </g>
        <g opacity={mood} fill="none" stroke={INK} strokeWidth={2.6} strokeLinecap="round">
          <path d="M47 58 Q51 53 55 58" />
          <path d="M65 58 Q69 53 73 58" />
        </g>
        <g stroke={INK} strokeWidth={2.2} strokeLinecap="round">
          <line x1={47} y1={50 - brow * 0.2} x2={55} y2={50 - brow} />
          <line x1={73} y1={50 - brow * 0.2} x2={65} y2={50 - brow} />
        </g>
        <circle cx={46} cy={65} r={4.5} fill="#ff9a9e" opacity={mood * 0.8} />
        <circle cx={74} cy={65} r={4.5} fill="#ff9a9e" opacity={mood * 0.8} />
        <path d={`M52 68 Q60 ${68 + mouth} 68 68`} fill="none" stroke={INK} strokeWidth={2.6} strokeLinecap="round" />
      </g>
    </svg>
  );
};

const Bubble: React.FC<{ text: string; from: number; to?: number; happy?: boolean }> = ({ text, from, to, happy }) => {
  const frame = useCurrentFrame();
  const inP = interpolate(frame, [s(from), s(from) + 12], [0, 1], { ...clamp, easing: EASE_OUT });
  const outP = to === undefined ? 1 : interpolate(frame, [s(to) - 8, s(to)], [1, 0], clamp);
  return (
    <div
      style={{
        position: "absolute",
        left: 140,
        top: 8,
        padding: "12px 20px",
        borderRadius: "20px 20px 20px 4px",
        background: happy ? GRADIENT : C.surface1,
        border: happy ? "none" : `2px solid ${C.border}`,
        color: happy ? "#fff" : C.text,
        fontSize: 24,
        fontWeight: 720,
        whiteSpace: "nowrap",
        boxShadow: "0 12px 30px rgba(0,0,0,.35)",
        opacity: inP * outP,
        scale: String(0.6 + 0.4 * inP),
        transformOrigin: "left bottom",
      }}
    >
      {text}
    </div>
  );
};

const SPARKS = Array.from({ length: 8 }, (_, i) => (i / 8) * Math.PI * 2 + 0.3);

export const UserNode: React.FC<{ node: NodeDef; act: number; appear: number }> = ({ node, act, appear }) => {
  const frame = useCurrentFrame();
  const mood = interpolate(frame, USER.mood.map(([t]) => s(t)), USER.mood.map(([, m]) => m), { ...clamp, easing: EASE_OUT });
  const happyAt = s([...USER.happyAt].reverse().find((t) => frame >= s(t)) ?? USER.happyAt[0]);
  const jump = frame >= happyAt ? Math.max(0, Math.sin(((frame - happyAt) / 10) * Math.PI)) * 14 * Math.exp(-(frame - happyAt) / 25) : 0;
  const burst = interpolate(frame, [happyAt, happyAt + 28], [0, 1], { ...clamp, easing: EASE_OUT });
  const ring = mood > 0.5 ? "rgba(23,97,77,.35)" : `rgba(192,77,255,${0.5 * act})`;

  return (
    <div
      style={{
        position: "absolute",
        left: node.cx - node.w / 2,
        top: node.cy - node.h / 2,
        width: node.w,
        height: node.h,
        opacity: appear,
        scale: String(0.7 + 0.3 * appear),
        fontFamily,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
      }}
    >
      <div style={{ position: "relative", translate: `0px ${-jump}px` }}>
        <div
          style={{
            position: "absolute",
            inset: -5,
            borderRadius: "50%",
            background: mood > 0.5 ? "#2f9e7a" : GRADIENT,
            opacity: Math.max(act, mood),
          }}
        />
        <div
          style={{
            position: "relative",
            borderRadius: "50%",
            border: `3px solid ${C.surface1}`,
            boxShadow: `0 18px 50px -8px ${ring}`,
            lineHeight: 0,
          }}
        >
          <Face mood={mood} />
        </div>
        {SPARKS.map((a, i) => {
          const r = 70 + burst * 40;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: 65 + Math.cos(a) * r - 7,
                top: 65 + Math.sin(a) * r - 7,
                width: 14,
                height: 14,
                rotate: "45deg",
                borderRadius: 3,
                background: i % 2 ? "#00E5FF" : "#2f9e7a",
                opacity: burst > 0 && burst < 1 ? 1 - burst : 0,
                scale: String(1 - burst * 0.5),
              }}
            />
          );
        })}
      </div>
      <div style={{ marginTop: 10, fontSize: 28, fontWeight: 780, letterSpacing: "-0.03em", color: C.text }}>{node.title}</div>
      {USER.bubbles.map((b) => (
        <Bubble key={b.text} text={b.text} from={b.from} to={b.to} happy={b.happy} />
      ))}
    </div>
  );
};
