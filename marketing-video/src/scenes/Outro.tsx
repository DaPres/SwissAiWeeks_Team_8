import { AbsoluteFill, Img, Interactive, interpolate, staticFile, useCurrentFrame } from "remotion";
import { EASE_OUT, fontFamily } from "../theme";
import { Sfx } from "../ui";

const WORDS = ["Describe.", "Get guidance.", "Resolve."];

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ background: "#421449", fontFamily, overflow: "hidden" }}>
      <Img
        name="Hero background"
        src={staticFile("brand/ai-weeks-support-hero.webp")}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: interpolate(frame, [0, 250], [1, 1.12], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}
      />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 40% 50%, rgba(48,12,54,.35), rgba(48,12,54,.8))" }} />

      <AbsoluteFill style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#fff" }}>
        <Img
          src={staticFile("brand/ai-weeks-support-logo.png")}
          style={{
            width: 170,
            height: 170,
            objectFit: "contain",
            opacity: interpolate(frame, [6, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            scale: interpolate(frame, [6, 34], [0.4, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }),
          }}
        />

        <div style={{ marginTop: 40, display: "flex", gap: 36, fontSize: 118, fontWeight: 780, letterSpacing: "-0.06em", lineHeight: 1 }}>
          {WORDS.map((w, i) => (
            <span
              key={w}
              style={{
                display: "inline-block",
                color: i === WORDS.length - 1 ? "#ff9a9e" : "#fff",
                opacity: interpolate(frame, [30 + i * 14, 44 + i * 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                translate: `0px ${interpolate(frame, [30 + i * 14, 54 + i * 14], [70, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT })}px`,
              }}
            >
              {w}
            </span>
          ))}
        </div>

        <Interactive.Div
          name="Loop line"
          style={{
            marginTop: 40,
            color: "#f8e9f4",
            fontSize: 46,
            fontWeight: 500,
            opacity: interpolate(frame, [90, 108], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [90, 112], ["0px 24px", "0px 0px"], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }),
          }}
        >
          …and every answer makes the next one better.
        </Interactive.Div>

        <Interactive.Div
          name="Footer"
          style={{
            marginTop: 90,
            display: "flex",
            alignItems: "center",
            gap: 18,
            padding: "16px 30px",
            borderRadius: 999,
            border: "1.5px solid rgba(255,255,255,.3)",
            background: "rgba(255,255,255,.08)",
            color: "#ffdee9",
            fontSize: 28,
            fontWeight: 700,
            letterSpacing: "0.04em",
            opacity: interpolate(frame, [124, 142], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}
        >
          <span>
            Swiss <b style={{ color: "#ff9a9e" }}>{"{ai}"}</b> Weeks · Support Agent
          </span>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#ff7279" }} />
          <span>Team 8 · SwissLife 2026</span>
        </Interactive.Div>
      </AbsoluteFill>

      <AbsoluteFill style={{ background: "#000", opacity: interpolate(frame, [225, 250], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }} />

      <Sfx src="whoosh.wav" at={0} volume={0.45} />
      <Sfx src="pluck_001.wav" at={8} volume={0.5} />
      <Sfx src="select_003.wav" at={30} volume={0.45} />
      <Sfx src="select_003.wav" at={44} volume={0.45} />
      <Sfx src="select_003.wav" at={58} volume={0.45} />
      <Sfx src="glass_002.wav" at={92} volume={0.4} />
      <Sfx src="ding.wav" at={126} volume={0.3} />
    </AbsoluteFill>
  );
};
