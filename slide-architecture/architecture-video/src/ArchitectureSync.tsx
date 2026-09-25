import React from "react";
import { Video } from "@remotion/media";
import { AbsoluteFill, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { EndScreen } from "./EndScreen";
import { Evaluation } from "./Evaluation";
import { Guard } from "./Guard";
import { Header } from "./Header";
import { PANEL } from "./layout";
import { Nodes } from "./Nodes";
import { Preparation } from "./Preparation";
import { DarkBackdrop, StartScreen } from "./StartScreen";
import { C, clamp, EASE_OUT, fontFamily, GRADIENT } from "./theme";
import { DEMO, DURATION, EVAL_DURATION, INTRO, PREP_DURATION, s, THANKS, THANKS_START } from "./timing";
import { Wires } from "./Wires";

export type ArchitectureSyncProps = {
  /** File in public/. Empty = placeholder frame. */
  demoSrc: string;
};

const Backdrop = DarkBackdrop;

/** Left half: browser frame holding the product demo recording, framed in the brand gradient. */
const DemoPanel: React.FC<{ demoSrc: string }> = ({ demoSrc }) => {
  const frame = useCurrentFrame();
  const width = 800;
  const k = width / DEMO.crop.width; // recording px → frame px
  const height = Math.round(DEMO.crop.height * k);
  const chrome = 46;
  const top = (1080 - height - chrome) / 2 + 20;
  const appear = interpolate(frame, [0, 20], [0, 1], { ...clamp, easing: EASE_OUT });

  return (
    <div style={{ position: "absolute", left: 58, top, width, fontFamily, opacity: appear, translate: `${(1 - appear) * -40}px 0px` }}>
      <div
        style={{
          position: "absolute",
          top: -46,
          left: 4,
          display: "flex",
          alignItems: "center",
          gap: 10,
          color: C.accent,
          fontSize: 20,
          fontWeight: 800,
          letterSpacing: "0.18em",
        }}
      >
        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#FF5A7A", opacity: 0.55 + 0.45 * Math.abs(Math.sin(frame / 12)) }} />
        LIVE DEMO
      </div>
      {/* gradient rim + glow */}
      <div style={{ position: "absolute", inset: -2, borderRadius: 26, background: GRADIENT, opacity: 0.7 }} />
      <div
        style={{
          position: "relative",
          borderRadius: 24,
          overflow: "hidden",
          background: C.surface1,
          boxShadow: "0 40px 100px -30px rgba(108,123,255,.55), 0 0 80px rgba(0,229,255,.12)",
        }}
      >
        <div style={{ height: chrome, display: "flex", alignItems: "center", gap: 9, padding: "0 18px", background: C.surface1 }}>
          {["#FF5A7A", "#FFB443", "#00D69A"].map((c) => (
            <span key={c} style={{ width: 12, height: 12, borderRadius: "50%", background: c }} />
          ))}
          <div
            style={{
              marginLeft: 12,
              flex: 1,
              height: 28,
              borderRadius: 8,
              background: C.surface2,
              color: C.muted,
              fontSize: 15,
              display: "flex",
              alignItems: "center",
              paddingLeft: 14,
            }}
          >
            support.swissaiweeks.app
          </div>
        </div>
        <div style={{ position: "relative", width, height, background: "#f6f5f4" }}>
          {demoSrc ? (
            <>
              {/* the recording has black side bars: show only the app, cropped via an oversized, shifted video */}
              <Video
                src={staticFile(demoSrc)}
                muted
                objectFit="fill"
                trimAfter={s(DEMO.playUntil)}
                style={{ position: "absolute", left: -DEMO.crop.x * k, top: 0, width: DEMO.sourceWidth * k, height }}
              />
            </>
          ) : (
            <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", color: C.muted, fontSize: 32, fontWeight: 700 }}>Product demo</AbsoluteFill>
          )}
        </div>
      </div>
      {DEMO.callouts.map((c) => (
        <Callout key={c.text} from={c.from} to={c.to} text={c.text} />
      ))}
    </div>
  );
};

/** Pill over the bottom of the recording that says what just happened in the demo. */
const Callout: React.FC<{ from: number; to: number; text: string }> = ({ from, to, text }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [s(from), s(from) + 12, s(to) - 10, s(to)], [0, 1, 1, 0], clamp);
  if (p <= 0) return null;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 36, display: "flex", justifyContent: "center", opacity: p, translate: `0px ${(1 - p) * 16}px` }}>
      <div
        style={{
          padding: "10px 22px",
          borderRadius: 999,
          background: "rgba(10,15,42,.9)",
          border: `2px solid ${C.good}`,
          boxShadow: "0 16px 40px rgba(0,0,0,.35)",
          color: C.good,
          fontSize: 24,
          fontWeight: 750,
          whiteSpace: "nowrap",
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const ArchitectureSync: React.FC<ArchitectureSyncProps> = ({ demoSrc }) => {
  return (
    <AbsoluteFill>
      <Backdrop />
      <Sequence name="Preparation" from={s(INTRO.hold)} durationInFrames={s(PREP_DURATION)}>
        <Preparation />
      </Sequence>
      {/* Architecture timings in timing.ts are relative to this start, i.e. to the product demo. */}
      <Sequence name="Architecture" from={s(INTRO.hold + PREP_DURATION)} durationInFrames={s(DURATION)}>
        <SceneFade duration={DURATION}>
          <ArchitectureWithDemo demoSrc={demoSrc} />
        </SceneFade>
      </Sequence>
      <Sequence name="Evaluation" from={s(INTRO.hold + PREP_DURATION + DURATION)} durationInFrames={s(EVAL_DURATION)}>
        <SceneFade duration={EVAL_DURATION} fadeOut={false}>
          <Evaluation />
        </SceneFade>
      </Sequence>
      {/* Start screen sits on top and opens into the preparation scene. */}
      <Sequence name="Start" durationInFrames={s(INTRO.hold + INTRO.reveal)}>
        <StartScreen />
      </Sequence>
      {/* Thank-you screen closes over the last seconds of the evaluation. */}
      <Sequence name="Thanks" from={s(THANKS_START)} durationInFrames={s(THANKS.duration)}>
        <EndScreen />
      </Sequence>
    </AbsoluteFill>
  );
};

/** Fades a scene in and (optionally) out over 12 frames. */
const SceneFade: React.FC<{ duration: number; fadeOut?: boolean; children: React.ReactNode }> = ({ duration, fadeOut = true, children }) => {
  const frame = useCurrentFrame();
  const out = fadeOut ? interpolate(frame, [s(duration) - 12, s(duration)], [1, 0], clamp) : 1;
  return <AbsoluteFill style={{ opacity: out }}>{children}</AbsoluteFill>;
};

const ArchitectureWithDemo: React.FC<ArchitectureSyncProps> = ({ demoSrc }) => {
  return (
    <AbsoluteFill>
      <DemoPanel demoSrc={demoSrc} />
      <div
        style={{
          position: "absolute",
          left: 958,
          top: 120,
          bottom: 120,
          width: 2,
          background: `linear-gradient(transparent, ${C.border}, transparent)`,
        }}
      />
      <ArchitectureDiagram />
    </AbsoluteFill>
  );
};

/** Right half: the animated architecture. Also usable standalone (960×1080). */
export const ArchitectureDiagram: React.FC<{ left?: number }> = ({ left = 960 }) => (
  <div style={{ position: "absolute", left, top: 0, width: PANEL.width, height: PANEL.height }}>
    <Header />
    <Wires />
    <Nodes />
    <Guard />
  </div>
);

export const EvaluationOnly: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <Evaluation />
  </AbsoluteFill>
);

export const StartOnly: React.FC = () => <StartScreen />;
export const ThanksOnly: React.FC = () => <EndScreen />;

export const PreparationOnly: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <Preparation />
  </AbsoluteFill>
);

export const ArchitectureOnly: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <ArchitectureDiagram left={0} />
  </AbsoluteFill>
);
