export async function evaluateDescription(description, signal, details = {}) {
  const response = await fetch('/api/description-quality', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, details }),
    signal,
  });
  if (!response.ok) {
    let message = 'Description check failed. Please try again.';
    try {
      const error = await response.json();
      if (typeof error.error === 'string') message = error.error;
    } catch { /* Keep a useful message for non-JSON proxy errors. */ }
    throw new Error(message);
  }
  return response.json();
}

export async function requestSuggestion(evaluationId, signal) {
  const response = await fetch('/api/description-suggestion', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ evaluationId }), signal,
  });
  if (!response.ok) {
    let message = 'Could not get a suggestion. Please try again.';
    try {
      const data = await response.json();
      if (typeof data.error === 'string') message = data.error;
    } catch { /* Proxy errors may not be JSON. */ }
    throw new Error(message);
  }
  return response.json();
}

export async function submitIncident(draft, evaluationId) {
  const response = await fetch('/api/incidents', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...draft, evaluationId }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Could not submit incident.');
  }
  return response.json();
}

export async function previewTriagemate(draft, signal) {
  const response = await fetch('/api/triagemate-demo', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft), signal,
  });
  if (!response.ok) {
    let message = 'TriageMate preview failed. Please try again.';
    try {
      const data = await response.json();
      if (typeof data.error === 'string') message = data.error;
    } catch { /* Keep the fallback for a non-JSON server error. */ }
    throw new Error(message);
  }
  return response.json();
}
