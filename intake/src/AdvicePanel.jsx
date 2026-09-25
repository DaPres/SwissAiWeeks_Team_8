import { Button } from '@base-ui/react/button';

function Loading() {
  return <div className="advice-loading" role="status" aria-label="Loading suggestions"><span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span></div>;
}

function Suggestions({ response, fieldsComplete }) {
  if (response.error) return <div className="advice-content" role="alert"><p>{response.error}</p><Button type="button" className="text-button" onClick={response.retry}>Retry</Button></div>;
  if (!response.result) return <Loading />;
  const actionable = response.result.relevance === 'support' && response.result.improvements.length === 0;
  const message = actionable
    ? (fieldsComplete ? 'Your incident looks good. Ready to submit.' : 'Your description looks good. Complete the remaining fields to submit.')
    : response.result.improvements[0]?.detail || response.result.summary;
  return <div className="advice-content appear"><p>{message}</p></div>;
}

export default function AdvicePanel({ readiness, onRetry, guidance, fieldsComplete }) {
  let content;
  if (readiness.phase === 'idle') content = <div className="advice-content"><p>Describe your issue to get suggestions.</p></div>;
  else if (readiness.phase === 'error') content = <div className="advice-content" role="alert"><p>{readiness.error}</p><Button type="button" className="text-button" onClick={onRetry}>Retry</Button></div>;
  else if (readiness.result) content = <Suggestions response={guidance} fieldsComplete={fieldsComplete} />;
  else content = <Loading />;
  return <aside className="composer advice-panel enter" aria-label="AI Suggestions" aria-live="polite">{content}</aside>;
}
