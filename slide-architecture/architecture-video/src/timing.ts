/**
 * The whole storyboard, in SECONDS. To sync with the product demo, only edit the numbers here.
 *
 * - STEPS drive the header (what the viewer reads).
 * - HOPS are packets travelling along a wire (`back: true` = returning towards the frontend).
 * - ACTIVE are windows in which a block is lit up / "working".
 */
import type { NodeId, WireId } from "./layout";

export const FPS = 30;
/**
 * product-demo.mp4 (1094×1080, 37.7 s) is the MASTER: its first 32 s play 1:1 and the architecture part is exactly
 * that long. Every architecture time below is demo time.
 */
export const DEMO = {
  // 1920×1080 recording with black side bars; the app itself is this crop (ffmpeg cropdetect).
  sourceWidth: 1920,
  crop: { x: 448, width: 1024, height: 1080 },
  playUntil: 32, // the whole recording (32.2 s)
  /** Callouts over the bottom of the demo. */
  callouts: [
    { from: 12.9, to: 15.6, text: "✓ Case 1 fixed by self-service in 13 s" },
    { from: 18.9, to: 23, text: "→ Case 2 routed to Risk & Controls" },
    { from: 23.4, to: 32, text: "Expert view: proposed fix + AI-corrected routing" },
  ],
};

/** Preparation scene (dataset → knowledge) before the architecture. */
export const PREP_DURATION = 12;
/** Architecture part = the product demo. */
export const DURATION = DEMO.playUntil;

/** Multiplies every number in a timing table, so a scene can be stretched to a new length. */
const stretch = <T,>(value: T, k: number): T => {
  if (typeof value === "number") return (value * k) as T;
  if (Array.isArray(value)) return value.map((v) => stretch(v, k)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, v]) => [key, stretch(v, k)])) as T;
  }
  return value;
};

export const s = (seconds: number) => Math.round(seconds * FPS);

export type Step = {
  from: number;
  eyebrow: string;
  title: string;
  chips: string[];
};

export const STEPS: Step[] = [
  // Case 1: "Which mail program do we use?" → self-service fix
  { from: 0, eyebrow: "① User → Dashboard", title: "User describes the issue", chips: ["Text", "Screenshots"] },
  { from: 1.2, eyebrow: "② Neural Engine · Guard", title: "Security check first", chips: ["Prompt injection", "PII", "Access policy"] },
  { from: 2.4, eyebrow: "③ Jev · TypeSafe AI", title: "Real-time matching as you type", chips: ["Work type", "Urgency", "Impact"] },
  { from: 7.2, eyebrow: "④ RAG", title: "Finds similar incidents", chips: ["Similar fixes", "Service catalog", "Live knowledge"] },
  { from: 9.7, eyebrow: "⑤ Apertus LLM", title: "Prepares the resolution", chips: ["Swiss open model", "Sovereign"] },
  { from: 10.6, eyebrow: "⑥ Back to the user", title: "Try this first → fixed", chips: ["Output filter", "Self-service", "Resolved"] },
  // Case 2: "LEI submission rejected…" → same flow, routed to the expert team
  { from: 13.4, eyebrow: "Case 2 · same flow", title: "A harder one: LEI file rejected", chips: ["Guard", "Jev", "RAG", "Apertus"] },
  { from: 18.2, eyebrow: "Case 2 · routing", title: "Needs an expert team", chips: ["Similar fixes", "Proposed fix", "Risk & Controls"] },
  { from: 22.4, eyebrow: "⑦ Expert team", title: "Arrives with a proposed fix", chips: ["Risk & Controls", "Expert fix", "Corrected by AI"] },
  { from: 29, eyebrow: "Swiss AI, end-to-end", title: "Real-time. Grounded. Sovereign.", chips: [] },
];

/** Each demo case reruns the architecture; ✓ badges reset when a new case starts. */
export const CASES = [0, 13.4];

export type Hop = { wire: WireId; back?: boolean; from: number; to: number };

// Synced to product-demo.mp4 (architecture time = demo time).
// Case 1: typed at 0 s, chips 1–6 s, submit 7 s, "Reviewing your incident" 8–11 s, "Try this first" 11.3 s, "This fixed it" 13.2 s.
// Case 2: pasted 13.7 s, chips 14–18 s, submit 18.4 s, "Sent to Risk & Controls" 18.75 s, expert's "My Incidents" 23 s → detail with proposed fix.
export const HOPS: Hop[] = [
  // case 1
  { wire: "frontend", from: 0.1, to: 0.7 },
  { wire: "engine", from: 0.7, to: 1.2 },
  { wire: "jev", from: 2.4, to: 2.9 },
  { wire: "jev", back: true, from: 6.4, to: 6.9 },
  { wire: "engine", from: 6.9, to: 7.4 },
  { wire: "rag", from: 7.5, to: 8 },
  { wire: "rag", back: true, from: 9.2, to: 9.6 },
  { wire: "apertus", from: 9.7, to: 10.1 },
  { wire: "apertus", back: true, from: 10.4, to: 10.7 },
  { wire: "engine", back: true, from: 11.1, to: 11.5 },
  { wire: "frontend", back: true, from: 11.5, to: 12 },
  // case 2
  { wire: "frontend", from: 13.5, to: 14 },
  { wire: "engine", from: 14, to: 14.5 },
  { wire: "jev", from: 15.5, to: 15.9 },
  { wire: "jev", back: true, from: 17.6, to: 18 },
  { wire: "engine", from: 18.1, to: 18.5 },
  { wire: "rag", from: 18.6, to: 18.9 },
  { wire: "rag", back: true, from: 19.6, to: 19.9 },
  { wire: "apertus", from: 19.9, to: 20.2 },
  { wire: "apertus", back: true, from: 21, to: 21.3 },
  { wire: "engine", back: true, from: 21.9, to: 22.4 },
];

export const ACTIVE: Record<NodeId, [number, number][]> = {
  user: [
    [0, 0.9],
    [11.8, 14.1],
    [18.9, 20.2],
  ],
  frontend: [
    [0.5, 7.3],
    [11.3, 18.4],
    [22.2, 32],
  ],
  engine: [
    [1, 11.5],
    [14.3, 22.4],
  ],
  jev: [
    [2.8, 6.5],
    [15.8, 17.7],
  ],
  rag: [
    [7.9, 9.3],
    [18.8, 19.7],
  ],
  apertus: [
    [10, 10.5],
    [20.1, 21.1],
  ],
};

/** The Neural Engine's security guard: scans each request and each answer. */
export const GUARD = [
  { from: 1.2, to: 2.4, checks: ["Prompt injection", "PII masking", "Access policy"] },
  { from: 10.6, to: 11.2, checks: ["Output filter", "No data leak"] },
  { from: 14.5, to: 15.5, checks: ["Prompt injection", "PII masking", "Access policy"] },
  { from: 21.3, to: 21.9, checks: ["Output filter", "No data leak"] },
];

/** The user's face (0 worried → 1 happy), happy moments and speech bubbles. */
export const USER = {
  mood: [
    [0, 0],
    [13.1, 0],
    [13.5, 1],
    [15.2, 1],
    [15.6, 0],
    [18.8, 0],
    [19.2, 0.7],
  ] as [number, number][],
  happyAt: [13.1],
  bubbles: [
    { text: "I need help…", from: 0.2, to: 4 },
    { text: "Solved, thanks!", from: 13.2, to: 15.4, happy: true },
    { text: "LEI file rejected?!", from: 15.5, to: 18.8 },
    { text: "With the experts ✓", from: 19, to: 32, happy: true },
  ],
};

/** Diagram build-up at the start. */
export const BUILD = { nodesFrom: 0, nodeStagger: 0.1, wiresFrom: 0.2, wireDur: 0.5 };

/** From here on, everything glows together. */
export const OUTRO_FROM = 29;

/** Preparation scene, in seconds from its start; authored for 10 s and stretched to PREP_DURATION. */
export const PREP = stretch({
  titles: [
    { from: 0, eyebrow: "Preparation · Data", title: "20,000 raw incidents", sub: "Jira history: mislabelled, half-resolved, noisy" },
    { from: 2.2, eyebrow: "Preparation · Quality", title: "Quality check on every ticket", sub: "Score 0–100: resolution evidence · closed · real service · clear input" },
    { from: 4.6, eyebrow: "Preparation · Clustering", title: "310 clusters of similar fixes", sub: "Grouped per service on a resolution-weighted embedding" },
    { from: 7, eyebrow: "Preparation · Knowledge", title: "Curated into knowledge", sub: "Gold clusters + service catalog, embedded for RAG" },
  ],
  emit: [0.4, 2.0], // tickets pour out of the Jira export card into the grid
  sourceOut: [2.05, 2.4], // Jira card leaves, making room for the quality legend
  countTo: 2.0, // ticket counter 0 → 20,000
  scan: [2.4, 4.3], // quality beam sweeps the dataset
  rejectOut: [4.6, 5.4], // rejected tickets drop away
  cluster: [4.8, 6.4], // remaining tickets gather into clusters
  bronzeOut: [7, 7.6], // bronze stays out of the knowledge base
  knowledgeIn: 7.2, // Knowledge cylinder appears
  flyIn: [7.4, 9.2], // gold + silver stream into the cylinder
  fadeOut: [9.2, 9.9], // everything but the cylinder leaves
}, PREP_DURATION / 10);

/** Real numbers from the last curation run (backend/data/knowledge.db → curation_run). */
export const CURATION = {
  tickets: 20000,
  levels: { gold: 5814, silver: 1792, bronze: 4100, reject: 8294 },
  clusters: 310,
  knowledgeItems: 40, // 21 gold clusters + 19 service catalog cards
};

/** Evaluation scene after the architecture; authored for 11.5 s and stretched to EVAL_DURATION. */
export const EVAL_DURATION = 13.5;
export const EVAL = stretch({
  titles: [
    { from: 0, title: "Same tickets, different models", sub: "10 challenge tickets · tuned retrieval: top K, min similarity" },
    { from: 4.3, title: "Side-by-side comparison", sub: "Speed, routing and agreement with the baseline, field by field" },
  ],
  table: 0.3, // runs table slides in
  params: [0.8, 1.8], // parameter chips tune in (top K, min sim)
  run: 1.8, // both runs start
  runDone: { luna6: 2.6, apertus: 4.0 },
  tableOut: [4.0, 4.5],
  cards: 4.4, // comparison cards slide in
  metrics: [4.9, 6.0],
  priority: [5.6, 6.4],
  agreement: [6.2, 9],
}, EVAL_DURATION / 11.5);

/** Numbers from the eval run shown in slide-architecture/eval.png. */
export type EvalRun = {
  id: string;
  name: string;
  model: string;
  logo: string;
  wallSeconds: number;
  avg: string;
  rerouted: string;
  issues: number;
  priority: Record<"high" | "medium" | "low" | "lowest", number>;
  agreement?: [string, number][];
};

export const RUNS: EvalRun[] = [
  {
    id: "apertus",
    name: "apertus",
    model: "swiss-ai/Apertus-v1.5-70B",
    logo: "logos/apertus.png",
    wallSeconds: 363,
    avg: "126.9s",
    rerouted: "4/10",
    issues: 3,
    priority: { high: 4, medium: 2, low: 2, lowest: 2 },
  },
  {
    id: "luna6",
    name: "luna6",
    model: "gpt-6-luna",
    logo: "logos/openai.svg",
    wallSeconds: 31,
    avg: "11.0s",
    rerouted: "2/10",
    issues: 4,
    priority: { high: 5, medium: 2, low: 3, lowest: 0 },
    agreement: [
      ["Work type", 100],
      ["Service", 70],
      ["Assignee", 90],
      ["Urgency", 60],
      ["Impact", 40],
      ["Priority", 60],
      ["Resolution", 80],
    ],
  },
];
export const EVAL_PARAMS = { topK: 2, minSim: 0.5, tickets: 10 };

/** Start screen (pause on frame 0 while introducing, then press play). */
export const INTRO = {
  hold: 1.5, // start screen alone (pause on frame 0 while introducing)
  reveal: 1.2, // circle opens from the logo into the preparation scene (overlaps its first 1.2s)
};

/** Thank-you screen with the full picture; its reveal overlaps the end of the evaluation. */
export const THANKS = {
  duration: 12.2, // stays on screen after the 60 s mark
  reveal: 1.2, // fully revealed exactly at 0:59
  panelsFrom: 0.5, // Prepare / Serve / Evaluate panels, staggered — complete before 1:00
  panelStagger: 0.2,
  rowStagger: 0.06,
  flowFrom: 2.4, // highlight runs through the whole pipeline
  flowStep: 0.22, // seconds per row
  thanksDelay: 0.5, // "Thank you!" replaces "The full picture" this long after the clock stops at 1:00
};

/** The pitch clock on the thank-you screen ticks 0:59 → 1:00 here. */
export const PITCH_LIMIT = 60;

/** When the thank-you screen starts closing over the evaluation (fully there at +reveal = 0:59). */
export const THANKS_START = INTRO.hold + PREP_DURATION + DURATION + EVAL_DURATION - THANKS.reveal;

/** Length of the full pitch video. */
export const TOTAL_DURATION = THANKS_START + THANKS.duration;
