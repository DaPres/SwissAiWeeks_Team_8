"""Service catalogue: service -> team (strict 1:1), criticality rating and a domain ontology.

* ``TEAM_OF`` and ``CRITICALITY`` come straight from the challenge README / training data and are
  asserted against the 20k training tickets by ``verify_against_training`` (and the test-suite).
* The ontology (``strong`` / ``weak`` terms, English + German + French) is *generic domain
  knowledge* about what each catalogue service does in an asset manager. It contains no
  ticket-specific identifiers; it is what a service-desk analyst would know on day one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

UNKNOWN = "UNKNOWN"
CHANNEL_SERVICE = "Emailed Support Tickets"  # a channel, not a system -> Service Desk


@dataclass(frozen=True)
class Service:
    name: str
    team: str
    critical: bool
    description: str
    strong: tuple[str, ...] = ()
    weak: tuple[str, ...] = ()
    # Terms that mean the ticket is *about the neighbour*, not this service (used as counter-evidence)
    not_this: tuple[str, ...] = ()
    _rx: tuple = field(default=(), repr=False, compare=False)


def _svc(name, team, critical, description, strong=(), weak=(), not_this=()):
    return Service(name, team, critical, description, tuple(strong), tuple(weak), tuple(not_this))


# NOTE on term syntax: plain phrases, matched case-insensitively on word boundaries.
# A trailing ``*`` means "any word continuation" (e.g. ``settle*`` -> settled, settlement).
_CATALOGUE: list[Service] = [
    _svc(
        "Trading Platform", "Investment Operations", True,
        "Front-office trading application: trade capture/entry, execution and market connectivity.",
        strong=["trading platform", "trading application", "trading system", "front office platform",
                "front-office platform", "trade capture", "trade entry", "execution venue*", "market connectivity",
                "fix session*", "fix gateway", "trader workstation", "trading screen*", "blotter",
                "handelsplattform", "plateforme de trading", "plateforme de négociation", "piattaforma di trading"],
        weak=["trading", "trader*", "quote*", "algo*", "venue*", "market access", "execution", "handel*"],
    ),
    _svc(
        "Order Management", "Trading Support", True,
        "Order management system (OMS): order creation, approval, broker routing and execution routing.",
        strong=["order management", "oms", "order routing", "execution routing", "order workflow", "staged order*", "order blotter", "broker routing", "auftragsverwaltung", "auftragsbuch", "gestion des ordres",
                ],
        weak=["order*", "broker account*", "broker mapping*", "route*", "routing", "pre-trade", "auftrag", "aufträge",
              "ordre*"],
    ),
    _svc(
        "Trade Matching", "Investment Operations", True,
        "Trade matching / confirmation / affirmation between our bookings and broker or counterparty messages.",
        strong=["trade matching", "matching adapter", "allocation message*", "allocation*", "unmatched trade*",
                "affirmation*", "trade confirmation*", "confirmation matching", "execution reference*",
                "matching backlog", "matching engine", "broker confirmation*", "ctm", "abgleich der trades",
                "rapprochement des transactions", "trade-matching"],
        weak=["matching", "matched", "confirmation*", "broker*", "counterpart*", "ssi", "adapter", "abgleich",
              "rapprochement"],
    ),
    _svc(
        "Securities Settlement", "Securities Operations", True,
        "Settlement of securities trades with custodians / CSDs: instructions, status messages, fails.",
        strong=["securities settlement", "settlement", "settle*", "custodian*", "custody", "mt536", "mt537", "mt540",
                "mt541", "mt542", "mt543", "mt544", "mt545", "mt548", "settlement status", "fail-chasing", "settlement fail*",
                "csd", "euroclear", "clearstream", "dvp", "rvp", "delivery versus payment", "abwicklung", "wertpapierabwicklung",
                "règlement-livraison", "règlement livraison", "règlement des titres", "dépositaire", "verwahrstelle", "swift status"],
        weak=["fails", "instruction*", "acknowledg*", "confirmation queue", "statement*", "depot", "isd", "règlement"],
    ),
    _svc(
        "Corporate Actions", "Securities Operations", True,
        "Corporate action events: dividends, splits, mergers, elections, option codes, event ingestion.",
        strong=["corporate action*", "corporate-action*", "caev", "option code*", "election*", "dividend*",
                "stock split*", "rights issue*", "tender offer*", "merger*", "record date*", "ex-date*", "ex date*",
                "mt564", "mt565", "mt566", "proxy voting", "kapitalmassnahme*", "opérations sur titres",
                "operations sur titres", "event payload*", "coupon payment*"],
        weak=["event*", "ingestion", "voluntary", "mandatory event*", "entitlement*"],
    ),
    _svc(
        "Fund Pricing", "Valuation & Pricing", True,
        "Security and fund price production: price validation, price mastering, tolerances, price snapshots.",
        strong=["fund pricing", "pricing run", "price validation", "price mastering", "stale price*", "price tolerance*",
                "unit price*", "security price*", "price snapshot*", "pricing source*", "swing pric*", "price file*",
                "fondspreis*", "preisfeststellung", "prix des fonds", "cours des fonds", "valorisation des titres",
                "pricing"],
        weak=["price*", "prices", "valuation source*", "tolerance*", "prix", "preis*", "kurs*"],
    ),
    _svc(
        "NAV Calculation", "Valuation & Pricing", True,
        "Net asset value calculation and publication for funds (end-of-day valuation run).",
        strong=["nav", "net asset value", "nav calculation", "nav publication", "nav snapshot*", "valuation run",
                "valuation tolerance*", "nav strike", "share class nav", "end-of-day valuation", "eod valuation",
                "fund valuation", "nettoinventarwert", "inventarwert", "valeur liquidative", "vni",
                "valuation tolerance breach"],
        weak=["valuation*", "tolerance breach*", "fund accounting", "share class*", "funds", "fonds", "bewertung*"],
    ),
    _svc(
        "Portfolio Accounting", "Investment Operations", True,
        "Portfolio / investment accounting: books and records, positions, reconciliation, ledger, P&L.",
        strong=["portfolio accounting", "book of record",
                "ibor", "abor", "general ledger", "accounting books", "position reconciliation", "journal entr*",
                "portfoliobuchhaltung", "buchhaltung", "comptabilité de portefeuille", "comptabilite de portefeuille",
                ],
        weak=["reconcil*", "ledger", "accounting", "p&l", "pnl", "holdings", "positions", "abstimmung", "rapprochement comptable"],
    ),
    _svc(
        "Cash Management", "Treasury & Cash", True,
        "Cash, liquidity and treasury operations: cash ledger, sweeps, margin, bank statements, nostro.",
        strong=["cash management", "margin sweep*", "cash sweep*", "cash ledger", "liquidity", "nostro", "vostro",
                "bank statement*", "cash position*", "cash balance*", "margin call*", "cash forecast*", "treasury",
                "liquidität", "liquiditätsmanagement", "trésorerie", "tresorerie",
                "cash-management"],
        weak=["cash", "margin", "sweep*", "payment*", "value date*", "value-dated", "intraday", "bank", "zahlung*",
              "paiement*", "kollateral", "collateral"],
    ),
    _svc(
        "Risk & Compliance Monitoring", "Risk & Controls", True,
        "Investment-guideline, risk-limit and compliance monitoring: breaches, sanctions/AML screening, surveillance.",
        strong=["compliance monitoring", "risk & compliance", "risk and compliance", "sanctions screening",
                "sanction screening", "sanctions list*", "aml", "compliance dashboard", "limit breach*",
                "guideline breach*", "investment restriction*", "pre-trade compliance", "post-trade compliance",
                "compliance rule*", "breach status*", "concentration limit*", "trade surveillance", "watchlist*",
                "risk limit*", "compliance-überwachung", "überwachung", "conformité", "surveillance de la conformité",
                "sanktionsprüfung", "filtrage des sanctions", "compliance check*"],
        weak=["compliance", "breach*", "risk", "exposure*", "var", "rule update*", "control*", "monitoring dashboard",
              "screening", "alerts", "restriction*", "limit*"],
    ),
    _svc(
        "Regulatory Reporting", "Risk & Controls", True,
        "Regulatory transaction / fund reporting to authorities (MiFID, EMIR, SFTR, AIFMD, LEI, FINMA, CSSF...).",
        strong=["regulatory reporting", "regulator*", "lei", "mifid*", "emir", "sftr", "aifmd", "transaction reporting",
                "regulatory filing*", "regulatory submission*", "finma", "cssf", "bafin", "esma", "amf", "approved reporting mechanism", "arm submission", "form pf", "priips", "kiid",
                "meldewesen", "aufsicht*", "reporting réglementaire", "déclaration réglementaire", "autorité de surveillance",
                ],
        weak=["submission*", "filing*", "gateway", "classification segment", "mandatory field*", "authority",
              "authorities", "compliance report*"],
    ),
    _svc(
        "Rimes Data Feed", "Market Data Services", True,
        "Vendor market-data / benchmark / index data delivered by Rimes and similar providers.",
        strong=["rimes", "benchmark file*", "benchmark data", "benchmark publication", "benchmark feed*", "benchmark delivery", "index data", "index constituent*", "market data", "data feed*", "vendor feed*",
                "feed delivery", "eod file*", "price file delivery",
                "index provider*", "msci", "ftse", "s&p dow jones", "bloomberg data license",
                "marktdaten", "données de marché", "donnees de marche", "indexdaten", "référentiel"],
        weak=["benchmark*", "feed*", "feed delay*", "delayed feed", "late feed", "vendor file*", "file delivery", "cutoff", "cut-off", "delivered late",
              "snapshot*", "constituent*", "reference data", ],
    ),
    _svc(
        "Client Reporting", "Client Services", True,
        "Production and distribution of client reports, statements, factsheets and PDF report packs.",
        strong=["client reporting", "client report*", "report pack*", "report template*", "quarterly report*",
                "investor report*", "performance report*", "factsheet*", "fact sheet*", "client statement*", "report generation", "kundenbericht*", "kundenreporting", "rapport client*",
                "rapports clients", "reporting client", "generated pdf*", "pdf pack*", "report batch*"],
        weak=["report*", "pdf*", "statement*", "distribution of reports", "fee section", "template*", "bericht*", "rapport*"],
    ),
    _svc(
        "Tax Reporting", "Tax & Reporting", False,
        "Tax reporting and tax calculation for funds and investors: withholding tax, reclaims, tax packs.",
        strong=["tax reporting", "withholding tax", "wht", "tax pack*", "tax extract*", "tax filing*", "tax reclaim*",
                "tax reclaims", "tax certificate*", "tax output", "vat", "tax return*", "dividend tax", "capital gains tax",
                "steuerreporting", "quellensteuer", "steuer*", "fiscalité", "retenue à la source", "retenue a la source",
                "déclaration fiscale", "impôt*"],
        weak=["tax*", "taxes", "fiscal*", "reclaim*", "quarterly filing"],
    ),
    _svc(
        "CRM & Client Portal", "Client Services", False,
        "Client relationship management and the investor-facing client portal.",
        strong=["crm", "client portal", "investor portal", "relationship manager*", "client relationship", "client onboarding",
                "investor interaction*", "salesforce", "kundenportal", "investorenportal", "portail client", "portail investisseur",
                "client contact*", "lead management"],
        weak=["portal", "client*", "investor*", "contact*", "sales", "kunden*", "opportunit*", "interaction*"],
    ),
    _svc(
        "Identity & Access Management", "Enterprise Applications", False,
        "Identity lifecycle and access governance: joiners/leavers, deactivation, MFA/SSO, role provisioning.",
        strong=["identity & access", "identity and access", "iam", "deactivated user*",
                "user deactivation*", "account deactivation*", "inactive account*", "inactive user*",
                "mfa", "multi-factor", "single sign-on", "sso", "active directory", "entra", "azure ad", "password reset",
                "access recertification", "access review", "role provisioning", "privileged access", "benutzerverwaltung",
                "identitäts", "gestion des identités", "gestion des acces", "gestion des accès", "zugriffsverwaltung",
                "orphaned account*", "account lifecycle"],
        weak=["identity", "joiner*", "leaver*", "deactivat*", "entitlement*", "role*", "account*", "permission*", "provisioning", "lockout",
              "locked out", "credential*", "passwort", "mot de passe"],
    ),
    _svc(
        "SharePoint & File Storage", "Enterprise Applications", False,
        "SharePoint sites, document libraries and file shares / OneDrive storage.",
        strong=["sharepoint", "document librar*", "file share*", "shared drive*", "onedrive", "site permission*",
                "teams site*", "file storage", "document storage",
                "dateiablage", "laufwerk", "stockage de fichiers", "bibliothèque de documents", "bibliotheque de documents",
                "collaboration site*", "site collection*"],
        weak=["folder*", "document*", "site access", "sync*", "storage", "ordner", "dossier*", "dokument*"],
    ),
    _svc(
        "Outlook & Email", "Enterprise Applications", False,
        "Outlook / Exchange mail: mailboxes, shared mailboxes, distribution lists, mail flow, calendars.",
        strong=["outlook", "shared mailbox*", "distribution list*", "mailbox*", "exchange online", "mail flow", "mail delivery",
                "email delivery", "calendar", "out of office", "postfach", "verteilerliste*", "boîte mail",
                "boite mail", "boîte aux lettres", "boite aux lettres", "liste de distribution", "e-mail-zustellung",
                "shared-mailbox"],
        weak=["smtp", "signature*", "courriel*"],
    ),
    _svc(
        "SimCorp Dimension", "Enterprise Applications", True,
        "SimCorp Dimension investment-management platform: batch jobs, replication, position sync, environments.",
        strong=["simcorp", "simcorp dimension", "dimension platform", "scd", "replication job*",
                "simcorp batch*", "coric", "simcorp environment*", "dimension batch", "simcorp-dimension", "simcorp job*"],
        weak=["replication", "batch job*", "sync job*", "job failed",
              "host"],
    ),
    _svc(
        "Emailed Support Tickets", "Service Desk", False,
        "Generic email intake channel of the service desk - a channel, not an underlying system.",
        strong=["emailed support ticket*", "support mailbox", "servicedesk mailbox", "service desk mailbox"],
        weak=[],
    ),
]

SERVICES: dict[str, Service] = {s.name: s for s in _CATALOGUE}
SERVICE_NAMES: list[str] = [s.name for s in _CATALOGUE]
TEAM_OF: dict[str, str] = {s.name: s.team for s in _CATALOGUE}
CRITICALITY: dict[str, str] = {s.name: ("Critical" if s.critical else "Non-Critical") for s in _CATALOGUE}
TEAMS: list[str] = sorted(set(TEAM_OF.values()))
ENTITIES = ["Luxembourg", "Nordics", "Switzerland", "Germany", "France"]

# The ticket-facing spelling of the 4 resolution outcomes (training vocabulary).
RESOLUTIONS = ("done", "cancelled", "clarification", "cannot reproduce")

# ---------------------------------------------------------------- matching helpers
_rx_cache: dict[str, re.Pattern] = {}


def _compile(term: str) -> re.Pattern:
    rx = _rx_cache.get(term)
    if rx is None:
        star = term.endswith("*")
        core = term[:-1] if star else term
        pat = re.escape(core).replace(r"\ ", r"\s+").replace(r"\-", r"[-\s]?")
        # unicode-aware word boundaries: letters/digits/underscore are "word" chars
        pat = r"(?<![\w])" + pat + (r"\w*" if star else "") + r"(?![\w])"
        rx = re.compile(pat, re.IGNORECASE | re.UNICODE)
        _rx_cache[term] = rx
    return rx


def find_terms(text: str, terms: Iterable[str]) -> list[str]:
    """Return the distinct terms from ``terms`` that occur in ``text``."""
    hits = []
    for t in terms:
        if _compile(t).search(text):
            hits.append(t)
    return hits


def team_for(service: str) -> str:
    """Strict lookup (Sec. 6.4): unknown service -> Service Desk queue for clarification, never a guess."""
    return TEAM_OF.get(service, TEAM_OF[CHANNEL_SERVICE])


def is_critical(service: str) -> bool:
    return service in SERVICES and SERVICES[service].critical


def verify_against_training(tickets) -> dict:
    """Assert the catalogue is exactly the 1:1 mapping present in the training data."""
    seen: dict[str, set[str]] = {}
    for t in tickets:
        for s in t.services:
            seen.setdefault(s, set()).update(t.teams)
    problems = []
    for s, teams in seen.items():
        if len(teams) != 1:
            problems.append(f"{s}: maps to {sorted(teams)}")
        elif TEAM_OF.get(s) not in teams:
            problems.append(f"{s}: catalogue says {TEAM_OF.get(s)!r}, data says {sorted(teams)}")
    missing = set(SERVICE_NAMES) - set(seen)
    if missing:
        problems.append(f"catalogue services never seen in data: {sorted(missing)}")
    return {"services_in_data": len(seen), "problems": problems, "ok": not problems}
