import { Audio } from "@remotion/media";
import { linearTiming, springTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { AbsoluteFill, interpolate, staticFile, useVideoConfig } from "remotion";
import { EnterTicket } from "./scenes/EnterTicket";
import { Expert } from "./scenes/Expert";
import { Intro } from "./scenes/Intro";
import { KnowledgeSearch } from "./scenes/KnowledgeSearch";
import { NotSolved } from "./scenes/NotSolved";
import { Outro } from "./scenes/Outro";
import { Proposal } from "./scenes/Proposal";
import { Solved } from "./scenes/Solved";

export const MarketingVideo: React.FC = () => {
  const { durationInFrames } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: "#f8f4f8" }}>
      <TransitionSeries>
        <TransitionSeries.Sequence name="Intro" durationInFrames={200}>
          <Intro />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 20 })} />
        <TransitionSeries.Sequence name="Enter ticket" durationInFrames={340}>
          <EnterTicket />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={springTiming({ config: { damping: 200 }, durationInFrames: 20 })}
        />
        <TransitionSeries.Sequence name="Knowledge search" durationInFrames={420}>
          <KnowledgeSearch />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={springTiming({ config: { damping: 200 }, durationInFrames: 20 })}
        />
        <TransitionSeries.Sequence name="Proposal" durationInFrames={360}>
          <Proposal />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
        <TransitionSeries.Sequence name="Solved" durationInFrames={300}>
          <Solved />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={slide({ direction: "from-bottom" })}
          timing={springTiming({ config: { damping: 200 }, durationInFrames: 20 })}
        />
        <TransitionSeries.Sequence name="Not solved" durationInFrames={510}>
          <NotSolved />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={springTiming({ config: { damping: 200 }, durationInFrames: 20 })}
        />
        <TransitionSeries.Sequence name="Expert" durationInFrames={420}>
          <Expert />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 20 })} />
        <TransitionSeries.Sequence name="Outro" durationInFrames={250}>
          <Outro />
        </TransitionSeries.Sequence>
      </TransitionSeries>

      <Audio
        name="Music bed"
        src={staticFile("music/bed.mp3")}
        volume={(f) =>
          interpolate(f, [0, 30, durationInFrames - 60, durationInFrames], [0, 0.32, 0.32, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        }
      />
    </AbsoluteFill>
  );
};
