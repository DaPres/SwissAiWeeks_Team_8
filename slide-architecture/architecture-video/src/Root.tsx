import { Composition } from "remotion";
import { ArchitectureOnly, ArchitectureSync, EvaluationOnly, PreparationOnly, StartOnly, ThanksOnly } from "./ArchitectureSync";
import { PANEL } from "./layout";
import { DURATION, EVAL_DURATION, FPS, INTRO, PREP_DURATION, THANKS, TOTAL_DURATION } from "./timing";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ArchitectureSync"
        component={ArchitectureSync}
        durationInFrames={Math.round(TOTAL_DURATION * FPS)}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={{ demoSrc: "product-demo.mp4" }}
      />
      <Composition id="Start" component={StartOnly} durationInFrames={Math.round((INTRO.hold + INTRO.reveal) * FPS)} fps={FPS} width={1920} height={1080} />
      <Composition id="Thanks" component={ThanksOnly} durationInFrames={THANKS.duration * FPS} fps={FPS} width={1920} height={1080} />
      <Composition id="Preparation" component={PreparationOnly} durationInFrames={PREP_DURATION * FPS} fps={FPS} width={1920} height={1080} />
      <Composition id="Evaluation" component={EvaluationOnly} durationInFrames={EVAL_DURATION * FPS} fps={FPS} width={1920} height={1080} />
      {/* Diagram only, for compositing next to the demo in another editor */}
      <Composition
        id="ArchitectureOnly"
        component={ArchitectureOnly}
        durationInFrames={DURATION * FPS}
        fps={FPS}
        width={PANEL.width}
        height={PANEL.height}
      />
    </>
  );
};
