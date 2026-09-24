import { useState } from 'react'
import type { NameCount } from './types'

const fmt = new Intl.NumberFormat('en-US')
export const n = (v: number) => fmt.format(v)
export const pct = (v: number, total: number) => `${((v / total) * 100).toFixed(1)}%`
export const short = (email: string | null) => (email ? email.replace('@intcom.com', '') : '—')

export function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="card stat">
      <div className="value">{value}</div>
      <div className="label">{label}</div>
    </div>
  )
}

/** Single-series horizontal bar list with per-row hover tooltip. */
export function Bars({
  data,
  highlight,
  total,
}: {
  data: NameCount[]
  highlight?: (name: string) => boolean
  total?: number
}) {
  const [hover, setHover] = useState<string | null>(null)
  const max = Math.max(...data.map((d) => d.count))
  const sum = total ?? data.reduce((a, d) => a + d.count, 0)
  return (
    <div className="bars" role="list">
      {data.map((d) => (
        <div
          key={d.name}
          className="bar-row"
          role="listitem"
          onMouseEnter={() => setHover(d.name)}
          onMouseLeave={() => setHover(null)}
        >
          <span className="bar-label" title={d.name}>{d.name}</span>
          <div className="bar-track">
            <div
              className={`bar-fill${highlight?.(d.name) ? ' hl' : ''}`}
              style={{ width: `${(d.count / max) * 100}%` }}
            />
          </div>
          <span className="bar-value">{n(d.count)}</span>
          {hover === d.name && (
            <span className="bar-tip">
              {d.name}: {n(d.count)} ({pct(d.count, sum)})
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

export function PriorityPill({ level }: { level: string }) {
  return <span className={`pill p-${level.toLowerCase()}`}>{level.toLowerCase()}</span>
}

const FLAG_LABEL: Record<string, string> = {
  'service-mismatch': '⚠ Service re-routed',
  'work-type-flip': '⇄ Work type flipped',
  'priority-inconsistent': '≠ Priority off-matrix',
  'unclear-input': '? Unclear input',
}
export function Flag({ flag }: { flag: string }) {
  return <span className="pill warn">{FLAG_LABEL[flag] ?? flag}</span>
}
