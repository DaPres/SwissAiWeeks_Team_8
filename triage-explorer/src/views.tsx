import { useMemo, useState } from 'react'
import type { Insights, Level, Service } from './types'
import { Bars, Flag, n, pct, PriorityPill, short, Stat } from './components'

const LEVELS: Level[] = ['highest', 'high', 'medium', 'low', 'lowest']
const URGENCY_LABEL: Record<Level, string> = {
  highest: 'Critical', high: 'High', medium: 'Medium', low: 'Low', lowest: 'Lowest',
}
const IMPACT_LABEL: Record<Level, string> = {
  highest: 'Major / Widespread', high: 'Significant / Large', medium: 'Moderate / Limited',
  low: 'Minor / Localized', lowest: 'No direct impact',
}

/* ------------------------------------------------------------------ Overview */
export function Overview({ data }: { data: Insights }) {
  const { meta, distributions: dist } = data
  const emailed = dist['Affected Business or IT Services'].find((d) => d.name === 'Emailed Support Tickets')!
  const rich = data.commentTiers.find((t) => t.name.startsWith('Rich'))!
  return (
    <>
      <div className="grid cols-4">
        <Stat value={n(meta.trainingTickets)} label="training tickets (synthetic Jira SM)" />
        <Stat value={pct(emailed.count, meta.trainingTickets)} label="parked in the generic “Emailed Support Tickets” bucket" />
        <Stat value={pct(rich.count, meta.trainingTickets)} label="carry a rich root-cause resolution comment" />
        <Stat value={pct(meta.matrixConsistentInTraining, meta.trainingTickets)} label="match the priority matrix — chance level, P/U/I are random" />
      </div>

      <h2 className="section-title">What the data really tells you</h2>
      <div className="grid cols-2">
        <div className="card">
          <h3>Affected service</h3>
          <p className="sub">Orange = generic intake bucket, not a real service. 20 services, one owning team each.</p>
          <Bars data={dist['Affected Business or IT Services']} highlight={(s) => s === 'Emailed Support Tickets'} />
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <h3>Comment quality tiers</h3>
            <p className="sub">Only the rich tier teaches <em>how</em> a class of problem is solved.</p>
            <Bars data={data.commentTiers} highlight={(s) => s.startsWith('Rich')} />
          </div>
          <div className="card">
            <h3>Resolution label</h3>
            <p className="sub">Uniform across done / cancelled / clarification / cannot reproduce — label is noise in training.</p>
            <Bars data={dist['Resolution']} />
          </div>
        </div>
        <div className="card">
          <h3>Service team</h3>
          <p className="sub">Service → Team is a strict 1:1 mapping (100% in training). Once the service is right, the team is free.</p>
          <Bars data={dist['Service Team(s)']} highlight={(s) => s === 'Service Desk'} />
        </div>
        <div className="card">
          <h3>Priority (training)</h3>
          <p className="sub">Skewed to “lowest” and drawn independently of Urgency/Impact — do <strong>not</strong> learn priority from it.</p>
          <Bars data={LEVELS.map((l) => dist['Priority'].find((d) => d.name === l)!)} />
        </div>
      </div>

      <h2 className="section-title">Ticket families (summary templates)</h2>
      <div className="card table-wrap">
        <p className="sub">
          Training text is templated: 173 distinct descriptions. Work type is fully determined by family — “Incorrect incident
          title…” is always a Service Request, “Incident mislabelled as service request…” always an Incident.
        </p>
        <table>
          <thead>
            <tr><th>Family</th><th className="num">Tickets</th><th className="num">Incident</th><th className="num">Service Request</th></tr>
          </thead>
          <tbody>
            {data.families.map((f) => (
              <tr key={f.name}>
                <td>{f.name}</td>
                <td className="num">{n(f.total)}</td>
                <td className="num">{f.incident ? n(f.incident) : <span className="muted">—</span>}</td>
                <td className="num">{f.serviceRequest ? n(f.serviceRequest) : <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ Services */
export function Services({ data }: { data: Insights }) {
  const [sel, setSel] = useState<Service>(data.services.find((s) => s.patterns.length > 0)!)
  return (
    <>
      <div className="callout" style={{ marginBottom: 16 }}>
        <strong>Key finding:</strong> the recorded <code>Assignee</code> is near-random (≈ every one of 30 agents appears on
        every service, top agent ≤ 4%). But each rich <code>Resolution:</code> comment for a service is always written by the{' '}
        <strong>same person</strong> — that resolver is the real routing signal.
      </div>
      <div className="split">
        <div className="card table-wrap" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Service</th><th>Team</th><th className="num">Rich</th></tr>
            </thead>
            <tbody>
              {data.services.map((s) => (
                <tr key={s.name} className="clickable" onClick={() => setSel(s)}
                  style={sel.name === s.name ? { background: 'var(--surface-2)' } : undefined}>
                  <td>
                    {s.name}{' '}
                    {s.critical && <span className="pill crit" title="Critical service">● Critical</span>}
                  </td>
                  <td className="muted">{s.team}</td>
                  <td className="num">{s.patterns.length ? n(s.patterns.reduce((a, p) => a + p.count, 0)) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="eyebrow">{sel.team}</div>
          <h3 style={{ fontSize: '1.2rem', margin: '2px 0 10px' }}>
            {sel.name} {sel.critical ? <span className="pill crit">● Critical</span> : <span className="pill">Non-critical</span>}
          </h3>
          <div className="grid cols-4" style={{ marginBottom: 16 }}>
            <div><div className="stat"><div className="value" style={{ fontSize: '1.4rem' }}>{n(sel.tickets)}</div><div className="label">tickets</div></div></div>
            <div><div className="stat"><div className="value" style={{ fontSize: '1.4rem' }}>{sel.distinctAssignees}</div><div className="label">distinct assignees</div></div></div>
            <div><div className="stat"><div className="value" style={{ fontSize: '1.4rem' }}>{(sel.topAssigneeShare * 100).toFixed(1)}%</div><div className="label">top assignee share</div></div></div>
          </div>
          <h4 style={{ marginBottom: 8 }}>Known resolution patterns</h4>
          {sel.patterns.length === 0 && (
            <p className="muted" style={{ fontSize: '0.88rem' }}>
              No rich resolution in training — only canned lines (“Resolution recorded: service restored.”). The resolution
              note must be synthesised from ticket content; assignee has no strong signal (fallback: team-level default).
            </p>
          )}
          {sel.patterns.map((p) => (
            <div className="expert" key={p.text}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                <span className="pill">{n(p.count)}×</span>
                <span className={`pill ${p.resolverInAssigneePool ? 'good' : 'warn'}`}>
                  {p.resolverInAssigneePool ? '✓' : '⚠'} {short(p.resolver)}
                  {!p.resolverInAssigneePool && ' (not in assignee pool)'}
                </span>
              </div>
              <div>{p.text}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ Matrix */
export function Matrix({ data }: { data: Insights }) {
  const [u, setU] = useState<Level>('high')
  const [i, setI] = useState<Level>('high')
  const p = data.matrix[u][LEVELS.indexOf(i)]
  return (
    <div className="grid cols-2">
      <div className="card">
        <h3>Urgency × Impact → Priority</h3>
        <p className="sub">Deterministic in the challenge set. Click a cell or use the selectors.</p>
        <div className="matrix" role="grid">
          <div className="hdr">Urgency ↓ / Impact →</div>
          {LEVELS.map((l) => <div className="hdr" key={l}>{IMPACT_LABEL[l]}</div>)}
          {LEVELS.map((ul) => (
            <div key={ul} style={{ display: 'contents' }}>
              <div className="hdr rowhdr">{URGENCY_LABEL[ul]}</div>
              {LEVELS.map((il, idx) => {
                const v = data.matrix[ul][idx]
                return (
                  <button key={il} className={`cell p-${v}${ul === u && il === i ? ' sel' : ''}`}
                    title={`Urgency ${URGENCY_LABEL[ul]} × Impact ${IMPACT_LABEL[il]} → ${v}`}
                    onClick={() => { setU(ul); setI(il) }}>
                    {v}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <h3>Calculator</h3>
        <div className="selectors" style={{ marginTop: 10 }}>
          <label>Urgency
            <select value={u} onChange={(e) => setU(e.target.value as Level)}>
              {LEVELS.map((l) => <option key={l} value={l}>{URGENCY_LABEL[l]}</option>)}
            </select>
          </label>
          <label>Impact
            <select value={i} onChange={(e) => setI(e.target.value as Level)}>
              {LEVELS.map((l) => <option key={l} value={l}>{IMPACT_LABEL[l]}</option>)}
            </select>
          </label>
        </div>
        <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Priority</div>
        <div style={{ margin: '4px 0 18px' }}><span className={`pill p-${p}`} style={{ fontSize: '1.1rem', padding: '6px 16px' }}>{p}</span></div>
        <div className="callout">
          <strong>How to judge it:</strong> Critical services (14 of 20) raise the ceiling — full outage of a critical service
          ⇒ Impact Major; partial / one entity ⇒ Significant or Moderate. Urgency follows workaround availability: none ⇒
          Critical, hard ⇒ High, easy ⇒ Medium. Service requests usually land Low/Minor. Always compute Priority from the
          table in code — never let the LLM write it free-hand.
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ Challenge */
export function Challenge({ data }: { data: Insights }) {
  const [id, setId] = useState(1)
  const t = data.triaged.find((x) => x.id === id)!
  const b = t.baseline
  const inp = t.input
  const rows = useMemo(() => [
    ['Work type', inp['Work type'], b.workType],
    ['Service', inp['Affected Business or IT Services'].join(', '), b.service],
    ['Team', '—', b.team],
    ['Assignee', '—', short(b.assignee) === '—' ? '(team default — no precedent)' : short(b.assignee)],
    ['Urgency', inp.Urgency, b.urgency],
    ['Impact', inp.Impact, b.impact],
    ['Priority', inp.Priority, b.priority],
    ['Resolution', '—', b.resolution],
  ], [inp, b])
  const withPrecedent = data.triaged.filter((x) => x.baseline.assignee).length
  return (
    <>
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat value={`${data.triaged.length}`} label={`challenge tickets · run ${data.meta.challengeRunId}`} />
        <Stat value={`${data.triaged.filter((x) => x.flags.includes('service-mismatch')).length}`} label="baseline re-routes to another service" />
        <Stat value={`${data.triaged.filter((x) => x.flags.includes('work-type-flip')).length}`} label="work type flipped" />
        <Stat value={`${withPrecedent} / ${data.triaged.length}`} label="matched to a historical resolver precedent" />
      </div>
      <div className="callout" style={{ marginBottom: 16 }}>
        The <strong>baseline</strong> column is produced by <code>analysis/build_insights.py</code> — a TF-IDF retrieval over
        training resolution patterns plus keyword heuristics. It is a starting point to measure against, not a hand-made answer
        key. Low-confidence rows are where the LLM stage must earn its keep.
      </div>
      <div className="split">
        <div className="ticket-list">
          {data.triaged.map((x) => (
            <button key={x.id} className={`ticket-item${x.id === id ? ' active' : ''}`} onClick={() => setId(x.id)}>
              <div className="eyebrow">#{x.id} · {x.input['Request type']}</div>
              <div className="t">{x.input.Summary}</div>
              <div className="meta">
                <span className="pill">{x.baseline.service}</span>
                {x.flags.map((f) => <Flag key={f} flag={f} />)}
              </div>
            </button>
          ))}
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="card">
            <div className="eyebrow">#{t.id} · {inp['Request type']} · {inp['Business Entity'].join(', ')}</div>
            <h3 style={{ fontSize: '1.15rem', margin: '4px 0 8px' }}>{inp.Summary}</h3>
            <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.92rem' }}>{inp.Description}</p>
            <div className="comments">
              {inp['All Comments'].map((c, k) => {
                const [who, ...rest] = c.split(': ')
                return <div className="comment" key={k}><b>{short(who)}</b>: {rest.join(': ')}</div>
              })}
            </div>
          </div>
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
              <h3>Intake vs. baseline triage</h3>
              <div className="conf">
                retrieval score
                <div className="track"><div className="fill" style={{ width: `${Math.min(1, b.confidence / 0.6) * 100}%` }} /></div>
                <span className="mono">{b.confidence.toFixed(2)}</span>
              </div>
            </div>
            <div className="compare">
              <div className="h">Field</div><div className="h">Intake</div><div className="h">Baseline</div>
              {rows.map(([k, a, c]) => {
                const changed = a !== '—' && String(a).toLowerCase() !== String(c).toLowerCase()
                const isPrio = k === 'Priority' || k === 'Urgency' || k === 'Impact'
                return (
                  <div key={k} style={{ display: 'contents' }}>
                    <div className="k">{k}</div>
                    <div>{isPrio && a ? <PriorityPill level={a} /> : a}</div>
                    <div className={changed && !isPrio ? 'changed' : ''}>
                      {isPrio ? <PriorityPill level={c} /> : c}
                      {k === 'Service' && b.serviceCritical && <> <span className="pill crit">● Critical</span></>}
                    </div>
                  </div>
                )
              })}
            </div>
            <div style={{ marginTop: 12, fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
              Runner-up services: {b.alternatives.slice(1).map((a) => `${a.service} (${a.score.toFixed(2)})`).join(' · ') || '—'}
            </div>
          </div>
          <div className="card">
            <h3>Nearest historical precedent</h3>
            {b.precedent ? (
              <>
                <p className="sub">Resolver <strong>{short(b.precedent.resolver)}</strong> · similarity {b.precedent.score.toFixed(2)}</p>
                <div className="comment">{b.precedent.text}</div>
                <p className="muted" style={{ fontSize: '0.84rem', marginBottom: 0 }}>
                  → LLM rewrites this into a ticket-specific note (IDs, broker, entity, counts) in the resolver’s voice.
                </p>
              </>
            ) : (
              <p className="muted" style={{ fontSize: '0.88rem', margin: 0 }}>
                No rich precedent for this service. Generate the note from ticket content + service runbook knowledge, and keep
                it concrete (what was checked, what was changed, how it was verified).
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
