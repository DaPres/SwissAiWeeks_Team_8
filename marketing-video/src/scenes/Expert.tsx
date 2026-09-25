import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, EASE_OUT, Level } from "../theme";
import { Accent, AppWindow, Backdrop, Button, Caption, Card, Caret, Cursor, Eyebrow, fadeUp, Pill, popIn, PriorityPill, Sfx, typed, TypingSfx } from "../ui";

const ENRICH = 40;
const DRAFT_CLICK = 176;
const DRAFT_START = 192;
const DRAFT_DUR = 80;
const RESOLVE_CLICK = 304;
const LEARNED = 316;

const RESOLUTION =
  "Root cause: new broker account BRK-EU-07 was not linked to the “EU Trading” approval group. Re-linked it in OMS admin, released the 12 pending orders, verified with the trader.";

const QUEUE: { id: number; title: string; service: string; priority: Level; isNew?: boolean }[] = [
  { id: 20417, title: "EU desk orders stuck in pending approval", service: "Order Management", priority: "high", isNew: true },
  { id: 20409, title: "Settlement instruction rejected by custodian", service: "Securities Settlement", priority: "medium" },
  { id: 20398, title: "NAV file late for Luxembourg funds", service: "NAV Calculation", priority: "highest" },
  { id: 20391, title: "Rimes benchmark feed missing values", service: "Rimes Data Feed", priority: "low" },
];

// layout of the resolve panel inside the AppWindow content area
const DRAFT_LINK = { x: 800, y: 442 };
const RESOLVE_BTN = { x: 640, y: 652 };

export const Expert: React.FC = () => {
  const frame = useCurrentFrame();
  const draft = typed(RESOLUTION, frame, DRAFT_START, DRAFT_DUR);
  const kb = frame >= LEARNED + 20 ? 20001 : 20000;

  return (
    <AbsoluteFill>
      <Backdrop />
      <Caption
        step="04 · Expert"
        title={
          <>
            Experts start with <Accent>context.</Accent>
          </>
        }
        sub="Enriched tickets, similar cases and a drafted fix. Every resolution teaches the system."
      />
      <AppWindow tab="Agent queue">
        {/* queue */}
        <div style={{ position: "absolute", left: 30, top: 18, width: 280, display: "flex", flexDirection: "column", gap: 10 }}>
          {QUEUE.map((t, i) => (
            <div
              key={t.id}
              style={{
                padding: "14px 16px",
                borderRadius: 16,
                background: "#fff",
                border: `1.5px solid ${t.isNew ? C.accent : C.border}`,
                boxShadow: t.isNew ? `0 0 0 1.5px ${C.accent}, 0 10px 22px rgba(100,34,116,.1)` : "none",
                ...fadeUp(frame, 6 + i * 5, 16, 20),
              }}
            >
              <div style={{ fontSize: 13, color: C.accent, fontWeight: 760, letterSpacing: "0.09em", textTransform: "uppercase" }}>
                #{t.id} · open {t.isNew && <span style={{ color: C.coral }}>· new</span>}
              </div>
              <div style={{ fontSize: 17, fontWeight: 580, margin: "4px 0 8px", lineHeight: 1.3 }}>{t.title}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <Pill style={{ fontSize: 13 }}>{t.service}</Pill>
                <PriorityPill level={t.priority} style={{ fontSize: 13 }} />
              </div>
            </div>
          ))}
          <div style={{ marginTop: 8, padding: "16px 18px", borderRadius: 16, background: C.surface2, ...fadeUp(frame, 30, 16, 20) }}>
            <div style={{ fontSize: 34, fontWeight: 760, color: C.accent, fontVariantNumeric: "tabular-nums", scale: frame >= LEARNED + 20 ? String(interpolate(frame, [LEARNED + 20, LEARNED + 28, LEARNED + 36], [1, 1.15, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })) : "1", transformOrigin: "left center" }}>
              {kb.toLocaleString("en-US")}
            </div>
            <div style={{ fontSize: 15, color: C.text2 }}>knowledge items</div>
          </div>
        </div>

        {/* detail */}
        <Card style={{ position: "absolute", left: 330, top: 18, width: 610, height: 372, padding: "22px 26px", ...fadeUp(frame, 12, 18, 30) }}>
          <Eyebrow>#20417 · Incident · Trading Support</Eyebrow>
          <div style={{ fontSize: 24, fontWeight: 720, margin: "6px 0 12px", letterSpacing: "-0.02em" }}>EU desk orders stuck in pending approval</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 16, background: C.surface2, padding: "9px 12px", borderRadius: 10, ...fadeUp(frame, ENRICH, 14, 12) }}>
              <b>User wrote</b>: Since we switched the broker account in OMS, all EU desk orders are stuck…
            </div>
            <div style={{ fontSize: 16, background: C.surface2, padding: "9px 12px", borderRadius: 10, ...fadeUp(frame, ENRICH + 12, 14, 12) }}>
              <b>Screenshot #1</b>: OMS blotter shows 12 orders in PENDING APPROVAL for broker account BRK-EU-07.
            </div>
            <div style={{ fontSize: 16, background: C.surface2, padding: "9px 12px", borderRadius: 10, ...fadeUp(frame, ENRICH + 24, 14, 12) }}>
              <b>AI triage</b>: Order Management · urgency high × impact high → <b>high</b> · a.keller resolved 14 similar
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
            <span style={{ ...popIn(frame, ENRICH + 40, 14) }}><Pill tone="warn">✦ 3 similar tickets linked</Pill></span>
            <span style={{ ...popIn(frame, ENRICH + 48, 14) }}><Pill tone="good">No open duplicates</Pill></span>
            <span style={{ ...popIn(frame, ENRICH + 56, 14) }}><Pill tone="crit">● Critical service</Pill></span>
          </div>
        </Card>

        {/* resolve */}
        <Card style={{ position: "absolute", left: 330, top: 404, width: 610, height: 338, padding: "22px 26px", ...fadeUp(frame, 24, 18, 30) }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <span style={{ fontSize: 24, fontWeight: 740 }}>Resolve</span>
            <span style={{ fontSize: 17, color: C.accent, fontWeight: 650, scale: frame >= DRAFT_CLICK && frame < DRAFT_CLICK + 6 ? "0.94" : "1" }}>
              {frame >= DRAFT_CLICK && frame < DRAFT_START ? "Drafting…" : "✨ Draft from similar tickets"}
            </span>
          </div>
          <div
            style={{
              marginTop: 12,
              height: 140,
              padding: "12px 14px",
              borderRadius: 12,
              border: `1.5px solid ${frame >= DRAFT_START && frame < DRAFT_START + DRAFT_DUR + 10 ? C.accent : C.border}`,
              fontSize: 18,
              lineHeight: 1.5,
              color: draft ? C.text : C.muted,
            }}
          >
            {draft || "Root cause, what you changed, how you verified it."}
            {frame >= DRAFT_START && frame < DRAFT_START + DRAFT_DUR + 10 && <Caret />}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 16 }}>
            <Pill>resolution · done</Pill>
            <Button primary pressed={frame >= RESOLVE_CLICK && frame < RESOLVE_CLICK + 6} style={{ fontSize: 19, padding: "12px 22px" }}>
              {frame >= RESOLVE_CLICK && frame < LEARNED ? "Resolving…" : "Resolve & teach"}
            </Button>
          </div>
        </Card>

        {/* learned toast */}
        <div
          style={{
            position: "absolute",
            left: 330,
            top: 686,
            width: 610,
            padding: "16px 20px",
            borderRadius: 16,
            background: C.goodBg,
            border: `1.5px solid ${C.goodInk}`,
            color: C.goodInk,
            fontSize: 19,
            fontWeight: 650,
            boxShadow: "0 20px 40px -18px rgba(23,97,77,.5)",
            zIndex: 3,
            ...fadeUp(frame, LEARNED, 16, 30),
          }}
        >
          ✓ Learned as live-20417 — the next similar request will find it
        </div>

        {/* knowledge orb flying into the counter */}
        <div
          style={{
            position: "absolute",
            left: interpolate(frame, [LEARNED + 4, LEARNED + 22], [620, 110], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }),
            top: interpolate(frame, [LEARNED + 4, LEARNED + 22], [680, 560], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE_OUT }),
            width: 26,
            height: 26,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #ff6266, #ae2a99)",
            boxShadow: "0 0 0 8px rgba(255,98,102,.2)",
            opacity: interpolate(frame, [LEARNED + 2, LEARNED + 6, LEARNED + 20, LEARNED + 24], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            zIndex: 4,
          }}
        />

        <Cursor
          points={[
            { f: 140, x: 700, y: 360 },
            { f: DRAFT_CLICK - 4, x: DRAFT_LINK.x, y: DRAFT_LINK.y },
            { f: 250, x: DRAFT_LINK.x - 10, y: DRAFT_LINK.y + 30 },
            { f: RESOLVE_CLICK - 4, x: RESOLVE_BTN.x, y: RESOLVE_BTN.y },
            { f: 340, x: RESOLVE_BTN.x + 30, y: RESOLVE_BTN.y + 30 },
          ]}
          clicks={[DRAFT_CLICK, RESOLVE_CLICK]}
          hideAfter={344}
        />
      </AppWindow>

      <Sfx src="whoosh.wav" at={0} volume={0.4} />
      <Sfx src="switch_002.wav" at={6} volume={0.3} />
      {[0, 12, 24].map((d) => (
        <Sfx key={d} src="select_003.wav" at={ENRICH + d} volume={0.35} />
      ))}
      {[40, 48, 56].map((d) => (
        <Sfx key={d} src="glass_002.wav" at={ENRICH + d} volume={0.3} />
      ))}
      <Sfx src="mouse-click.wav" at={DRAFT_CLICK} volume={0.7} />
      <TypingSfx from={DRAFT_START} to={DRAFT_START + DRAFT_DUR} every={2} />
      <Sfx src="mouse-click.wav" at={RESOLVE_CLICK} volume={0.7} />
      <Sfx src="confirmation_002.wav" at={LEARNED} volume={0.55} />
      <Sfx src="powerUp4.wav" at={LEARNED + 18} volume={0.4} />
    </AbsoluteFill>
  );
};
