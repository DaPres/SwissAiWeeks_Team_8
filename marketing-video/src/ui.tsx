import React from "react";
import { Audio } from "@remotion/media";
import {
  AbsoluteFill,
  Img,
  Interactive,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { C, EASE_IN_OUT, EASE_OUT, fontFamily, GRADIENT, Level, PRIORITY_STYLE } from "./theme";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Fade + slide up, starting at `start`. */
export const fadeUp = (frame: number, start: number, dur = 20, dist = 30): React.CSSProperties => ({
  opacity: interpolate(frame, [start, start + dur], [0, 1], { ...clamp, easing: EASE_OUT }),
  translate: `0px ${interpolate(frame, [start, start + dur], [dist, 0], { ...clamp, easing: EASE_OUT })}px`,
});

/** Spring-like pop in. */
export const popIn = (frame: number, start: number, dur = 18): React.CSSProperties => ({
  opacity: interpolate(frame, [start, start + dur * 0.5], [0, 1], clamp),
  scale: String(interpolate(frame, [start, start + dur], [0.6, 1], { ...clamp, easing: EASE_OUT })),
});

/** Typewriter: characters of `text` revealed between `start` and `start + dur`. */
export const typed = (text: string, frame: number, start: number, dur: number) =>
  text.slice(0, Math.round(interpolate(frame, [start, start + dur], [0, text.length], clamp)));

export const Caret: React.FC<{ visible?: boolean }> = ({ visible = true }) => {
  const frame = useCurrentFrame();
  return (
    <span
      style={{
        display: "inline-block",
        width: 3,
        height: "1.1em",
        marginLeft: 2,
        verticalAlign: "text-bottom",
        background: C.accent,
        opacity: visible && Math.floor(frame / 15) % 2 === 0 ? 1 : 0,
      }}
    />
  );
};

export const Sfx: React.FC<{ src: string; at: number; volume?: number }> = ({ src, at, volume = 0.6 }) => (
  <Sequence from={at} layout="none" name={`sfx ${src}`}>
    <Audio src={staticFile(`sfx/${src}`)} volume={volume} />
  </Sequence>
);

/** Soft key ticks while text is being typed. */
export const TypingSfx: React.FC<{ from: number; to: number; every?: number }> = ({ from, to, every = 3 }) => {
  const ticks: number[] = [];
  for (let f = from; f < to; f += every) ticks.push(f);
  return (
    <>
      {ticks.map((f, i) => (
        <Sfx key={f} src={i % 3 === 0 ? "click_002.wav" : "tick_002.wav"} at={f} volume={0.22 + (i % 4) * 0.04} />
      ))}
    </>
  );
};

/** Light app surface with slowly drifting brand glows. */
export const Backdrop: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: C.surface0, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          width: 1100,
          height: 1100,
          borderRadius: "50%",
          left: -380 + Math.sin(frame / 90) * 40,
          top: -520 + Math.cos(frame / 110) * 30,
          background: "radial-gradient(circle, rgba(255,98,102,.22), rgba(255,98,102,0) 65%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1300,
          height: 1300,
          borderRadius: "50%",
          right: -520 + Math.cos(frame / 100) * 50,
          bottom: -700 + Math.sin(frame / 120) * 40,
          background: "radial-gradient(circle, rgba(174,42,153,.18), rgba(174,42,153,0) 65%)",
        }}
      />
    </AbsoluteFill>
  );
};

/** Left-hand caption column used by every product scene. */
export const Caption: React.FC<{ step: string; title: React.ReactNode; sub: string; out?: number }> = ({
  step,
  title,
  sub,
  out,
}) => {
  const frame = useCurrentFrame();
  const fadeOut = out === undefined ? 1 : interpolate(frame, [out, out + 15], [1, 0], clamp);
  return (
    <div
      style={{
        position: "absolute",
        left: 110,
        top: 0,
        bottom: 0,
        width: 620,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        opacity: fadeOut,
        fontFamily,
      }}
    >
      <Interactive.Div
        name="Step"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 14,
          color: C.accent,
          fontSize: 26,
          fontWeight: 800,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          opacity: interpolate(frame, [4, 22], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translate: interpolate(frame, [4, 22], ["-30px 0px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: EASE_OUT,
          }),
        }}
      >
        <span
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            background: C.coral,
            boxShadow: "0 0 0 8px rgba(255,98,102,.18)",
          }}
        />
        {step}
      </Interactive.Div>
      <Interactive.Div
        name="Headline"
        style={{
          marginTop: 26,
          color: C.text,
          fontSize: 92,
          lineHeight: 1.02,
          fontWeight: 780,
          letterSpacing: "-0.055em",
          opacity: interpolate(frame, [10, 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translate: interpolate(frame, [10, 34], ["0px 40px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: EASE_OUT,
          }),
        }}
      >
        {title}
      </Interactive.Div>
      <Interactive.Div
        name="Subline"
        style={{
          marginTop: 30,
          color: C.text2,
          fontSize: 38,
          lineHeight: 1.4,
          fontWeight: 500,
          opacity: interpolate(frame, [22, 42], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          translate: interpolate(frame, [22, 46], ["0px 30px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: EASE_OUT,
          }),
        }}
      >
        {sub}
      </Interactive.Div>
    </div>
  );
};

export const Accent: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={{ background: GRADIENT, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
    {children}
  </span>
);

const TABS = ["Get help", "Agent queue", "Data curation", "Evaluation"];

/** Browser-like frame showing the Support Agent app chrome (brand bar + tabs). */
export const AppWindow: React.FC<{ tab: string; children: React.ReactNode; enter?: number }> = ({
  tab,
  children,
  enter = 0,
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: 790,
        top: 90,
        width: 1030,
        height: 900,
        borderRadius: 30,
        background: "rgba(255,255,255,.72)",
        border: `1.5px solid ${C.border}`,
        boxShadow: "0 40px 90px -40px rgba(79,16,75,.45), 0 8px 30px rgba(62,25,59,.06)",
        overflow: "hidden",
        fontFamily,
        color: C.text,
        opacity: interpolate(frame, [enter, enter + 18], [0, 1], clamp),
        translate: `0px ${interpolate(frame, [enter, enter + 26], [60, 0], { ...clamp, easing: EASE_OUT })}px`,
        scale: String(interpolate(frame, [enter, enter + 26], [0.96, 1], { ...clamp, easing: EASE_OUT })),
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "18px 24px", borderBottom: `1px solid ${C.border}` }}>
        {["#ff6266", "#f3afd6", "#d963ad"].map((c) => (
          <span key={c} style={{ width: 14, height: 14, borderRadius: "50%", background: c }} />
        ))}
        <div
          style={{
            marginLeft: 18,
            flex: 1,
            height: 34,
            borderRadius: 10,
            background: C.surface2,
            color: C.muted,
            fontSize: 17,
            display: "flex",
            alignItems: "center",
            paddingLeft: 16,
          }}
        >
          support.swissaiweeks.app
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "18px 30px 10px" }}>
        <Img src={staticFile("brand/ai-weeks-support-logo.png")} style={{ width: 52, height: 52, objectFit: "contain" }} />
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.05 }}>
          <span style={{ fontSize: 24, fontWeight: 780, letterSpacing: "-0.04em" }}>
            Swiss <b style={{ color: C.accent }}>{"{ai}"}</b> Weeks
          </span>
          <small style={{ marginTop: 4, color: C.muted, fontSize: 13, fontWeight: 750, letterSpacing: "0.17em", textTransform: "uppercase" }}>
            Support Agent
          </small>
        </div>
        <div style={{ flex: 1 }} />
        <div
          style={{
            display: "flex",
            gap: 4,
            padding: 6,
            border: `1px solid ${C.border}`,
            borderRadius: 14,
            background: "rgba(255,255,255,.9)",
          }}
        >
          {TABS.map((t) => (
            <span
              key={t}
              style={{
                padding: "8px 14px",
                borderRadius: 9,
                fontSize: 17,
                fontWeight: 650,
                background: t === tab ? C.accent : "transparent",
                color: t === tab ? "#fff" : C.text2,
                boxShadow: t === tab ? "0 4px 12px rgba(158,37,138,.22)" : "none",
              }}
            >
              {t}
            </span>
          ))}
        </div>
      </div>
      <div style={{ position: "relative", padding: "18px 30px", height: 760 }}>{children}</div>
    </div>
  );
};

export const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div
    style={{
      background: C.surface1,
      border: `1.5px solid ${C.border}`,
      borderRadius: 22,
      padding: "26px 30px",
      boxShadow: "0 10px 34px rgba(62,25,59,.06)",
      ...style,
    }}
  >
    {children}
  </div>
);

export const Eyebrow: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ fontSize: 16, textTransform: "uppercase", letterSpacing: "0.11em", color: C.accent, fontWeight: 760, ...style }}>
    {children}
  </div>
);

export const Pill: React.FC<{
  children: React.ReactNode;
  tone?: "default" | "good" | "warn" | "crit";
  style?: React.CSSProperties;
}> = ({ children, tone = "default", style }) => {
  const tones = {
    default: { background: C.surface2, color: "#7d2c70" },
    good: { background: C.goodBg, color: C.goodInk },
    warn: { background: C.warnBg, color: C.warnInk },
    crit: { background: C.critBg, color: C.critInk },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 17,
        padding: "5px 13px",
        borderRadius: 999,
        whiteSpace: "nowrap",
        fontWeight: 650,
        ...tones[tone],
        ...style,
      }}
    >
      {children}
    </span>
  );
};

export const PriorityPill: React.FC<{ level: Level; style?: React.CSSProperties }> = ({ level, style }) => (
  <Pill style={{ background: PRIORITY_STYLE[level].bg, color: PRIORITY_STYLE[level].fg, textTransform: "capitalize", ...style }}>
    {level}
  </Pill>
);

export const Button: React.FC<{
  children: React.ReactNode;
  primary?: boolean;
  pressed?: boolean;
  style?: React.CSSProperties;
}> = ({ children, primary, pressed, style }) => (
  <span
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      borderRadius: 13,
      padding: "14px 24px",
      fontSize: 20,
      fontWeight: 680,
      border: `1.5px solid ${primary ? C.accent : C.border}`,
      background: primary ? C.accent : C.surface1,
      color: primary ? "#fff" : C.text,
      boxShadow: primary ? "0 8px 18px rgba(158,37,138,.22)" : "none",
      scale: pressed ? "0.94" : "1",
      ...style,
    }}
  >
    {children}
  </span>
);

type CursorPoint = { f: number; x: number; y: number };

/** Animated mouse pointer that glides between keyframes and ripples on clicks. Coordinates are in the parent's space. */
export const Cursor: React.FC<{ points: CursorPoint[]; clicks?: number[]; hideAfter?: number }> = ({
  points,
  clicks = [],
  hideAfter,
}) => {
  const frame = useCurrentFrame();
  const frames = points.map((p) => p.f);
  const x = interpolate(frame, frames, points.map((p) => p.x), { ...clamp, easing: EASE_IN_OUT });
  const y = interpolate(frame, frames, points.map((p) => p.y), { ...clamp, easing: EASE_IN_OUT });
  const opacity =
    interpolate(frame, [points[0].f - 8, points[0].f], [0, 1], clamp) *
    (hideAfter === undefined ? 1 : interpolate(frame, [hideAfter, hideAfter + 10], [1, 0], clamp));
  const pressed = clicks.some((c) => frame >= c && frame < c + 6);
  return (
    <div style={{ position: "absolute", left: x, top: y, opacity, zIndex: 50, pointerEvents: "none" }}>
      {clicks.map((c) => {
        const p = interpolate(frame, [c, c + 18], [0, 1], clamp);
        if (frame < c || p >= 1) return null;
        return (
          <div
            key={c}
            style={{
              position: "absolute",
              left: -30,
              top: -30,
              width: 60,
              height: 60,
              borderRadius: "50%",
              border: `3px solid ${C.accent}`,
              opacity: 1 - p,
              scale: String(0.3 + p * 1.2),
            }}
          />
        );
      })}
      <svg width="42" height="42" viewBox="0 0 24 24" style={{ scale: pressed ? "0.85" : "1", filter: "drop-shadow(0 4px 8px rgba(44,23,50,.35))" }}>
        <path d="M4 2 L4 19 L8.5 14.8 L11.6 21.5 L14.4 20.2 L11.4 13.6 L17.5 13.6 Z" fill="#2c1732" stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </div>
  );
};

/** The gradient AI mark from the app's AnalysisProgress card. */
export const AiMark: React.FC<{ size?: number; spin?: boolean }> = ({ size = 66, spin }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "relative",
        display: "grid",
        placeItems: "center",
        width: size,
        height: size,
        borderRadius: "50%",
        background: GRADIENT,
        color: "#fff",
        fontSize: size * 0.46,
        fontWeight: 650,
        boxShadow: "0 12px 26px rgba(158,37,138,.25)",
      }}
    >
      {spin && (
        <div
          style={{
            position: "absolute",
            inset: -10,
            borderRadius: "50%",
            border: "3px solid transparent",
            borderTopColor: C.coral,
            borderRightColor: "rgba(174,42,153,.5)",
            rotate: `${frame * 8}deg`,
          }}
        />
      )}
      ✦
    </div>
  );
};
