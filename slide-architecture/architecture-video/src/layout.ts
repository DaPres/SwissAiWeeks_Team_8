/** Diagram geometry, following arvch-wire-diagram.png. Coordinates are local to the 960×1080 diagram panel. */

export const PANEL = { width: 960, height: 1080 };

export type NodeId = "user" | "frontend" | "engine" | "jev" | "rag" | "apertus";
/** A wire is named after the node it leads to. */
export type WireId = Exclude<NodeId, "user">;

export type NodeDef = {
  id: NodeId;
  cx: number;
  cy: number;
  w: number;
  h: number;
  title: string;
  sub: string;
  logo?: string;
  badge?: string;
  shape?: "box" | "cylinder";
};

export const NODES: Record<NodeId, NodeDef> = {
  user: { id: "user", cx: 150, cy: 335, w: 170, h: 170, title: "User", sub: "" },
  frontend: { id: "frontend", cx: 150, cy: 610, w: 210, h: 150, title: "Frontend", sub: "Dashboard", logo: "logos/app.png", badge: "logos/react.svg" },
  engine: { id: "engine", cx: 460, cy: 610, w: 240, h: 180, title: "Neural Engine", sub: "Orchestrator", badge: "logos/fastapi.svg" },
  jev: { id: "jev", cx: 800, cy: 330, w: 210, h: 150, title: "Jev", sub: "Real-time matching", logo: "logos/typesafe.png" },
  rag: { id: "rag", cx: 800, cy: 610, w: 200, h: 190, title: "Knowledge", sub: "RAG · vectors", shape: "cylinder" },
  apertus: { id: "apertus", cx: 800, cy: 890, w: 210, h: 150, title: "Apertus", sub: "Swiss LLM", logo: "logos/apertus.png" },
};

export type Pt = [number, number];

const left = (n: NodeDef): Pt => [n.cx - n.w / 2, n.cy];
const e = NODES.engine;
const f = NODES.frontend;
const u = NODES.user;

/** Orthogonal wires, drawn in the "out" direction (away from the user). */
export const WIRES: Record<WireId, Pt[]> = {
  frontend: [[u.cx, u.cy + u.h / 2 + 6], [f.cx, f.cy - f.h / 2]],
  engine: [[f.cx + f.w / 2, f.cy], left(e)],
  jev: [[e.cx, e.cy - e.h / 2], [e.cx, NODES.jev.cy], left(NODES.jev)],
  rag: [[e.cx + e.w / 2, e.cy], left(NODES.rag)],
  apertus: [[e.cx, e.cy + e.h / 2], [e.cx, NODES.apertus.cy], left(NODES.apertus)],
};

const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/** Point at progress t (0..1) along a polyline. */
export const pointAt = (pts: Pt[], t: number): Pt => {
  const segs = pts.slice(1).map((p, i) => dist(pts[i], p));
  let d = Math.max(0, Math.min(1, t)) * segs.reduce((a, b) => a + b, 0);
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) {
      const k = segs[i] === 0 ? 0 : d / segs[i];
      return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k];
    }
    d -= segs[i];
  }
  return pts[pts.length - 1];
};

/** SVG path for a polyline with rounded corners. */
export const roundedPath = (pts: Pt[], r = 26): string => {
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [p0, p1, p2] = [pts[i - 1], pts[i], pts[i + 1]];
    const r1 = Math.min(r, dist(p0, p1) / 2, dist(p1, p2) / 2);
    const a: Pt = [p1[0] + ((p0[0] - p1[0]) / dist(p0, p1)) * r1, p1[1] + ((p0[1] - p1[1]) / dist(p0, p1)) * r1];
    const b: Pt = [p1[0] + ((p2[0] - p1[0]) / dist(p1, p2)) * r1, p1[1] + ((p2[1] - p1[1]) / dist(p1, p2)) * r1];
    d += ` L ${a[0]} ${a[1]} Q ${p1[0]} ${p1[1]} ${b[0]} ${b[1]}`;
  }
  const last = pts[pts.length - 1];
  return `${d} L ${last[0]} ${last[1]}`;
};
