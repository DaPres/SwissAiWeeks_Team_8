import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { pointAt, Pt, roundedPath, WireId, WIRES } from "./layout";
import { C, clamp, EASE_IN_OUT, EASE_OUT } from "./theme";
import { BUILD, HOPS, OUTRO_FROM, s } from "./timing";

const WIRE_ORDER: WireId[] = ["frontend", "engine", "jev", "rag", "apertus"];

/** Arrowhead at `at`, pointing away from `prev`. */
const Arrow: React.FC<{ at: Pt; prev: Pt; color: string; opacity: number }> = ({ at, prev, color, opacity }) => {
  const angle = (Math.atan2(at[1] - prev[1], at[0] - prev[0]) * 180) / Math.PI;
  return (
    <polygon
      points={`${at[0]},${at[1]} ${at[0] - 16},${at[1] - 9} ${at[0] - 16},${at[1] + 9}`}
      transform={`rotate(${angle} ${at[0]} ${at[1]})`}
      fill={color}
      opacity={opacity}
    />
  );
};

/** Grey wires that draw in during the build, plus the lit overlays and packets of every hop. */
export const Wires: React.FC = () => {
  const frame = useCurrentFrame();
  const outro = interpolate(frame, [s(OUTRO_FROM), s(OUTRO_FROM + 1)], [0, 1], clamp);

  return (
    <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, overflow: "visible" }}>
      <defs>
        {/* userSpaceOnUse: a straight wire has a zero-height bbox, which would hide an objectBoundingBox gradient */}
        <linearGradient id="wireGrad" gradientUnits="userSpaceOnUse" x1={200} y1={300} x2={800} y2={900}>
          <stop offset="0%" stopColor="#00E5FF" />
          <stop offset="100%" stopColor="#C04DFF" />
        </linearGradient>
        <radialGradient id="packetGlow">
          <stop offset="0%" stopColor="#00E5FF" stopOpacity={0.55} />
          <stop offset="100%" stopColor="#C04DFF" stopOpacity={0} />
        </radialGradient>
      </defs>

      {WIRE_ORDER.map((id, i) => {
        const pts = WIRES[id];
        const start = s(BUILD.wiresFrom + i * 0.1);
        const drawn = interpolate(frame, [start, start + s(BUILD.wireDur)], [0, 1], { ...clamp, easing: EASE_IN_OUT });
        const d = roundedPath(pts);
        return (
          <g key={id}>
            <path d={d} pathLength={1} fill="none" stroke={C.wire} strokeWidth={5} strokeLinecap="round" strokeDasharray="1 1" strokeDashoffset={1 - drawn} />
            {/* Outro: everything flows at once */}
            <path
              d={d}
              pathLength={1}
              fill="none"
              stroke="url(#wireGrad)"
              strokeWidth={5}
              strokeLinecap="round"
              strokeDasharray="0.04 0.05"
              strokeDashoffset={-frame / 90}
              opacity={outro}
            />
            <Arrow at={pts[pts.length - 1]} prev={pts[pts.length - 2]} color={outro > 0.5 ? "#C04DFF" : C.wire} opacity={drawn >= 0.98 ? 1 : 0} />
          </g>
        );
      })}

      {HOPS.map((hop, i) => {
        const pts = hop.back ? [...WIRES[hop.wire]].reverse() : WIRES[hop.wire];
        const [from, to] = [s(hop.from), s(hop.to)];
        if (frame < from || frame > to + 30) return null;
        const t = interpolate(frame, [from, to], [0, 1], { ...clamp, easing: EASE_IN_OUT });
        const fade = interpolate(frame, [to, to + 30], [1, 0], clamp);
        const [x, y] = pointAt(pts, t);
        const packetOpacity = interpolate(frame, [from, from + 5, to - 3, to + 4], [0, 1, 1, 0], clamp);
        return (
          <g key={i}>
            <path
              d={roundedPath(pts)}
              pathLength={1}
              fill="none"
              stroke="url(#wireGrad)"
              strokeWidth={7}
              strokeLinecap="round"
              strokeDasharray={`${t} 1`}
              opacity={fade}
            />
            {[5, 4, 3, 2, 1].map((k) => {
              const [tx, ty] = pointAt(pts, t - k * 0.018);
              return <circle key={k} cx={tx} cy={ty} r={9 - k} fill="#00E5FF" opacity={packetOpacity * (0.5 - k * 0.08)} />;
            })}
            <circle cx={x} cy={y} r={30} fill="url(#packetGlow)" opacity={packetOpacity} />
            <circle
              cx={x}
              cy={y}
              r={interpolate(frame, [from, from + 8], [0, 11], { ...clamp, easing: EASE_OUT })}
              fill="#fff"
              stroke="url(#wireGrad)"
              strokeWidth={5}
              opacity={packetOpacity}
            />
          </g>
        );
      })}
    </svg>
  );
};
