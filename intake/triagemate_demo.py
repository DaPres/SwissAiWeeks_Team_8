"""Compatibility imports for the former preview endpoint; all calls use the shared API."""
from engine_client import complete_draft_fields, prepare_incident, preview_incident

__all__ = ['complete_draft_fields', 'prepare_incident', 'preview_incident']
