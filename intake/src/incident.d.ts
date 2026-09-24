export type Level = 'lowest' | 'low' | 'medium' | 'high' | 'highest';
export type Resolution = 'done' | 'cancelled' | 'clarification' | 'cannot reproduce';
export interface Incident {
  'Work type': 'Incident';
  Summary: string;
  Description: string;
  'Affected Business or IT Services': string[];
  'Business Entity': ('Switzerland' | 'France' | 'Germany' | 'Luxembourg' | 'Nordics')[];
  'Service Team(s)': string[];
  Reporter: string;
  Assignee: string;
  Priority: Level;
  Urgency: Level;
  Impact: Level;
  'Created date': string;
  Status: 'open' | 'in progress' | 'done';
  Resolution: Resolution | null;
  'Resolution date': string | null;
  'All Comments': string[];
}

/** Progressive intake leaves unknown fields absent for later enrichment. */
export type IntakeIncident = Partial<Incident> & Pick<Incident,
  'Work type' | 'Description' | 'Status' | 'Created date' | 'Resolution' | 'Resolution date' | 'All Comments'>;
