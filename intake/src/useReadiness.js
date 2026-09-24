import { useEffect, useState } from 'react';
import { evaluateDescription } from './quality-api.js';

export function useReadiness(snapshot, attempt, hasText) {
  const [evaluation, setEvaluation] = useState(null);
  const key = `${attempt}:${snapshot}`;
  const current = evaluation?.key === key ? evaluation : null;
  useEffect(() => {
    if (!hasText) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setEvaluation(previous => ({ key, phase: 'checking', lastResult: previous?.result ?? previous?.lastResult, lastScore: previous?.result?.readiness ?? previous?.lastScore ?? 0 }));
      try {
        const draft = JSON.parse(snapshot);
        const result = await evaluateDescription(draft.description,
          AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]), draft.details);
        if (!Number.isFinite(result.readiness) || result.readiness < 0 || result.readiness > 100 || !result.evaluationId) throw new Error('Readiness check returned an invalid result.');
        if (!controller.signal.aborted) {
          setEvaluation({ key, phase: 'done', result });
        }
      } catch (error) {
        if (!controller.signal.aborted) setEvaluation({ key, phase: 'error', error: error.name === 'TimeoutError' ? 'Readiness check timed out. Please retry.' : error.message });
      }
    }, 450);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [snapshot, key, hasText]);
  useEffect(() => {
    if (evaluation?.phase !== 'checking') return;
    const slowTimer = setTimeout(() => setEvaluation(previous => previous?.phase === 'checking' ? { ...previous, phase: 'slow' } : previous), 4000);
    return () => clearTimeout(slowTimer);
  }, [evaluation?.phase, evaluation?.key]);
  useEffect(() => {
    if (evaluation?.phase !== 'done') return;
    const evaluatedKey = evaluation.key;
    const expiry = setTimeout(() => setEvaluation({ key: evaluatedKey, phase: 'error', error: 'Readiness check expired. Check again to submit.' }), 590000);
    return () => clearTimeout(expiry);
  }, [evaluation?.phase, evaluation?.key]);
  return {
    phase: !hasText ? 'idle' : current?.phase || 'waiting',
    result: current?.phase === 'done' ? current.result : null,
    error: current?.error,
    previousResult: evaluation?.result ?? evaluation?.lastResult,
    score: hasText ? current?.result?.readiness ?? evaluation?.result?.readiness ?? evaluation?.lastScore ?? 0 : 0,
  };
}
