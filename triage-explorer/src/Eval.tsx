import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import {
  api, evalApi, type EvalConfigIn, type EvalOptions, type EvalRecord, type EvalRunSummary, type EvalTicket, type Llms,
} from './api'
import { PriorityPill, short } from './components'
import { ModelMark, ModelPicker } from './ModelPicker'

type Details = Record<string, (EvalTicket | null)[]>
interface Draft extends EvalConfigIn { key: number }

const FIELDS: { key: string; label: string; get: (r: EvalRecord) => string }[] = [
  { key: 'workType', label: 'Work type', get: (r) => r['Work type'] },
  { key: 'service', label: 'Service', get: (r) => r['Affected Business or IT Services']?.[0] ?? '—' },
  { key: 'assignee', label: 'Assignee', get: (r) => r.Assignee ?? '—' },
  { key: 'urgency', label: 'Urgency', get: (r) => r.Urgency },
  { key: 'impact', label: 'Impact', get: (r) => r.Impact },
  { key: 'priority', label: 'Priority', get: (r) => r.Priority },
  { key: 'resolution', label: 'Resolution', get: (r) => r.Resolution },
]
const PRIORITIES = ['Highest', 'High', 'Medium', 'Low', 'Lowest']
const STATUS_PILL: Record<string, string> = { done: 'good', failed: 'crit', cancelled: 'warn', interrupted: 'warn' }

let nextKey = 1
const secs = (s: number) => (s < 90 ? `${s.toFixed(0)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)

function elapsed(r: EvalRunSummary, now: number) {
  return r.startedAt ? ((r.finishedAt ?? now / 1000) - r.startedAt) : 0
}

export function Eval() {
  const [options, setOptions] = useState<EvalOptions | null>(null)
  const [llms, setLlms] = useState<Llms | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [limit, setLimit] = useState('')
  const [workers, setWorkers] = useState(4)
  const [challenge, setChallenge] = useState('')
  const [starting, setStarting] = useState(false)

  const [runs, setRuns] = useState<Record<string, EvalRunSummary>>({})
  const [details, setDetails] = useState<Details>({})
  const [selected, setSelected] = useState<string[]>([])
  const [live, setLive] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    Promise.all([evalApi.options(), api.llms()]).then(([o, l]) => {
      setOptions(o)
      setLlms(l)
      setChallenge(o.challenges[0] ?? '')
      setWorkers(o.defaults.workers)
      setDrafts([{ key: nextKey++, llm: l.default, top_k: o.defaults.topK, min_score: o.defaults.minScore }])
    }).catch((e) => setError(`Backend not reachable: ${(e as Error).message}`))
  }, [])

  // One SSE stream carries every run's progress; per-ticket results are merged into whatever we have loaded.
  useEffect(() => evalApi.stream((e) => {
    if (e.type === 'snapshot') {
      setRuns(Object.fromEntries(e.runs.map((r) => [r.id, r])))
      setSelected((cur) => cur.length ? cur : e.runs.filter((r) => r.batch && r.batch === e.runs[0]?.batch).map((r) => r.id).reverse())
    }
    if (e.type === 'run') setRuns((cur) => ({ ...cur, [e.run.id]: e.run }))
    if (e.type === 'deleted') {
      setRuns((cur) => Object.fromEntries(Object.entries(cur).filter(([id]) => id !== e.id)))
      setSelected((cur) => cur.filter((id) => id !== e.id))
    }
    if (e.type === 'ticket') {
      setDetails((cur) => {
        const list = [...(cur[e.runId] ?? [])]
        list[e.index] = e.ticket
        return { ...cur, [e.runId]: list }
      })
    }
  }, setLive), [])

  // Load the full results of each selected run once; later tickets arrive over the stream and are merged.
  const loaded = useRef(new Set<string>())
  useEffect(() => {
    for (const id of selected) {
      if (loaded.current.has(id)) continue
      loaded.current.add(id)
      evalApi.run(id).then((run) => setDetails((cur) => ({
        ...cur, [id]: run.tickets.map((t, i) => t ?? cur[id]?.[i] ?? null),
      }))).catch(() => loaded.current.delete(id))
    }
  }, [selected])

  const anyRunning = Object.values(runs).some((r) => r.status === 'running' || r.status === 'queued')
  useEffect(() => {
    if (!anyRunning) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [anyRunning])

  const history = useMemo(() => Object.values(runs).sort((a, b) => b.createdAt - a.createdAt), [runs])

  if (error) return <div className="pill crit">⚠ {error}</div>
  if (!options || !llms) return <div className="muted">Loading evaluation…</div>

  const providers = llms.providers.length ? llms.providers : [{ id: 'mock', label: 'Offline (mock)', model: 'heuristic fallback', vision: false }]
  const update = (key: number, patch: Partial<Draft>) => setDrafts((d) => d.map((x) => (x.key === key ? { ...x, ...patch } : x)))
  const addDraft = (base?: Draft) => setDrafts((d) => [...d, {
    ...(base ?? d[d.length - 1] ?? { llm: llms.default, top_k: options.defaults.topK, min_score: 0 }), key: nextKey++, label: '',
  }])
  const onePerModel = () => {
    const base = drafts[0] ?? { top_k: options.defaults.topK, min_score: 0 }
    setDrafts(providers.map((p) => ({ key: nextKey++, llm: p.id, top_k: base.top_k, min_score: base.min_score })))
  }

  async function start() {
    setStarting(true)
    try {
      const n = parseInt(limit, 10)
      const started = await evalApi.start({
        configs: drafts.map((c) => ({ llm: c.llm, top_k: c.top_k, min_score: c.min_score, label: c.label?.trim() || undefined })),
        challenge: challenge || undefined,
        limit: Number.isFinite(n) && n > 0 ? n : null,
        workers,
      })
      setRuns((cur) => ({ ...cur, ...Object.fromEntries(started.map((r) => [r.id, r])) }))
      setSelected(started.map((r) => r.id))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  const toggle = (id: string) => setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  const total = options.records.length

  return (
    <>
      <div className="card">
        <div className="ev-head">
          <div>
            <h3>Configure evaluation runs</h3>
            <p className="sub" style={{ margin: 0 }}>
              Each configuration triages the {total} blind-eval tickets with the same pipeline as <code>python -m app.evaluate</code>.
              Add several to compare them side by side.
            </p>
          </div>
          <span className={`pill ${live ? 'good' : 'warn'}`} title="Server-sent events stream">{live ? '● Live' : '○ Reconnecting…'}</span>
        </div>

        <div className="ev-configs">
          {drafts.map((d, i) => (
            <div className="ev-config" key={d.key}>
              <div className="ev-config-top">
                <span className="ev-config-n">{i + 1}</span>
                <input className="ev-label" placeholder="Label (optional)" value={d.label ?? ''} maxLength={80}
                       onChange={(e) => update(d.key, { label: e.target.value })} />
                <button className="ev-icon" title="Duplicate" aria-label="Duplicate configuration" onClick={() => addDraft(d)}>⧉</button>
                <button className="ev-icon" title="Remove" aria-label="Remove configuration" disabled={drafts.length < 2}
                        onClick={() => setDrafts((x) => x.filter((y) => y.key !== d.key))}>✕</button>
              </div>
              <ModelPicker providers={providers} value={d.llm} onChange={(llm) => update(d.key, { llm })} embeddingModel={llms.embeddingModel} />
              <label className="ev-field">
                <span>Knowledge items in prompt (top K)</span>
                <input type="number" min={1} max={30} value={d.top_k ?? ''} className="num-input"
                       onChange={(e) => update(d.key, { top_k: e.target.value ? Math.max(1, Math.min(30, +e.target.value)) : null })} />
              </label>
              <label className="ev-field">
                <span>Min. RAG similarity <b className="mono">{d.min_score.toFixed(2)}</b></span>
                <input type="range" min={0} max={0.9} step={0.05} value={d.min_score}
                       onChange={(e) => update(d.key, { min_score: +e.target.value })} />
                <small className="muted">{d.min_score === 0 ? 'Keep every match' : `Drop matches ≤ ${d.min_score.toFixed(2)} cosine`} · assistant uses {options.defaults.assistMinScore}</small>
              </label>
            </div>
          ))}
          <div className="ev-add">
            <button className="btn" onClick={() => addDraft()} disabled={drafts.length >= 8}>+ Add configuration</button>
            {providers.length > 1 && <button className="btn" onClick={onePerModel}>One per model</button>}
          </div>
        </div>

        <div className="ev-run-bar">
          {options.challenges.length > 1 && (
            <label className="ev-inline">Challenge
              <select value={challenge} onChange={(e) => setChallenge(e.target.value)}>
                {options.challenges.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
          )}
          <label className="ev-inline">Tickets
            <input className="num-input" inputMode="numeric" placeholder={`all ${total}`} value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, ''))} />
          </label>
          <label className="ev-inline">Parallel calls
            <input className="num-input" type="number" min={1} max={16} value={workers} onChange={(e) => setWorkers(Math.max(1, Math.min(16, +e.target.value || 1)))} />
          </label>
          <span style={{ flex: 1 }} />
          <button className="btn primary" onClick={start} disabled={starting || !drafts.length}>
            {starting ? 'Starting…' : `Run ${drafts.length} configuration${drafts.length === 1 ? '' : 's'}`}
          </button>
        </div>
      </div>

      <h2 className="section-title">Runs</h2>
      {history.length === 0 && <div className="card muted">No runs yet — configure one above.</div>}
      {history.length > 0 && (
        <div className="card table-wrap" style={{ padding: 0 }}>
          <table className="ev-runs">
            <thead>
              <tr><th aria-label="Compare" /><th>Run</th><th>Progress</th><th className="num">Time</th><th className="num">Issues</th><th /></tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => toggle(r.id)} style={selected.includes(r.id) ? { background: 'var(--surface-2)' } : undefined}>
                  <td><input type="checkbox" checked={selected.includes(r.id)} onChange={() => toggle(r.id)} onClick={(e) => e.stopPropagation()} aria-label={`Compare ${r.label}`} /></td>
                  <td>
                    <div className="ev-run-name"><ModelMark id={r.config.llm} /> <b>{r.label}</b></div>
                    <div className="muted" style={{ fontSize: '0.78rem' }}>
                      {r.model} · top K {r.config.top_k ?? r.meta?.topK ?? 'default'} · min sim {r.config.min_score.toFixed(2)} · {new Date(r.createdAt * 1000).toLocaleString()}
                    </div>
                  </td>
                  <td style={{ minWidth: 170 }}><Progress run={r} /></td>
                  <td className="num mono">{r.startedAt ? secs(elapsed(r, now)) : '—'}</td>
                  <td className="num">{r.completed ? <span className={`pill ${r.problems ? 'warn' : 'good'}`}>{r.problems}</span> : '—'}</td>
                  <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
                    {(r.status === 'running' || r.status === 'queued') && <button className="btn small" onClick={() => evalApi.cancel(r.id)}>Stop</button>}
                    {r.completed > 0 && <a className="btn small" href={evalApi.resultsUrl(r.id)} download>results.json</a>}
                    {r.status !== 'running' && r.status !== 'queued' && (
                      <button className="ev-icon" title="Delete run" aria-label={`Delete ${r.label}`} onClick={() => { if (confirm(`Delete run “${r.label}”?`)) void evalApi.remove(r.id) }}>🗑</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected.length > 0 && (
        <Comparison
          runs={selected.map((id) => runs[id]).filter(Boolean)}
          details={details}
          inputs={options.records}
          now={now}
          onBaseline={(id) => setSelected((cur) => [id, ...cur.filter((x) => x !== id)])}
        />
      )}
    </>
  )
}

function Progress({ run }: { run: EvalRunSummary }) {
  const pctDone = run.total ? (run.completed / run.total) * 100 : 0
  return (
    <div className="ev-progress">
      <div className="ev-track"><div className={`ev-fill ${run.status}`} style={{ width: `${pctDone}%` }} /></div>
      <span className="mono">{run.completed}/{run.total}</span>
      {run.status === 'running' || run.status === 'queued'
        ? <span className="pill"><span className="ev-dot" /> {run.status}</span>
        : <span className={`pill ${STATUS_PILL[run.status] ?? ''}`} title={run.error ?? undefined}>{run.status}</span>}
    </div>
  )
}

function Comparison({ runs, details, inputs, now, onBaseline }: {
  runs: EvalRunSummary[]
  details: Details
  inputs: EvalOptions['records']
  now: number
  onBaseline: (id: string) => void
}) {
  const [onlyDiff, setOnlyDiff] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const base = runs[0]
  const rows = Math.max(...runs.map((r) => r.total))
  const at = (runId: string, i: number) => details[runId]?.[i] ?? null

  // Per field: share of tickets (answered by both) where the run agrees with the baseline.
  const agreement = useMemo(() => runs.slice(1).map((r) => Object.fromEntries(FIELDS.map((f) => {
    let both = 0, same = 0
    for (let i = 0; i < rows; i++) {
      const a = at(base.id, i), b = at(r.id, i)
      if (!a || !b) continue
      both++
      if (f.get(a.record) === f.get(b.record)) same++
    }
    return [f.key, both ? same / both : null]
  }))), [runs, details, rows]) // eslint-disable-line react-hooks/exhaustive-deps

  const disagrees = (i: number) => runs.slice(1).some((r) => {
    const a = at(base.id, i), b = at(r.id, i)
    return a && b && FIELDS.some((f) => f.get(a.record) !== f.get(b.record))
  })
  const indices = [...Array(rows).keys()].filter((i) => !onlyDiff || disagrees(i))

  return (
    <>
      <h2 className="section-title">Side-by-side comparison</h2>
      <div className="ev-summary" style={{ gridTemplateColumns: `repeat(${runs.length}, minmax(220px, 1fr))` }}>
        {runs.map((r, n) => {
          const done = (details[r.id] ?? []).filter(Boolean) as EvalTicket[]
          const rerouted = done.filter((t, i) => t.record['Affected Business or IT Services'][0] !== inputs[i]?.['Affected Business or IT Services']?.[0]).length
          const prio = PRIORITIES.map((p) => done.filter((t) => t.record.Priority === p).length)
          const avg = done.length ? done.reduce((a, t) => a + t.seconds, 0) / done.length : 0
          return (
            <div key={r.id} className={`card ev-run-card${n === 0 ? ' baseline' : ''}`}>
              <div className="ev-run-name"><ModelMark id={r.config.llm} /> <b>{r.label}</b></div>
              <div className="muted mono" style={{ fontSize: '0.75rem', margin: '2px 0 8px' }}>{r.model}</div>
              <div className="ev-chips">
                <span className="pill">top K {r.config.top_k ?? r.meta?.topK ?? '—'}</span>
                <span className="pill">min sim {r.config.min_score.toFixed(2)}</span>
                {n === 0 ? <span className="pill good">baseline</span>
                  : <button className="pill ev-pill-btn" onClick={() => onBaseline(r.id)}>set as baseline</button>}
              </div>
              <Progress run={r} />
              <dl className="ev-kv">
                <dt>Wall time</dt><dd>{r.startedAt ? secs(elapsed(r, now)) : '—'}</dd>
                <dt>Avg / ticket</dt><dd>{avg ? `${avg.toFixed(1)}s` : '—'}</dd>
                <dt>Service re-routed</dt><dd>{done.length ? `${rerouted}/${done.length}` : '—'}</dd>
                <dt>Consistency issues</dt><dd>{r.problems}</dd>
              </dl>
              <div className="ev-prio" title="Priority distribution">
                {prio.map((c, i) => c > 0 && (
                  <div key={i} className={`p-${PRIORITIES[i].toLowerCase()}`} style={{ flex: c }} title={`${PRIORITIES[i]}: ${c}`}>{c}</div>
                ))}
              </div>
              {n > 0 && (
                <div className="ev-agree">
                  {FIELDS.map((f) => {
                    const v = agreement[n - 1][f.key]
                    return (
                      <div key={f.key} className="ev-agree-row">
                        <span>{f.label}</span>
                        <div className="ev-track"><div className="ev-fill" style={{ width: `${(v ?? 0) * 100}%`, background: v !== null && v < 0.7 ? 'var(--series-2)' : undefined }} /></div>
                        <span className="mono">{v === null ? '—' : `${Math.round(v * 100)}%`}</span>
                      </div>
                    )
                  })}
                  <div className="muted" style={{ fontSize: '0.72rem', marginTop: 4 }}>agreement with baseline</div>
                </div>
              )}
              {r.error && <div className="pill crit" style={{ marginTop: 8, whiteSpace: 'normal' }}>{r.error}</div>}
            </div>
          )
        })}
      </div>

      <div className="filters" style={{ marginTop: 16 }}>
        <label className="ev-inline"><input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} /> Only tickets where runs disagree</label>
        <span className="muted" style={{ fontSize: '0.85rem' }}>{indices.length} tickets · highlighted values differ from the baseline · click a row for resolution notes and rationale</span>
      </div>
      <div className="card table-wrap" style={{ padding: 0 }}>
        <table className="ev-grid">
          <thead>
            <tr>
              <th style={{ minWidth: 240 }}>Ticket (as reported)</th>
              {runs.map((r, n) => <th key={r.id} className={n === 0 ? 'baseline' : ''}><ModelMark id={r.config.llm} /> {r.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {indices.map((i) => {
              const input = inputs[i]
              const baseT = at(base.id, i)
              return (
                <Fragment key={i}>
                  <tr className="clickable" onClick={() => setOpen(open === i ? null : i)}>
                    <td>
                      <div className="ev-ticket-title"><span className="muted mono">#{i + 1}</span> {input?.Summary ?? `Ticket ${i + 1}`}</div>
                      {input && (
                        <div className="muted" style={{ fontSize: '0.76rem' }}>
                          {input['Work type']} · {input['Affected Business or IT Services']?.[0] ?? '—'} · {input.Priority}
                        </div>
                      )}
                    </td>
                    {runs.map((r, n) => {
                      const t = at(r.id, i)
                      if (!t) return <td key={r.id} className={n === 0 ? 'baseline' : ''}>{i < r.total ? <span className="ev-pending">{r.status === 'running' || r.status === 'queued' ? 'triaging…' : '—'}</span> : ''}</td>
                      const diff = (f: string) => n > 0 && baseT && FIELDS.find((x) => x.key === f)!.get(t.record) !== FIELDS.find((x) => x.key === f)!.get(baseT.record) ? ' ev-diff' : ''
                      const rec = t.record
                      return (
                        <td key={r.id} className={`ev-cell${n === 0 ? ' baseline' : ''}`}>
                          <div><span className={`ev-v${diff('workType')}`}>{rec['Work type']}</span></div>
                          <div><span className={`ev-v strong${diff('service')}`}>{rec['Affected Business or IT Services'][0]}</span></div>
                          <div><span className={`ev-v${diff('assignee')}`}>{short(rec.Assignee)}</span></div>
                          <div className="ev-prio-line">
                            <span className={`ev-v${diff('urgency')}`}>{rec.Urgency}</span>×<span className={`ev-v${diff('impact')}`}>{rec.Impact}</span>→
                            <span className={diff('priority') ? 'ev-diff-ring' : ''}><PriorityPill level={rec.Priority} /></span>
                          </div>
                          <div><span className={`ev-v muted${diff('resolution')}`}>{rec.Resolution}</span>{t.problems.length > 0 && <span className="pill warn" title={t.problems.join('\n')} style={{ marginLeft: 6 }}>⚠ {t.problems.length}</span>}</div>
                        </td>
                      )
                    })}
                  </tr>
                  {open === i && (
                    <tr className="ev-detail">
                      <td>
                        {input && <p className="muted" style={{ fontSize: '0.8rem', margin: 0 }}>{input.Description}</p>}
                      </td>
                      {runs.map((r) => {
                        const t = at(r.id, i)
                        return (
                          <td key={r.id}>
                            {t ? (
                              <>
                                <div className="eyebrow">Resolution note</div>
                                <div className="comment" style={{ margin: '4px 0 8px' }}>{t.trace.resolutionText}</div>
                                <div className="eyebrow">Why</div>
                                <p className="ev-small">{t.trace.rationale}</p>
                                <div className="eyebrow">Assignee</div>
                                <p className="ev-small">{t.trace.assigneeReason}</p>
                                <div className="eyebrow">Knowledge used ({t.trace.matches.length})</div>
                                <ul className="ev-matches">
                                  {t.trace.matches.slice(0, 4).map((m) => <li key={m.id}><span className="mono">{m.score.toFixed(2)}</span> {m.title}</li>)}
                                  {t.trace.matches.length === 0 && <li className="muted">none above the similarity floor</li>}
                                </ul>
                                {t.problems.map((p) => <div key={p} className="pill warn" style={{ whiteSpace: 'normal', marginTop: 4 }}>{p}</div>)}
                                <div className="muted mono" style={{ fontSize: '0.72rem', marginTop: 6 }}>{t.seconds.toFixed(1)}s</div>
                              </>
                            ) : <span className="muted">—</span>}
                          </td>
                        )
                      })}
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
