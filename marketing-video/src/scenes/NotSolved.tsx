import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, EASE_OUT, Level, LEVELS, MATRIX, PRIORITY_STYLE } from "../theme";
import { Accent, AiMark, AppWindow, Backdrop, Caption, Card, Cursor, Eyebrow, fadeUp, Pill, popIn, PriorityPill, Sfx } from "../ui";
import { SelfServiceCard, TICKET_BTN, UnderstoodCard } from "./Proposal";

const CLICK = 20;
const FORM_IN = 40;
const FILL = 64; // first field fills
const FILL_STEP = 12;
const ROUTE = 196; // phase B
const MATRIX_AT = 270;
const DONE = 360; // phase C

const TEAMS = ["Investment Operations", "Trading Support", "Securities Operations", "Valuation & Pricing", "Treasury & Cash", "Enterprise Applications"];
const TARGET = 1;

const Field: React.FC<{ label: string; value: React.ReactNode; at: number; span?: boolean }> = ({ label, value, at, span }) => {
  const frame = useCurrentFrame();
  const flash = interpolate(frame, [at, at + 6, at + 24], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const filled = frame >= at;
  return (
    <div style={{ gridColumn: span ? "1 / -1" : undefined, display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 16, color: C.text2, fontWeight: 500 }}>{label}</span>
      <div
        style={{
          position: "relative",
          minHeight: 48,
          padding: "10px 14px",
          borderRadius: 11,
          border: `1.5px solid ${flash > 0.05 ? C.accent : C.border}`,
          background: `rgba(251,234,245,${flash})`,
          fontSize: 19,
          lineHeight: 1.4,
          color: C.text,
        }}
      >
        <span style={{ opacity: filled ? 1 : 0 }}>{value}</span>
        {filled && (
          <span style={{ position: "absolute", right: 10, top: 10, color: C.accent, fontSize: 18, opacity: interpolate(frame, [at, at + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>✦</span>
        )}
      </div>
    </div>
  );
};

export const NotSolved: React.FC = () => {
  const frame = useCurrentFrame();
  const selfOut = interpolate(frame, [30, 44], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const formOut = interpolate(frame, [ROUTE - 16, ROUTE], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const routeOut = interpolate(frame, [DONE - 10, DONE + 6], [1, 0.25], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const lineP = interpolate(frame, [ROUTE + 40, ROUTE + 70], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT });
  const nodeY = (i: number) => 40 + i * 58;
  const urgency: Level = "high";
  const impact: Level = "high";
  const ui = LEVELS.indexOf(urgency);
  const ii = LEVELS.indexOf(impact);

  return (
    <AbsoluteFill>
      <Backdrop />
      <Caption
        step="03 · Not solved?"
        title={
          <>
            Routed right, <Accent>first time.</Accent>
          </>
        }
        sub="A complete ticket with the right team and the right priority, before you’ve finished reading."
      />
      <AppWindow tab="Get help">
        {/* start: the self-service card from before */}
        <div style={{ opacity: selfOut }}>
          <UnderstoodCard />
          <SelfServiceCard pressed={frame >= CLICK && frame < CLICK + 6 ? "ticket" : undefined} />
        </div>

        {/* phase A: proposed ticket */}
        <div style={{ opacity: formOut, scale: String(interpolate(frame, [ROUTE - 16, ROUTE], [1, 0.94], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) }}>
          <Card style={{ position: "absolute", left: 30, top: 18, width: 910, height: 640, ...fadeUp(frame, FORM_IN, 20, 50) }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ fontSize: 28, fontWeight: 760 }}>Proposed ticket</span>
              <span style={{ color: C.muted, fontSize: 18 }}>Drafted by the assistant · adjust anything</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px 18px", marginTop: 18 }}>
              <Field span label="Summary" at={FILL} value="EU desk orders stuck in pending approval after OMS broker switch" />
              <Field
                span
                label="Description"
                at={FILL + FILL_STEP}
                value="Since the broker account in OMS was switched, EU desk orders stay in pending approval and can’t be released. Screenshot: 12 orders pending for BRK-EU-07."
              />
              <Field label="Type" at={FILL + FILL_STEP * 2} value="Incident" />
              <Field label="Service" at={FILL + FILL_STEP * 3} value="Order Management" />
              <Field label="Urgency" at={FILL + FILL_STEP * 4} value="high — traders are blocked" />
              <Field label="Impact" at={FILL + FILL_STEP * 5} value="high — critical service affected" />
            </div>
            <div
              style={{
                marginTop: 18,
                display: "flex",
                flexDirection: "column",
                gap: 10,
                padding: "16px 18px",
                borderRadius: 13,
                background: C.surface2,
                fontSize: 20,
                ...fadeUp(frame, FILL + FILL_STEP * 6, 16, 16),
              }}
            >
              <div>
                <span style={{ display: "inline-block", width: 110, color: C.muted, fontSize: 17 }}>Team</span>Trading Support <Pill tone="crit">● Critical</Pill>
              </div>
              <div>
                <span style={{ display: "inline-block", width: 110, color: C.muted, fontSize: 17 }}>Assignee</span>a.keller{" "}
                <span style={{ color: C.muted, fontSize: 17 }}>resolved 14 similar tickets</span>
              </div>
              <div>
                <span style={{ display: "inline-block", width: 110, color: C.muted, fontSize: 17 }}>Priority</span>
                <PriorityPill level="high" /> <span style={{ color: C.muted, fontSize: 17 }}>from urgency × impact matrix</span>
              </div>
            </div>
          </Card>
        </div>

        {/* phase B: routing + matrix */}
        <div style={{ position: "absolute", left: 30, top: 18, width: 910, height: 722, opacity: routeOut }}>
          <Card style={{ position: "absolute", left: 0, top: 0, width: 910, height: 420, padding: 0, overflow: "hidden", ...fadeUp(frame, ROUTE, 18, 40) }}>
            <div style={{ padding: "20px 28px 0" }}>
              <Eyebrow>Routing</Eyebrow>
            </div>
            <svg width={910} height={380} style={{ position: "absolute", left: 0, top: 40 }}>
              {TEAMS.map((t, i) => (
                <path
                  key={t}
                  d={`M 470 170 C 560 170, 560 ${nodeY(i) + 22}, 640 ${nodeY(i) + 22}`}
                  fill="none"
                  stroke={i === TARGET ? "url(#route)" : C.grid}
                  strokeWidth={i === TARGET ? 5 : 2}
                  strokeDasharray={i === TARGET ? 300 : undefined}
                  strokeDashoffset={i === TARGET ? 300 * (1 - lineP) : undefined}
                  opacity={i === TARGET ? 1 : interpolate(frame, [ROUTE + 16, ROUTE + 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
                />
              ))}
              <path
                d="M 270 170 L 400 170"
                stroke="url(#route)"
                strokeWidth={5}
                strokeDasharray={130}
                strokeDashoffset={130 * (1 - interpolate(frame, [ROUTE + 18, ROUTE + 38], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }))}
              />
              <defs>
                <linearGradient id="route" x1="0" x2="1">
                  <stop offset="0" stopColor="#ff6266" />
                  <stop offset="1" stopColor="#ae2a99" />
                </linearGradient>
              </defs>
            </svg>
            {/* ticket chip */}
            <div style={{ position: "absolute", left: 28, top: 150, width: 240, padding: "14px 16px", borderRadius: 16, background: "#fff", border: `1.5px solid ${C.border}`, boxShadow: "0 12px 26px rgba(62,25,59,.1)", ...popIn(frame, ROUTE + 6, 16) }}>
              <div style={{ fontSize: 14, color: C.accent, fontWeight: 760, letterSpacing: "0.1em", textTransform: "uppercase" }}>New ticket</div>
              <div style={{ fontSize: 18, fontWeight: 620, marginTop: 4, lineHeight: 1.3 }}>Orders stuck in pending approval</div>
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <Pill style={{ fontSize: 14 }}>Order Mgmt</Pill>
                <Pill style={{ fontSize: 14 }}>Incident</Pill>
              </div>
            </div>
            <div style={{ position: "absolute", left: 403, top: 176, ...popIn(frame, ROUTE + 30, 14) }}>
              <AiMark size={66} spin={frame < ROUTE + 70} />
            </div>
            {TEAMS.map((t, i) => {
              const hit = i === TARGET && lineP >= 1;
              return (
                <div
                  key={t}
                  style={{
                    position: "absolute",
                    left: 640,
                    top: 40 + nodeY(i),
                    width: 245,
                    height: 44,
                    borderRadius: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "0 14px",
                    fontSize: 17,
                    fontWeight: 650,
                    border: `1.5px solid ${hit ? C.accent : C.border}`,
                    background: hit ? C.accent : "#fff",
                    color: hit ? "#fff" : i === TARGET ? C.text : C.muted,
                    boxShadow: hit ? `0 0 0 ${interpolate(frame, [ROUTE + 70, ROUTE + 90], [0, 10], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px rgba(158,37,138,.14)` : "none",
                    ...fadeUp(frame, ROUTE + 12 + i * 4, 14, 10),
                  }}
                >
                  {t}
                  {hit && <span style={{ marginLeft: "auto", ...popIn(frame, ROUTE + 72, 12) }}>✓</span>}
                </div>
              );
            })}
            <div style={{ position: "absolute", left: 28, top: 290, fontSize: 18, color: C.text2, ...fadeUp(frame, ROUTE + 80, 14, 10) }}>
              → assigned to <b style={{ color: C.text }}>a.keller</b> · resolved 14 similar tickets
            </div>
          </Card>

          <Card style={{ position: "absolute", left: 0, top: 440, width: 910, height: 282, padding: "20px 28px", ...fadeUp(frame, MATRIX_AT - 16, 18, 40) }}>
            <div style={{ display: "flex", gap: 30 }}>
              <div style={{ width: 280 }}>
                <Eyebrow>Priority</Eyebrow>
                <div style={{ fontSize: 20, color: C.text2, marginTop: 10, lineHeight: 1.45 }}>
                  Urgency and impact are assessed from the ticket, then the matrix decides. Consistent every time.
                </div>
                <div style={{ marginTop: 16, ...popIn(frame, MATRIX_AT + 36, 16) }}>
                  <PriorityPill level="high" style={{ fontSize: 26, padding: "8px 22px" }} />
                </div>
              </div>
              <div style={{ flex: 1, display: "grid", gridTemplateColumns: "90px repeat(5, 1fr)", gap: 4, fontSize: 14 }}>
                <span />
                {LEVELS.map((l, c) => (
                  <span key={l} style={{ textAlign: "center", color: c === ii && frame >= MATRIX_AT + 12 ? C.accent : C.muted, fontWeight: 700, textTransform: "capitalize" }}>
                    {l}
                  </span>
                ))}
                {LEVELS.map((u, r) => (
                  <React.Fragment key={u}>
                    <span style={{ color: r === ui && frame >= MATRIX_AT ? C.accent : C.muted, fontWeight: 700, textTransform: "capitalize", display: "flex", alignItems: "center" }}>
                      {u}
                    </span>
                    {MATRIX[u].map((p, c) => {
                      const inRow = r === ui && frame >= MATRIX_AT;
                      const inCol = c === ii && frame >= MATRIX_AT + 12;
                      const target = r === ui && c === ii && frame >= MATRIX_AT + 24;
                      const dim = frame >= MATRIX_AT + 24 && !target;
                      return (
                        <span
                          key={`${u}-${c}`}
                          style={{
                            height: 36,
                            borderRadius: 7,
                            display: "grid",
                            placeItems: "center",
                            background: PRIORITY_STYLE[p].bg,
                            color: PRIORITY_STYLE[p].fg,
                            fontWeight: 650,
                            textTransform: "capitalize",
                            opacity: dim ? 0.35 : inRow || inCol || frame < MATRIX_AT ? 1 : 0.6,
                            outline: target ? `3px solid ${C.text}` : "none",
                            scale: target ? String(interpolate(frame, [MATRIX_AT + 24, MATRIX_AT + 32, MATRIX_AT + 40], [1, 1.18, 1.08], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) : "1",
                            zIndex: target ? 2 : 1,
                          }}
                        >
                          {p}
                        </span>
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </Card>
        </div>

        {/* phase C: created */}
        <Card
          style={{
            position: "absolute",
            left: 90,
            top: 250,
            width: 790,
            padding: "34px 38px",
            background: C.goodBg,
            borderColor: C.goodInk,
            boxShadow: "0 40px 80px -30px rgba(23,97,77,.45)",
            zIndex: 5,
            ...popIn(frame, DONE, 20),
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
            <div style={{ width: 72, height: 72, borderRadius: "50%", background: C.goodInk, color: "#fff", display: "grid", placeItems: "center", fontSize: 38, fontWeight: 800 }}>✓</div>
            <div>
              <div style={{ fontSize: 34, fontWeight: 780, color: C.goodInk }}>Ticket #20417 created</div>
              <div style={{ fontSize: 22, color: C.text2, marginTop: 6, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                Routed to <b style={{ color: C.text }}>Trading Support</b> · a.keller · priority <PriorityPill level="high" />
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 20, ...fadeUp(frame, DONE + 24, 14, 10) }}>
            <Pill tone="good">🔔 a.keller notified</Pill>
            <Pill>screenshot & context attached</Pill>
            <Pill>3 similar cases linked</Pill>
          </div>
        </Card>

        <Cursor
          points={[
            { f: 0, x: 360, y: 640 },
            { f: CLICK - 2, x: TICKET_BTN.x, y: TICKET_BTN.y },
            { f: 40, x: TICKET_BTN.x + 20, y: TICKET_BTN.y + 20 },
          ]}
          clicks={[CLICK]}
          hideAfter={40}
        />
      </AppWindow>

      <Sfx src="mouse-click.wav" at={CLICK} volume={0.7} />
      <Sfx src="open_002.wav" at={FORM_IN} volume={0.4} />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <Sfx key={i} src="glass_002.wav" at={FILL + i * FILL_STEP} volume={0.3} />
      ))}
      <Sfx src="whoosh.wav" at={ROUTE - 6} volume={0.4} />
      <Sfx src="phaserUp3.wav" at={ROUTE + 40} volume={0.3} />
      <Sfx src="select_003.wav" at={ROUTE + 72} volume={0.55} />
      <Sfx src="tick_002.wav" at={MATRIX_AT} volume={0.5} />
      <Sfx src="tick_002.wav" at={MATRIX_AT + 12} volume={0.5} />
      <Sfx src="threeTone2.wav" at={MATRIX_AT + 24} volume={0.3} />
      <Sfx src="confirmation_002.wav" at={DONE + 2} volume={0.65} />
      <Sfx src="ding.wav" at={DONE + 26} volume={0.25} />
    </AbsoluteFill>
  );
};
