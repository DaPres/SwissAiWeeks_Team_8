import React from "react";
import { fontFamily } from "./theme";

/**
 * ai-support-agent-logo-compact.svg as JSX, so the text uses the loaded Inter font
 * and the bars / sparkle can be animated.
 */
export const TeamLogo: React.FC<{ width: number; bars?: [number, number, number]; sparkle?: number; idSuffix?: string }> = ({
  width,
  bars = [1, 1, 1],
  sparkle = 1,
  idSuffix = "",
}) => {
  const id = (name: string) => `${name}${idSuffix}`;
  const bar = (x: number, full: number, k: number, grad: string) => {
    const h = full * k;
    return <rect x={x} y={48 - h} width={6} height={h} rx={2} fill={`url(#${id(grad)})`} />;
  };
  return (
    <svg viewBox="0 0 340 64" width={width} height={(width * 64) / 340} role="img" aria-label="AI Support Agent, Team 8">
      <defs>
        <linearGradient id={id("nbrand")} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#00E5FF" />
          <stop offset="0.5" stopColor="#6C7BFF" />
          <stop offset="1" stopColor="#C04DFF" />
        </linearGradient>
        <linearGradient id={id("ntile")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1B2458" />
          <stop offset="1" stopColor="#0A0F2A" />
        </linearGradient>
        <linearGradient id={id("nlow")} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#FF5A7A" />
          <stop offset="1" stopColor="#FF9A6B" />
        </linearGradient>
        <linearGradient id={id("nmid")} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#FFB443" />
          <stop offset="1" stopColor="#FFE27A" />
        </linearGradient>
        <linearGradient id={id("nhigh")} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#00D69A" />
          <stop offset="1" stopColor="#7CFFD6" />
        </linearGradient>
        <linearGradient id={id("neight")} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7CF3FF" />
          <stop offset="1" stopColor="#C04DFF" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="16" fill={`url(#${id("ntile")})`} stroke={`url(#${id("nbrand")})`} strokeWidth="3" />
      {bar(11, 11, bars[0], "nlow")}
      {bar(19.5, 19, bars[1], "nmid")}
      {bar(28, 29, bars[2], "nhigh")}
      <text x="46.5" y="47.5" textAnchor="middle" fontFamily={fontFamily} fontSize="34" fontWeight="900" fill={`url(#${id("neight")})`}>
        8
      </text>
      <path
        d="M53,9 Q53.8,13.2 58,14 Q53.8,14.8 53,19 Q52.2,14.8 48,14 Q52.2,13.2 53,9 Z"
        fill="#FFFFFF"
        opacity={sparkle}
        transform={`rotate(${(1 - sparkle) * 45} 53 14)`}
      />
      <g fontFamily={fontFamily}>
        <text x="78" y="36" fontSize="26" fontWeight="800" fill="#FFFFFF" letterSpacing="-0.5">
          AI Support <tspan fill={`url(#${id("nbrand")})`}>Agent</tspan>
        </text>
        <text x="79" y="55" fontSize="11.5" fontWeight="700" fill="#8E9BD6" letterSpacing="2.4">
          TEAM 8 · SWISS AI WEEKS
        </text>
      </g>
    </svg>
  );
};

export const NAVY = "#0A0F2A";
export const NAVY_MUTED = "#8E9BD6";
export const BRAND_GRADIENT = "linear-gradient(90deg, #00E5FF, #6C7BFF, #C04DFF)";
