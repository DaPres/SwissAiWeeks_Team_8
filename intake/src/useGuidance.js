import { useEffect, useState } from 'react';
import { requestSuggestion } from './quality-api.js';

export function useGuidance(evaluationId, paused) {
  const [response, setResponse] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${evaluationId}:${attempt}`;
  useEffect(() => {
    if (!evaluationId || paused) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      requestSuggestion(evaluationId, AbortSignal.any([controller.signal, AbortSignal.timeout(20000)]))
        .then(result => { if (!controller.signal.aborted) setResponse({ key, result }); })
        .catch(error => { if (!controller.signal.aborted) setResponse({ key,
          error: error.name === 'TimeoutError' ? 'Suggestions timed out. Try again.' : error.message }); });
    }, 500);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [evaluationId, key, paused]);
  const current = response?.key === key ? response : null;
  return { ...current, retry: () => setAttempt(value => value + 1) };
}
