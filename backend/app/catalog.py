"""Service catalog, criticality and the Urgency x Impact -> Priority matrix (from the challenge README)."""

LEVELS = ["highest", "high", "medium", "low", "lowest"]

URGENCY_DEFINITIONS = {
    "highest": "Critical: immediate action required (regulatory breach, security compromise, major outage). No workaround.",
    "high": "High: rapid resolution needed within hours. Workaround available but difficult/time-consuming.",
    "medium": "Medium: important to fix soon; no immediate operational/regulatory threat. Easy workaround available.",
    "low": "Low: handled in normal workflow without urgent escalation.",
    "lowest": "Lowest: routine/informational with no effect on operations or compliance.",
}
IMPACT_DEFINITIONS = {
    "highest": "Major/Widespread: full unavailability of critical IT services supporting key operations (>2h downtime).",
    "high": "Significant/Large: partial unavailability of critical services, 1+ business entities or financial counterparts affected.",
    "medium": "Moderate/Limited: full unavailability of non-critical services, or up to 1 business entity affected.",
    "low": "Minor/Localized: partial unavailability of non-critical services, or individuals affected.",
    "lowest": "No direct impact: informational/maintenance without service degradation.",
}

# MATRIX[urgency][impact] -> priority
_ROWS = {
    "highest": ["highest", "highest", "high", "medium", "medium"],
    "high":    ["highest", "high", "high", "medium", "low"],
    "medium":  ["high", "high", "medium", "low", "low"],
    "low":     ["medium", "medium", "low", "low", "lowest"],
    "lowest":  ["medium", "low", "low", "lowest", "lowest"],
}
MATRIX = {u: dict(zip(LEVELS, row)) for u, row in _ROWS.items()}


def priority(urgency: str, impact: str) -> str:
    return MATRIX[urgency][impact]


def matrix_table() -> str:
    """The README's Incident Priority Calculation Matrix as a plain-text table for prompts."""
    head = "urgency \\ impact | " + " | ".join(f"{i:<7}" for i in LEVELS)
    return "\n".join([head, *(f"{u:>16} | " + " | ".join(f"{MATRIX[u][i]:<7}" for i in LEVELS) for u in LEVELS)])


# name -> (owning team, critical?, short description used as a catalog knowledge card)
SERVICES: dict[str, tuple[str, bool, str]] = {
    "Trading Platform": ("Investment Operations", True, "Front-office trading platform used by traders to execute orders; execution screens, trader workstations."),
    "Order Management": ("Trading Support", True, "OMS: order creation, approval workflow, broker account mapping and routing of orders to execution."),
    "Trade Matching": ("Investment Operations", True, "Matching adapters pairing broker executions with staged allocations; confirmations, SSI mappings, allocation rejections."),
    "Securities Settlement": ("Securities Operations", True, "Post-matching settlement: custodian status messages (MT536/MT548), settlement confirmation queues, custody reconciliation."),
    "Corporate Actions": ("Securities Operations", True, "Corporate action event ingestion (CAEV), option codes, elections and instruction processing."),
    "Fund Pricing": ("Valuation & Pricing", True, "Security and fund price validation, stale price checks, price mastering."),
    "NAV Calculation": ("Valuation & Pricing", True, "End-of-day NAV batches, valuation tolerance checks, NAV publication to downstream control queues."),
    "Portfolio Accounting": ("Investment Operations", True, "Portfolio accounting, positions ledger, month-end reconciliation and exception review."),
    "Cash Management": ("Treasury & Cash", True, "Treasury cash ledger, margin sweeps, bank statement reconciliation, liquidity movements and cutoffs."),
    "Risk & Compliance Monitoring": ("Risk & Controls", True, "Compliance rule monitoring, breach dashboards, sanctions screening, pre/post-trade checks."),
    "Regulatory Reporting": ("Risk & Controls", True, "Regulatory submissions (LEI, EMIR, AIFMD) to regulator gateways; classification master data."),
    "SimCorp Dimension": ("Enterprise Applications", True, "SimCorp Dimension platform: position sync/replication jobs (e.g. SCD_POS_SYNC), hosts, reporting layer feeds."),
    "Rimes Data Feed": ("Market Data Services", True, "Rimes benchmark and index data files; vendor delivery windows, late or incomplete benchmark publications."),
    "Client Reporting": ("Client Services", True, "Client report generation (PDF packs), report templates, fee sections, quarterly batches."),
    "Tax Reporting": ("Tax & Reporting", False, "Tax output: withholding tax workflow, tax packs and extracts, quarterly filings."),
    "CRM & Client Portal": ("Client Services", False, "CRM for relationship managers and the investor-facing client portal."),
    "Identity & Access Management": ("Enterprise Applications", False, "User identities, joiner/mover/leaver, deactivation clean-up, role-based access provisioning."),
    "SharePoint & File Storage": ("Enterprise Applications", False, "SharePoint sites, document libraries, synced folders and permissions."),
    "Outlook & Email": ("Enterprise Applications", False, "Mailboxes, shared mailboxes, distribution lists, Outlook client issues."),
}
# Generic intake bucket from the training data; never a valid routing target.
GENERIC_BUCKET = "Emailed Support Tickets"


def team_for(service: str) -> str:
    return SERVICES[service][0]


def is_critical(service: str) -> bool:
    return SERVICES[service][1]
