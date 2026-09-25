"""Resolution status + resolution note (README task items 6 and 7).

Status vocabulary (training data): done | cancelled | clarification | cannot reproduce.
Training statuses are ~25% each *independent of content* (a random-labels finding), so status is a **policy**
over the triage signals, never a learned label.

The note is the interesting part. Order of preference:
  1. playbook  - the best-matching human-written resolution mined from the 20k training comments
                 (README: "use its resolution pattern as the basis for yours"), adapted with ticket identifiers
  2. template  - a service/intent-specific note authored from the KB procedures (no historical evidence available)
Generation with an LLM (``llm_tasks.write_resolution_note``) sits on top of (1)/(2) and falls back to them.
"""
from __future__ import annotations

import re

from .catalogue import CHANNEL_SERVICE, SERVICES, UNKNOWN, team_for
from .models import Classification, Flags

# ------------------------------------------------------------------ intent detection
_RX = {
    "removal": re.compile(r"\b(?:remov\w*\s+(?:all\s+)?(?:access|permissions?|rights)|access\s+(?:removal|removed|revocation)|revoke|"
                          r"deactivat\w+|offboard\w*|leaver|left\s+the\s+organi[sz]ation|contract\s+(?:ended|end))\b", re.I),
    "license": re.compile(r"\blicen[sc]es?\b", re.I),
    "access": re.compile(r"\b(?:access|role|entitlement|permission|profile|account)\b", re.I),
    "provision": re.compile(r"\b(?:shared\s+mailbox|distribution\s+list|new\s+(?:mailbox|site|folder|group|account|dashboard|report)|creation\s+of|set\s*up\s+(?:a|the))\b", re.I),
    "vendor": re.compile(r"\b(?:vendor|custodian|third[\s-]party|external|broker|provider|notice|bank)\b", re.I),
    "feed": re.compile(r"\b(?:feed|file|publication|benchmark|index|delivery|delivered)\b", re.I),
    "transient": re.compile(r"\b(?:self[- ]?recover\w*|resolved\s+itself|could\s+not\s+reproduce|cannot\s+be\s+reproduced|transient|no\s+longer\s+(?:reproduc|occur)\w*|auto[- ]?cleared)\b", re.I),
}


def detect_intent(text: str, work_type: str) -> str:
    if work_type == "Service Request":
        if _RX["removal"].search(text):
            return "removal"
        if _RX["license"].search(text):
            return "license"
        if _RX["provision"].search(text):
            return "provision"
        return "access"
    if _RX["vendor"].search(text) and _RX["feed"].search(text):
        return "vendor_notice"
    return "incident"


_INTENT_WORDS = {
    "access": re.compile(r"\b(access|entitlement|role|permission|profile)\b", re.I),
    "license": re.compile(r"\blicen[sc]e", re.I),
    "removal": re.compile(r"\b(remov|revok|deactivat|offboard)", re.I),
    "provision": re.compile(r"\b(provision|mailbox|distribution|set up|created|site)\b", re.I),
}


def playbook_fits_intent(note: str, intent: str) -> bool:
    """A historical note about a margin sweep must not become the resolution of an access request just because both mention 'Cash'.
    Request intents (access / licence / removal / provision) reuse a note only when the note is about that kind of request."""
    if intent in ("incident", "vendor_notice"):                 # ...and an incident must not reuse a request-fulfilment note
        return not re.search(r"\b(provision\w*|licen[sc]e|granted|set up the shared|reclassified the ticket as a service request)\b", note, re.I)
    rx = _INTENT_WORDS.get(intent)
    return True if rx is None else bool(rx.search(note))


# ------------------------------------------------------------------ note templates (authored from the KB procedures)
INCIDENT_NOTE = {
    "Trading Platform": "Resolution: Isolated the fault to the affected execution connector, restarted the FIX session and replayed the queued messages after checking for duplicates; confirmed with the trading desk that orders and quotes flow normally again.",
    "Order Management": "Resolution: Found the orders stopping at the approval/routing step, corrected the routing configuration for the affected broker account, tested with a single order and then released the held orders; confirmed with the desk that new orders reach execution.",
    "Trade Matching": "Resolution: Identified the rejected messages as a reference/setup mismatch with the broker, corrected the mapping and replayed the rejected messages; confirmed the affected trades reached matched status.",
    "Securities Settlement": "Resolution: Checked the settlement message flow with the custodian, cleared the blocked messages and replayed the pending statuses; confirmed custody records and the operations dashboard were back in sync.",
    "Corporate Actions": "Resolution: Corrected the incomplete event data (mandatory fields and mapping), reprocessed the ingestion feed and confirmed the elections were published to the operations screen.",
    "Fund Pricing": "Resolution: Validated the affected prices against the secondary source, reloaded the corrected prices and re-ran price validation; confirmed all securities passed the tolerance checks.",
    "NAV Calculation": "Resolution: Reviewed the tolerance report to separate a genuine market move from a data error, corrected the underlying input where needed, re-ran the valuation and confirmed the NAV snapshot reached the downstream control queue.",
    "Portfolio Accounting": "Resolution: Identified the source of the reconciliation break, booked the approved correcting entry and re-ran the reconciliation; confirmed the exceptions cleared.",
    "Cash Management": "Resolution: Reconciled the cash ledger with the bank statement, booked the approved value-dated adjustment and confirmed the balance with the treasury desk.",
    "Risk & Compliance Monitoring": "Resolution: Rebuilt the dashboard summary from the underlying rule results, validated a sample of breaches manually and confirmed the statuses now match the detailed checks.",
    "Regulatory Reporting": "Resolution: Corrected the rejected data in the master records, regenerated the submission file and resubmitted it; the gateway confirmed acceptance.",
    "Rimes Data Feed": "Resolution: Confirmed with the vendor that the corrected file was available, reloaded it and re-ran the dependent price and valuation jobs; validated row counts and key prices against the previous delivery.",
    "Client Reporting": "Resolution: Corrected the report template logic, regenerated the affected batch and spot-checked the output PDFs before release.",
    "Tax Reporting": "Resolution: Corrected the tax output configuration, regenerated the affected extract and confirmed the figures with the tax team.",
    "CRM & Client Portal": "Resolution: Reproduced the portal/CRM error, corrected the affected configuration and confirmed with the user that the function works again.",
    "Identity & Access Management": "Resolution: Corrected the identity record that failed to synchronise, re-provisioned the account and confirmed the user can sign in.",
    "SharePoint & File Storage": "Resolution: Corrected the site or library configuration, re-synchronised the affected folders and confirmed access with the requester.",
    "Outlook & Email": "Resolution: Traced mail flow for the affected mailbox or list, corrected the routing configuration and verified delivery with test messages.",
    "SimCorp Dimension": "Resolution: Cleared the blocking lock on the failed job, restarted it from its last checkpoint and reconciled positions against the downstream reporting layer.",
    CHANNEL_SERVICE: "Resolution: Asked the requester to identify the affected application, then routed the ticket to the owning service team.",
}

VENDOR_NOTE = ("Resolution: Verified the vendor notice against monitoring and the vendor portal, obtained the corrected delivery for {service}, "
               "re-ran the dependent jobs and confirmed downstream processing completed normally.")
GRANT_NOTE = ("Resolution: Validated the request and the manager approval, assigned the standard role-based access for {service}"
              "{entity_clause}, and confirmed with the requester that access works.")
LICENSE_NOTE = ("Resolution: Confirmed a licence was available and approved by the {team} lead, assigned the {service} licence "
                "and verified that the user can sign in.")
REMOVAL_NOTE = ("Resolution: Removed direct permissions, group memberships and any temporary or inherited rights for the affected accounts on "
                "{service}, then ran an access review confirming that no active entitlements remain.")
PROVISION_NOTE = ("Resolution: Provisioned the requested item in {service}, granted the agreed rights to the requesting team and "
                  "confirmed with the requester that it is available.")
CLARIFY_NOTE = ("Resolution: Asked the reporter for the missing details ({asks}) before any action was taken; the ticket stays in "
                "clarification until they reply.")
DUPLICATE_NOTE = "Resolution: Linked this ticket to the open parent incident {parent} on {service} and closed it as a duplicate."
TRANSIENT_NOTE = ("Resolution: Monitored {service} after the alert, found no ongoing failure and could not reproduce the fault; "
                  "documented the observation and kept the alert under watch.")


def template_note(service: str, work_type: str, text: str, team: str, entity: str | None) -> tuple[str, str]:
    """Returns (note, template_id)."""
    intent = detect_intent(text, work_type)
    ent = f" for {entity}" if entity else ""
    if intent == "removal":
        return REMOVAL_NOTE.format(service=service), "removal"
    if intent == "license":
        return LICENSE_NOTE.format(service=service, team=team), "license"
    if intent == "provision":
        return PROVISION_NOTE.format(service=service), "provision"
    if intent == "access":
        return GRANT_NOTE.format(service=service, entity_clause=ent), "access"
    if intent == "vendor_notice" and service != CHANNEL_SERVICE:
        return VENDOR_NOTE.format(service=service), "vendor_notice"
    return INCIDENT_NOTE.get(service, INCIDENT_NOTE[CHANNEL_SERVICE]), f"incident:{service}"


# ------------------------------------------------------------------ identifiers for specificity
_REF_PATTERNS = [
    re.compile(r"\b[A-Z][A-Z0-9]{1,9}(?:[-_][A-Z0-9]{2,}){1,4}\b"),     # job / adapter / queue ids such as ABC-123 or JOB_NAME_42
    re.compile(r"\b\S+\.(?:txt|csv|xml|json|xlsx|dat)\b", re.I),        # file names
    re.compile(r"\b[A-Z]{3,5}\d{3,6}\b"),                               # host names like ABCD1234
]
_REF_SKIP = re.compile(r"^(?:KB|HIST|CH|TRN|T)-", re.I)


def extract_refs(text: str, limit: int = 3) -> list[str]:
    seen: list[str] = []
    for rx in _REF_PATTERNS:
        for m in rx.finditer(text or ""):
            v = m.group(0).strip(".,;:()")
            if v and not _REF_SKIP.match(v) and not v.startswith("[") and v not in seen and len(v) <= 60:
                seen.append(v)
    return seen[:limit]


def with_refs(note: str, refs: list[str]) -> str:
    if not refs:
        return note
    return f"{note.rstrip()} (Ref: {', '.join(refs)}.)"


# ------------------------------------------------------------------ status policy
def decide_status(cls: Classification, flags: Flags, text: str, has_playbook: bool, duplicate_of: str | None) -> tuple[str, str]:
    """(status, why). The 'done' default reflects that the deliverable is a concrete, completed resolution note."""
    if flags.injection:
        return "clarification", "instruction-like text in an external ticket: escalated to a human, no auto-action"
    if duplicate_of:
        return "cancelled", f"duplicate of open incident {duplicate_of}"
    if _RX["transient"].search(text):
        return "cannot reproduce", "text reports a self-cleared / non-reproducible alert"
    if cls.unclear and not has_playbook:
        return "clarification", "input is unclear and no comparable historical resolution exists: ask, never guess"
    if cls.service == UNKNOWN:
        return "clarification", "affected system cannot be identified from the ticket"
    return "done", "actionable ticket with a concrete resolution path"
