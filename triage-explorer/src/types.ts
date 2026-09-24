export type Level = 'lowest' | 'low' | 'medium' | 'high' | 'highest'

export interface NameCount { name: string; count: number }

export interface Pattern {
  text: string
  count: number
  resolver: string
  resolverInAssigneePool: boolean
}

export interface Service {
  name: string
  team: string
  critical: boolean
  tickets: number
  distinctAssignees: number
  topAssigneeShare: number
  patterns: Pattern[]
}

export interface Triaged {
  id: number
  input: {
    'Work type': string
    'Request type': string
    Summary: string
    Description: string
    'Affected Business or IT Services': string[]
    'Business Entity': string[]
    Priority: string
    Urgency: string
    Impact: string
    'All Comments': string[]
  }
  baseline: {
    workType: string
    service: string
    serviceCritical: boolean
    team: string
    assignee: string | null
    urgency: Level
    impact: Level
    priority: Level
    resolution: string
    confidence: number
    precedent: { service: string; text: string; resolver: string; score: number } | null
    alternatives: { service: string; score: number }[]
  }
  flags: string[]
}

export interface Insights {
  meta: {
    trainingTickets: number
    challengeTickets: number
    challengeRunId: string
    assigneePoolSize: number
    matrixConsistentInTraining: number
  }
  distributions: Record<string, NameCount[]>
  commentTiers: NameCount[]
  families: { name: string; total: number; incident: number; serviceRequest: number }[]
  services: Service[]
  matrix: Record<Level, Level[]>
  triaged: Triaged[]
}
