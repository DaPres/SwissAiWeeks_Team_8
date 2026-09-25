import React from "react";
import { AbsoluteFill, Img, Interactive, interpolate, staticFile, useCurrentFrame } from "remotion";
import { DarkBackdrop, logoBars } from "./StartScreen";
import { BRAND_GRADIENT, NAVY_MUTED, TeamLogo } from "./TeamLogo";
import { clamp, EASE_IN_OUT, EASE_OUT, fontFamily } from "./theme";
import { PITCH_LIMIT, s, THANKS, THANKS_START } from "./timing";

/** Thank-you screen: the full picture, Prepare → Serve → Evaluate. */

type IconName = "check" | "clusters" | "db" | "shield" | "sliders" | "bars" | "star";

const ICON_PATHS: Record<IconName, React.ReactNode> = {
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  clusters: (
    <>
      <circle cx="7" cy="8" r="2.5" />
      <circle cx="16" cy="7" r="2.5" />
      <circle cx="11" cy="16" r="2.5" />
      <circle cx="18" cy="16" r="1.5" />
    </>
  ),
  db: (
    <>
      <path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Z" />
      <path d="M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 2 L20 5 V11 C20 16.5 16.6 20.7 12 22 C7.4 20.7 4 16.5 4 11 V5 Z" />
      <path d="M8.5 12 L11 14.5 L15.8 9.6" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7h16M4 17h16" />
      <circle cx="9" cy="7" r="2.5" />
      <circle cx="15" cy="17" r="2.5" />
    </>
  ),
  bars: <path d="M5 20V12M10 20V5M15 20V9M20 20V14" />,
  star: <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9Z" />,
};

type Row = { title: string; sub: string; logo?: string; icon?: IconName };
type Panel = { step: string; title: string; rows: Row[] };

const PANELS: Panel[] = [
  {
    step: "①",
    title: "Prepare",
    rows: [
      { title: "Jira export", sub: "20'000 incidents", logo: "logos/jira.svg" },
      { title: "Quality check", sub: "gold · silver · bronze · reject", icon: "check" },
      { title: "Clustering", sub: "310 clusters of similar fixes", icon: "clusters" },
      { title: "Knowledge", sub: "40 curated items for RAG", icon: "db" },
    ],
  },
  {
    step: "②",
    title: "Serve",
    rows: [
      { title: "Dashboard", sub: "user describes the issue", logo: "logos/app.png" },
      { title: "Neural Engine", sub: "orchestrates · security guard", icon: "shield" },
      { title: "Jev", sub: "real-time matching", logo: "logos/typesafe.png" },
      { title: "Apertus", sub: "Swiss LLM writes the answer", logo: "logos/apertus.png" },
    ],
  },
  {
    step: "③",
    title: "Evaluate",
    rows: [
      { title: "Models", sub: "Apertus 70B vs. luna6", logo: "logos/openai.svg" },
      { title: "Parameters", sub: "top K · min similarity", icon: "sliders" },
      { title: "Agreement", sub: "field by field vs. baseline", icon: "bars" },
      { title: "Best setup", sub: "measured, not guessed", icon: "star" },
    ],
  },
];

const PANEL_W = 520;
const GAP = 70;
const LEFT = (1920 - PANEL_W * 3 - GAP * 2) / 2;
const TOP = 390;
const ROWS_TOTAL = PANELS.reduce((n, p) => n + p.rows.length, 0);

const Icon: React.FC<{ name: IconName }> = ({ name }) => (
  <svg width={34} height={34} viewBox="0 0 24 24" fill="none" stroke="url(#endIcon)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <defs>
      <linearGradient id="endIcon" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#00E5FF" />
        <stop offset="1" stopColor="#C04DFF" />
      </linearGradient>
    </defs>
    {ICON_PATHS[name]}
  </svg>
);

/** Which row (0..ROWS_TOTAL-1, panel-major) the flow highlight is on; -1 before it starts. */
const flowIndex = (frame: number) => {
  const t = frame - s(THANKS.flowFrom);
  if (t < 0) return -1;
  return Math.floor(t / s(THANKS.flowStep)) % (ROWS_TOTAL + 3);
};

const PanelCard: React.FC<{ panel: Panel; index: number }> = ({ panel, index }) => {
  const frame = useCurrentFrame();
  const at = s(THANKS.panelsFrom + index * THANKS.panelStagger);
  const inP = interpolate(frame, [at, at + 18], [0, 1], { ...clamp, easing: EASE_OUT });
  const current = flowIndex(frame);
  const offset = PANELS.slice(0, index).reduce((n, p) => n + p.rows.length, 0);
  const panelLit = current >= offset && current < offset + panel.rows.length;

  return (
    <div
      style={{
        position: "absolute",
        left: LEFT + index * (PANEL_W + GAP),
        top: TOP,
        width: PANEL_W,
        padding: "26px 28px 30px",
        borderRadius: 30,
        background: "rgba(255,255,255,.045)",
        border: `1.5px solid ${panelLit ? "rgba(124,243,255,.55)" : "rgba(142,155,214,.25)"}`,
        boxShadow: panelLit ? "0 0 60px rgba(0,229,255,.18)" : "none",
        opacity: inP,
        translate: `0px ${(1 - inP) * 50}px`,
        fontFamily,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 18 }}>
        <span style={{ fontSize: 30, color: NAVY_MUTED, fontWeight: 700 }}>{panel.step}</span>
        <span style={{ fontSize: 40, fontWeight: 800, letterSpacing: "-0.03em", background: BRAND_GRADIENT, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>
          {panel.title}
        </span>
      </div>
      {panel.rows.map((row, i) => {
        const rowAt = at + 8 + s(THANKS.rowStagger) * (i + 1);
        const rowIn = interpolate(frame, [rowAt, rowAt + 12], [0, 1], { ...clamp, easing: EASE_OUT });
        const lit = current === offset + i;
        return (
          <React.Fragment key={row.title}>
            {i > 0 && <div style={{ width: 2, height: 14, marginLeft: 44, background: lit ? "#7CF3FF" : "rgba(142,155,214,.35)", opacity: rowIn }} />}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                padding: "10px 14px",
                borderRadius: 18,
                background: lit ? "rgba(0,229,255,.12)" : "rgba(255,255,255,.06)",
                border: `1.5px solid ${lit ? "rgba(124,243,255,.9)" : "rgba(142,155,214,.18)"}`,
                boxShadow: lit ? "0 0 30px rgba(0,229,255,.35)" : "none",
                opacity: rowIn,
                translate: `${(1 - rowIn) * 24}px 0px`,
              }}
            >
              <div style={{ width: 60, height: 60, flexShrink: 0, borderRadius: 14, background: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
                {row.logo ? <Img src={staticFile(row.logo)} style={{ width: 38, height: 38, objectFit: "contain", borderRadius: 8 }} /> : <Icon name={row.icon!} />}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 28, fontWeight: 760, color: "#fff", letterSpacing: "-0.02em" }}>{row.title}</div>
                <div style={{ fontSize: 20, fontWeight: 550, color: NAVY_MUTED, whiteSpace: "nowrap" }}>{row.sub}</div>
              </div>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
};

/** Chevron between panels, lit when the flow crosses over. */
const Connector: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  const at = s(THANKS.panelsFrom + (index + 1) * THANKS.panelStagger);
  const inP = interpolate(frame, [at, at + 14], [0, 1], clamp);
  const boundary = PANELS.slice(0, index + 1).reduce((n, p) => n + p.rows.length, 0);
  const current = flowIndex(frame);
  const lit = current === boundary - 1 || current === boundary;
  const x = LEFT + (index + 1) * PANEL_W + index * GAP;
  return (
    <svg width={GAP} height={40} style={{ position: "absolute", left: x, top: TOP + 250, opacity: inP, overflow: "visible" }}>
      <path d={`M 12 20 L ${GAP - 16} 20`} stroke={lit ? "#7CF3FF" : "rgba(142,155,214,.5)"} strokeWidth={4} strokeLinecap="round" />
      <path d={`M ${GAP - 26} 10 L ${GAP - 14} 20 L ${GAP - 26} 30`} fill="none" stroke={lit ? "#7CF3FF" : "rgba(142,155,214,.5)"} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

/** Pitch clock: shows the video time, lands on 0:59 as the screen settles and ticks to 1:00. */
const PitchClock: React.FC = () => {
  const frame = useCurrentFrame();
  // Stops dead at the limit.
  const seconds = Math.min(PITCH_LIMIT, Math.floor(THANKS_START + frame / 30 + 1e-6));
  const hit = seconds >= PITCH_LIMIT;
  const hitAt = s(PITCH_LIMIT - THANKS_START);
  const inP = interpolate(frame, [s(THANKS.reveal) - 8, s(THANKS.reveal) + 6], [0, 1], clamp);
  const pop = interpolate(frame, [hitAt, hitAt + 6, hitAt + 18], [1, 1.25, 1], clamp);
  const ring = interpolate(frame, [hitAt, hitAt + 24], [0, 1], { ...clamp, easing: EASE_OUT });
  const label = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <div style={{ position: "absolute", right: 110, top: 70, display: "flex", flexDirection: "column", alignItems: "center", gap: 12, opacity: inP, fontFamily }}>
      <div style={{ position: "relative" }}>
        {hit && ring < 1 && (
          <div
            style={{
              position: "absolute",
              inset: -10 - ring * 30,
              borderRadius: 999,
              border: `3px solid rgba(124,255,214,${1 - ring})`,
            }}
          />
        )}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "12px 24px",
            borderRadius: 999,
            background: hit ? "rgba(0,214,154,.18)" : "rgba(255,255,255,.06)",
            border: `2px solid ${hit ? "#7CFFD6" : "rgba(142,155,214,.35)"}`,
            scale: String(pop),
          }}
        >
          <svg width={30} height={30} viewBox="0 0 24 24" fill="none" stroke={hit ? "#7CFFD6" : NAVY_MUTED} strokeWidth={2.2} strokeLinecap="round">
            <circle cx="12" cy="13" r="8" />
            <path d="M12 9v4l2.5 2.5M9.5 2.5h5" />
          </svg>
          <span style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 40, fontWeight: 700, color: hit ? "#7CFFD6" : "#fff", fontVariantNumeric: "tabular-nums" }}>
            {label}
          </span>
        </div>
      </div>
      <span style={{ fontSize: 24, fontWeight: 700, color: "#7CFFD6", opacity: interpolate(frame, [hitAt, hitAt + 10], [0, 1], clamp) }}>
        right on time ✓
      </span>
    </div>
  );
};

export const EndScreen: React.FC = () => {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [0, s(THANKS.reveal)], [0, 1], { ...clamp, easing: EASE_IN_OUT });
  const radius = reveal * 1500;
  const mask = reveal < 1 ? `radial-gradient(circle at 960px 540px, black ${radius}px, transparent ${radius + 2}px)` : undefined;
  const headIn = interpolate(frame, [s(THANKS.reveal) - 6, s(THANKS.reveal) + 14], [0, 1], { ...clamp, easing: EASE_OUT });
  const footIn = interpolate(frame, [s(THANKS.flowFrom), s(THANKS.flowFrom) + 20], [0, 1], clamp);
  const thanksAt = s(PITCH_LIMIT - THANKS_START + THANKS.thanksDelay);
  const thanks = interpolate(frame, [thanksAt, thanksAt + 16], [0, 1], { ...clamp, easing: EASE_OUT });
  const thanksGlow = interpolate(frame, [thanksAt + 8, thanksAt + 20, thanksAt + 45], [0, 1, 0], clamp);
  const sparkle = 0.55 + 0.45 * Math.abs(Math.sin(frame / 18));

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ WebkitMaskImage: mask, maskImage: mask }}>
        <DarkBackdrop />
        <AbsoluteFill style={{ fontFamily }}>
          <div style={{ position: "absolute", left: 0, right: 0, top: 70, display: "flex", justifyContent: "center", opacity: headIn }}>
            <TeamLogo width={560} bars={logoBars(frame)} sparkle={sparkle} idSuffix="end" />
          </div>
          {/* "The full picture" until the clock stops at 1:00, then "Thank you!" */}
          <Interactive.Div
            name="FullPictureTitle"
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 190,
              textAlign: "center",
              fontSize: 120,
              fontWeight: 850,
              letterSpacing: "-0.05em",
              color: "#fff",
              opacity: headIn * (1 - thanks),
              translate: `0px ${(1 - headIn) * 30 - thanks * 40}px`,
            }}
          >
            The full picture
          </Interactive.Div>
          <Interactive.Div
            name="ThanksTitle"
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 190,
              textAlign: "center",
              fontSize: 120,
              fontWeight: 850,
              letterSpacing: "-0.05em",
              color: "#fff",
              opacity: thanks,
              scale: String(interpolate(thanks, [0, 1], [0.7, 1])),
              filter: `drop-shadow(0 0 ${thanksGlow * 40}px rgba(0,229,255,.8))`,
            }}
          >
            Thank{" "}
            <span style={{ background: BRAND_GRADIENT, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>you!</span>
          </Interactive.Div>
          {PANELS.map((p, i) => (
            <PanelCard key={p.title} panel={p} index={i} />
          ))}
          {[0, 1].map((i) => (
            <Connector key={i} index={i} />
          ))}
          <PitchClock />
          <Interactive.Div
            name="ThanksFooter"
            style={{ position: "absolute", left: 0, right: 0, top: 950, textAlign: "center", fontSize: 30, fontWeight: 700, letterSpacing: "0.22em", textTransform: "uppercase", color: NAVY_MUTED, opacity: footIn }}
          >
            Real-time · Grounded · Secure · Sovereign
          </Interactive.Div>
        </AbsoluteFill>
      </AbsoluteFill>
      {reveal > 0 && reveal < 1 && (
        <div
          style={{
            position: "absolute",
            left: 960 - radius,
            top: 540 - radius,
            width: radius * 2,
            height: radius * 2,
            borderRadius: "50%",
            border: "4px solid rgba(124,243,255,.9)",
            boxShadow: "0 0 40px rgba(0,229,255,.7), inset 0 0 40px rgba(192,77,255,.5)",
            opacity: 1 - reveal * 0.6,
          }}
        />
      )}
    </AbsoluteFill>
  );
};
