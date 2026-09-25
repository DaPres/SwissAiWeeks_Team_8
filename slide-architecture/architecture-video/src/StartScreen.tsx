import React from "react";
import { AbsoluteFill, Interactive, interpolate, useCurrentFrame } from "remotion";
import { BRAND_GRADIENT, NAVY, NAVY_MUTED, TeamLogo } from "./TeamLogo";
import { clamp, EASE_IN_OUT, fontFamily } from "./theme";
import { INTRO, s } from "./timing";

/** Dark navy stage with drifting cyan/violet glows and a faint dot grid. Complete on frame 0. */
export const DarkBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: NAVY, overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          backgroundImage: "radial-gradient(rgba(142,155,214,.16) 1.5px, transparent 1.5px)",
          backgroundSize: "44px 44px",
          backgroundPosition: `${frame * 0.3}px ${frame * 0.15}px`,
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1200,
          height: 1200,
          borderRadius: "50%",
          left: -420 + Math.sin(frame / 80) * 60,
          top: -560 + Math.cos(frame / 95) * 40,
          background: "radial-gradient(circle, rgba(0,229,255,.22), rgba(0,229,255,0) 62%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 1400,
          height: 1400,
          borderRadius: "50%",
          right: -560 + Math.cos(frame / 90) * 60,
          bottom: -760 + Math.sin(frame / 105) * 50,
          background: "radial-gradient(circle, rgba(192,77,255,.26), rgba(192,77,255,0) 62%)",
        }}
      />
    </AbsoluteFill>
  );
};

/** Bars of the logo breathing like a tiny equaliser. */
export const logoBars = (frame: number): [number, number, number] => [
  0.75 + 0.25 * Math.sin(frame / 7),
  0.8 + 0.2 * Math.sin(frame / 7 + 1.4),
  0.85 + 0.15 * Math.sin(frame / 7 + 2.8),
];

const CENTER = { x: 960, y: 470 };

export const StartScreen: React.FC = () => {
  const frame = useCurrentFrame();
  const [r0, r1] = [s(INTRO.hold), s(INTRO.hold + INTRO.reveal)];
  const reveal = interpolate(frame, [r0, r1], [0, 1], { ...clamp, easing: EASE_IN_OUT });
  const radius = reveal * 1500;
  const zoom = 1 + reveal * 0.35;
  const sparkle = 0.55 + 0.45 * Math.abs(Math.sin(frame / 18));
  const mask = radius > 0 ? `radial-gradient(circle at ${CENTER.x}px ${CENTER.y}px, transparent ${radius}px, black ${radius + 2}px)` : undefined;

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ WebkitMaskImage: mask, maskImage: mask }}>
        <DarkBackdrop />
        <AbsoluteFill style={{ alignItems: "center", fontFamily, scale: String(zoom), transformOrigin: `${CENTER.x}px ${CENTER.y}px` }}>
          <Interactive.Div
            name="StartEyebrow"
            style={{ position: "absolute", top: 250, color: NAVY_MUTED, fontSize: 28, fontWeight: 800, letterSpacing: "0.3em", textTransform: "uppercase" }}
          >
            Swiss AI Weeks · Hackathon Pitch
          </Interactive.Div>
          <div style={{ position: "absolute", top: CENTER.y - 113, filter: "drop-shadow(0 30px 80px rgba(108,123,255,.35))" }}>
            <TeamLogo width={1200} bars={logoBars(frame)} sparkle={sparkle} idSuffix="start" />
          </div>
          <div style={{ position: "absolute", top: 660, width: 360, height: 4, borderRadius: 2, background: BRAND_GRADIENT }} />
          <Interactive.Div
            name="StartTagline"
            style={{ position: "absolute", top: 700, color: "#fff", fontSize: 48, fontWeight: 700, letterSpacing: "-0.02em", textAlign: "center" }}
          >
            AI-powered ticket triage
          </Interactive.Div>
          <Interactive.Div name="StartSub" style={{ position: "absolute", top: 770, color: NAVY_MUTED, fontSize: 32, fontWeight: 500, textAlign: "center" }}>
            From 20&apos;000 incidents to grounded answers in seconds
          </Interactive.Div>
        </AbsoluteFill>
      </AbsoluteFill>
      {/* glowing edge of the reveal */}
      {reveal > 0 && reveal < 1 && (
        <div
          style={{
            position: "absolute",
            left: CENTER.x - radius,
            top: CENTER.y - radius,
            width: radius * 2,
            height: radius * 2,
            borderRadius: "50%",
            border: "4px solid rgba(124,243,255,.9)",
            boxShadow: "0 0 40px rgba(0,229,255,.7), inset 0 0 40px rgba(192,77,255,.5)",
            opacity: 1 - reveal * 0.6,
          }}
        />
      )}
    </AbsoluteFill>
  );
};
