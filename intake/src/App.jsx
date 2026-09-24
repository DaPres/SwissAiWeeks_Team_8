import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button } from '@base-ui/react/button';
import { Popover } from '@base-ui/react/popover';
import catalog from './catalog.json';
import { ChevronDown, Moon, Sun } from 'lucide-react';
import '@fontsource-variable/geist';
import AdvicePanel from './AdvicePanel.jsx';
import { useReadiness } from './useReadiness.js';
import { previewTriagemate, submitIncident } from './quality-api.js';

const chipFields = {
  service: { label: 'Service', options: catalog['Affected Business or IT Services'] },
  department: { label: 'Team', options: catalog['Service Team(s)'] },
  entity: { label: 'Entity', options: catalog['Business Entity'] },
  urgency: { label: 'Urgency', options: ['lowest', 'low', 'medium', 'high', 'highest'] },
  impact: { label: 'Impact', options: ['lowest', 'low', 'medium', 'high', 'highest'] },
};
const emptyHiddenDetails = { summary: '', reporter: '', assignee: '', context: '', evidence: '' };

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

function EnrichmentChip({ id, config, onSave, index, disabled }) {
  const [open, setOpen] = useState(false);
  return <Popover.Root open={open} onOpenChange={setOpen}>
    <Popover.Trigger type="button" className="field-chip" style={{ animationDelay: `${index * 45}ms` }} disabled={disabled} aria-label={`Edit ${config.label}`}>
      <span className="chip-label">{config.label}</span><ChevronDown size={12} />
    </Popover.Trigger>
    <Popover.Portal><Popover.Positioner className="chip-positioner" side="bottom" align="start" sideOffset={8} collisionPadding={12}>
      <Popover.Popup className="chip-popover">
        <Popover.Title className="sr-only">{config.label}</Popover.Title>
        <ChipOptions config={config} value="" onSelect={option => { onSave(id, option); setOpen(false); }} />

      </Popover.Popup>
    </Popover.Positioner></Popover.Portal>
  </Popover.Root>;
}

function EnrichmentChips({ values, onSave, saving }) {
  return <div className="chip-list" data-empty={Object.values(values).every(value => Boolean(value))}>
    {Object.entries(chipFields).map(([id, config], index) => <span className="chip-slot" data-hidden={Boolean(values[id])} aria-hidden={Boolean(values[id])} inert={Boolean(values[id])} key={id}>
      <EnrichmentChip key={`${id}:${Boolean(values[id]) || saving}`} index={index} id={id} config={config} disabled={Boolean(values[id]) || saving} onSave={onSave} />
    </span>)}
  </div>;
}

function SelectedChips({ values, onClear, saving }) {
  const scrollRef = useRef(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  const signature = Object.values(values).join('\u0000');
  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const update = () => {
      const left = element.scrollLeft > 1;
      const right = element.scrollWidth - element.clientWidth - element.scrollLeft > 1;
      setEdges(previous => previous.left === left && previous.right === right ? previous : { left, right });
    };
    const observer = new ResizeObserver(update);
    observer.observe(element);
    for (const chip of element.children) observer.observe(chip);
    element.addEventListener('scroll', update, { passive: true });
    update();
    return () => { observer.disconnect(); element.removeEventListener('scroll', update); };
  }, [signature]);
  return <div ref={scrollRef} className="selected-chips" role="group" aria-label="Selected incident details" data-fade-left={edges.left} data-fade-right={edges.right}>
    {Object.entries(chipFields).map(([id, config]) => <span className="selected-chip-slot" data-visible={Boolean(values[id])} aria-hidden={!values[id]} inert={!values[id]} key={id}>
      <button key={values[id]} type="button" className="selected-chip" disabled={!values[id] || saving} aria-label={`Clear ${config.label}: ${values[id]}`} onClick={() => onClear(id)}>{values[id]}</button>
    </span>)}
  </div>;
}

function Receipt({ saved, onNew }) {
  return <section className="receipt enter"><h1>Incident Submitted</h1><p className="muted">{saved.id}</p><div className="receipt-card">{saved.incident.Description}</div><Button className="submit-button" onClick={onNew}>New Incident</Button></section>;
}

export default function App() {
  const [dark, setDark] = useState(() => { try { return (localStorage.getItem('intake-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark'; } catch { return false; } });
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); document.documentElement.style.colorScheme = dark ? 'dark' : 'light'; try { localStorage.setItem('intake-theme', dark ? 'dark' : 'light'); } catch { /* Storage can be unavailable. */ } }, [dark]);
  const [description, setDescription] = useState('');
  const descriptionInput = useRef(null);
  const [details, setDetails] = useState(() => ({ ...emptyHiddenDetails }));
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState('');
  const [submitAttempt, setSubmitAttempt] = useState(0);
  const [lastPanelReadiness, setLastPanelReadiness] = useState(null);
  const [demo, setDemo] = useState(null);
  const demoRequest = useRef(null);
  const demoLoading = demo?.status === 'loading';

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
  const inferred = (readiness.result || readiness.previousResult)?.inferred || {};
  const chipValues = Object.fromEntries(Object.keys(chipFields).map(id => [id,
    Object.prototype.hasOwnProperty.call(details, id) ? details[id] : inferred[id] || '']));
  useEffect(() => {
    if (!hasText || typing) return;
    setLastPanelReadiness({ phase: readiness.phase, result: readiness.result, error: readiness.error });
  }, [hasText, typing, readiness.phase, readiness.result, readiness.error]);
  function clearDemo() { demoRequest.current?.abort(); demoRequest.current = null; setDemo(null); }
  function edit(value) { clearDemo(); setDescription(value); setError(''); if (!value.trim()) { setDetails({ ...emptyHiddenDetails }); setLastPanelReadiness(null); } }
  function changeChip(field, value) { clearDemo(); setDetails(previous => ({ ...previous, [field]: value })); setError(''); }
  async function runDemo() {
    if (!hasText || demoLoading) return;
    const controller = new AbortController();
    demoRequest.current = controller;
    setDemo({ status: 'loading' });
    try {
      const result = await previewTriagemate({ description, details: { ...details, ...chipValues } },
        AbortSignal.any([controller.signal, AbortSignal.timeout(60000)]));
      if (demoRequest.current === controller) setDemo({ json: JSON.stringify(result, null, 2) });
    } catch (failure) {
      if (demoRequest.current === controller) setDemo({ error: failure.name === 'TimeoutError' ? 'TriageMate preview timed out.' : failure.message });
    } finally {
      if (demoRequest.current === controller) demoRequest.current = null;
    }
  }
  async function submit(event) {
    event.preventDefault();
    if (saving) return;
    if (!ready) {
      setSubmitAttempt(value => value + 1);
      setError(!hasText ? 'Please describe your issue.' : readiness.phase === 'error'
        ? 'Retry the check before submitting.' : readiness.phase === 'done'
          ? 'Please provide more details.' : 'Checking your latest changes…');
      return;
    }
    setSaving(true); setError('');
    try { setSaved(await submitIncident({ description, details }, readiness.result.evaluationId)); clearDemo(); }
    catch (failure) { setError(failure.message); setAttempt(value => value + 1); }
    finally { setSaving(false); }
  }
  function reset() { clearDemo(); setDescription(''); setDetails({ ...emptyHiddenDetails }); setLastPanelReadiness(null); setSaved(null); setError(''); setSubmitAttempt(0); }

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
          {error && <p key={submitAttempt} className="check-error appear" role="alert">{error}</p>}
          {hasText && <div className="composer-footer appear">
            <SelectedChips values={chipValues} onClear={field => changeChip(field, '')} saving={saving} />
            <Button key={submitAttempt} type="submit" className={`submit-button ${submitAttempt ? 'button-wobble' : ''}`} aria-busy={saving}>{saving ? 'Submitting…' : 'Submit Incident'}</Button>
          </div>}
        </form>
          {showEnrichment && <EnrichmentChips values={chipValues} onSave={changeChip} saving={saving} />}
        </div>
        {showEnrichment && <AdvicePanel readiness={panelReadiness} ready={panelReady} paused={typing} onRetry={() => setAttempt(value => value + 1)} />}
        </div>
        <section className="demo-section" aria-label="TriageMate demo">
          <Button type="button" className="demo-button" onClick={runDemo} disabled={!hasText || demoLoading} aria-busy={demoLoading}>{demoLoading ? 'Running TriageMate…' : 'Run TriageMate Demo'}</Button>
          {demo?.error && <p className="demo-error" role="alert">{demo.error}</p>}
          {demo?.json && <textarea className="demo-json" aria-label="TriageMate JSON" readOnly spellCheck={false} value={demo.json} rows={18} />}
        </section>
      </>}
    </main>
  </div>;
}
