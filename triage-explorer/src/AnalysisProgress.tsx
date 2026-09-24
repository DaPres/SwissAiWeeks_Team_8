import { useEffect, useRef, useState } from 'react'
import { DotLottieReact } from '@lottiefiles/dotlottie-react'
import type { AssistProgress } from './api'

const STEPS: { id: AssistProgress['step']; label: string }[] = [
  { id: 'vision', label: 'Read screenshots' },
  { id: 'embedding', label: 'Prepare search' },
  { id: 'knowledge', label: 'Retrieve knowledge' },
  { id: 'duplicates', label: 'Check open tickets' },
  { id: 'decision', label: 'Analyse issue' },
  { id: 'routing', label: 'Validate routing' },
]

interface MatchInsight {
  id: string | number
  title?: string
  summary?: string
  source?: string
  service?: string
  score?: number
}

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function EventData({ event }: { event: AssistProgress }) {
  const data = event.data
  if (!data || event.status !== 'completed') return null
  const matches = Array.isArray(data.matches) ? data.matches as MatchInsight[] : []
  const fields = Object.entries(data).filter(([key, value]) =>
    key !== 'matches' && key !== 'usedKnowledgeIds' && value !== null && ['string', 'number', 'boolean'].includes(typeof value))
  const citations = Array.isArray(data.usedKnowledgeIds) ? data.usedKnowledgeIds as string[] : []

  return (
    <div className="trace-data">
      {fields.length > 0 && <div className="trace-facts">
        {fields.map(([key, value]) => <span key={key}><b>{key.replace(/([A-Z])/g, ' $1')}</b> {String(value)}</span>)}
      </div>}
      {matches.length > 0 && <div className="trace-matches">
        {matches.map((match) => <div className="trace-match" key={match.id}>
          <div><strong>{match.title ?? match.summary ?? `Ticket #${match.id}`}</strong><small>{match.source ?? 'open ticket'} · {match.service ?? `#${match.id}`}</small></div>
          {typeof match.score === 'number' && <span aria-label={`Relevance score ${match.score.toFixed(2)}`}>{match.score.toFixed(2)}</span>}
        </div>)}
      </div>}
      {citations.length > 0 && <div className="trace-citations">Evidence used: {citations.join(', ')}</div>}
    </div>
  )
}

export function AnalysisProgress({ events, working, failed, debug, hasImages }: {
  events: AssistProgress[]
  working: boolean
  failed: boolean
  debug: boolean
  hasImages: boolean
}) {
  const [reduceMotion, setReduceMotion] = useState(prefersReducedMotion)
  const traceRef = useRef<HTMLOListElement>(null)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduceMotion(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  const completed = new Set(events.filter((event) => event.status === 'completed').map((event) => event.step))
  const last = events.at(-1)
  const active = last?.status === 'started' ? last.step : null
  const visibleSteps = STEPS.filter((step) => hasImages || step.id !== 'vision')
  const traceEvents = events.filter((event) => event.status === 'completed' || !completed.has(event.step))
  const hasDebugData = events.some((event) => event.tool)

  useEffect(() => {
    if (working && debug && traceRef.current) traceRef.current.scrollTop = traceRef.current.scrollHeight
  }, [events.length, working, debug])

  return <section className={`analysis-progress card${working ? ' is-working' : failed ? ' is-failed' : ' is-complete'}`} aria-label="Analysis progress">
    <div className="analysis-progress-top">
      <div className="analysis-animation" aria-hidden="true">
        {working && !reduceMotion
          ? <DotLottieReact src="/animations/support-analysis.lottie" autoplay loop style={{ width: '100%', height: '100%' }} />
          : <span className="analysis-mark">{working ? '✦' : failed ? '!' : '✓'}</span>}
      </div>
      <div className="analysis-progress-copy">
        <div className="eyebrow">{working ? 'Agent at work' : failed ? 'Stopped' : 'Completed'}</div>
        <h3 aria-live="polite">{working ? last?.title ?? 'Starting analysis…' : failed ? 'Analysis stopped' : 'Analysis complete'}</h3>
        <p>{working ? 'Finding relevant knowledge and checking the best route for your issue.' : failed ? 'See the error above. You can try again.' : 'Your guidance and proposed ticket are ready below.'}</p>
        <div className="analysis-steps" aria-label="Analysis stages">
          {visibleSteps.map((step) => <span key={step.id} className={`${completed.has(step.id) ? 'done' : ''}${active === step.id ? ' active' : ''}`}>
            <i aria-hidden="true">{completed.has(step.id) ? '✓' : active === step.id ? '•' : '○'}</i>{step.label}
          </span>)}
        </div>
      </div>
    </div>
    {debug && <div className="debug-trace">
      <div className="debug-trace-heading"><div><span className="eyebrow">Debug trace</span><h4>RAG and tool activity</h4></div><span className="trace-count">{events.filter((event) => event.status === 'completed').length} steps</span></div>
      {events.length === 0 && <p className="muted">Waiting for the first backend event…</p>}
      {!working && events.length > 0 && !hasDebugData && <p className="muted">Run the analysis again with Debug enabled to capture tool details.</p>}
      {hasDebugData && <ol ref={traceRef}>
        {traceEvents.map((event) => <li key={`${event.step}-${event.status}`} className={`trace-event ${event.status}`}>
          <span className="trace-status" aria-hidden="true">{event.status === 'completed' ? '✓' : '↗'}</span>
          <div>
            <div className="trace-line"><code>{event.tool ?? event.step}</code><span>{event.durationMs === null || event.durationMs === undefined ? 'running' : `${event.durationMs} ms`}</span></div>
            <strong>{event.title}</strong>
            {event.detail && <p>{event.detail}</p>}
            <EventData event={event} />
          </div>
        </li>)}
      </ol>}
      <p className="trace-note">Backend operations and retrieved evidence for this request.</p>
      <a className="motion-credit" href="https://lottiefiles.com/free-animation/search-loading-pYaJ6RTjMH" target="_blank" rel="noreferrer">Motion by Risa on LottieFiles</a>
    </div>}
  </section>
}
