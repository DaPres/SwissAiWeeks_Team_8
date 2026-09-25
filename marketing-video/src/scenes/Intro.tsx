import { AbsoluteFill, Img, Interactive, interpolate, staticFile, useCurrentFrame } from "remotion";
import { EASE_OUT, fontFamily } from "../theme";
import { Sfx } from "../ui";

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const words = ["Help", "starts", "here"];

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
          scale: interpolate(frame, [0, 200], [1.14, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}
      />
      <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(48,12,54,.72), rgba(48,12,54,.1) 70%)" }} />

      <div style={{ position: "absolute", left: 150, top: 0, bottom: 0, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <Interactive.Div
          name="Brand"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 22,
            opacity: interpolate(frame, [8, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [8, 30], ["0px 30px", "0px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: EASE_OUT,
            }),
          }}
        >
          <Img src={staticFile("brand/ai-weeks-support-logo.png")} style={{ width: 110, height: 110, objectFit: "contain" }} />
          <div style={{ display: "flex", flexDirection: "column", color: "#fff", lineHeight: 1.05 }}>
            <span style={{ fontSize: 48, fontWeight: 780, letterSpacing: "-0.04em" }}>
              Swiss <b style={{ color: "#ff9a9e" }}>{"{ai}"}</b> Weeks
            </span>
            <small style={{ marginTop: 8, color: "#ffccd9", fontSize: 22, fontWeight: 750, letterSpacing: "0.2em", textTransform: "uppercase" }}>
              Support Agent
            </small>
          </div>
        </Interactive.Div>

        <div style={{ marginTop: 60, display: "flex", gap: 34, color: "#fff", fontSize: 168, fontWeight: 780, letterSpacing: "-0.065em", lineHeight: 1 }}>
          {words.map((w, i) => (
            <span
              key={w}
              style={{
                display: "inline-block",
                opacity: interpolate(frame, [32 + i * 7, 46 + i * 7], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                translate: `0px ${interpolate(frame, [32 + i * 7, 56 + i * 7], [80, 0], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                  easing: EASE_OUT,
                })}px`,
              }}
            >
              {w}
              {i === words.length - 1 && <span style={{ color: "#ff9a9e" }}>.</span>}
            </span>
          ))}
        </div>

        <Interactive.Div
          name="Tagline"
          style={{
            marginTop: 40,
            maxWidth: 900,
            color: "#f8e9f4",
            fontSize: 44,
            lineHeight: 1.4,
            fontWeight: 500,
            opacity: interpolate(frame, [62, 80], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [62, 86], ["0px 30px", "0px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: EASE_OUT,
            }),
          }}
        >
          AI support that learns from every ticket your team has ever solved.
        </Interactive.Div>

        <div style={{ marginTop: 56, display: "flex", alignItems: "center", gap: 22, color: "#ffdee9", fontSize: 26, fontWeight: 720, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          {["01   Describe", "02   Get guidance", "03   Resolve"].map((s, i) => (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 22 }}>
              {i > 0 && (
                <i
                  style={{
                    width: interpolate(frame, [96 + i * 10, 110 + i * 10], [0, 50], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                    height: 2,
                    background: "rgba(255,255,255,.55)",
                  }}
                />
              )}
              <span
                style={{
                  whiteSpace: "pre",
                  opacity: interpolate(frame, [96 + i * 10, 108 + i * 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                }}
              >
                {s}
              </span>
            </div>
          ))}
        </div>
      </div>

      <Sfx src="whoosh.wav" at={2} volume={0.5} />
      <Sfx src="pluck_001.wav" at={10} volume={0.6} />
      <Sfx src="glass_002.wav" at={34} volume={0.5} />
      <Sfx src="select_003.wav" at={98} volume={0.35} />
      <Sfx src="select_003.wav" at={108} volume={0.35} />
      <Sfx src="select_003.wav" at={118} volume={0.35} />
    </AbsoluteFill>
  );
};
