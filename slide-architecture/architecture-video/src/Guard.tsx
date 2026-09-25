import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { NODES } from "./layout";
import { C, clamp, EASE_IN_OUT, EASE_OUT, fontFamily, GRADIENT } from "./theme";
import { GUARD, s } from "./timing";

const e = NODES.engine;
const box = { left: e.cx - e.w / 2, top: e.cy - e.h / 2, width: e.w, height: e.h };
const WINDOWS = GUARD;

const SHIELD = "M12 2 L20 5 V11 C20 16.5 16.6 20.7 12 22 C7.4 20.7 4 16.5 4 11 V5 Z";

type Window = (typeof WINDOWS)[number];

const envelope = (frame: number, w: Window) =>
  interpolate(frame, [s(w.from), s(w.from) + 8, s(w.to) - 6, s(w.to) + 6], [0, 1, 1, 0], clamp);

/** Frame at which check `i` of a window turns green. */
const checkAt = (w: Window, i: number) =>
  s(w.from) + Math.round(((i + 1) * (s(w.to) - s(w.from) - 12)) / w.checks.length);

const Spinner: React.FC<{ frame: number }> = ({ frame }) => (
  <svg width={22} height={22} viewBox="0 0 22 22" style={{ rotate: `${frame * 14}deg` }}>
    <circle cx={11} cy={11} r={8} fill="none" stroke={C.border} strokeWidth={3} />
    <path d="M11 3 A8 8 0 0 1 19 11" fill="none" stroke={C.accent} strokeWidth={3} strokeLinecap="round" />
  </svg>
);

const Checklist: React.FC<{ w: Window }> = ({ w }) => {
  const frame = useCurrentFrame();
  const env = envelope(frame, w);
  if (env <= 0) return null;
  return (
    <div
      style={{
        position: "absolute",
        right: 960 - box.left + 6,
        top: box.top + box.height + 22,
        padding: "14px 18px",
        borderRadius: 18,
        background: C.surface1,
        border: `2px solid ${C.border}`,
        boxShadow: "0 16px 40px rgba(0,0,0,.14)",
        opacity: env,
        translate: `0px ${(1 - env) * 16}px`,
        fontFamily,
        display: "flex",
        flexDirection: "column",
        gap: 9,
      }}
    >
      {w.checks.map((label, i) => {
        const at = checkAt(w, i);
        const shown = interpolate(frame, [s(w.from) + i * 5, s(w.from) + i * 5 + 8], [0, 1], clamp);
        const ok = frame >= at;
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 10, opacity: shown, whiteSpace: "nowrap" }}>
            {ok ? (
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  background: C.goodBg,
                  color: C.good,
                  fontSize: 14,
                  fontWeight: 900,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  scale: String(interpolate(frame, [at, at + 8], [0.4, 1], { ...clamp, easing: EASE_OUT })),
                }}
              >
                ✓
              </span>
            ) : (
              <Spinner frame={frame} />
            )}
            <span style={{ fontSize: 19, fontWeight: 680, color: ok ? C.text : C.muted }}>{label}</span>
          </div>
        );
      })}
    </div>
  );
};

/** Security guard on the Neural Engine: force field, scan beam, shield badge and a live checklist. */
export const Guard: React.FC = () => {
  const frame = useCurrentFrame();
  const env = Math.max(...WINDOWS.map((w) => envelope(frame, w)));
  const active = WINDOWS.find((w) => frame >= s(w.from) - 2 && frame <= s(w.to) + 6);

  // Scan beam sweeps down and up while a window is active.
  const beamY = active
    ? interpolate(Math.sin(((frame - s(active.from)) / 22) * Math.PI - Math.PI / 2), [-1, 1], [0, box.height], { easing: EASE_IN_OUT })
    : 0;

  // Shockwave when a window starts.
  const wave = active ? interpolate(frame, [s(active.from), s(active.from) + 22], [0, 1], { ...clamp, easing: EASE_OUT }) : 1;

  // Shield badge appears with the first check and stays; it grows while guarding.
  const badgeIn = interpolate(frame, [s(GUARD[0].from), s(GUARD[0].from) + 12], [0, 1], { ...clamp, easing: EASE_OUT });
  const allClear = active ? frame >= checkAt(active, active.checks.length - 1) : true;
  const badgeSize = 50 + env * 18 + (active ? Math.sin(frame / 4) * 2 * env : 0);

  return (
    <>
      <svg width={960} height={1080} style={{ position: "absolute", inset: 0, overflow: "visible", pointerEvents: "none" }}>
        <defs>
          <linearGradient id="guardGrad" gradientUnits="userSpaceOnUse" x1={box.left} y1={box.top} x2={box.left + box.width} y2={box.top + box.height}>
            <stop offset="0%" stopColor="#00E5FF" />
            <stop offset="100%" stopColor="#C04DFF" />
          </linearGradient>
        </defs>
        {/* force field */}
        <rect
          x={box.left - 22}
          y={box.top - 22}
          width={box.width + 44}
          height={box.height + 44}
          rx={42}
          fill="rgba(192,77,255,.05)"
          stroke="url(#guardGrad)"
          strokeWidth={3}
          strokeDasharray="14 10"
          strokeDashoffset={-frame * 1.5}
          opacity={env}
        />
        {active && wave < 1 && (
          <rect
            x={box.left - 22 - wave * 40}
            y={box.top - 22 - wave * 40}
            width={box.width + 44 + wave * 80}
            height={box.height + 44 + wave * 80}
            rx={42 + wave * 30}
            fill="none"
            stroke="#00E5FF"
            strokeWidth={4 * (1 - wave)}
            opacity={1 - wave}
          />
        )}
      </svg>

      {/* scan beam, clipped to the engine card */}
      <div style={{ position: "absolute", ...box, borderRadius: 26, overflow: "hidden", opacity: env, pointerEvents: "none" }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: beamY - 40,
            height: 40,
            background: "linear-gradient(transparent, rgba(0,229,255,.22))",
          }}
        />
        <div style={{ position: "absolute", left: 0, right: 0, top: beamY - 2, height: 3, background: GRADIENT, boxShadow: "0 0 14px #00E5FF" }} />
      </div>

      {/* shield badge */}
      <div
        style={{
          position: "absolute",
          left: box.left - badgeSize / 2 + 4,
          top: box.top - badgeSize / 2 + 4,
          width: badgeSize,
          height: badgeSize,
          opacity: badgeIn,
          scale: String(0.4 + 0.6 * badgeIn),
          filter: `drop-shadow(0 8px 16px rgba(192,77,255,${0.25 + env * 0.35}))`,
        }}
      >
        <svg width="100%" height="100%" viewBox="0 0 24 24">
          <defs>
            <linearGradient id="shieldGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#00E5FF" />
              <stop offset="100%" stopColor="#C04DFF" />
            </linearGradient>
          </defs>
          <path d={SHIELD} fill="url(#shieldGrad)" stroke="#fff" strokeWidth={1.4} strokeLinejoin="round" />
          {allClear ? (
            <path d="M8.5 12 L11 14.5 L15.8 9.6" fill="none" stroke="#fff" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
          ) : (
            <g fill="#fff">
              <rect x={9} y={11} width={6} height={5} rx={1} />
              <path d="M10.2 11 V9.6 a1.8 1.8 0 0 1 3.6 0 V11" fill="none" stroke="#fff" strokeWidth={1.4} />
            </g>
          )}
        </svg>
      </div>

      {WINDOWS.map((w) => (
        <Checklist key={w.from} w={w} />
      ))}
    </>
  );
};
