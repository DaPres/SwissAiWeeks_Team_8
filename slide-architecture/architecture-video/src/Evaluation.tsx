import React from "react";
import { AbsoluteFill, Img, Interactive, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, clamp, EASE_IN_OUT, EASE_OUT, fontFamily } from "./theme";
import { EVAL, EVAL_PARAMS, EvalRun, RUNS, s } from "./timing";

/** Evaluation of models + retrieval parameters, rebuilt from the app's Eval tab (eval.png). Full 1920×1080. */

const BAR = "linear-gradient(90deg, #00E5FF, #6C7BFF, #C04DFF)";
const MONO = "ui-monospace, Menlo, monospace";
const PRIO_STYLE = {
  high: { bg: "#C04DFF", fg: "#fff" },
  medium: { bg: "#6C7BFF", fg: "#fff" },
  low: { bg: "#2FB6E8", fg: "#0A0F2A" },
  lowest: { bg: "#2A3668", fg: "#C9D0FF" },
};
const PRIOS = ["high", "medium", "low", "lowest"] as const;

const byId = (id: string) => RUNS.find((r) => r.id === id)!;
const apertus = byId("apertus");
const luna = byId("luna6");

const duration = (sec: number) => (sec >= 60 ? `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s` : `${Math.round(sec)}s`);

/** 0..1 progress of a run's 10 tickets. */
const useRunProgress = (run: EvalRun) => {
  const frame = useCurrentFrame();
  const done = EVAL.runDone[run.id as keyof typeof EVAL.runDone];
  return interpolate(frame, [s(EVAL.run), s(done)], [0, 1], { ...clamp, easing: EASE_IN_OUT });
};

const Pill: React.FC<{ children: React.ReactNode; tone?: "default" | "good" | "warn"; style?: React.CSSProperties }> = ({ children, tone = "default", style }) => {
  const tones = {
    default: { background: C.surface2, color: "#C9D0FF" },
    good: { background: C.goodBg, color: C.good },
    warn: { background: "rgba(255,180,67,.18)", color: "#FFE27A" },
  };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", padding: "6px 15px", borderRadius: 999, fontSize: 21, fontWeight: 700, whiteSpace: "nowrap", ...tones[tone], ...style }}>
      {children}
    </span>
  );
};

/** top K / min sim chips that "tune in" before the run starts. */
const ParamChips: React.FC = () => {
  const frame = useCurrentFrame();
  const [a, b] = [s(EVAL.params[0]), s(EVAL.params[1])];
  const tuning = frame >= a && frame < b;
  const step = Math.floor((frame - a) / 5);
  const topK = tuning ? [1, 3, 5, 2, 4, 1, 3][step % 7] : EVAL_PARAMS.topK;
  const minSim = tuning ? [0.3, 0.7, 0.4, 0.6, 0.35, 0.55][step % 6] : EVAL_PARAMS.minSim;
  const settle = interpolate(frame, [b, b + 10], [1.15, 1], { ...clamp, easing: EASE_OUT });
  const glow = tuning ? "0 0 0 3px rgba(0,229,255,.35)" : "none";
  return (
    <>
      <Pill style={{ boxShadow: glow, scale: String(settle) }}>top K {topK}</Pill>
      <Pill style={{ boxShadow: glow, scale: String(settle) }}>min sim {minSim.toFixed(2)}</Pill>
    </>
  );
};

const Progress: React.FC<{ run: EvalRun; width: number }> = ({ run, width }) => {
  const p = useRunProgress(run);
  const frame = useCurrentFrame();
  const running = p > 0 && p < 1;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{ width, height: 14, borderRadius: 999, background: C.surface2, overflow: "hidden" }}>
        <div
          style={{
            width: `${p * 100}%`,
            height: "100%",
            borderRadius: 999,
            background: running ? "linear-gradient(90deg, #6C7BFF, #00E5FF, #6C7BFF)" : BAR,
            backgroundSize: "200% 100%",
            backgroundPosition: `${-frame * 4}px 0`,
          }}
        />
      </div>
      <span style={{ fontFamily: MONO, fontSize: 24, fontWeight: 600, color: C.text, width: 72, fontVariantNumeric: "tabular-nums" }}>
        {Math.floor(p * EVAL_PARAMS.tickets)}/{EVAL_PARAMS.tickets}
      </span>
      <Pill tone={p >= 1 ? "good" : "default"} style={{ opacity: p > 0 ? 1 : 0.5 }}>
        {p >= 1 ? "done" : p > 0 ? "running" : "queued"}
      </Pill>
    </div>
  );
};

const RunName: React.FC<{ run: EvalRun; size?: number }> = ({ run, size = 36 }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
    <div
      style={{
        width: size * 1.45,
        height: size * 1.45,
        borderRadius: 12,
        border: `1.5px solid ${C.border}`,
        background: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Img src={staticFile(run.logo)} style={{ width: size * 0.95, height: size * 0.95, objectFit: "contain" }} />
    </div>
    <span style={{ fontSize: size, fontWeight: 780, color: C.text, letterSpacing: "-0.02em" }}>{run.name}</span>
  </div>
);

const RunsTable: React.FC = () => {
  const frame = useCurrentFrame();
  const inP = interpolate(frame, [s(EVAL.table), s(EVAL.table) + 16], [0, 1], { ...clamp, easing: EASE_OUT });
  const out = interpolate(frame, [s(EVAL.tableOut[0]), s(EVAL.tableOut[1])], [0, 1], { ...clamp, easing: EASE_IN_OUT });
  if (out >= 1) return null;
  const cols = "1fr 560px 170px 140px";
  return (
    <div
      style={{
        position: "absolute",
        left: 110,
        right: 110,
        top: 360,
        borderRadius: 28,
        background: C.surface1,
        border: `2px solid ${C.border}`,
        boxShadow: "0 30px 80px -40px rgba(0,0,0,.35)",
        overflow: "hidden",
        opacity: inP * (1 - out),
        translate: `0px ${(1 - inP) * 50 - out * 80}px`,
        fontFamily,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: cols,
          padding: "22px 44px",
          background: "rgba(255,255,255,.035)",
          borderBottom: `1.5px solid ${C.border}`,
          fontSize: 20,
          fontWeight: 800,
          letterSpacing: "0.14em",
          color: C.muted,
        }}
      >
        <span>RUN</span>
        <span>PROGRESS</span>
        <span>TIME</span>
        <span>ISSUES</span>
      </div>
      {[luna, apertus].map((run, i) => (
        <RunRow key={run.id} run={run} cols={cols} last={i === 1} delay={i * 5} />
      ))}
    </div>
  );
};

const RunRow: React.FC<{ run: EvalRun; cols: string; last: boolean; delay: number }> = ({ run, cols, last, delay }) => {
  const frame = useCurrentFrame();
  const p = useRunProgress(run);
  const inP = interpolate(frame, [s(EVAL.table) + 8 + delay, s(EVAL.table) + 22 + delay], [0, 1], { ...clamp, easing: EASE_OUT });
  const issuesIn = interpolate(p, [0.98, 1], [0, 1], clamp);
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: cols,
        alignItems: "center",
        padding: "28px 44px",
        borderBottom: last ? "none" : `1.5px solid ${C.border}`,
        background: p > 0 && p < 1 ? "rgba(0,229,255,.07)" : C.surface1,
        opacity: inP,
      }}
    >
      <div>
        <RunName run={run} size={34} />
        <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontFamily: MONO, fontSize: 21, color: C.muted, marginRight: 4 }}>{run.model}</span>
          <ParamChips />
        </div>
      </div>
      <Progress run={run} width={300} />
      <span style={{ fontFamily: MONO, fontSize: 28, fontWeight: 600, color: C.text, fontVariantNumeric: "tabular-nums" }}>{duration(run.wallSeconds * p)}</span>
      <span>
        <Pill tone="warn" style={{ fontSize: 24, opacity: issuesIn, scale: String(0.6 + 0.4 * issuesIn) }}>
          {run.issues}
        </Pill>
      </span>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: string; index: number }> = ({ label, value, index }) => {
  const frame = useCurrentFrame();
  const at = s(EVAL.metrics[0]) + index * 6;
  const inP = interpolate(frame, [at, at + 10], [0, 1], clamp);
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 24, padding: "4px 0", opacity: inP, translate: `${(1 - inP) * 20}px 0px` }}>
      <span style={{ color: C.text2, fontWeight: 500 }}>{label}</span>
      <span style={{ color: C.text, fontWeight: 780, fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
};

const PriorityBar: React.FC<{ run: EvalRun }> = ({ run }) => {
  const frame = useCurrentFrame();
  const grow = interpolate(frame, [s(EVAL.priority[0]), s(EVAL.priority[1])], [0, 1], { ...clamp, easing: EASE_OUT });
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: "flex", gap: 4, height: 40, width: `${grow * 100}%`, borderRadius: 10, overflow: "hidden" }}>
        {PRIOS.filter((p) => run.priority[p] > 0).map((p) => (
          <div
            key={p}
            style={{
              flex: run.priority[p],
              background: PRIO_STYLE[p].bg,
              color: PRIO_STYLE[p].fg,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 22,
              fontWeight: 750,
              opacity: grow > 0.6 ? 1 : 0.8,
            }}
          >
            {grow > 0.8 ? run.priority[p] : ""}
          </div>
        ))}
      </div>
      <div style={{ marginTop: 8, fontSize: 18, color: C.muted, fontWeight: 600 }}>priority distribution · high → lowest</div>
    </div>
  );
};

const Agreement: React.FC<{ rows: [string, number][] }> = ({ rows }) => {
  const frame = useCurrentFrame();
  const [a, b] = [s(EVAL.agreement[0]), s(EVAL.agreement[1])];
  const per = (b - a) / rows.length;
  return (
    <div style={{ marginTop: 14 }}>
      {rows.map(([label, pct], i) => {
        const t = interpolate(frame, [a + i * per * 0.6, a + i * per * 0.6 + 18], [0, 1], { ...clamp, easing: EASE_OUT });
        const weak = pct < 70;
        return (
          <div key={label} style={{ display: "grid", gridTemplateColumns: "150px 1fr 70px", alignItems: "center", gap: 16, height: 32, opacity: t > 0 ? 1 : 0.3 }}>
            <span style={{ fontSize: 22, color: C.text2, fontWeight: 500 }}>{label}</span>
            <div style={{ height: 12, borderRadius: 999, background: C.surface2, overflow: "hidden" }}>
              <div style={{ width: `${pct * t}%`, height: "100%", borderRadius: 999, background: weak ? "#00E5FF" : BAR }} />
            </div>
            <span style={{ fontFamily: MONO, fontSize: 21, color: C.text, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{Math.round(pct * t)}%</span>
          </div>
        );
      })}
      <div style={{ marginTop: 6, fontSize: 18, color: C.muted, fontWeight: 600 }}>agreement with baseline</div>
    </div>
  );
};

const RunCard: React.FC<{ run: EvalRun; baseline?: boolean; left: number; delay: number }> = ({ run, baseline, left, delay }) => {
  const frame = useCurrentFrame();
  const at = s(EVAL.cards) + delay;
  const inP = interpolate(frame, [at, at + 20], [0, 1], { ...clamp, easing: EASE_OUT });
  return (
    <div
      style={{
        position: "absolute",
        left,
        top: 285,
        width: 830,
        padding: "26px 40px",
        borderRadius: 28,
        background: C.surface1,
        border: baseline ? `3px solid ${C.accent}` : `2px solid ${C.border}`,
        boxShadow: baseline ? "0 30px 80px -36px rgba(108,123,255,.55)" : "0 30px 80px -40px rgba(0,0,0,.3)",
        opacity: inP,
        translate: `0px ${(1 - inP) * 60}px`,
        fontFamily,
      }}
    >
      <RunName run={run} size={34} />
      <div style={{ marginTop: 8, fontFamily: MONO, fontSize: 22, color: C.muted }}>{run.model}</div>
      <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
        <Pill>top K {EVAL_PARAMS.topK}</Pill>
        <Pill>min sim {EVAL_PARAMS.minSim.toFixed(2)}</Pill>
        {baseline ? <Pill tone="good">baseline</Pill> : <Pill style={{ background: "transparent", border: `2px dashed ${C.border}` }}>vs. baseline</Pill>}
      </div>
      <div style={{ marginTop: 16 }}>
        <Progress run={run} width={560} />
      </div>
      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 48 }}>
        <Metric label="Wall time" value={duration(run.wallSeconds)} index={0} />
        <Metric label="Avg / ticket" value={run.avg} index={1} />
        <Metric label="Service re-routed" value={run.rerouted} index={2} />
        <Metric label="Consistency issues" value={String(run.issues)} index={3} />
      </div>
      <PriorityBar run={run} />
      {run.agreement && <Agreement rows={run.agreement} />}
    </div>
  );
};

const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const index = EVAL.titles.filter((t) => frame >= s(t.from)).length - 1;
  const step = EVAL.titles[Math.max(0, index)];
  const next = EVAL.titles[index + 1];
  const local = frame - s(step.from);
  const out = next ? interpolate(frame, [s(next.from) - 8, s(next.from)], [1, 0], clamp) : 1;
  const enter = (delay: number) => ({
    opacity: interpolate(local, [delay, delay + 14], [0, 1], clamp) * out,
    translate: `0px ${interpolate(local, [delay, delay + 18], [24, 0], { ...clamp, easing: EASE_OUT })}px`,
  });
  const eyebrowIn = interpolate(frame, [0, 14], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", left: 110, top: 70, fontFamily }}>
      <Interactive.Div
        name="EvalEyebrow"
        style={{ display: "flex", alignItems: "center", gap: 14, color: C.accent, fontSize: 26, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", opacity: eyebrowIn }}
      >
        <span style={{ width: 12, height: 12, borderRadius: "50%", background: C.coral, boxShadow: "0 0 0 8px rgba(0,229,255,.18)" }} />
        Evaluation
      </Interactive.Div>
      <Interactive.Div name="EvalTitle" style={{ marginTop: 14, color: C.text, fontSize: 76, lineHeight: 1.02, fontWeight: 780, letterSpacing: "-0.05em", ...enter(2) }}>
        {step.title}
      </Interactive.Div>
      <Interactive.Div name="EvalSub" style={{ marginTop: 12, color: C.text2, fontSize: 30, fontWeight: 500, ...enter(7) }}>
        {step.sub}
      </Interactive.Div>
    </div>
  );
};

export const Evaluation: React.FC = () => (
  <AbsoluteFill>
    <Title />
    <RunsTable />
    <RunCard run={apertus} baseline left={110} delay={0} />
    <RunCard run={luna} left={980} delay={6} />
  </AbsoluteFill>
);
