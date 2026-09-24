import { useCallback, useEffect, useState } from 'react'
import { api, type Catalog, type Stats, type Ticket } from './api'
import { PriorityPill, short, Stat } from './components'
import type { Level } from './types'

const RESOLUTIONS = ['done', 'cancelled', 'clarification', 'cannot reproduce']

export function Queue({ catalog }: { catalog: Catalog | null }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [selId, setSelId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([api.tickets(), api.stats()])
      setTickets(t); setStats(s); setError(null)
      setSelId((cur) => cur ?? t.find((x) => x.status === 'open')?.id ?? t[0]?.id ?? null)
    } catch (e) {
      setError(`Backend not reachable: ${(e as Error).message}`)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const sel = tickets.find((t) => t.id === selId) ?? null
  const k = stats?.knowledge

  return (
    <>
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat value={k ? String(k.total) : '—'} label={k ? `knowledge items · ${k.bySource.training ?? 0} history · ${k.bySource.catalog ?? 0} catalog` : 'knowledge items'} />
        <Stat value={String(k?.bySource.live ?? 0)} label="learned from tickets resolved here" />
        <Stat value={String(stats?.assists.helpful ?? 0)} label="problems solved without a ticket" />
        <Stat value={stats ? `${stats.tickets.open} / ${stats.tickets.resolved}` : '—'} label="open / resolved tickets" />
      </div>
      {error && <div className="pill crit" style={{ marginBottom: 12 }}>⚠ {error}</div>}
      {tickets.length === 0 && !error && (
        <div className="card muted">No tickets yet — raise one from <strong>Get help</strong>.</div>
      )}
      {tickets.length > 0 && (
        <div className="split">
          <div className="ticket-list">
            {tickets.map((t) => (
              <button key={t.id} className={`ticket-item${t.id === selId ? ' active' : ''}`} onClick={() => setSelId(t.id)}>
                <div className="eyebrow">#{t.id} · {t.work_type} · {t.status}</div>
                <div className="t">{t.summary}</div>
                <div className="meta">
                  <span className="pill">{t.service}</span>
                  <PriorityPill level={t.priority} />
                  {t.assignee && <span className="pill">{short(t.assignee)}</span>}
                </div>
              </button>
            ))}
          </div>
          {sel && <TicketDetail key={sel.id} ticket={sel} catalog={catalog} onResolved={refresh} />}
        </div>
      )}
    </>
  )
}

function TicketDetail({ ticket, catalog, onResolved }: { ticket: Ticket; catalog: Catalog | null; onResolved: () => Promise<void> }) {
  const open = ticket.status === 'open'
  const [service, setService] = useState(ticket.service)
  const [workType, setWorkType] = useState(ticket.work_type)
  const [urgency, setUrgency] = useState<Level>(ticket.urgency)
  const [impact, setImpact] = useState<Level>(ticket.impact)
  const [assignee, setAssignee] = useState(ticket.assignee ?? '')
  const [resolution, setResolution] = useState(ticket.resolution ?? 'done')
  const [text, setText] = useState(ticket.resolution_text ?? '')
  const [busy, setBusy] = useState<'draft' | 'resolve' | null>(null)
  const [learned, setLearned] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const team = catalog?.services.find((s) => s.name === service)?.team ?? ticket.team
  const priority = catalog ? catalog.matrix[urgency][impact] : ticket.priority
  const ai = ticket.ai_triage

  async function draft() {
    setBusy('draft'); setError(null)
    try { setText((await api.draftResolution(ticket.id)).text) } catch (e) { setError((e as Error).message) } finally { setBusy(null) }
  }

  async function resolve() {
    setBusy('resolve'); setError(null)
    try {
      const r = await api.resolve(ticket.id, { resolution, resolution_text: text, assignee, service, work_type: workType, urgency, impact })
      setLearned(r.learnedKnowledgeId ?? 'none')
      await onResolved()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="grid" style={{ alignContent: 'start' }}>
      <div className="card">
        <div className="eyebrow">#{ticket.id} · created {new Date(ticket.created_at * 1000).toLocaleString()}</div>
        <h3 style={{ fontSize: '1.15rem', margin: '4px 0 8px' }}>{ticket.summary}</h3>
        <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.92rem', whiteSpace: 'pre-wrap' }}>{ticket.description}</p>
        <div className="comments">
          <div className="comment"><b>User wrote</b>: {ticket.user_text || <span className="muted">(screenshot only)</span>}</div>
          {ticket.image_descriptions.map((d, i) => <div className="comment" key={i}><b>Screenshot #{i + 1}</b>: {d}</div>)}
        </div>
      </div>

      <div className="card">
        <h3>{open ? 'Resolve' : 'Resolved'}</h3>
        <p className="sub">Correct the AI triage if it was wrong — the final values are what the system learns from.</p>
        <div className="form">
          <label>Type
            <select value={workType} disabled={!open} onChange={(e) => setWorkType(e.target.value as Ticket['work_type'])}>
              <option>Incident</option><option>Service Request</option>
            </select>
            {ai.workType !== workType && <span className="was">AI: {ai.workType}</span>}
          </label>
          <label>Service
            <select value={service} disabled={!open} onChange={(e) => setService(e.target.value)}>
              {catalog?.services.map((s) => <option key={s.name}>{s.name}</option>)}
            </select>
            {ai.service !== service && <span className="was">AI: {ai.service}</span>}
          </label>
          <label>Urgency
            <select value={urgency} disabled={!open} onChange={(e) => setUrgency(e.target.value as Level)}>
              {catalog?.levels.map((l) => <option key={l}>{l}</option>)}
            </select>
          </label>
          <label>Impact
            <select value={impact} disabled={!open} onChange={(e) => setImpact(e.target.value as Level)}>
              {catalog?.levels.map((l) => <option key={l}>{l}</option>)}
            </select>
          </label>
          <label>Assignee
            <input value={assignee} disabled={!open} placeholder="name@intcom.com" onChange={(e) => setAssignee(e.target.value)} />
          </label>
          <label>Resolution
            <select value={resolution} disabled={!open} onChange={(e) => setResolution(e.target.value)}>
              {RESOLUTIONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <label className="span2">
            <span style={{ display: 'flex', justifyContent: 'space-between' }}>
              Resolution comment
              {open && <button className="linkbtn" onClick={draft} disabled={busy !== null}>{busy === 'draft' ? 'Drafting…' : '✨ Draft from similar tickets'}</button>}
            </span>
            <textarea rows={4} value={text} disabled={!open} onChange={(e) => setText(e.target.value)}
              placeholder="Root cause, what you changed, how you verified it." />
          </label>
        </div>
        <div className="routing">
          <div><span className="k">Team</span>{team}</div>
          <div><span className="k">Priority</span><PriorityPill level={priority} /></div>
        </div>
        {error && <div className="pill crit" style={{ margin: '8px 0' }}>⚠ {error}</div>}
        {open && (
          <button className="btn primary" onClick={resolve} disabled={busy !== null || text.trim().length < 10 || !assignee.trim()}>
            {busy === 'resolve' ? 'Resolving…' : 'Resolve & teach'}
          </button>
        )}
        {learned && (
          <div className={`pill ${learned === 'none' ? '' : 'good'}`} style={{ marginTop: 10 }}>
            {learned === 'none' ? 'Closed — not added to knowledge (only “done” fixes are learned)' : `✓ Learned as ${learned} — the next similar request will find it`}
          </div>
        )}
      </div>
    </div>
  )
}
