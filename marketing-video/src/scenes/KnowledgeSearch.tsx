import { AbsoluteFill, interpolate, random, useCurrentFrame } from "remotion";
import { C, EASE_OUT } from "../theme";
import { Accent, AiMark, AppWindow, Backdrop, Caption, Card, Eyebrow, fadeUp, Pill, Sfx } from "../ui";

const STEPS = ["Read screenshots", "Prepare search", "Retrieve knowledge", "Check open tickets", "Analyse issue", "Validate routing"];
const STEP_START = 30;
const STEP_LEN = 28;

const COLS = 34;
const ROWS = 9;
const FIELD_W = 910;
const FIELD_H = 290;
const CX = FIELD_W / 2;
const CY = FIELD_H / 2;

// indices of the dots that turn out to be the best matches
const HITS = [3 * COLS + 22, 6 * COLS + 9, 1 * COLS + 13];

const MATCHES = [
  { title: "Orders blocked in pending approval after broker change", service: "Order Management", resolver: "a.keller", helpful: 14, score: 0.91 },
  { title: "OMS approval workflow not triggered for new counterparty", service: "Order Management", resolver: "m.dubois", helpful: 6, score: 0.87 },
  { title: "Broker account mapping missing after SimCorp migration", service: "SimCorp Dimension", resolver: "l.nielsen", helpful: 3, score: 0.79 },
];

const MATCH_START = 236;

export const KnowledgeSearch: React.FC = () => {
  const frame = useCurrentFrame();
  const count = Math.round(interpolate(frame, [24, 90], [0, 20000], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }));
  const ring = interpolate(frame, [70, 170], [0, 560], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const fieldOpacity = interpolate(frame, [212, 230], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const doneSteps = Math.max(0, Math.min(STEPS.length, Math.floor((frame - STEP_START) / STEP_LEN)));

  return (
    <AbsoluteFill>
      <Backdrop />
      <Caption
        step="02 · Get guidance"
        title={
          <>
            Searches every <Accent>solved ticket.</Accent>
          </>
        }
        sub="The assistant retrieves what actually worked before — from 20,000 past resolutions."
      />
      <AppWindow tab="Get help">
        {/* question bar */}
        <Card style={{ position: "absolute", left: 30, top: 18, width: 910, height: 104, padding: "18px 26px", display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <Eyebrow>Your question</Eyebrow>
            <div style={{ marginTop: 4, fontSize: 22, fontWeight: 560, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              Since we switched the broker account in OMS, all EU desk orders are stuck in “pending approval”…
            </div>
          </div>
          <div style={{ width: 54, height: 40, borderRadius: 8, background: "#1f2233", border: `1px solid ${C.border}` }} />
        </Card>

        {/* analysis progress */}
        <Card
          style={{
            position: "absolute",
            left: 30,
            top: 142,
            width: 910,
            height: 190,
            padding: "24px 28px",
            display: "flex",
            gap: 26,
            alignItems: "center",
            background: "linear-gradient(135deg, #fff, #fdf6fb)",
            borderColor: "#edcde4",
            ...fadeUp(frame, 8, 20),
          }}
        >
          <div style={{ display: "grid", placeItems: "center", width: 140, height: 140, borderRadius: 22, background: "radial-gradient(circle, #fff 28%, #fbeaf5 100%)", flex: "none" }}>
            <AiMark size={70} spin={doneSteps < STEPS.length} />
          </div>
          <div style={{ flex: 1 }}>
            <Eyebrow>{doneSteps < STEPS.length ? "Working on it" : "Done"}</Eyebrow>
            <div style={{ marginTop: 4, fontSize: 28, fontWeight: 740 }}>
              {doneSteps < STEPS.length ? "Analysing your issue" : "Found a likely fix"}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
              {STEPS.map((s, i) => {
                const done = i < doneSteps;
                const active = i === doneSteps && frame >= STEP_START;
                return (
                  <span
                    key={s}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "6px 12px",
                      borderRadius: 999,
                      fontSize: 16,
                      fontWeight: 650,
                      border: `1.5px solid ${done ? "#eed1e8" : active ? "#d96bb8" : C.border}`,
                      background: done ? "#fbeaf5" : active ? "#fff5fb" : "#fff",
                      color: done ? "#8d267d" : active ? C.accent : C.muted,
                      scale: active ? String(1 + 0.04 * Math.sin(frame / 3)) : "1",
                    }}
                  >
                    <i style={{ fontStyle: "normal" }}>{done ? "✓" : active ? "●" : "○"}</i>
                    {s}
                  </span>
                );
              })}
            </div>
          </div>
        </Card>

        {/* knowledge field */}
        <div style={{ position: "absolute", left: 30, top: 352, opacity: fieldOpacity }}>
        <Card style={{ width: 910, height: 380, padding: 0, overflow: "hidden", ...fadeUp(frame, 16, 20) }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "20px 28px 0" }}>
            <Eyebrow>Knowledge base</Eyebrow>
            <span style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
              <span style={{ color: C.accent }}>{count.toLocaleString("en-US")}</span> <span style={{ color: C.text2, fontWeight: 500 }}>resolved tickets</span>
            </span>
          </div>
          <div style={{ position: "relative", width: FIELD_W, height: FIELD_H, marginTop: 20 }}>
            {/* radar ring */}
            <div
              style={{
                position: "absolute",
                left: CX - ring,
                top: CY - ring,
                width: ring * 2,
                height: ring * 2,
                borderRadius: "50%",
                border: `2px solid rgba(217,99,173,${interpolate(ring, [0, 560], [0.7, 0])})`,
                background: `radial-gradient(circle, rgba(255,98,102,0) 60%, rgba(255,98,102,${interpolate(ring, [0, 560], [0.18, 0])}) 100%)`,
              }}
            />
            <svg width={FIELD_W} height={FIELD_H} style={{ position: "absolute", inset: 0 }}>
              {HITS.map((h, i) => {
                const x = 40 + (h % COLS) * ((FIELD_W - 80) / (COLS - 1));
                const y = 20 + Math.floor(h / COLS) * ((FIELD_H - 40) / (ROWS - 1));
                const p = interpolate(frame, [124 + i * 14, 150 + i * 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT });
                return <line key={h} x1={CX} y1={CY} x2={CX + (x - CX) * p} y2={CY + (y - CY) * p} stroke="#d963ad" strokeWidth={3} strokeLinecap="round" />;
              })}
            </svg>
            {Array.from({ length: COLS * ROWS }).map((_, i) => {
              const x = 40 + (i % COLS) * ((FIELD_W - 80) / (COLS - 1)) + (random(`x${i}`) - 0.5) * 10;
              const y = 20 + Math.floor(i / COLS) * ((FIELD_H - 40) / (ROWS - 1)) + (random(`y${i}`) - 0.5) * 10;
              const hit = HITS.indexOf(i);
              const appear = interpolate(frame, [20 + random(`a${i}`) * 50, 34 + random(`a${i}`) * 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
              const dist = Math.hypot(x - CX, y - CY);
              const pulse = Math.max(0, 1 - Math.abs(dist - ring) / 40);
              const lit = hit >= 0 ? interpolate(frame, [124 + hit * 14, 140 + hit * 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
              const size = 8 + pulse * 6 + lit * 16;
              return (
                <div
                  key={i}
                  style={{
                    position: "absolute",
                    left: x - size / 2,
                    top: y - size / 2,
                    width: size,
                    height: size,
                    borderRadius: "50%",
                    opacity: appear * (hit >= 0 ? 1 : 0.35 + pulse * 0.65 - (frame > 150 ? 0.15 : 0)),
                    background: lit > 0 ? "linear-gradient(135deg, #ff6266, #ae2a99)" : pulse > 0.2 ? "#d963ad" : "#e3c6dc",
                    boxShadow: lit > 0 ? `0 0 0 ${lit * 8}px rgba(255,98,102,.18)` : "none",
                  }}
                />
              );
            })}
            {/* query node */}
            <div style={{ position: "absolute", left: CX - 32, top: CY - 32, opacity: interpolate(frame, [56, 70], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
              <AiMark size={64} />
            </div>
          </div>
        </Card>
        </div>

        {/* matches */}
        <div style={{ position: "absolute", left: 30, top: 350, width: 910, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", ...fadeUp(frame, MATCH_START - 10, 16) }}>
            <span style={{ fontSize: 26, fontWeight: 760 }}>Knowledge used</span>
            <span style={{ color: C.muted, fontSize: 19 }}>3 strong matches · ranked by relevance & helpfulness</span>
          </div>
          {MATCHES.map((m, i) => {
            const s = MATCH_START + i * 18;
            return (
              <Card key={m.title} style={{ padding: "13px 22px", ...fadeUp(frame, s, 18, 40) }}>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                      <Pill>history</Pill>
                      <Pill>{m.service}</Pill>
                      <Pill>{m.resolver}</Pill>
                      <Pill tone="good">👍 {m.helpful}</Pill>
                      {i < 2 && <Pill tone="warn" style={{ ...fadeUp(frame, 312 + i * 8, 12, 10) }}>cited</Pill>}
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 600 }}>{m.title}</div>
                  </div>
                  <div style={{ width: 150, textAlign: "right" }}>
                    <div style={{ fontSize: 30, fontWeight: 760, color: C.accent, fontVariantNumeric: "tabular-nums" }}>
                      {interpolate(frame, [s + 4, s + 30], [0, m.score], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }).toFixed(2)}
                    </div>
                    <div style={{ height: 8, borderRadius: 999, background: C.surface2, overflow: "hidden", marginTop: 6 }}>
                      <div
                        style={{
                          height: "100%",
                          borderRadius: 999,
                          background: "linear-gradient(90deg, #9e258a, #d94eac)",
                          width: `${interpolate(frame, [s + 4, s + 30], [0, m.score * 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT })}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </AppWindow>

      <Sfx src="whoosh.wav" at={0} volume={0.4} />
      {STEPS.map((s, i) => (
        <Sfx key={s} src="tick_002.wav" at={STEP_START + (i + 1) * STEP_LEN} volume={0.5} />
      ))}
      <Sfx src="phaserUp3.wav" at={70} volume={0.25} />
      <Sfx src="glass_002.wav" at={126} volume={0.45} />
      <Sfx src="glass_002.wav" at={140} volume={0.4} />
      <Sfx src="glass_002.wav" at={154} volume={0.35} />
      {MATCHES.map((m, i) => (
        <Sfx key={m.title} src="select_003.wav" at={MATCH_START + i * 18} volume={0.45} />
      ))}
      <Sfx src="pluck_001.wav" at={312} volume={0.4} />
    </AbsoluteFill>
  );
};
