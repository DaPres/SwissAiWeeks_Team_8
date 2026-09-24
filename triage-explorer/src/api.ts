import type { Level } from './types'

export interface Draft {
  summary: string
  description: string
  workType: 'Incident' | 'Service Request'
  service: string
  team: string
  critical: boolean
  assignee: string | null
  assigneeReason: string
  urgency: Level
  impact: Level
  priority: Level
}

export interface Match {
  id: string
  source: 'training' | 'catalog' | 'live'
  service: string
  title: string
  resolver: string | null
  resolution: string | null
  helpful: number
  score: number
}

export interface AssistResult {
  assistId: string
  mode: 'azure' | 'mock'
  imageDescriptions: string[]
  understanding: string
  selfService: { possible: boolean; answer: string }
  needsTicket: boolean
  clarifyingQuestion: string
  draft: Draft
  rationale: string
  usedKnowledgeIds: string[]
  matches: Match[]
  duplicates: { id: number; summary: string; service: string; score: number }[]
}

export interface AssistProgress {
  step: 'vision' | 'embedding' | 'knowledge' | 'duplicates' | 'decision' | 'routing' | 'complete'
  status: 'started' | 'completed'
  title: string
  tool?: string | null
  detail?: string | null
  durationMs?: number | null
  data?: Record<string, unknown> | null
}

export interface Ticket {
  id: number
  created_at: number
  status: 'open' | 'resolved'
  reporter: string | null
  user_text: string
  image_descriptions: string[]
  summary: string
  description: string
  work_type: 'Incident' | 'Service Request'
  service: string
  team: string
  assignee: string | null
  urgency: Level
  impact: Level
  priority: Level
  ai_triage: Draft
  resolution: string | null
  resolution_text: string | null
  resolved_at: number | null
}

export interface CatalogService { name: string; team: string; critical: boolean }
export interface Catalog { services: CatalogService[]; levels: Level[]; matrix: Record<Level, Record<Level, Level>> }

export interface Stats {
  knowledge: { bySource: Record<string, number>; total: number; helpfulVotes: number }
  assists: Record<string, number>
  tickets: { open: number; resolved: number }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json()
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: 'POST', body: JSON.stringify(body) })

async function assistStream(text: string, images: string[], debug: boolean,
                            onProgress: (event: AssistProgress) => void, signal?: AbortSignal): Promise<AssistResult> {
  const res = await fetch('/api/assist/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ text, images, debug }),
    signal,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* not json */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (!res.body) throw new Error('The analysis stream is unavailable')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: AssistResult | null = null

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = block.match(/^event: (.+)$/m)?.[1]
        const data = block.match(/^data: (.+)$/m)?.[1]
        if (event && data) {
          const payload = JSON.parse(data)
          if (event === 'progress') onProgress(payload as AssistProgress)
          if (event === 'result') result = payload as AssistResult
          if (event === 'error') throw new Error(payload.message ?? 'Analysis failed')
        }
        boundary = buffer.indexOf('\n\n')
      }
      if (done) break
    }
  } finally {
    reader.releaseLock()
  }
  if (!result) throw new Error('The analysis ended before returning a result')
  return result
}

export const api = {
  catalog: () => call<Catalog>('/catalog'),
  stats: () => call<Stats>('/stats'),
  assist: (text: string, images: string[]) => post<AssistResult>('/assist', { text, images }),
  assistStream,
  feedback: (assistId: string, helpful: boolean) => post<{ ok: boolean }>(`/assist/${assistId}/feedback`, { helpful }),
  createTicket: (assistId: string, d: Draft) =>
    post<Ticket>('/tickets', {
      assist_id: assistId, summary: d.summary, description: d.description, work_type: d.workType,
      service: d.service, urgency: d.urgency, impact: d.impact,
    }),
  tickets: () => call<Ticket[]>('/tickets'),
  draftResolution: (id: number) => post<{ text: string; precedents: { id: string; resolution: string; score: number }[] }>(`/tickets/${id}/draft-resolution`, {}),
  resolve: (id: number, body: {
    resolution: string; resolution_text: string; assignee: string; service: string
    work_type: string; urgency: Level; impact: Level
  }) => post<{ ticket: Ticket; learnedKnowledgeId: string | null; knowledge: Stats['knowledge'] }>(`/tickets/${id}/resolve`, body),
}

export type QualityLevel = 'gold' | 'silver' | 'bronze' | 'reject'

export interface CurationCluster {
  id: number
  service: string
  team: string
  size: number
  score: number
  level: QualityLevel
  meanTicketScore: number
  coherence: number
  resolutionKind: 'rich' | 'canned' | 'fixed_only' | 'none'
  kinds: Record<string, number>
  title: string
  problem?: string
  problemVariants: number
  resolution: string | null
  resolver: string | null
  flags: Record<string, number>
  components: Record<string, number>
}

export interface CurationSummary {
  createdAt: number
  embeddingModel: string
  threshold: number
  seconds: number
  tickets: number
  clusters: number
  ticketLevels: Record<QualityLevel, number>
  clusterLevels: Record<QualityLevel, { clusters: number; tickets: number }>
  scoreHistogram: { bucket: number; count: number }[]
  flags: { flag: string; label: string; count: number }[]
  levelThresholds: Record<QualityLevel, number>
}

export interface CurationSample {
  idx: number
  score: number
  level: QualityLevel
  flags: string[]
  'Work type': string
  Summary: string
  Description: string
  'Affected Business or IT Services': string[]
  Assignee: string
  Status: string
  Resolution: string | null
  'Created date': string
  'All Comments': string[]
}

export const curationApi = {
  get: () => call<{ summary: CurationSummary; clusters: CurationCluster[]; knowledge: Stats['knowledge'] & { byLevel: Record<string, number>; minLevel: QualityLevel | null } }>('/curation'),
  cluster: (id: number) => call<{ cluster: CurationCluster; samples: CurationSample[] }>(`/curation/clusters/${id}`),
  run: (threshold?: number) => post<{ summary: CurationSummary }>('/curation/run', { threshold }),
  publish: (minLevel: Exclude<QualityLevel, 'reject'>) =>
    post<{ minLevel: string; published: number; tickets: number; knowledge: Stats['knowledge'] }>('/curation/publish', { min_level: minLevel }),
}
