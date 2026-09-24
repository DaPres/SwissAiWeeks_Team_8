import { useCallback, useEffect, useMemo, useState } from 'react'
import { curationApi, type CurationCluster, type CurationSample, type CurationSummary, type QualityLevel } from './api'
import { Bars, n, pct, short, Stat } from './components'

type Publishable = Exclude<QualityLevel, 'reject'>
const LEVELS: QualityLevel[] = ['gold', 'silver', 'bronze', 'reject']
const PUBLISHABLE: Publishable[] = ['gold', 'silver', 'bronze']
const LEVEL_TEXT: Record<QualityLevel, string> = {
  gold: 'Root cause documented — teaches routing and how to fix',
  silver: 'Closed with a short outcome — good for routing, thin on “how”',
  bronze: 'Closed without detail — weak signal, mostly service/team',
  reject: 'Open, generic intake bucket or no usable signal — never published',
}
const FLAG_LABEL: Record<string, string> = {
  no_resolution_detail: 'No resolution recorded',
  problem_fixed_only: "Only 'Problem fixed.'",
  canned_resolution: 'Canned one-liner',
  not_closed: 'Not closed',
  generic_bucket: 'Generic intake bucket',
  unclear_input: 'Unclear input',
  label_conflict: 'Label conflicts with fix',
}
const COMPONENT_MAX: Record<string, number> = { evidence: 50, closure: 15, routing: 15, clarity: 10, trail: 10 }

export function LevelPill({ level }: { level: QualityLevel }) {
  const icon = { gold: '★', silver: '◆', bronze: '●', reject: '✕' }[level]
  return <span className={`pill lvl-${level}`}>{icon} {level}</span>
}

type Data = Awaited<ReturnType<typeof curationApi.get>>

export function Curation() {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'publish' | 'run' | null>(null)
  const [target, setTarget] = useState<Publishable>('gold')
  const [message, setMessage] = useState<string | null>(null)
  const [levelFilter, setLevelFilter] = useState<QualityLevel | 'all'>('all')
  const [serviceFilter, setServiceFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [selId, setSelId] = useState<number | null>(null)
  const [threshold, setThreshold] = useState('')

  const load = useCallback(async () => {
    try {
      const d = await curationApi.get()
      setData(d)
      setError(null)
      if (d.knowledge.minLevel) setTarget(d.knowledge.minLevel as Publishable)
      setThreshold((t) => t || String(d.summary.threshold))
      setSelId((cur) => cur ?? d.clusters[0]?.id ?? null)
    } catch (e) {
      setError(`Backend not reachable: ${(e as Error).message}`)
    }
  }, [])
  useEffect(() => { void load() }, [load])

  const services = useMemo(() => [...new Set(data?.clusters.map((c) => c.service) ?? [])].sort(), [data])
  const filtered = useMemo(() => (data?.clusters ?? []).filter((c) =>
    (levelFilter === 'all' || c.level === levelFilter) &&
    (serviceFilter === 'all' || c.service === serviceFilter) &&
    (!query || `${c.title} ${c.resolution ?? ''} ${c.resolver ?? ''}`.toLowerCase().includes(query.toLowerCase())),
  ), [data, levelFilter, serviceFilter, query])

  if (error) return <div className="pill crit">⚠ {error}</div>
  if (!data) return <div className="muted">Loading curation…</div>

  const s: CurationSummary = data.summary
  const published = data.knowledge.minLevel as Publishable | null
  const preview = PUBLISHABLE.slice(0, PUBLISHABLE.indexOf(target) + 1).reduce(
    (a, l) => ({ clusters: a.clusters + s.clusterLevels[l].clusters, tickets: a.tickets + s.clusterLevels[l].tickets }),
    { clusters: 0, tickets: 0 },
  )

  async function doPublish() {
    setBusy('publish'); setMessage(null)
    try {
      const r = await curationApi.publish(target)
      setMessage(`✓ Knowledge now holds ${r.published} ${target}+ clusters (${n(r.tickets)} tickets).`)
      await load()
    } catch (e) { setMessage(`⚠ ${(e as Error).message}`) } finally { setBusy(null) }
  }

  async function doRun() {
    setBusy('run'); setMessage(null)
    try {
      const t = parseFloat(threshold)
      const r = await curationApi.run(Number.isFinite(t) ? t : undefined)
      setMessage(`✓ Re-analysed ${n(r.summary.tickets)} tickets into ${r.summary.clusters} clusters in ${r.summary.seconds}s; knowledge re-published at ${published ?? 'gold'}.`)
      setSelId(null)
      await load()
    } catch (e) { setMessage(`⚠ ${(e as Error).message}`) } finally { setBusy(null) }
  }

  return (
    <>
      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <Stat value={n(s.tickets)} label={`tickets analysed · ${s.embeddingModel.replace(/^\w+:/, '')}`} />
        <Stat value={String(s.clusters)} label={`problem clusters (similarity ≥ ${s.threshold})`} />
        <Stat value={pct(s.ticketLevels.reject, s.tickets)} label="of tickets rejected as bad data" />
        <Stat value={published ? `${published}+` : '—'} label={`published to knowledge · ${data.knowledge.bySource.training ?? 0} clusters`} />
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h3>Ticket quality</h3>
          <p className="sub">Each ticket scored 0–100: resolution evidence 50 · closed 15 · real service 15 · clear input 10 · triage trail 10.</p>
          <Bars data={LEVELS.map((l) => ({ name: `${l} (≥ ${s.levelThresholds[l]})`, count: s.ticketLevels[l] }))} highlight={(x) => x.startsWith('gold')} />
          <h4 style={{ margin: '16px 0 8px', fontSize: '0.9rem' }}>Score distribution</h4>
          <Bars data={s.scoreHistogram.map((h) => ({ name: `${h.bucket}–${h.bucket + 9}`, count: h.count }))} />
        </div>
        <div className="card">
          <h3>Bad-data findings</h3>
          <p className="sub">Tickets can carry several findings; they explain every deduction.</p>
          <Bars data={s.flags.map((f) => ({ name: f.label, count: f.count }))} total={s.tickets} />
        </div>
      </div>

      <div className="card publish" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, alignItems: 'baseline' }}>
          <div>
            <h3>Feed the knowledge base</h3>
            <p className="sub" style={{ margin: 0 }}>Choose the lowest level that should be learned. One knowledge item per cluster.</p>
          </div>
          {published && <span className="muted" style={{ fontSize: '0.85rem' }}>Currently published: <LevelPill level={published} /> and above</span>}
        </div>
        <div className="level-choice" role="radiogroup" aria-label="Minimum quality level">
          {PUBLISHABLE.map((l) => (
            <button key={l} role="radio" aria-checked={target === l} className={`level-option${target === l ? ' active' : ''}`} onClick={() => setTarget(l)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6 }}>
                <LevelPill level={l} />
                <span className="mono muted">≥ {s.levelThresholds[l]}</span>
              </div>
              <div className="lv-num">{s.clusterLevels[l].clusters} <span>clusters · {n(s.clusterLevels[l].tickets)} tickets</span></div>
              <div className="lv-text">{LEVEL_TEXT[l]}</div>
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn primary" onClick={doPublish} disabled={busy !== null}>
            {busy === 'publish' ? 'Publishing…' : `Feed ${preview.clusters} clusters (${n(preview.tickets)} tickets)`}
          </button>
          <span className="muted" style={{ fontSize: '0.85rem' }}>{target === published ? 'Same as current — republishing refreshes embeddings.' : `Changes knowledge from ${published ?? 'none'}+ to ${target}+.`}</span>
          <span style={{ flex: 1 }} />
          <label className="muted" style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6 }}>
            Cluster similarity
            <input className="num-input" value={threshold} onChange={(e) => setThreshold(e.target.value)} inputMode="decimal" />
          </label>
          <button className="btn" onClick={doRun} disabled={busy !== null}>{busy === 'run' ? 'Analysing…' : 'Re-run analysis'}</button>
        </div>
        {message && <div className={`pill ${message.startsWith('✓') ? 'good' : 'crit'}`} style={{ marginTop: 10 }}>{message}</div>}
      </div>

      <h2 className="section-title">Cluster browser</h2>
      <div className="filters">
        <div className="seg" role="tablist" aria-label="Filter by level">
          {(['all', ...LEVELS] as const).map((l) => (
            <button key={l} className={levelFilter === l ? 'active' : ''} onClick={() => setLevelFilter(l)}>
              {l} <span className="muted">{l === 'all' ? s.clusters : s.clusterLevels[l].clusters}</span>
            </button>
          ))}
        </div>
        <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} aria-label="Service">
          <option value="all">All services</option>
          {services.map((x) => <option key={x}>{x}</option>)}
        </select>
        <input className="search" placeholder="Search title, resolution, resolver…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <span className="muted" style={{ fontSize: '0.85rem' }}>{filtered.length} clusters · {n(filtered.reduce((a, c) => a + c.size, 0))} tickets</span>
      </div>
      <div className="split wide-left">
        <div className="card table-wrap" style={{ padding: 0, maxHeight: '80vh', overflowY: 'auto' }}>
          <table>
            <thead>
              <tr><th>Level</th><th>Cluster</th><th className="num">Tickets</th><th className="num">Score</th></tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => setSelId(c.id)} style={selId === c.id ? { background: 'var(--surface-2)' } : undefined}>
                  <td><LevelPill level={c.level} /></td>
                  <td>
                    <div style={{ fontWeight: 550 }}>{c.title}</div>
                    <div className="muted" style={{ fontSize: '0.8rem' }}>{c.service}{c.resolver && ` · ${short(c.resolver)}`}</div>
                  </td>
                  <td className="num">{n(c.size)}</td>
                  <td className="num">{c.score.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selId !== null && <ClusterDetail key={selId} id={selId} />}
      </div>
    </>
  )
}

function ClusterDetail({ id }: { id: number }) {
  const [d, setD] = useState<{ cluster: CurationCluster; samples: CurationSample[] } | null>(null)
  useEffect(() => { curationApi.cluster(id).then(setD).catch(() => setD(null)) }, [id])
  if (!d) return <div className="card muted">Loading cluster…</div>
  const c = d.cluster
  return (
    <div className="grid" style={{ alignContent: 'start' }}>
      <div className="card">
        <div className="eyebrow">Cluster #{c.id} · {c.service} · {c.team}</div>
        <h3 style={{ fontSize: '1.1rem', margin: '4px 0 10px' }}>{c.title}</h3>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          <LevelPill level={c.level} />
          <span className="pill">score {c.score}</span>
          <span className="pill">{n(c.size)} tickets</span>
          <span className="pill">coherence {(c.coherence * 100).toFixed(0)}%</span>
          <span className="pill">{c.problemVariants} description variant{c.problemVariants === 1 ? '' : 's'}</span>
          {c.resolver && <span className="pill good">expert: {short(c.resolver)}</span>}
        </div>
        <div className="eyebrow">Representative resolution <span className="muted">({c.resolutionKind})</span></div>
        <div className="comment" style={{ margin: '6px 0 14px' }}>{c.resolution || <span className="muted">No resolution recorded</span>}</div>
        <div className="grid cols-2" style={{ gap: 20 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Average score components</div>
            {Object.entries(COMPONENT_MAX).map(([k, max]) => (
              <div className="comp" key={k}>
                <span>{k}</span>
                <div className="track"><div className="fill" style={{ width: `${(c.components[k] / max) * 100}%` }} /></div>
                <span className="mono">{c.components[k]}/{max}</span>
              </div>
            ))}
            {c.components.penalty < 0 && <div className="comp"><span>penalty</span><div /><span className="mono">{c.components.penalty}</span></div>}
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Findings in this cluster</div>
            {Object.keys(c.flags).length === 0 && <div className="muted" style={{ fontSize: '0.85rem' }}>None — clean data</div>}
            {Object.entries(c.flags).sort((a, b) => b[1] - a[1]).map(([f, cnt]) => (
              <div key={f} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', padding: '2px 0' }}>
                <span>{FLAG_LABEL[f] ?? f}</span><span className="mono">{pct(cnt, c.size)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Sample tickets <span className="muted" style={{ fontWeight: 400 }}>(top {d.samples.length} by score)</span></h3>
        <div className="samples">
          {d.samples.map((t) => (
            <details key={t.idx} className="sample">
              <summary>
                <LevelPill level={t.level} /> <span className="mono">{t.score}</span>
                <span className="sample-title">{t.Summary}</span>
                <span className="muted" style={{ fontSize: '0.8rem' }}>{t['Work type']} · {t.Status}{t.Resolution ? ` · ${t.Resolution}` : ''}</span>
              </summary>
              <p className="muted" style={{ fontSize: '0.85rem', margin: '6px 0' }}>{t.Description}</p>
              {t.flags.length > 0 && <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>{t.flags.map((f) => <span key={f} className="pill warn">{FLAG_LABEL[f] ?? f}</span>)}</div>}
              <div className="comments">
                {t['All Comments'].map((cm, i) => {
                  const [who, ...rest] = cm.split(': ')
                  return <div className="comment" key={i}><b>{short(who)}</b>: {rest.join(': ')}</div>
                })}
              </div>
            </details>
          ))}
        </div>
      </div>
    </div>
  )
}
