import { useEffect, useState } from 'react';
import { Button } from '@base-ui/react/button';
import { requestSuggestion } from './quality-api.js';

function Loading() {
  return <div className="advice-loading" role="status" aria-label="Loading suggestions"><span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span></div>;
}

function Suggestions({ evaluationId, paused }) {
  const [response, setResponse] = useState(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (paused) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      requestSuggestion(evaluationId, AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]))
        .then(result => { if (!controller.signal.aborted) setResponse({ result }); })
        .catch(error => { if (!controller.signal.aborted) setResponse({ error: error.name === 'TimeoutError' ? 'Suggestions timed out. Try again.' : error.message }); });
    }, 500);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [evaluationId, attempt, paused]);
  if (!response) return <Loading />;
  if (response.error) return <div className="advice-content" role="alert"><p>{response.error}</p><Button type="button" className="text-button" onClick={() => { setResponse(null); setAttempt(value => value + 1); }}>Retry</Button></div>;
  const message = response.result.improvements[0]?.detail || response.result.summary;
  return <div className="advice-content appear"><p>{message}</p></div>;
}

export default function AdvicePanel({ readiness, paused, onRetry }) {
  let content;
  if (readiness.phase === 'idle') content = <div className="advice-content"><p>Describe your issue to get suggestions.</p></div>;
  else if (readiness.phase === 'error') content = <div className="advice-content" role="alert"><p>{readiness.error}</p><Button type="button" className="text-button" onClick={onRetry}>Retry</Button></div>;
  else if (readiness.result) content = <Suggestions key={readiness.result.evaluationId} evaluationId={readiness.result.evaluationId} paused={paused} />;
  else content = <Loading />;
  return <aside className="composer advice-panel enter" aria-label="AI Suggestions" aria-live="polite">{content}</aside>;
}
