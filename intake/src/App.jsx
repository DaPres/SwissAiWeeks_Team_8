import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button } from '@base-ui/react/button';
import { Popover } from '@base-ui/react/popover';
import { chipFields, resolvedFields, calculatePriority } from './incident-fields.js';
import { PriorityEditor } from './IncidentFieldEditors.jsx';
import { ChevronDown, Check, Moon, Sun } from 'lucide-react';
import '@fontsource-variable/geist';
import AdvicePanel from './AdvicePanel.jsx';
import AccountSwitcher from './AccountSwitcher.jsx';
import { accounts } from './accounts.js';
import IncidentDialog from './IncidentDialog.jsx';
import ValidationMessage from './ValidationMessage.jsx';
import IncidentsView from './IncidentsView.jsx';
import { useReadiness } from './useReadiness.js';
import { useGuidance } from './useGuidance.js';
import { decideIncident, listIncidents, processIncident } from './quality-api.js';

const emptyHiddenDetails = { summary: '', reporter: '', context: '', evidence: '' };

function ChipOptions({ config, value, onSelect }) {
  const [query, setQuery] = useState('');
  const options = config.options.filter(option => (config.format?.(option) || option).toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="chip-picker">
    <div className="chip-options" role="group" aria-label={`${config.label} options`}>
      {options.map(option => <button key={option} type="button" className="chip-option" aria-pressed={option === value} onClick={() => onSelect(option)}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            (event.key === 'ArrowDown' ? event.currentTarget.nextElementSibling : event.currentTarget.previousElementSibling)?.focus();
          }
        }}>{config.format?.(option) || option}<span aria-hidden="true">{option === value ? '✓' : ''}</span></button>)}
      {!options.length && <p className="no-options">No matching options</p>}
    </div>
    <input className="chip-search" type="search" aria-label={`Search ${config.label}`} placeholder={`Search ${config.label.toLowerCase()}…`} value={query} onChange={event => setQuery(event.target.value)}
      onKeyDown={event => { if (event.key === 'Enter' && options.length) { event.preventDefault(); onSelect(options[0]); } }} />
  </div>;
}

function EnrichmentChip({ id, config, onSave, index, disabled, values, loading, loadingIndex, invalidAttempt }) {
  const [open, setOpen] = useState(false);
  const value = values[id];
  const label = value ? (config.format?.(value) || value) : config.label;
  const save = next => { onSave(id, next); setOpen(false); };
  return <Popover.Root open={open} onOpenChange={setOpen}>
    <Popover.Trigger type="button" className="field-chip" data-filled={Boolean(value)} data-loading={loading && !value && !invalidAttempt}
      aria-invalid={Boolean(invalidAttempt && !value) || undefined}
      style={{ animationDelay: `${index * 45}ms`, '--chip-delay': `${loadingIndex * 220}ms` }} disabled={disabled}
      aria-label={`Edit ${config.label}${value ? `: ${label}` : ''}`} title={config.label}>
      {invalidAttempt > 0 && !value && <span key={invalidAttempt} className="chip-validation-outline" aria-hidden="true" />}
      <span className="chip-label" key={label}>{config.label}{value ? `: ${label}` : ''}</span>
      {value ? <Check size={15} strokeWidth={1.75} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
    </Popover.Trigger>
    <Popover.Portal><Popover.Positioner className="chip-positioner" side="bottom" align="start" sideOffset={8} collisionPadding={12}>
      <Popover.Popup className="chip-popover">
        <Popover.Title className="sr-only">{config.label}</Popover.Title>
        {config.kind === 'priority' ? <PriorityEditor key={`${values.urgency}:${values.impact}`} values={values} onSave={save} />
          : <ChipOptions config={config} value={value} onSelect={save} />}
      </Popover.Popup>
    </Popover.Positioner></Popover.Portal>
  </Popover.Root>;
}

function EnrichmentChips({ values, onSave, saving, loading, onInteract, invalidAttempt }) {
  const missing = Object.keys(chipFields).filter(field => !values[field]);
  return <div className="chip-list" onPointerDownCapture={onInteract} onFocusCapture={onInteract}>
    {Object.entries(chipFields).map(([id, config], index) =>
      <EnrichmentChip key={id} index={index} id={id} config={config} disabled={saving} onSave={onSave}
        values={values} loading={loading} loadingIndex={Math.max(0, missing.indexOf(id))} invalidAttempt={invalidAttempt} />)}
  </div>;
}

export default function App() {
  const [dark, setDark] = useState(() => { try { return (localStorage.getItem('intake-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark'; } catch { return false; } });
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); document.documentElement.style.colorScheme = dark ? 'dark' : 'light'; try { localStorage.setItem('intake-theme', dark ? 'dark' : 'light'); } catch { /* Storage can be unavailable. */ } }, [dark]);
  const [account, setAccount] = useState(() => { try { const savedAccount = localStorage.getItem('intake-demo-account'); return accounts.some(item => item.id === savedAccount) ? savedAccount : 'client'; } catch { return 'client'; } });
  const [view, setView] = useState('create');
  const [records, setRecords] = useState([]);
  const [listState, setListState] = useState({ loading: false, error: '' });
  const [listRefresh, setListRefresh] = useState(0);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [handoff, setHandoff] = useState(null);
  const saving = handoff?.phase === 'loading' || handoff?.phase === 'deciding';
  useEffect(() => { try { localStorage.setItem('intake-demo-account', account); } catch { /* Storage can be unavailable. */ } }, [account]);
  useEffect(() => {
    if (view !== 'incidents') return;
    const controller = new AbortController();
    setListState({ loading: true, error: '' });
    listIncidents(account, controller.signal)
      .then(items => { if (!controller.signal.aborted) { setRecords(items); setListState({ loading: false, error: '' }); } })
      .catch(failure => { if (!controller.signal.aborted) setListState({ loading: false, error: failure.message }); });
    return () => controller.abort();
  }, [view, account, listRefresh]);
  const [description, setDescription] = useState('');
  const descriptionInput = useRef(null);
  const [details, setDetails] = useState(() => ({ ...emptyHiddenDetails }));
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState('');
  const [validationClosing, setValidationClosing] = useState(false);
  function dismissValidation() { setValidationClosing(true); }
  const [submitAttempt, setSubmitAttempt] = useState(0);
  const [lastPanelReadiness, setLastPanelReadiness] = useState(null);
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setValidationClosing(true), 5000);
    return () => clearTimeout(timer);
  }, [error, submitAttempt]);
  useEffect(() => {
    if (!error || !validationClosing) return;
    const timer = setTimeout(() => setError(''), 350);
    return () => clearTimeout(timer);
  }, [error, validationClosing]);

  useLayoutEffect(() => {
    const input = descriptionInput.current;
    if (!input) return;
    const resize = () => {
      input.style.height = '0px';
      input.style.height = `${input.scrollHeight}px`;
    };
    resize();
    let width = input.getBoundingClientRect().width;
    const observer = new ResizeObserver(entries => {
      const nextWidth = entries[0].contentRect.width;
      if (nextWidth !== width) { width = nextWidth; resize(); }
    });
    observer.observe(input);
    return () => observer.disconnect();
  }, [description]);

  const snapshot = JSON.stringify({ description, details });
  const readiness = useReadiness(snapshot, attempt, Boolean(description.trim()) && view === 'create');
  const hasText = Boolean(description.trim());
  const typing = hasText && readiness.phase === 'waiting';
  const showEnrichment = hasText && (submitAttempt > 0 || !typing || lastPanelReadiness !== null);
  const panelReadiness = typing && lastPanelReadiness ? lastPanelReadiness : readiness;
  const guidance = useGuidance(hasText ? panelReadiness.result?.evaluationId : null, typing || view !== 'create');
  const inferred = (readiness.result || readiness.previousResult)?.inferred || {};
  const fieldValues = resolvedFields(details, inferred);
  const chipValues = Object.fromEntries(Object.keys(chipFields).map(id => [id,
    fieldValues[id] || '']));
  const missingFields = Object.entries(chipFields).filter(([id]) => !chipValues[id]).map(([, config]) => config.label);
  const readyToSubmit = hasText && !missingFields.length && !handoff && !error && readiness.phase === 'done'
    && guidance.result?.relevance === 'support' && guidance.result.improvements.length === 0;
  useEffect(() => {
    if (!hasText || typing) return;
    setLastPanelReadiness({ phase: readiness.phase, result: readiness.result, error: readiness.error });
  }, [hasText, typing, readiness.phase, readiness.result, readiness.error]);
  function edit(value) { setDescription(value); dismissValidation(); if (!value.trim()) setLastPanelReadiness(null); }
  function changeChip(field, value) {
    setDetails(previous => {
      if (field === 'priority') return { ...previous, urgency: value.urgency, impact: value.impact,
        priority: calculatePriority(value.urgency, value.impact) };
      const next = { ...previous, [field]: value };
      if (['urgency', 'impact'].includes(field)) {
        const priority = calculatePriority(field === 'urgency' ? value : fieldValues.urgency,
          field === 'impact' ? value : fieldValues.impact);
        if (priority) next.priority = priority;
        else delete next.priority;
      }
      return next;
    });
    dismissValidation();
  }
  async function processDraft() {
    setHandoff({ phase: 'loading' });
    try {
      const selected = chipValues;
      const record = await processIncident({ description, details, selected, account });
      setHandoff({ phase: record.enriched?.clientResolution ? 'fix' : 'handoff', record });
    } catch (failure) { setHandoff({ phase: 'error', error: failure.message }); }
  }
  async function chooseResolution(decision) {
    const record = handoff.record;
    setHandoff({ phase: 'deciding', record });
    try {
      const updated = await decideIncident(record.id, decision, account);
      setHandoff({ phase: decision === 'resolved' ? 'resolved' : 'handoff', record: updated });
    } catch (failure) {
      setHandoff({ phase: 'fix', record, error: failure.message });
    }
  }
  async function submit(event) {
    event.preventDefault();
    if (saving) return;
    if (!hasText || missingFields.length) {
      setSubmitAttempt(value => value + 1);
      setValidationClosing(false);
      setError('Please complete the incident details.');
      return;
    }
    setError('');
    await processDraft();
  }
  function resetDraft() { setDescription(''); setDetails({ ...emptyHiddenDetails }); setLastPanelReadiness(null); setError(''); setSubmitAttempt(0); }
  function switchAccount(nextAccount) { setAccount(nextAccount); setSelectedIncident(null); if (nextAccount !== 'client') setView('incidents'); }
  function showIncident() {
    const identifier = handoff.record.id;
    setHandoff(null); resetDraft(); setSelectedIncident(identifier); setListRefresh(value => value + 1); setView('incidents');
  }

  return <div className="app-shell min-h-svh bg-[var(--page)] text-[var(--text)] transition-colors duration-200">
    <div className="workspace">
    <header className="app-header">
      <a href="/" className="wordmark" aria-label="team8 home">team8</a>
      <nav className="header-nav" aria-label="Main navigation">
        <Button type="button" className="nav-item" aria-current={view === 'create' ? 'page' : undefined} onClick={() => { setView('create'); setSelectedIncident(null); }}>Create Incident</Button>
        <Button type="button" className="nav-item" aria-current={view === 'incidents' ? 'page' : undefined} onClick={() => { setView('incidents'); setSelectedIncident(null); }}>My Incidents</Button>
      </nav>
      <div className="header-controls"><AccountSwitcher account={account} onChange={switchAccount} />
        <Button type="button" className="theme-toggle" onClick={() => setDark(value => !value)} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>{dark ? <Sun size={17} /> : <Moon size={17} />}</Button></div>
    </header>
    <main className={`workspace-main ${view === 'create' ? 'workspace-create' : ''}`}>
      {view === 'create' ? <div className="create-stage">
        <div className="intake-layout"><div className="input-column"><form id="incident-form" onSubmit={submit} className={`composer enter ${typing ? 'typing-glow' : ''}`}>
          <label className="sr-only" htmlFor="incident-description">What do you need help with?</label>
          <textarea ref={descriptionInput} id="incident-description" placeholder="What do you need help with?" value={description} onPointerDown={dismissValidation} onFocus={dismissValidation} onChange={event => edit(event.target.value)} maxLength={10000} disabled={saving} spellCheck rows={3} />
          {hasText && <div className="composer-footer appear">
            {error && <ValidationMessage key={`validation-${submitAttempt}`} message={error} closing={validationClosing} />}
            <Button key={`submit-${submitAttempt}`} type="submit" className={`submit-button ${submitAttempt ? 'button-wobble' : ''}`} data-ready={readyToSubmit || undefined} aria-busy={saving}>{saving ? 'Submitting…' : 'Submit Incident'}</Button>
          </div>}
        </form>
          {showEnrichment && <EnrichmentChips onInteract={dismissValidation} values={fieldValues} onSave={changeChip} saving={saving} loading={['checking', 'slow', 'enriching'].includes(readiness.phase)} invalidAttempt={error && !validationClosing ? submitAttempt : 0} />}
        </div>
        {showEnrichment && !error && <AdvicePanel readiness={panelReadiness} onRetry={() => setAttempt(value => value + 1)} guidance={guidance} fieldsComplete={!missingFields.length} />}
        </div>
      </div> : <IncidentsView account={account} records={records} loading={listState.loading} error={listState.error}
        onRetry={() => setListRefresh(value => value + 1)} selectedId={selectedIncident} onSelect={setSelectedIncident}
        onReviewFix={record => setHandoff({ phase: 'fix', record })} />}
    </main></div>
    <IncidentDialog state={handoff} onDecision={chooseResolution} onRetry={processDraft} onBack={() => setHandoff(null)}
      onDone={() => { setHandoff(null); resetDraft(); setListRefresh(value => value + 1); }} onView={showIncident} />
  </div>;
}
