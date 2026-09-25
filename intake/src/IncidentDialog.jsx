import { Dialog } from '@base-ui/react/dialog';
import { Button } from '@base-ui/react/button';
import { Search, SlidersHorizontal, Lightbulb, LoaderCircle } from 'lucide-react';

const reviewSteps = [
  { Icon: Search, label: 'Find similar incidents', detail: 'Look for solutions that worked before.' },
  { Icon: SlidersHorizontal, label: 'Review details and routing', detail: 'Check the fields, priority, and responsible team.' },
  { Icon: Lightbulb, label: 'Prepare a resolution', detail: 'Find a fix for you or the expert team.' },
];

function EngineReview() {
  return <div className="engine-review" role="status" aria-live="polite">
    <Dialog.Title>Reviewing your incident</Dialog.Title>
    <Dialog.Description className="handoff-description">The neural engine is working on it.</Dialog.Description>
    <ul className="engine-review-list" aria-label="Neural engine review">
      {reviewSteps.map(({ Icon, label, detail }, index) => <li key={label} className="engine-review-step" style={{ '--step-delay': `${index * 1.6}s`, '--entry-delay': `${index * 100}ms` }}>
        <span className="engine-step-icon" aria-hidden="true"><Icon size={21} strokeWidth={1.5} /></span>
        <span className="engine-step-copy"><span>{label}</span><span>{detail}</span></span>
        <span className="engine-step-pulse" aria-hidden="true" />
      </li>)}
    </ul>
  </div>;
}

function DialogActions({ children }) {
  return <div className="handoff-actions">{children}</div>;
}

export default function IncidentDialog({ state, onDecision, onRetry, onBack, onDone, onView }) {
  const phase = state?.phase;
  const record = state?.record;
  const fix = record?.enriched?.clientResolution;
  const team = record?.enriched?.team || record?.incident?.['Service Team(s)']?.[0] || 'the service team';
  return <Dialog.Root open={Boolean(state)} onOpenChange={() => {}} disablePointerDismissal>
    <Dialog.Portal>
      <Dialog.Backdrop className="handoff-backdrop" />
      <Dialog.Popup className="handoff-dialog" tabIndex={-1}>
        {phase === 'loading' && <EngineReview />}
        {phase === 'deciding' && <div className="handoff-wait" role="status">
          <LoaderCircle className="handoff-saving-icon" size={28} strokeWidth={1.5} aria-hidden="true" />
          <Dialog.Title>Saving your choice</Dialog.Title>
          <Dialog.Description>One moment.</Dialog.Description>
        </div>}

        {phase === 'fix' && <>
          <span className="handoff-eyebrow">A fix you can try</span>
          <Dialog.Title>{fix?.title || 'Try this first'}</Dialog.Title>
          <Dialog.Description className="handoff-description">These steps may resolve the issue right away.</Dialog.Description>
          {fix?.steps?.length ? <ol className="handoff-steps">{fix.steps.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol>
            : <p className="handoff-prose">{fix?.text}</p>}
          {state.error && <p className="handoff-error" role="alert">{state.error}</p>}
          <DialogActions>
            <Button className="quiet-button" type="button" onClick={() => onDecision('handoff')}>I still need help</Button>
            <Button className="submit-button" type="button" onClick={() => onDecision('resolved')}>This fixed it</Button>
          </DialogActions>
        </>}

        {phase === 'handoff' && <>
          <span className="handoff-eyebrow">Incident {record?.id}</span>
          <Dialog.Title>Sent to {team}</Dialog.Title>
          <Dialog.Description className="handoff-description">Your incident is with the team. They have the details and a proposed expert fix.</Dialog.Description>
          <DialogActions>
            <Button className="quiet-button" type="button" onClick={onDone}>Done</Button>
            <Button className="submit-button" type="button" onClick={onView}>View incident</Button>
          </DialogActions>
        </>}

        {phase === 'resolved' && <>
          <span className="handoff-eyebrow">Incident {record?.id}</span>
          <Dialog.Title>Glad that worked</Dialog.Title>
          <Dialog.Description className="handoff-description">Your incident is marked resolved.</Dialog.Description>
          <DialogActions>
            <Button className="quiet-button" type="button" onClick={onDone}>Done</Button>
            <Button className="submit-button" type="button" onClick={onView}>View incident</Button>
          </DialogActions>
        </>}

        {phase === 'error' && <>
          <Dialog.Title>We couldn’t finish the review</Dialog.Title>
          <Dialog.Description className="handoff-description" role="alert">{state.error}</Dialog.Description>
          <DialogActions>
            <Button className="quiet-button" type="button" onClick={onBack}>Back to draft</Button>
            <Button className="submit-button" type="button" onClick={onRetry}>Try again</Button>
          </DialogActions>
        </>}
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
