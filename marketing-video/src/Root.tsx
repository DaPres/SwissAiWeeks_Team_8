import { Composition, Folder } from "remotion";
import { MarketingVideo } from "./MarketingVideo";
import { EnterTicket } from "./scenes/EnterTicket";
import { Expert } from "./scenes/Expert";
import { Intro } from "./scenes/Intro";
import { KnowledgeSearch } from "./scenes/KnowledgeSearch";
import { NotSolved } from "./scenes/NotSolved";
import { Outro } from "./scenes/Outro";
import { Proposal } from "./scenes/Proposal";
import { Solved } from "./scenes/Solved";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="MarketingVideo" component={MarketingVideo} durationInFrames={2668} fps={30} width={1920} height={1080} />
      <Folder name="MarketingVideo-Scenes">
        <Composition id="Intro" component={Intro} durationInFrames={200} fps={30} width={1920} height={1080} />
        <Composition id="EnterTicket" component={EnterTicket} durationInFrames={340} fps={30} width={1920} height={1080} />
        <Composition id="KnowledgeSearch" component={KnowledgeSearch} durationInFrames={420} fps={30} width={1920} height={1080} />
        <Composition id="Proposal" component={Proposal} durationInFrames={360} fps={30} width={1920} height={1080} />
        <Composition id="Solved" component={Solved} durationInFrames={300} fps={30} width={1920} height={1080} />
        <Composition id="NotSolved" component={NotSolved} durationInFrames={510} fps={30} width={1920} height={1080} />
        <Composition id="Expert" component={Expert} durationInFrames={420} fps={30} width={1920} height={1080} />
        <Composition id="Outro" component={Outro} durationInFrames={250} fps={30} width={1920} height={1080} />
      </Folder>
    </>
  );
};
