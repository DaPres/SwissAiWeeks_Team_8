import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C } from "../theme";
import { Accent, AppWindow, Backdrop, Button, Caption, Card, Cursor, Eyebrow, fadeUp, Pill, Sfx } from "../ui";

export const ANSWER = [
  "1. In OMS → Admin → Broker accounts, open the new EU account.",
  "2. Link it to your desk’s approval group “EU Trading”.",
  "3. Re-submit one pending order — it releases within a minute.",
];

// Button centres inside the AppWindow content area (shared with the Solved / NotSolved scenes).
export const SOLVED_BTN = { x: 191, y: 522 };
export const TICKET_BTN = { x: 525, y: 522 };

/** The "Try this first" self-service card. `revealStart` streams the answer in word by word; omit to show it complete. */
export const SelfServiceCard: React.FC<{ revealStart?: number; pressed?: "solved" | "ticket" }> = ({ revealStart, pressed }) => {
  const frame = useCurrentFrame();
  const words = ANSWER.map((l) => l.split(" "));
  const total = words.reduce((a, w) => a + w.length, 0);
  const shown = revealStart === undefined ? total : Math.floor(interpolate(frame, [revealStart, revealStart + 130], [0, total], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const extrasAt = revealStart === undefined ? -100 : revealStart + 140;
  let seen = 0;

  return (
    <Card style={{ position: "absolute", left: 30, top: 190, width: 910, height: 400, borderLeft: `7px solid ${C.accent}` }}>
      <Eyebrow>Try this first</Eyebrow>
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 12, fontSize: 25, lineHeight: 1.45 }}>
        {words.map((line, li) => (
          <div key={li}>
            {line.map((w, wi) => {
              seen++;
              const visible = seen <= shown;
              return (
                <span key={wi} style={{ opacity: visible ? 1 : 0 }}>
                  {w}{" "}
                </span>
              );
            })}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 20, ...fadeUp(frame, extrasAt, 14, 12) }}>
        <Pill tone="warn">cited · #18342</Pill>
        <Pill tone="warn">cited · #11907</Pill>
        <Pill tone="good">👍 14 people solved it this way</Pill>
      </div>
      <div style={{ position: "absolute", left: 34, top: 302, display: "flex", gap: 14, ...fadeUp(frame, extrasAt + 12, 14, 16) }}>
        <Button primary pressed={pressed === "solved"} style={{ width: 240, justifyContent: "center" }}>
          That solved it
        </Button>
        <Button pressed={pressed === "ticket"} style={{ width: 400, justifyContent: "center" }}>
          Still need help — create ticket
        </Button>
      </div>
    </Card>
  );
};

export const UnderstoodCard: React.FC<{ enter?: number }> = ({ enter = -100 }) => {
  const frame = useCurrentFrame();
  return (
    <Card style={{ position: "absolute", left: 30, top: 18, width: 910, height: 150, ...fadeUp(frame, enter, 18) }}>
      <Eyebrow>
        What we understood <span style={{ color: C.muted, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>· Order Management</span>
      </Eyebrow>
      <div style={{ marginTop: 8, fontSize: 24, lineHeight: 1.45 }}>
        EU desk orders are stuck in pending approval since the broker account in OMS was switched — likely a missing approval-group link.
      </div>
    </Card>
  );
};

export const Proposal: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Backdrop />
      <Caption
        step="02 · Get guidance"
        title={
          <>
            A fix, <Accent>before</Accent> a ticket.
          </>
        }
        sub="Grounded in resolutions that actually worked — with the sources to prove it."
      />
      <AppWindow tab="Get help">
        <UnderstoodCard enter={8} />
        <div style={{ ...fadeUp(frame, 34, 20, 40) }}>
          <SelfServiceCard revealStart={50} />
        </div>
        <Cursor
          points={[
            { f: 250, x: 700, y: 720 },
            { f: 280, x: SOLVED_BTN.x + 10, y: SOLVED_BTN.y + 6 },
            { f: 312, x: TICKET_BTN.x, y: TICKET_BTN.y + 6 },
            { f: 350, x: 350, y: SOLVED_BTN.y + 40 },
          ]}
        />
      </AppWindow>
      <Sfx src="whoosh.wav" at={0} volume={0.4} />
      <Sfx src="open_002.wav" at={10} volume={0.4} />
      <Sfx src="glass_002.wav" at={48} volume={0.45} />
      <Sfx src="select_003.wav" at={190} volume={0.4} />
      <Sfx src="pluck_001.wav" at={202} volume={0.4} />
    </AbsoluteFill>
  );
};
