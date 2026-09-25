import React from "react";
import { AbsoluteFill, Img, Interactive, interpolate, random, staticFile, useCurrentFrame } from "remotion";
import { NODES, PANEL } from "./layout";
import { Node } from "./Nodes";
import { C, clamp, EASE_IN_OUT, EASE_OUT, fontFamily, GRADIENT } from "./theme";
import { CURATION, PREP, s } from "./timing";

/** Dataset → quality checks → clustering → Knowledge. Full 1920×1080 frame, before the architecture. */

type Level = "gold" | "silver" | "bronze" | "reject";

const LEVEL_COLOR: Record<Level, string> = {
  gold: "#e0a526",
  silver: "#9aa3b2",
  bronze: "#c07a45",
  reject: "#2E3870",
};
const LEVEL_LABEL: Record<Level, string> = { gold: "Gold", silver: "Silver", bronze: "Bronze", reject: "Reject" };
const LEVELS: Level[] = ["gold", "silver", "bronze", "reject"];

// Each dot stands for 25 tickets.
const COLS = 40;
const ROWS = 20;
const SP = 22;
const GX = 130;
const GY = 380;
const N = COLS * ROWS;

const CLUSTERS = [
  { name: "Trading Platform", x: 250, y: 480 },
  { name: "NAV Calculation", x: 580, y: 480 },
  { name: "Settlement", x: 910, y: 480 },
  { name: "Client Reporting", x: 250, y: 740 },
  { name: "Identity & Access", x: 580, y: 740 },
  { name: "Cash Management", x: 910, y: 740 },
];

/** Jira export card the tickets pour out of. */
const SOURCE = { x: 1480, y: 590 };

const KNOWLEDGE: [number, number] = [PANEL.width + NODES.rag.cx, NODES.rag.cy];

const total = CURATION.tickets;
const cumulative = LEVELS.reduce<number[]>((acc, l) => [...acc, (acc[acc.length - 1] ?? 0) + CURATION.levels[l] / total], []);

const DOTS = Array.from({ length: N }, (_, i) => {
  const r = random(`level-${i}`);
  const level = LEVELS[cumulative.findIndex((c) => r <= c)] ?? "reject";
  const cluster = CLUSTERS[Math.floor(random(`cluster-${i}`) * CLUSTERS.length)];
  const angle = random(`angle-${i}`) * Math.PI * 2;
  const radius = Math.sqrt(random(`radius-${i}`)) * 80;
  return {
    level,
    gx: GX + (i % COLS) * SP,
    gy: GY + Math.floor(i / COLS) * SP,
    cx: cluster.x + Math.cos(angle) * radius,
    cy: cluster.y + Math.sin(angle) * radius * 0.75,
    delay: random(`delay-${i}`),
  };
});

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const fmt = (n: number) => Math.round(n).toLocaleString("de-CH");

const Dots: React.FC = () => {
  const frame = useCurrentFrame();
  const scanX = interpolate(frame, [s(PREP.scan[0]), s(PREP.scan[1])], [GX - 30, GX + COLS * SP + 30], { ...clamp, easing: EASE_IN_OUT });

  return (
    <>
      {DOTS.map((d, i) => {
        // Emitted from the Jira card, flying into the grid.
        const e0 = s(PREP.emit[0]) + d.delay * s(PREP.emit[1] - PREP.emit[0] - 0.55);
        const emit = interpolate(frame, [e0, e0 + s(0.55)], [0, 1], { ...clamp, easing: EASE_IN_OUT });
        const appear = frame < e0 ? 0 : 1;
        const scanned = frame >= s(PREP.scan[0]) && scanX > d.gx;
        const color = scanned ? LEVEL_COLOR[d.level] : "#4A5594";

        // Clustering
        const c0 = s(PREP.cluster[0]) + d.delay * 12;
        const toCluster = interpolate(frame, [c0, c0 + s(PREP.cluster[1] - PREP.cluster[0]) - 12], [0, 1], { ...clamp, easing: EASE_IN_OUT });
        let x = lerp(lerp(SOURCE.x, d.gx, emit), d.cx, toCluster);
        let y = lerp(lerp(SOURCE.y, d.gy, emit) - Math.sin(emit * Math.PI) * 90, d.cy, toCluster);
        let opacity = appear;
        let size = lerp(6, 12, emit);

        if (d.level === "reject") {
          const out = interpolate(frame, [s(PREP.rejectOut[0]) + d.delay * 8, s(PREP.rejectOut[1])], [0, 1], { ...clamp, easing: EASE_IN_OUT });
          x = d.gx;
          y = d.gy + out * 60;
          opacity *= 1 - out;
        } else if (d.level === "bronze") {
          opacity *= interpolate(frame, [s(PREP.bronzeOut[0]), s(PREP.bronzeOut[1])], [1, 0], clamp);
        } else {
          // Gold + silver stream into Knowledge along an arc.
          const f0 = s(PREP.flyIn[0]) + d.delay * s(PREP.flyIn[1] - PREP.flyIn[0] - 0.8);
          const t = interpolate(frame, [f0, f0 + s(0.8)], [0, 1], { ...clamp, easing: EASE_IN_OUT });
          const bx = lerp(x, KNOWLEDGE[0], t);
          const by = lerp(y, KNOWLEDGE[1], t) - Math.sin(t * Math.PI) * 120;
          x = bx;
          y = by;
          size = lerp(12, 5, t);
          opacity *= t >= 1 ? 0 : 1;
        }
        if (opacity <= 0.01) return null;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x - size / 2,
              top: y - size / 2,
              width: size,
              height: size,
              borderRadius: 3,
              background: color,
              opacity,
            }}
          />
        );
      })}
      {/* quality scan beam */}
      <div
        style={{
          position: "absolute",
          left: scanX - 2,
          top: GY - 30,
          width: 4,
          height: ROWS * SP + 50,
          borderRadius: 2,
          background: GRADIENT,
          boxShadow: "0 0 24px #00E5FF",
          opacity: interpolate(frame, [s(PREP.scan[0]), s(PREP.scan[0]) + 6, s(PREP.scan[1]) - 6, s(PREP.scan[1])], [0, 1, 1, 0], clamp),
        }}
      />
    </>
  );
};

const Legend: React.FC = () => {
  const frame = useCurrentFrame();
  const inP = interpolate(frame, [s(PREP.scan[0]), s(PREP.scan[0]) + 12], [0, 1], { ...clamp, easing: EASE_OUT });
  const counted = interpolate(frame, [s(PREP.scan[0]), s(PREP.scan[1])], [0, 1], { ...clamp, easing: EASE_IN_OUT });
  // Leaves before gold + silver fly past it towards Knowledge.
  const out = interpolate(frame, [s(PREP.flyIn[0]) - 6, s(PREP.flyIn[0]) + 6], [1, 0], clamp);
  const dim = (l: Level) => {
    if (l === "reject") return interpolate(frame, [s(PREP.rejectOut[0]), s(PREP.rejectOut[1])], [1, 0.35], clamp);
    if (l === "bronze") return interpolate(frame, [s(PREP.bronzeOut[0]), s(PREP.bronzeOut[1])], [1, 0.35], clamp);
    return 1;
  };
  return (
    <div style={{ position: "absolute", left: 1110, top: 400, opacity: inP * out, translate: `${(1 - inP) * 30}px 0px`, fontFamily }}>
      {LEVELS.map((l) => (
        <div key={l} style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20, opacity: dim(l) }}>
          <span style={{ width: 22, height: 22, borderRadius: 5, background: LEVEL_COLOR[l] }} />
          <span style={{ width: 120, fontSize: 32, fontWeight: 700, color: C.text }}>{LEVEL_LABEL[l]}</span>
          <span style={{ fontSize: 32, fontWeight: 600, color: C.text2, fontVariantNumeric: "tabular-nums" }}>{fmt(CURATION.levels[l] * counted)}</span>
        </div>
      ))}
    </div>
  );
};

const ClusterLabels: React.FC = () => {
  const frame = useCurrentFrame();
  const inP = interpolate(frame, [s(PREP.cluster[1]) - 12, s(PREP.cluster[1])], [0, 1], clamp);
  const out = interpolate(frame, [s(PREP.flyIn[0]), s(PREP.flyIn[0]) + 20], [1, 0], clamp);
  return (
    <>
      {CLUSTERS.map((c) => (
        <div
          key={c.name}
          style={{
            position: "absolute",
            left: c.x - 150,
            width: 300,
            top: c.y + 78,
            textAlign: "center",
            fontFamily,
            fontSize: 24,
            fontWeight: 700,
            color: C.text2,
            opacity: inP * out,
          }}
        >
          {c.name}
        </div>
      ))}
    </>
  );
};

const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const index = PREP.titles.filter((t) => frame >= s(t.from)).length - 1;
  const step = PREP.titles[Math.max(0, index)];
  const end = PREP.titles[index + 1] ? s(PREP.titles[index + 1].from) : s(PREP.fadeOut[1]);
  const local = frame - s(step.from);
  const out = interpolate(frame, [end - 8, end], [1, 0], clamp);
  const enter = (delay: number) => ({
    opacity: interpolate(local, [delay, delay + 14], [0, 1], clamp) * out,
    translate: `0px ${interpolate(local, [delay, delay + 18], [24, 0], { ...clamp, easing: EASE_OUT })}px`,
  });
  const count = interpolate(frame, [4, s(PREP.countTo)], [0, CURATION.tickets], { ...clamp, easing: EASE_OUT });
  const title = index === 0 ? `${fmt(count)} raw incidents` : step.title;

  return (
    <div style={{ position: "absolute", left: 110, top: 90, fontFamily }}>
      <Interactive.Div
        name="PrepEyebrow"
        style={{ display: "flex", alignItems: "center", gap: 14, color: C.accent, fontSize: 26, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", ...enter(0) }}
      >
        <span style={{ width: 12, height: 12, borderRadius: "50%", background: C.coral, boxShadow: "0 0 0 8px rgba(0,229,255,.18)" }} />
        {step.eyebrow}
      </Interactive.Div>
      <Interactive.Div
        name="PrepTitle"
        style={{ marginTop: 16, color: C.text, fontSize: 84, lineHeight: 1.02, fontWeight: 780, letterSpacing: "-0.05em", fontVariantNumeric: "tabular-nums", ...enter(3) }}
      >
        {title}
      </Interactive.Div>
      <Interactive.Div name="PrepSub" style={{ marginTop: 14, color: C.text2, fontSize: 32, fontWeight: 500, ...enter(8) }}>
        {step.sub}
      </Interactive.Div>
    </div>
  );
};

const KnowledgeTarget: React.FC = () => {
  const frame = useCurrentFrame();
  const glow = interpolate(frame, [s(PREP.flyIn[0]), s(PREP.flyIn[0]) + 10, s(PREP.flyIn[1]), s(PREP.fadeOut[1])], [0, 1, 1, 0], clamp);
  const items = interpolate(frame, [s(PREP.flyIn[0]) + 10, s(PREP.flyIn[1])], [0, CURATION.knowledgeItems], clamp);
  const labelIn = interpolate(frame, [s(PREP.flyIn[0]), s(PREP.flyIn[0]) + 12], [0, 1], clamp);
  const labelOut = interpolate(frame, [s(PREP.fadeOut[0]), s(PREP.fadeOut[1])], [1, 0], clamp);
  const pulse = 0.5 + 0.5 * Math.sin(frame / 4);
  return (
    <div style={{ position: "absolute", left: PANEL.width, top: 0, width: PANEL.width, height: PANEL.height }}>
      <div
        style={{
          position: "absolute",
          left: NODES.rag.cx - 190,
          top: NODES.rag.cy - 190,
          width: 380,
          height: 380,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(224,165,38,.35), rgba(192,77,255,.12) 45%, rgba(192,77,255,0) 70%)",
          opacity: glow * (0.7 + 0.3 * pulse),
        }}
      />
      <Node node={NODES.rag} index={0} enterAt={s(PREP.knowledgeIn)} />
      <div
        style={{
          position: "absolute",
          left: NODES.rag.cx - 200,
          width: 400,
          top: NODES.rag.cy + NODES.rag.h / 2 + 24,
          textAlign: "center",
          fontFamily,
          opacity: labelIn * labelOut,
        }}
      >
        <div style={{ fontSize: 44, fontWeight: 800, color: C.text, letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums" }}>{Math.round(items)}</div>
        <div style={{ fontSize: 22, fontWeight: 650, color: C.muted }}>knowledge items</div>
      </div>
    </div>
  );
};

const SourceCard: React.FC = () => {
  const frame = useCurrentFrame();
  const inP = interpolate(frame, [0, 14], [0, 1], { ...clamp, easing: EASE_OUT });
  const out = interpolate(frame, [s(PREP.sourceOut[0]), s(PREP.sourceOut[1])], [1, 0], { ...clamp, easing: EASE_IN_OUT });
  const read = interpolate(frame, [s(PREP.emit[0]), s(PREP.emit[1])], [0, 1], clamp);
  const emitting = read > 0 && read < 1;
  const shake = emitting ? Math.sin(frame * 1.7) * 1.5 : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: SOURCE.x - 230,
        top: SOURCE.y - 150,
        width: 460,
        padding: "30px 34px",
        borderRadius: 28,
        background: C.surface1,
        border: `2px solid ${C.border}`,
        boxShadow: `0 30px 70px -20px rgba(0,82,204,${0.15 + (emitting ? 0.15 : 0)}), 0 10px 30px rgba(0,0,0,.08)`,
        fontFamily,
        opacity: inP * out,
        scale: String((0.85 + 0.15 * inP) * (0.8 + 0.2 * out)),
        translate: `${shake}px 0px`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <div style={{ width: 72, height: 72, borderRadius: 18, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Img src={staticFile("logos/jira.svg")} style={{ width: 44, height: 44 }} />
        </div>
        <div>
          <div style={{ fontSize: 30, fontWeight: 780, color: C.text, letterSpacing: "-0.02em" }}>Jira export</div>
          <div style={{ fontSize: 20, fontWeight: 600, color: C.muted, fontFamily: "ui-monospace, Menlo, monospace" }}>tickets.json</div>
        </div>
      </div>
      {/* JSON skeleton lines */}
      <div style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 9 }}>
        {[0.9, 0.7, 0.8, 0.55].map((w, i) => (
          <div key={i} style={{ display: "flex", gap: 8 }}>
            <span style={{ width: `${w * 38}%`, height: 10, borderRadius: 5, background: "rgba(124,243,255,.28)" }} />
            <span style={{ width: `${(1 - w) * 60 + 15}%`, height: 10, borderRadius: 5, background: C.surface2 }} />
          </div>
        ))}
      </div>
      <div style={{ marginTop: 22, display: "flex", justifyContent: "space-between", fontSize: 20, fontWeight: 650, color: C.text2 }}>
        <span>{read >= 1 ? "Loaded" : "Reading…"}</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{fmt(CURATION.tickets * read)} tickets</span>
      </div>
      <div style={{ marginTop: 10, height: 8, borderRadius: 4, background: C.surface2, overflow: "hidden" }}>
        <div style={{ width: `${read * 100}%`, height: "100%", background: GRADIENT }} />
      </div>
    </div>
  );
};

export const Preparation: React.FC = () => (
  <AbsoluteFill>
    <Title />
    <SourceCard />
    <Dots />
    <Legend />
    <ClusterLabels />
    <KnowledgeTarget />
  </AbsoluteFill>
);
