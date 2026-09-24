import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button } from '@base-ui/react/button';
import { Popover } from '@base-ui/react/popover';
import catalog from './catalog.json';
import { ChevronDown, Moon, Sun } from 'lucide-react';
import '@fontsource-variable/geist';
import { TextField } from './fields.jsx';
import AdvicePanel from './AdvicePanel.jsx';
import { useReadiness } from './useReadiness.js';
import { submitIncident } from './quality-api.js';

const chipFields = {
  summary: { label: 'Summary' },
  service: { label: 'Service', options: catalog['Affected Business or IT Services'] },
  department: { label: 'Team', options: catalog['Service Team(s)'] },
  entity: { label: 'Entity', options: catalog['Business Entity'] },
  urgency: { label: 'Urgency', options: ['lowest', 'low', 'medium', 'high', 'highest'] },
  impact: { label: 'Impact', options: ['lowest', 'low', 'medium', 'high', 'highest'] },
  reporter: { label: 'Reporter' }, assignee: { label: 'Assignee' },
  context: { label: 'Context' }, evidence: { label: 'Evidence' },
};

function ChipOptions({ config, value, onSelect }) {
  const [query, setQuery] = useState('');
  const options = config.options.filter(option => option.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="chip-picker">
    <div className="chip-options" role="group" aria-label={`${config.label} options`}>
      {options.map(option => <button key={option} type="button" className="chip-option" aria-pressed={option === value} onClick={() => onSelect(option)}
        onKeyDown={event => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            (event.key === 'ArrowDown' ? event.currentTarget.nextElementSibling : event.currentTarget.previousElementSibling)?.focus();
          }
        }}>{option}<span aria-hidden="true">{option === value ? '✓' : ''}</span></button>)}
      {!options.length && <p className="no-options">No matching options</p>}
    </div>
    <input className="chip-search" type="search" aria-label={`Search ${config.label}`} placeholder={`Search ${config.label.toLowerCase()}…`} value={query} onChange={event => setQuery(event.target.value)}
      onKeyDown={event => { if (event.key === 'Enter' && options.length) { event.preventDefault(); onSelect(options[0]); } }} />
  </div>;
}

function EnrichmentChip({ id, config, value, onSave, index }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  return <Popover.Root open={open} onOpenChange={next => { if (next) setDraft(value); setOpen(next); }}>
    <Popover.Trigger type="button" className="field-chip" style={{ animationDelay: `${index * 45}ms` }} data-filled={Boolean(value)} aria-label={`Edit ${config.label}${value ? ': ' + value : ''}`}>
      <span key={value} className={value ? 'chip-value chip-bounce' : 'chip-value'}><span className="chip-label">{config.label}</span>{value && <span className="chip-content">{value}</span>}</span><ChevronDown size={12} />
    </Popover.Trigger>
    <Popover.Portal><Popover.Positioner className="chip-positioner" side="bottom" align="start" sideOffset={8} collisionPadding={12}>
      <Popover.Popup className="chip-popover">
        <Popover.Title className="popover-title">{config.label}</Popover.Title>
        {config.options ? <ChipOptions config={config} value={value} onSelect={option => { onSave(id, option); setOpen(false); }} /> :
          <form onSubmit={event => { event.preventDefault(); event.stopPropagation(); onSave(id, draft.trim()); setOpen(false); }}>
            <TextField label={config.label} name={`chip-${id}`} value={draft} onChange={setDraft} maxLength={2000} multiline={id === 'context' || id === 'evidence'} />
            <div className="popover-actions"><Popover.Close className="text-button" type="button">Cancel</Popover.Close><button className="popover-save" type="submit">Save</button></div>
          </form>}

      </Popover.Popup>
    </Popover.Positioner></Popover.Portal>
  </Popover.Root>;
}

function EnrichmentChips({ details, inferred, onSave }) {
  return <div className="chip-list">{Object.entries(chipFields).map(([id, config], index) => <EnrichmentChip index={index} key={id} id={id} config={config} value={details[id] || inferred[id] || ''} onSave={onSave} />)}</div>;
}

function Receipt({ saved, onNew }) {
  return <section className="receipt enter"><h1>Incident Submitted</h1><p className="muted">{saved.id}</p><div className="receipt-card">{saved.incident.Description}</div><Button className="submit-button" onClick={onNew}>New Incident</Button></section>;
}

export default function App() {
  const [dark, setDark] = useState(() => { try { return (localStorage.getItem('intake-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark'; } catch { return false; } });
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); document.documentElement.style.colorScheme = dark ? 'dark' : 'light'; try { localStorage.setItem('intake-theme', dark ? 'dark' : 'light'); } catch { /* Storage can be unavailable. */ } }, [dark]);
  const [description, setDescription] = useState('');
  const descriptionInput = useRef(null);
  const [details, setDetails] = useState({});
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState('');
  const [lastPanelReadiness, setLastPanelReadiness] = useState(null);

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
  }, [description, saved]);

  const snapshot = JSON.stringify({ description, details });
  const readiness = useReadiness(saved ? JSON.stringify({ description: '', details: {} }) : snapshot, attempt, Boolean(description.trim()) && !saved);
  const hasText = Boolean(description.trim());
  const typing = hasText && readiness.phase === 'waiting';
  const showEnrichment = hasText && (!typing || lastPanelReadiness !== null);
  const panelReadiness = typing && lastPanelReadiness ? lastPanelReadiness : readiness;
  const panelReady = panelReadiness.phase === 'done' && panelReadiness.result?.readiness >= 80;
  const ready = readiness.phase === 'done' && readiness.result.readiness >= 80;
  useEffect(() => {
    if (!hasText || typing) return;
    setLastPanelReadiness({ phase: readiness.phase, result: readiness.result, error: readiness.error });
  }, [hasText, typing, readiness.phase, readiness.result, readiness.error]);
  function edit(value) { setDescription(value); setError(''); if (!value.trim()) { setDetails({}); setLastPanelReadiness(null); } }
  async function submit(event) {
    event.preventDefault();
    if (saving) return;
    if (!ready) return;
    setSaving(true); setError('');
    try { setSaved(await submitIncident({ description, details }, readiness.result.evaluationId)); }
    catch (failure) { setError(failure.message); setAttempt(value => value + 1); }
    finally { setSaving(false); }
  }
  function reset() { setDescription(''); setDetails({}); setLastPanelReadiness(null); setSaved(null); setError(''); }

  return <div className="min-h-svh bg-[var(--page)] text-[var(--text)] transition-colors duration-200">
    <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-7 sm:px-10">
      <a href="/" className="wordmark" aria-label="Intake home">intake<span>.</span></a>
      <Button type="button" className="theme-toggle" onClick={() => setDark(value => !value)} aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}>{dark ? <Sun size={17} /> : <Moon size={17} />}</Button>
    </header>
    <main className="mx-auto w-[calc(100%-32px)] max-w-6xl pt-[12vh] pb-16 sm:pt-[16vh]">
      {saved ? <Receipt saved={saved} onNew={reset} /> : <>
        <div className="intake-layout"><div className="input-column"><form id="incident-form" onSubmit={submit} className={`composer enter ${typing ? 'typing-glow' : ''}`}>
          <label className="sr-only" htmlFor="incident-description">What do you need help with?</label>
          <textarea ref={descriptionInput} id="incident-description" placeholder="What do you need help with?" value={description} onChange={event => edit(event.target.value)} maxLength={10000} disabled={saving} spellCheck rows={3} />
          {error && <p className="check-error" role="alert">{error}</p>}
        </form>
          {showEnrichment && <EnrichmentChips details={details} inferred={(readiness.result || readiness.previousResult)?.inferred || {}} onSave={(field, value) => { setDetails(previous => ({ ...previous, [field]: value })); setError(''); }} />}
        </div>
        {showEnrichment && <AdvicePanel readiness={panelReadiness} ready={panelReady} canSubmit={ready} paused={typing} saving={saving} onRetry={() => setAttempt(value => value + 1)} />}
        </div>
      </>}
    </main>
  </div>;
}
