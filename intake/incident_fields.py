"""The challenge fields, their allowed values, and deterministic priority policy."""
import json
from pathlib import Path

SOURCE = Path(__file__).parent / 'src'
CATALOG = json.loads((SOURCE / 'catalog.json').read_text())
ASSIGNEES = json.loads((SOURCE / 'assignees.json').read_text())
PRIORITY = json.loads((SOURCE / 'priority-matrix.json').read_text())
LEVELS, MATRIX = PRIORITY['levels'], PRIORITY['matrix']
RESOLUTIONS = ['done', 'cancelled', 'clarification', 'cannot reproduce']
WORK_TYPES = ['Incident', 'Service Request']
CHIP_OPTIONS = {
    'workType': ('Work Type', WORK_TYPES),
    'urgency': ('Urgency', LEVELS),
    'impact': ('Impact', LEVELS),
    'priority': ('Priority', LEVELS),
    'department': ('Service Teams', CATALOG['Service Team(s)']),
}


def calculate_priority(urgency, impact):
    if urgency not in LEVELS or impact not in LEVELS:
        return None
    return MATRIX[LEVELS.index(urgency)][LEVELS.index(impact)]
