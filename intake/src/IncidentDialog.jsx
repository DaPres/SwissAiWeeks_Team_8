import { Dialog } from '@base-ui/react/dialog';
import { Button } from '@base-ui/react/button';

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
        {(phase === 'loading' || phase === 'deciding') && <div className="handoff-wait" role="status">
          <div className="handoff-orbit" aria-hidden="true"><span /><span /><span /></div>
          <Dialog.Title>{phase === 'loading' ? 'Reviewing your incident' : 'Saving your choice'}</Dialog.Title>
          <Dialog.Description>{phase === 'loading' ? 'Looking for a fix and the right team.' : 'One moment.'}</Dialog.Description>
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
