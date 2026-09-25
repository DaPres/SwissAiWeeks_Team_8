import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { NodeDef, NodeId, NODES } from "./layout";
import { C, clamp, EASE_OUT, fontFamily, GRADIENT } from "./theme";
import { ACTIVE, BUILD, CASES, OUTRO_FROM, s } from "./timing";
import { UserNode } from "./User";

const ORDER: NodeId[] = ["user", "frontend", "engine", "jev", "rag", "apertus"];

/** 0..1 how "lit" a node is right now. */
const useActivity = (id: NodeId) => {
  const frame = useCurrentFrame();
  const windows = ACTIVE[id].map(([a, b]) => {
    const ramp = Math.min(8, Math.floor((s(b) - s(a)) / 2) - 1); // short windows get shorter fades
    return interpolate(frame, [s(a), s(a) + ramp, s(b) - ramp, s(b)], [0, 1, 1, 0], clamp);
  });
  const outro = interpolate(frame, [s(OUTRO_FROM), s(OUTRO_FROM + 1)], [0, 0.6], clamp);
  // The latest window that has started: a second run resets progress and the ✓.
  const started = ACTIVE[id].filter(([from]) => frame >= s(from));
  const [a, b] = started[started.length - 1] ?? ACTIVE[id][0];
  return {
    act: Math.max(outro, ...windows),
    progress: interpolate(frame, [s(a), s(b)], [0, 1], clamp),
    done:
      started.length > 0 &&
      frame > s(b) &&
      b >= Math.max(...CASES.filter((c) => frame >= s(c))) && // finished in the current case
      (id === "jev" || id === "rag" || id === "apertus"),
    doneAt: s(b),
  };
};

const EngineIcon: React.FC<{ spin: number; act: number }> = ({ spin, act }) => {
  const nodes: [number, number][] = [
    [30, 14], [14, 30], [46, 30], [30, 46], [30, 30],
  ];
  return (
    <svg width={64} height={64} viewBox="-2 -2 64 64">
      <defs>
        <linearGradient id="engGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#00E5FF" />
          <stop offset="100%" stopColor="#C04DFF" />
        </linearGradient>
      </defs>
      <circle cx={30} cy={30} r={29} fill="none" stroke="url(#engGrad)" strokeWidth={2.5} strokeDasharray="10 7" opacity={0.35 + act * 0.65} transform={`rotate(${spin} 30 30)`} />
      {nodes.slice(0, 4).map(([x, y], i) => (
        <line key={i} x1={30} y1={30} x2={x} y2={y} stroke="url(#engGrad)" strokeWidth={3} />
      ))}
      <polygon points="30,14 46,30 30,46 14,30" fill="none" stroke="url(#engGrad)" strokeWidth={3} />
      {nodes.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 4 ? 7 : 5} fill={i === 4 ? "url(#engGrad)" : C.surface1} stroke="url(#engGrad)" strokeWidth={3} />
      ))}
    </svg>
  );
};

const DbIcon: React.FC = () => (
  <svg width={52} height={52} viewBox="0 0 24 24" fill="none" stroke="url(#dbGrad)" strokeWidth={1.8} strokeLinecap="round">
    <defs>
      <linearGradient id="dbGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#00E5FF" />
        <stop offset="100%" stopColor="#C04DFF" />
      </linearGradient>
    </defs>
    <path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Z" />
    <path d="M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7" />
    <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
  </svg>
);

const Label: React.FC<{ node: NodeDef }> = ({ node }) => (
  <>
    <div style={{ marginTop: 8, fontSize: 30, fontWeight: 780, letterSpacing: "-0.03em", color: C.text, lineHeight: 1.1 }}>{node.title}</div>
    <div style={{ marginTop: 3, fontSize: 18, fontWeight: 600, color: C.muted, letterSpacing: "0.01em" }}>{node.sub}</div>
  </>
);

const Cylinder: React.FC<{ w: number; h: number; act: number }> = ({ w, h, act }) => {
  const ry = 22;
  const body = `M 2 ${ry} L 2 ${h - ry} A ${w / 2 - 2} ${ry} 0 0 0 ${w - 2} ${h - ry} L ${w - 2} ${ry}`;
  return (
    <svg width={w} height={h} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
      <defs>
        <linearGradient id="cylStroke" gradientUnits="userSpaceOnUse" x1={0} y1={0} x2={w} y2={h}>
          <stop offset="0%" stopColor="#00E5FF" />
          <stop offset="100%" stopColor="#C04DFF" />
        </linearGradient>
      </defs>
      <path d={`${body} A ${w / 2 - 2} ${ry} 0 0 0 2 ${ry} Z`} fill={C.surface1} stroke={C.border} strokeWidth={2.5} />
      <path d={`${body} A ${w / 2 - 2} ${ry} 0 0 0 2 ${ry} Z`} fill="none" stroke="url(#cylStroke)" strokeWidth={4} opacity={act} />
      <ellipse cx={w / 2} cy={ry} rx={w / 2 - 2} ry={ry} fill={C.surface2} stroke={C.border} strokeWidth={2.5} />
      <ellipse cx={w / 2} cy={ry} rx={w / 2 - 2} ry={ry} fill="none" stroke="url(#cylStroke)" strokeWidth={4} opacity={act} />
    </svg>
  );
};

/** `enterAt` (frames) overrides the staggered build-up entrance. */
export const Node: React.FC<{ node: NodeDef; index: number; enterAt?: number }> = ({ node, index, enterAt }) => {
  const frame = useCurrentFrame();
  const { act, progress, done, doneAt } = useActivity(node.id);
  const enter = enterAt ?? s(BUILD.nodesFrom + index * BUILD.nodeStagger);
  const appear = interpolate(frame, [enter, enter + 20], [0, 1], { ...clamp, easing: EASE_OUT });
  const pulse = act * (0.5 + 0.5 * Math.sin(frame / 6));
  const isCyl = node.shape === "cylinder";
  if (node.id === "user") return <UserNode node={node} act={act} appear={appear} />;
  const showProgress = node.id === "jev" || node.id === "rag" || node.id === "apertus";

  return (
    <div
      style={{
        position: "absolute",
        left: node.cx - node.w / 2,
        top: node.cy - node.h / 2,
        width: node.w,
        height: node.h,
        opacity: appear,
        scale: String((0.7 + 0.3 * appear) * (1 + 0.045 * act)),
        fontFamily,
      }}
    >
      {/* glow */}
      <div
        style={{
          position: "absolute",
          inset: isCyl ? "10px 0" : 0,
          borderRadius: isCyl ? 60 : 28,
          boxShadow: `0 24px 70px -10px rgba(192,77,255,${0.55 * act}), 0 0 0 ${10 + pulse * 8}px rgba(0,229,255,${0.12 * act})`,
        }}
      />
      {isCyl ? (
        <Cylinder w={node.w} h={node.h} act={act} />
      ) : (
        <>
          <div style={{ position: "absolute", inset: -3, borderRadius: 29, background: GRADIENT, opacity: act }} />
          <div
            style={{
              position: "absolute",
              inset: 0,
              borderRadius: 26,
              background: C.surface1,
              border: `2px solid ${C.border}`,
              boxShadow: "0 12px 34px rgba(0,0,0,.08)",
              overflow: "hidden",
            }}
          >
            {showProgress && (
              <div style={{ position: "absolute", left: 0, bottom: 0, height: 6, width: `${progress * 100}%`, background: GRADIENT, opacity: act }} />
            )}
          </div>
        </>
      )}
      <div
        style={{
          position: "absolute",
          inset: 0,
          paddingTop: isCyl ? 34 : 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {node.id === "engine" ? (
          <EngineIcon spin={frame * (1 + act * 3)} act={act} />
        ) : isCyl ? (
          <DbIcon />
        ) : (
          <Img src={staticFile(node.logo!)} style={{ width: 56, height: 56, objectFit: "contain", borderRadius: 12 }} />
        )}
        <Label node={node} />
      </div>
      {node.badge && (
        <div
          style={{
            position: "absolute",
            right: -14,
            top: -14,
            width: 44,
            height: 44,
            borderRadius: "50%",
            background: C.surface1,
            border: `2px solid ${C.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 6px 16px rgba(0,0,0,.1)",
          }}
        >
          <Img src={staticFile(node.badge)} style={{ width: 26, height: 26 }} />
        </div>
      )}
      {done && (
        <div
          style={{
            position: "absolute",
            left: -14,
            top: isCyl ? 0 : -14,
            width: 40,
            height: 40,
            borderRadius: "50%",
            background: C.goodBg,
            color: C.good,
            border: `2px solid ${C.surface1}`,
            fontSize: 22,
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            scale: String(interpolate(frame, [doneAt, doneAt + 10], [0, 1], { ...clamp, easing: EASE_OUT })),
          }}
        >
          ✓
        </div>
      )}
    </div>
  );
};

export const Nodes: React.FC = () => (
  <>
    {ORDER.map((id, i) => (
      // Knowledge was already formed by the preparation scene, so it is there from the first frame.
      <Node key={id} node={NODES[id]} index={i} enterAt={id === "rag" ? -30 : undefined} />
    ))}
  </>
);
