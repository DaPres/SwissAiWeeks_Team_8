import { useEffect, useRef, useState } from 'react'
import { api, type AssistProgress, type AssistResult, type Catalog, type Draft, type Llms, type Ticket } from './api'
import { PriorityPill, short } from './components'
import { AnalysisProgress } from './AnalysisProgress'
import { ModelMark, ModelPicker } from './ModelPicker'
import type { Level } from './types'

const MAX_IMAGES = 4
const MAX_BYTES = 5 * 1024 * 1024

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result as string)
    r.onerror = () => reject(r.error)
    r.readAsDataURL(file)
  })
}

export function Assist({ catalog, onFoldChange }: { catalog: Catalog | null; onFoldChange?: (folded: boolean) => void }) {
  const [text, setText] = useState('')
  const [images, setImages] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [analysing, setAnalysing] = useState(false)
  const [debug, setDebug] = useState(() => localStorage.getItem('assist-debug') === 'true')
  const [llms, setLlms] = useState<Llms | null>(null)
  const [llm, setLlm] = useState<string | null>(() => localStorage.getItem('assist-llm'))
  const [progress, setProgress] = useState<AssistProgress[]>([])
  const [analysedImages, setAnalysedImages] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AssistResult | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  // After submit the composer folds into a compact question bar (and the page hero folds away).
  const [folded, setFolded] = useState(false)
  const [asked, setAsked] = useState<{ text: string; images: string[]; llm: string | null } | null>(null)
  const [outcome, setOutcome] = useState<{ kind: 'solved' } | { kind: 'ticket'; ticket: Ticket } | null>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => { textRef.current?.focus() }, [])
  const askedProvider = llms?.providers.find((p) => p.id === (asked?.llm ?? llms.default))
  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => { localStorage.setItem('assist-debug', String(debug)) }, [debug])
  useEffect(() => {
    api.llms().then((l) => {
      setLlms(l)
      setLlm((current) => (l.providers.some((p) => p.id === current) ? current : l.providers.length ? l.default : null))
    }).catch(() => setLlms(null))
  }, [])
  useEffect(() => { if (llm) localStorage.setItem('assist-llm', llm) }, [llm])
  // hero stays folded while editing; only a new question brings it back
  // Fold as soon as the user starts describing the problem; stays folded (no bounce while typing/editing)
  // until "New question" / "Clear".
  const engaged = asked !== null || text.length > 0 || images.length > 0
  const [started, setStarted] = useState(false)
  if (engaged && !started) setStarted(true)
  useEffect(() => { onFoldChange?.(started) }, [started, onFoldChange])
  useEffect(() => () => onFoldChange?.(false), [onFoldChange])

  async function addFiles(files: File[]) {
    const imgs = files.filter((f) => f.type.startsWith('image/'))
    if (!imgs.length) return
    const tooBig = imgs.find((f) => f.size > MAX_BYTES)
    if (tooBig) { setError(`${tooBig.name || 'Image'} is larger than 5 MB`); return }
    const urls = await Promise.all(imgs.map(readAsDataUrl))
    setImages((prev) => [...prev, ...urls].slice(0, MAX_IMAGES))
    setError(null)
  }

  function onPaste(e: React.ClipboardEvent) {
    const files = Array.from(e.clipboardData.files)
    if (files.some((f) => f.type.startsWith('image/'))) {
      e.preventDefault()
      void addFiles(files)
    }
  }

  async function submit() {
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(true); setAnalysing(true); setError(null); setResult(null); setDraft(null); setOutcome(null); setProgress([])
    setAnalysedImages(images.length > 0)
    setAsked({ text, images, llm })
    setFolded(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    try {
      const r = await api.assistStream(text, images, debug, llm, (event) => setProgress((current) => [...current, event]), controller.signal)
      setResult(r)
      setDraft(r.draft)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError((e as Error).message)
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setBusy(false); setAnalysing(false)
    }
  }

  function reset() {
    abortRef.current?.abort()
    setText(''); setImages([]); setResult(null); setDraft(null); setOutcome(null); setError(null); setProgress([])
    setAsked(null); setFolded(false); setStarted(false)
    requestAnimationFrame(() => textRef.current?.focus())
  }

  function editQuestion() {
    setFolded(false)
    requestAnimationFrame(() => textRef.current?.focus())
  }

  async function markSolved() {
    if (!result) return
    await api.feedback(result.assistId, true)
    setOutcome({ kind: 'solved' })
  }

  async function createTicket() {
    if (!result || !draft) return
    setBusy(true)
    try {
      if (result.selfService.possible) await api.feedback(result.assistId, false)
      const ticket = await api.createTicket(result.assistId, draft)
      setOutcome({ kind: 'ticket', ticket })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  function updateDraft(patch: Partial<Draft>) {
    if (!draft || !catalog) return
    const next = { ...draft, ...patch }
    const svc = catalog.services.find((s) => s.name === next.service)
    if (svc) { next.team = svc.team; next.critical = svc.critical }
    if (patch.service && patch.service !== result?.draft.service) { next.assignee = null; next.assigneeReason = 'service changed — team queue' }
    if (patch.service === result?.draft.service) { next.assignee = result!.draft.assignee; next.assigneeReason = result!.draft.assigneeReason }
    next.priority = catalog.matrix[next.urgency][next.impact]
    setDraft(next)
  }

  const canSubmit = !busy && (text.trim().length > 0 || images.length > 0)

  return (
    <div className="assist">
      {folded && asked ? (
        <div className="card question-bar">
          <div className="question-bar-body">
            <div className="eyebrow">Your question</div>
            <p className="question-bar-text">{asked.text.trim() || <span className="muted">Screenshot only</span>}</p>
            <div className="question-bar-meta">
              {asked.images.length > 0 && (
                <span className="question-bar-thumbs">
                  {asked.images.map((src, i) => <img key={i} src={src} alt={`Screenshot ${i + 1}`} />)}
                </span>
              )}
              {askedProvider && <span className="question-bar-model"><ModelMark id={askedProvider.id} /> {askedProvider.label}</span>}
            </div>
          </div>
          <div className="question-bar-actions">
            <button className="btn ghost" onClick={editQuestion} disabled={busy}>Edit</button>
            <button className="btn" onClick={reset}>New question</button>
          </div>
        </div>
      ) : (
      <div className="card composer">
        <div className="assist-title-row">
          <h3>What’s going wrong?</h3>
          <label className="debug-switch" title="Show retrieval and tool activity while the agent works">
            <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} disabled={analysing} />
            <span className="debug-switch-track" aria-hidden="true" />
            <span>Debug</span>
          </label>
        </div>
        <p className="sub">Describe the problem in your own words. Paste (⌘V) or drop screenshots — they’re read by the assistant too.</p>
        <div
          className={`dropbox${dragging ? ' dragging' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(Array.from(e.dataTransfer.files)) }}
        >
          <textarea
            ref={textRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onPaste={onPaste}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canSubmit) void submit() }}
            placeholder="e.g. Orders stay in pending approval since we switched the broker account in OMS…"
            rows={6}
            disabled={busy}
            aria-label="Problem description"
          />
          {images.length > 0 && (
            <div className="thumbs">
              {images.map((src, i) => (
                <div className="thumb" key={i}>
                  <img src={src} alt={`Screenshot ${i + 1}`} />
                  <button aria-label={`Remove screenshot ${i + 1}`} onClick={() => setImages(images.filter((_, j) => j !== i))}>×</button>
                </div>
              ))}
            </div>
          )}
          <div className="dropbox-bar">
            <div className="dropbox-tools">
              <label className="attach">
                <input type="file" accept="image/*" multiple hidden onChange={(e) => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = '' }} />
                📎 Add screenshot <span className="muted">({images.length}/{MAX_IMAGES})</span>
              </label>
              {llms && llms.providers.length > 0 && (
                <ModelPicker providers={llms.providers} value={llm} onChange={setLlm} disabled={busy} embeddingModel={llms.embeddingModel} />
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              {(result || text || images.length > 0) && <button className="btn ghost" onClick={reset} disabled={busy}>Clear</button>}
              <button className="btn primary" onClick={submit} disabled={!canSubmit}>
                {busy && !result ? 'Analysing…' : 'Get help'} <span className="kbd">⌘↵</span>
              </button>
            </div>
          </div>
        </div>
        {error && !folded && <div className="note crit" style={{ marginTop: 10 }}><span className="note-icon" aria-hidden="true">⚠</span><span>{error}</span></div>}
      </div>
      )}
      {error && folded && <div className="note crit" style={{ marginTop: 12 }}><span className="note-icon" aria-hidden="true">⚠</span><span>{error}</span></div>}

      {(analysing || result || progress.length > 0) && <AnalysisProgress
        events={progress} working={analysing} failed={Boolean(error) && !result} debug={debug} hasImages={analysedImages}
      />}

      {result && draft && (
        <div className="grid" style={{ marginTop: 16 }}>
          {result.mode === 'mock' && (
            <div className="callout">Running in <strong>mock mode</strong> (no LLM provider configured): keyword retrieval and heuristic triage only.</div>
          )}

          {result.duplicates.length > 0 && (
            <div className="card notice">
              <h3>🔁 This may already be reported</h3>
              {result.duplicates.map((d) => (
                <div key={d.id} className="muted" style={{ fontSize: '0.9rem' }}>
                  Ticket <strong>#{d.id}</strong> — {d.summary} <span className="pill">{d.service}</span> <span className="mono">{d.score.toFixed(2)}</span>
                </div>
              ))}
              <p className="sub" style={{ margin: '6px 0 0' }}>The team is already working on it — you only need a new ticket if your case is different.</p>
            </div>
          )}

          <div className="card">
            <div className="eyebrow">What we understood{result.mode !== 'mock' && <span className="muted" style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}> · answered by {llms?.providers.find((p) => p.id === result.mode)?.label ?? result.mode} ({result.model})</span>}</div>
            <p style={{ margin: '4px 0 0', fontSize: '1.02rem' }}>{result.understanding}</p>
            {result.clarifyingQuestion && (
              <div className="note warn" style={{ marginTop: 12 }}>
                <span className="note-icon" aria-hidden="true">?</span>
                <span><strong>One question for you</strong>{result.clarifyingQuestion}</span>
              </div>
            )}
            {result.imageDescriptions.length > 0 && (
              <details style={{ marginTop: 10 }}>
                <summary className="muted" style={{ cursor: 'pointer', fontSize: '0.88rem' }}>What the assistant saw in your {result.imageDescriptions.length} screenshot(s)</summary>
                <div className="comments">
                  {result.imageDescriptions.map((d, i) => <div className="comment" key={i}><b>#{i + 1}</b> {d}</div>)}
                </div>
              </details>
            )}
          </div>

          {outcome?.kind === 'solved' && (
            <div className="card success"><h3>✓ Great — no ticket needed</h3><p className="sub" style={{ margin: 0 }}>Thanks for confirming. This answer will be ranked higher for the next person with the same problem.</p></div>
          )}
          {outcome?.kind === 'ticket' && (
            <div className="card success">
              <h3>✓ Ticket #{outcome.ticket.id} created</h3>
              <p className="sub" style={{ margin: 0 }}>
                Routed to <strong>{outcome.ticket.team}</strong>{outcome.ticket.assignee && <> · {short(outcome.ticket.assignee)}</>} with priority <PriorityPill level={outcome.ticket.priority} />.
              </p>
            </div>
          )}

          {!outcome && result.selfService.possible && result.selfService.answer && (
            <div className="card selfservice">
              <div className="eyebrow">Try this first</div>
              <p style={{ whiteSpace: 'pre-wrap', margin: '6px 0 12px' }}>{result.selfService.answer}</p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button className="btn primary" onClick={markSolved}>That solved it</button>
                <button className="btn" onClick={createTicket} disabled={busy}>Still need help — create ticket</button>
              </div>
            </div>
          )}

          {!outcome && (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
                <h3>{result.selfService.possible ? 'Or raise a ticket' : 'Proposed ticket'}</h3>
                <span className="muted" style={{ fontSize: '0.84rem' }}>You can adjust before submitting</span>
              </div>
              <div className="form">
                <label className="span2">Summary<input value={draft.summary} onChange={(e) => updateDraft({ summary: e.target.value })} /></label>
                <label className="span2">Description<textarea rows={4} value={draft.description} onChange={(e) => updateDraft({ description: e.target.value })} /></label>
                <label>Type
                  <select value={draft.workType} onChange={(e) => updateDraft({ workType: e.target.value as Draft['workType'] })}>
                    <option>Incident</option><option>Service Request</option>
                  </select>
                </label>
                <label>Service
                  <select value={draft.service} onChange={(e) => updateDraft({ service: e.target.value })}>
                    {catalog?.services.map((s) => <option key={s.name}>{s.name}</option>)}
                  </select>
                </label>
                <label>Urgency
                  <select value={draft.urgency} onChange={(e) => updateDraft({ urgency: e.target.value as Level })}>
                    {catalog?.levels.map((l) => <option key={l}>{l}</option>)}
                  </select>
                </label>
                <label>Impact
                  <select value={draft.impact} onChange={(e) => updateDraft({ impact: e.target.value as Level })}>
                    {catalog?.levels.map((l) => <option key={l}>{l}</option>)}
                  </select>
                </label>
              </div>
              <div className="routing">
                <div><span className="k">Team</span>{draft.team} {draft.critical && <span className="pill crit">● Critical</span>}</div>
                <div><span className="k">Assignee</span>{draft.assignee ? short(draft.assignee) : '—'} <span className="muted" style={{ fontSize: '0.8rem' }}>{draft.assigneeReason}</span></div>
                <div><span className="k">Priority</span><PriorityPill level={draft.priority} /> <span className="muted" style={{ fontSize: '0.8rem' }}>from urgency × impact matrix</span></div>
              </div>
              {result.rationale && <p className="sub" style={{ marginTop: 10 }}><strong>Why:</strong> {result.rationale}</p>}
              <button className="btn primary" onClick={createTicket} disabled={busy}>{busy ? 'Creating…' : 'Create ticket'}</button>
            </div>
          )}

          <details className="card">
            <summary style={{ cursor: 'pointer' }}><strong>Knowledge used</strong> <span className="muted">({result.matches.length} matches)</span></summary>
            <div style={{ marginTop: 10 }}>
              {result.matches.map((m) => (
                <div className="expert" key={m.id}>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                    <span className={`pill ${m.source === 'live' ? 'good' : ''}`}>{m.source}</span>
                    <span className="pill">{m.service}</span>
                    {m.resolver && <span className="pill">{short(m.resolver)}</span>}
                    {m.helpful > 0 && <span className="pill good">👍 {m.helpful}</span>}
                    {result.usedKnowledgeIds.includes(m.id) && <span className="pill warn">cited</span>}
                    <span className="mono muted">{m.score.toFixed(2)}</span>
                  </div>
                  <div style={{ fontWeight: 550 }}>{m.title}</div>
                  {m.resolution && <div className="muted">{m.resolution}</div>}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
