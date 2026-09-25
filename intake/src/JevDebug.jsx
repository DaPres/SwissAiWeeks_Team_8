import { ChevronDown } from 'lucide-react';

const phaseLabels = {
  idle: 'Waiting for input', waiting: 'Debouncing', checking: 'Checking', slow: 'Checking',
  done: 'Complete', error: 'Check failed',
  enriching: 'Jev Complete · Finding Historical Resolutions',
};

export default function JevDebug({ readiness }) {
  const { debug, debugIsCurrent, phase } = readiness;
  const pending = ['checking', 'slow', 'waiting', 'enriching'].includes(phase);
  return <details className="jev-debug">
    <summary><span>Jev Debug</span><span className="jev-debug-status" data-pending={pending}>
      {phaseLabels[phase]}{debugIsCurrent && debug?.durationMs != null ? ` · ${(debug.durationMs / 1000).toFixed(2)}s` : ''}
    </span><ChevronDown size={14} aria-hidden="true" /></summary>
    <div className="jev-debug-content">
      {debug && !debugIsCurrent && <p className="jev-debug-note">{pending
        ? 'Showing the previous check while the current draft is evaluated.' : 'Showing the previous check.'}</p>}
      <div className="jev-debug-grid">
        <section><h3>Request</h3><pre tabIndex={0} aria-label="Jev request">{debug
          ? JSON.stringify(debug.request, null, 2) : 'The actual Jev request will appear when the check returns.'}</pre></section>
        <section><h3>Response</h3><pre tabIndex={0} aria-label="Jev response">{debug
          ? JSON.stringify(debug.response, null, 2) : 'No response yet.'}</pre></section>
      </div>
    </div>
  </details>;
}
