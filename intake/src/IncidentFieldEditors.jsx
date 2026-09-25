import { useState } from 'react';
import { calculatePriority, levels } from './incident-fields.js';

const titleCase = value => value ? value[0].toUpperCase() + value.slice(1) : '—';

export function PriorityEditor({ values, onSave }) {
  const [urgency, setUrgency] = useState(values.urgency || '');
  const [impact, setImpact] = useState(values.impact || '');
  const priority = calculatePriority(urgency, impact);
  return <div>
    <div className="priority-inputs">
      {[{ label: 'Urgency', value: urgency, change: setUrgency }, { label: 'Impact', value: impact, change: setImpact }].map(field =>
        <fieldset key={field.label}><legend>{field.label}</legend>{levels.map(level =>
          <button key={level} type="button" className="priority-level" aria-label={`Set ${field.label}: ${titleCase(level)}`}
            aria-pressed={field.value === level} onClick={() => field.change(level)}>{titleCase(level)}</button>)}</fieldset>)}
    </div>
    <div className="priority-result"><span>Priority</span><output aria-live="polite">{titleCase(priority)}</output></div>
    <button type="button" className="field-save" disabled={!priority} onClick={() => onSave({ urgency, impact })}>Apply Priority</button>
  </div>;
}

export function ResolutionCommentEditor({ value, sources = [], onSave }) {
  const [text, setText] = useState(value || '');
  return <div className="resolution-editor">
    <textarea aria-label="Resolution Comment" placeholder="Write a concrete resolution note…" value={text}
      onChange={event => setText(event.target.value)} maxLength={2000} rows={6} />
    {sources.length > 0 && <details className="resolution-sources"><summary>Similar Historical Tickets</summary>
      {sources.slice(0, 3).map(source => <p key={source.id}><span>{source.id}</span>{source.text}</p>)}
    </details>}
    <button type="button" className="field-save" disabled={!text.trim()} onClick={() => onSave(text.trim())}>Save Comment</button>
  </div>;
}
