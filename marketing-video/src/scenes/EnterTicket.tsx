import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, EASE_OUT } from "../theme";
import { Accent, AppWindow, Backdrop, Button, Caption, Caret, Cursor, Sfx, typed, TypingSfx } from "../ui";

const QUESTION =
  "Since we switched the broker account in OMS, all EU desk orders are stuck in “pending approval”. Traders can’t release anything.";

const TYPE_START = 40;
const TYPE_DUR = 130;
const DROP = 190;
const CLICK = 272;

/** Tiny mock of an OMS blotter used as the pasted screenshot. */
const OmsScreenshot: React.FC = () => (
  <div style={{ width: 170, height: 118, borderRadius: 10, overflow: "hidden", background: "#1f2233", padding: 8, display: "flex", flexDirection: "column", gap: 5 }}>
    <div style={{ height: 10, width: 70, borderRadius: 3, background: "#5b6180" }} />
    {[0, 1, 2, 3, 4].map((i) => (
      <div key={i} style={{ display: "flex", gap: 5, alignItems: "center" }}>
        <div style={{ height: 8, flex: 1, borderRadius: 2, background: "#3a3f58" }} />
        <div style={{ height: 11, width: 52, borderRadius: 3, background: i === 4 ? "#3a3f58" : "#f5a524", fontSize: 6, color: "#1f2233", fontWeight: 800, display: "grid", placeItems: "center" }}>
          {i === 4 ? "" : "PENDING"}
        </div>
      </div>
    ))}
  </div>
);

export const EnterTicket: React.FC = () => {
  const frame = useCurrentFrame();
  const text = typed(QUESTION, frame, TYPE_START, TYPE_DUR);
  const typing = frame >= TYPE_START && frame < TYPE_START + TYPE_DUR + 10;
  const dragging = frame > DROP - 22 && frame < DROP + 4;
  const clicked = frame >= CLICK;
  const shotProgress = interpolate(frame, [DROP - 24, DROP], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_OUT,
  });

  return (
    <AbsoluteFill>
      <Backdrop />
      <Caption
        step="01 · Describe"
        title={
          <>
            Just say what’s <Accent>wrong.</Accent>
          </>
        }
        sub="Plain words, screenshots welcome. No forms, no guessing which team to pick."
      />
      <AppWindow tab="Get help">
        {/* composer card */}
        <div
          style={{
            position: "absolute",
            left: 30,
            top: 18,
            width: 910,
            height: 700,
            background: C.surface1,
            border: `1.5px solid ${C.border}`,
            borderRadius: 22,
            boxShadow: "0 10px 34px rgba(62,25,59,.06)",
          }}
        >
          <div style={{ position: "absolute", left: 34, top: 30, right: 34, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 32, fontWeight: 760, letterSpacing: "-0.02em" }}>What’s going wrong?</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 10, color: C.text2, fontSize: 17, fontWeight: 700 }}>
              <span style={{ position: "relative", width: 40, height: 24, borderRadius: 999, background: "#d7c9d8" }}>
                <span style={{ position: "absolute", top: 4, left: 4, width: 16, height: 16, borderRadius: "50%", background: "#fff" }} />
              </span>
              Debug
            </span>
          </div>
          <div style={{ position: "absolute", left: 34, top: 82, right: 34, color: C.text2, fontSize: 20 }}>
            Describe the problem in your own words. Paste (⌘V) or drop screenshots — they’re read by the assistant too.
          </div>

          {/* dropbox */}
          <div
            style={{
              position: "absolute",
              left: 34,
              top: 150,
              width: 842,
              height: 520,
              borderRadius: 18,
              border: `2px ${dragging || typing ? "solid" : "dashed"} ${dragging || typing ? C.accent : "#dcb8d6"}`,
              background: dragging ? C.surface2 : "#fffafe",
              boxShadow: dragging ? "0 0 0 6px rgba(158,37,138,.1)" : "none",
            }}
          >
            <div style={{ position: "absolute", left: 24, top: 20, right: 24, fontSize: 28, lineHeight: 1.45, color: C.text }}>
              {text.length === 0 ? (
                <span style={{ color: C.muted }}>e.g. Orders stay in pending approval since we switched the broker account in OMS…</span>
              ) : (
                text
              )}
              {typing && <Caret />}
            </div>

            {/* screenshot flying in */}
            <div
              style={{
                position: "absolute",
                left: interpolate(shotProgress, [0, 1], [900, 24]),
                top: interpolate(shotProgress, [0, 1], [-160, 268]),
                rotate: `${interpolate(shotProgress, [0, 1], [18, 0])}deg`,
                scale: String(interpolate(shotProgress, [0, 1], [1.6, 1])),
                opacity: interpolate(frame, [DROP - 24, DROP - 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                border: `1.5px solid ${C.border}`,
                borderRadius: 12,
                boxShadow: shotProgress < 1 ? "0 24px 40px rgba(44,23,50,.3)" : "0 2px 6px rgba(44,23,50,.1)",
              }}
            >
              <OmsScreenshot />
            </div>

            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: 0,
                height: 88,
                borderTop: `1px solid ${C.grid}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 18px",
              }}
            >
              <span style={{ color: C.accent, fontSize: 20, fontWeight: 650 }}>
                📎 Add screenshot <span style={{ color: C.muted }}>({frame >= DROP ? 1 : 0}/4)</span>
              </span>
              <Button primary pressed={frame >= CLICK && frame < CLICK + 6} style={{ width: 230, justifyContent: "center" }}>
                {clicked ? "Analysing…" : "Get help"} <span style={{ fontSize: 16, opacity: 0.75 }}>⌘↵</span>
              </Button>
            </div>

            {/* shimmer once submitted */}
            {clicked && (
              <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 5, borderRadius: "18px 18px 0 0", overflow: "hidden" }}>
                <div
                  style={{
                    width: "40%",
                    height: "100%",
                    background: "linear-gradient(90deg, transparent, #ff6266, #ae2a99, transparent)",
                    translate: `${((frame - CLICK) * 22) % 1400 - 400}px 0px`,
                  }}
                />
              </div>
            )}
          </div>
        </div>

        <Cursor
          points={[
            { f: 226, x: 520, y: 520 },
            { f: 262, x: 772, y: 640 },
            { f: 300, x: 768, y: 646 },
          ]}
          clicks={[CLICK]}
        />
      </AppWindow>

      <Sfx src="whoosh.wav" at={0} volume={0.45} />
      <Sfx src="maximize_004.wav" at={6} volume={0.4} />
      <TypingSfx from={TYPE_START} to={TYPE_START + TYPE_DUR} />
      <Sfx src="whip.wav" at={DROP - 22} volume={0.25} />
      <Sfx src="drop_002.wav" at={DROP} volume={0.7} />
      <Sfx src="mouse-click.wav" at={CLICK} volume={0.7} />
      <Sfx src="glass_002.wav" at={CLICK + 8} volume={0.4} />
    </AbsoluteFill>
  );
};
