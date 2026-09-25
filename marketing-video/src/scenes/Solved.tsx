import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, EASE_IN_OUT, EASE_OUT } from "../theme";
import { Accent, AppWindow, Backdrop, Caption, Card, Cursor, Eyebrow, fadeUp, Pill, popIn, Sfx } from "../ui";
import { SelfServiceCard, SOLVED_BTN, UnderstoodCard } from "./Proposal";

const CLICK = 18;
const VOTE = 120;
const SWAP = 150;
const ROW = 104;

const ROWS = [
  { key: "A", title: "Restart the OMS approval service", helpful: 11, score: 0.88, from: 0, to: 1 },
  { key: "C", title: "Clear OMS client cache and log in again", helpful: 7, score: 0.74, from: 1, to: 2 },
  { key: "B", title: "Link broker account to the desk approval group", helpful: 14, score: 0.72, from: 2, to: 0, ours: true },
  { key: "D", title: "Escalate to Trading Support", helpful: 4, score: 0.61, from: 3, to: 3 },
];

export const Solved: React.FC = () => {
  const frame = useCurrentFrame();
  const cardOut = interpolate(frame, [30, 48], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <Backdrop />
      <Caption
        step="03 · Resolve"
        title={
          <>
            Solved? It <Accent>learns.</Accent>
          </>
        }
        sub="One click confirms the fix — and ranks it higher for the next person with the same problem."
      />
      <AppWindow tab="Get help">
        <UnderstoodCard />
        <div style={{ opacity: cardOut, scale: String(interpolate(frame, [30, 48], [1, 0.96], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) }}>
          <SelfServiceCard pressed={frame >= CLICK && frame < CLICK + 6 ? "solved" : undefined} />
        </div>

        {/* success */}
        <Card
          style={{
            position: "absolute",
            left: 30,
            top: 190,
            width: 910,
            height: 130,
            background: C.goodBg,
            borderColor: C.goodInk,
            ...popIn(frame, 40, 20),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div style={{ width: 56, height: 56, borderRadius: "50%", background: C.goodInk, color: "#fff", display: "grid", placeItems: "center", fontSize: 30, fontWeight: 800 }}>✓</div>
            <div>
              <div style={{ fontSize: 28, fontWeight: 760, color: C.goodInk }}>Great — no ticket needed</div>
              <div style={{ fontSize: 20, color: C.text2, marginTop: 4 }}>Thanks for confirming. This answer will be ranked higher for the next person.</div>
            </div>
          </div>
        </Card>

        {/* ranking */}
        <Card style={{ position: "absolute", left: 30, top: 340, width: 910, height: 400, padding: "22px 28px", ...fadeUp(frame, 70, 20, 40) }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <Eyebrow>Knowledge ranking</Eyebrow>
            <span style={{ color: C.muted, fontSize: 18 }}>for “orders stuck in pending approval”</span>
          </div>
          <div style={{ position: "relative", marginTop: 14, height: 4 * ROW }}>
            {ROWS.map((r) => {
              const y = interpolate(frame, [SWAP, SWAP + 26], [r.from * (ROW - 22), r.to * (ROW - 22)], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: EASE_IN_OUT,
              });
              const score = r.ours ? interpolate(frame, [VOTE, VOTE + 24], [r.score, 0.95], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }) : r.score;
              const helpful = r.ours && frame >= VOTE + 6 ? r.helpful + 1 : r.helpful;
              const rank = (frame >= SWAP + 13 ? r.to : r.from) + 1;
              const glow = r.ours ? interpolate(frame, [VOTE - 6, VOTE + 6, SWAP + 60, SWAP + 90], [0, 1, 1, 0.5], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
              return (
                <div
                  key={r.key}
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    top: y,
                    height: ROW - 32,
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    padding: "0 16px",
                    borderRadius: 14,
                    border: `1.5px solid ${glow > 0 ? `rgba(158,37,138,${glow})` : C.grid}`,
                    background: glow > 0 ? `rgba(251,234,245,${glow})` : "#fff",
                    boxShadow: glow > 0 ? `0 10px 24px rgba(158,37,138,${0.18 * glow})` : "none",
                    zIndex: r.ours ? 2 : 1,
                    scale: r.ours ? String(interpolate(frame, [SWAP, SWAP + 13, SWAP + 26], [1, 1.04, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) : "1",
                  }}
                >
                  <span
                    style={{
                      width: 42,
                      height: 42,
                      borderRadius: 12,
                      display: "grid",
                      placeItems: "center",
                      fontWeight: 780,
                      fontSize: 20,
                      background: rank === 1 ? "linear-gradient(135deg, #ff6266, #ae2a99)" : C.surface2,
                      color: rank === 1 ? "#fff" : C.accent,
                    }}
                  >
                    #{rank}
                  </span>
                  <span style={{ flex: 1, fontSize: 21, fontWeight: 600 }}>{r.title}</span>
                  <span style={{ position: "relative" }}>
                    <Pill tone="good">👍 {helpful}</Pill>
                    {r.ours && (
                      <span
                        style={{
                          position: "absolute",
                          right: 0,
                          top: interpolate(frame, [VOTE, VOTE + 30], [0, -46], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }),
                          opacity: interpolate(frame, [VOTE, VOTE + 6, VOTE + 24, VOTE + 34], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
                          color: C.goodInk,
                          fontWeight: 800,
                          fontSize: 22,
                        }}
                      >
                        +1
                      </span>
                    )}
                  </span>
                  <span style={{ width: 150, display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ flex: 1, height: 8, borderRadius: 999, background: C.surface2, overflow: "hidden" }}>
                      <span style={{ display: "block", height: "100%", width: `${score * 100}%`, borderRadius: 999, background: "linear-gradient(90deg, #9e258a, #d94eac)" }} />
                    </span>
                    <span style={{ fontSize: 18, fontWeight: 700, color: C.accent, fontVariantNumeric: "tabular-nums" }}>{score.toFixed(2)}</span>
                  </span>
                </div>
              );
            })}
          </div>
        </Card>

        <Cursor
          points={[
            { f: 0, x: 380, y: 610 },
            { f: CLICK - 2, x: SOLVED_BTN.x, y: SOLVED_BTN.y },
            { f: 40, x: SOLVED_BTN.x + 10, y: SOLVED_BTN.y + 10 },
          ]}
          clicks={[CLICK]}
          hideAfter={44}
        />
      </AppWindow>

      <Sfx src="mouse-click.wav" at={CLICK} volume={0.7} />
      <Sfx src="confirmation_002.wav" at={42} volume={0.6} />
      <Sfx src="open_002.wav" at={72} volume={0.35} />
      <Sfx src="pluck_001.wav" at={VOTE} volume={0.55} />
      <Sfx src="whip.wav" at={SWAP} volume={0.25} />
      <Sfx src="powerUp4.wav" at={SWAP + 8} volume={0.45} />
    </AbsoluteFill>
  );
};
