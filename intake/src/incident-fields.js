import catalog from './catalog.json';
import priorityPolicy from './priority-matrix.json';

export const levels = priorityPolicy.levels;
const impactLabels = {
  highest: 'Major / Widespread', high: 'Significant / Large', medium: 'Moderate / Limited',
  low: 'Minor / Localized', lowest: 'No Direct Impact / Information',
};
const titleCase = value => value ? value[0].toUpperCase() + value.slice(1) : '';
export const chipFields = {
  workType: { label: 'Work Type', options: ['Incident', 'Service Request'] },
  urgency: { label: 'Urgency', options: levels, format: titleCase },
  impact: { label: 'Impact', options: levels, format: value => impactLabels[value] || value },
  priority: { label: 'Priority', kind: 'priority', format: titleCase },
  department: { label: 'Service Teams', options: catalog['Service Team(s)'] },
};

export function calculatePriority(urgency, impact) {
  const row = levels.indexOf(urgency);
  const column = levels.indexOf(impact);
  return row < 0 || column < 0 ? '' : priorityPolicy.matrix[row][column];
}

export function resolvedFields(details, inferred) {
  return { ...inferred, ...details };
}
