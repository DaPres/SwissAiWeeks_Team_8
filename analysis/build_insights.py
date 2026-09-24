"""Profile the 20k training set and run a baseline retrieval pipeline over the
challenge tickets. Writes a compact JSON consumed by the React explorer.

Usage: python3 analysis/build_insights.py
"""
import collections as C
import glob
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN = os.path.join(ROOT, "jira_first_20000_requested_fields_synthetic.json")
CHALLENGE = sorted(glob.glob(os.path.join(ROOT, "jira_hackathon_*challenge*.json")))[-1]
OUT = os.path.join(ROOT, "triage-explorer", "src", "data", "insights.json")

CRITICAL = {
    "Trading Platform", "Order Management", "Trade Matching", "Securities Settlement",
    "Corporate Actions", "Fund Pricing", "NAV Calculation", "Portfolio Accounting",
    "Cash Management", "Risk & Compliance Monitoring", "Regulatory Reporting",
    "SimCorp Dimension", "Rimes Data Feed", "Client Reporting",
}
LEVELS = ["lowest", "low", "medium", "high", "highest"]
# MATRIX[urgency][impact] -> priority (impact order: highest..lowest)
MATRIX = {
    "highest": ["highest", "highest", "high", "medium", "medium"],
    "high":    ["highest", "high", "high", "medium", "low"],
    "medium":  ["high", "high", "medium", "low", "low"],
    "low":     ["medium", "medium", "low", "low", "lowest"],
    "lowest":  ["medium", "low", "low", "lowest", "lowest"],
}


def priority(urgency, impact):
    return MATRIX[urgency][["highest", "high", "medium", "low", "lowest"].index(impact)]


def family(summary):
    return re.sub(r" (for|in) [A-Z].*$", "", summary)


def author(comment):
    return comment.split(": ", 1)[0]


def body(comment):
    return comment.split(": ", 1)[1] if ": " in comment else comment


# ---------------------------------------------------------------- training
train = json.load(open(TRAIN))
assignee_pool = sorted({r["Assignee"] for r in train if r["Assignee"]})


def counter(field):
    c = C.Counter()
    for r in train:
        v = r.get(field)
        for x in (v if isinstance(v, list) else [v]):
            c[str(x) if x is not None else "(none)"] += 1
    return [{"name": k, "count": v} for k, v in c.most_common()]


service_team = C.defaultdict(C.Counter)
for r in train:
    for s in r["Affected Business or IT Services"]:
        for t in r["Service Team(s)"]:
            service_team[s][t] += 1

# Rich "Resolution:" comments = the real signal. Group by (service, text).
patterns = C.defaultdict(lambda: {"count": 0, "authors": C.Counter(), "families": C.Counter()})
for r in train:
    for c in r["All Comments"]:
        b = body(c)
        if b.startswith("Resolution: "):
            for s in r["Affected Business or IT Services"]:
                p = patterns[(s, b)]
                p["count"] += 1
                p["authors"][author(c)] += 1
                p["families"][family(r["Summary"])] += 1

services = []
for s, teams in service_team.items():
    ps = [
        {
            "text": b,
            "count": p["count"],
            "resolver": p["authors"].most_common(1)[0][0],
            "resolverInAssigneePool": p["authors"].most_common(1)[0][0] in assignee_pool,
        }
        for (svc, b), p in patterns.items() if svc == s
    ]
    ps.sort(key=lambda x: -x["count"])
    assignees = C.Counter(r["Assignee"] for r in train if s in r["Affected Business or IT Services"])
    services.append({
        "name": s,
        "team": teams.most_common(1)[0][0],
        "critical": s in CRITICAL,
        "rated": s in CRITICAL or s != "Emailed Support Tickets",
        "tickets": sum(teams.values()),
        "distinctAssignees": len(assignees),
        "topAssigneeShare": round(assignees.most_common(1)[0][1] / sum(assignees.values()), 3),
        "patterns": ps,
    })
services.sort(key=lambda s: -s["tickets"])

# Comment quality tiers
tiers = C.Counter()
for r in train:
    bodies = [body(c) for c in r["All Comments"]]
    if any(b.startswith("Resolution: ") for b in bodies):
        tiers["Rich root-cause resolution"] += 1
    elif any(b.startswith("Resolution recorded:") for b in bodies):
        tiers["Short canned resolution"] += 1
    elif any(b == "Problem fixed." for b in bodies):
        tiers["'Problem fixed.' only"] += 1
    else:
        tiers["Triage chatter, no resolution"] += 1

families = C.defaultdict(C.Counter)
for r in train:
    families[family(r["Summary"])][r["Work type"]] += 1

# Is P/U/I consistent with the matrix in training? (README says: random)
consistent = sum(
    1 for r in train
    if r["Urgency"] in MATRIX and r["Impact"] in MATRIX
    and priority(r["Urgency"], r["Impact"]) == r["Priority"]
)

# ---------------------------------------------------------------- baseline retrieval
TOKEN = re.compile(r"[a-z0-9_]+")
STOP = set("the a an and or of to for in on is are was were be by with from that this it as at its not but".split())


def tokens(text):
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 2]


# Documents: one per rich resolution pattern, text = resolution + service name + description sample
docs = []
for (s, b), p in patterns.items():
    docs.append({"service": s, "text": b, "resolver": p["authors"].most_common(1)[0][0]})
# Service keyword docs (so services without rich patterns can still be matched)
SERVICE_HINTS = {
    "Rimes Data Feed": "rimes benchmark vendor feed file delivery cutoff index data late publication price snapshot",
    "NAV Calculation": "nav net asset value tolerance breach valuation run eod funds publish snapshot",
    "Fund Pricing": "price pricing stale prices fund price validation",
    "Risk & Compliance Monitoring": "compliance breach sanctions screening rule monitoring dashboard alert analyst control",
    "Identity & Access Management": "identity deactivation deactivated users accounts access removal cleanup inactive provisioning",
    "SharePoint & File Storage": "sharepoint site folder document permissions synced files storage",
    "CRM & Client Portal": "crm relationship manager investor portal client interactions sales",
    "Portfolio Accounting": "portfolio accounting reconciliation month end positions ledger exception",
    "Trading Platform": "trading platform trader execution front office",
    "Tax Reporting": "tax withholding tax packs extracts quarterly filing",
    "Regulatory Reporting": "regulator gateway submission lei classification regulatory report file rejected",
    "Securities Settlement": "settlement custodian custody mt536 confirmation queue acknowledgements settlement status",
    "Trade Matching": "matching adapter allocations broker execution references pairing confirmation",
    "Corporate Actions": "corporate action event option code election ingestion",
    "Cash Management": "cash margin sweep treasury liquidity balance ledger bank",
    "Order Management": "oms order routing broker account pending approval orders",
    "Client Reporting": "client report pdf template fee section batch quarterly",
    "SimCorp Dimension": "simcorp replication job position sync host holdings",
    "Outlook & Email": "shared mailbox distribution list outlook email dl",
}
for s, hint in SERVICE_HINTS.items():
    docs.append({"service": s, "text": hint, "resolver": None})

df = C.Counter()
doc_tokens = [C.Counter(tokens(d["text"] + " " + d["service"])) for d in docs]
for dt in doc_tokens:
    df.update(dt.keys())
N = len(docs)


def vec(counts):
    v = {t: (1 + math.log(c)) * math.log((N + 1) / (df.get(t, 0) + 1)) for t, c in counts.items()}
    n = math.sqrt(sum(x * x for x in v.values())) or 1
    return {t: x / n for t, x in v.items()}


doc_vecs = [vec(dt) for dt in doc_tokens]


def cosine(a, b):
    return sum(a[t] * b.get(t, 0) for t in a)


SR_HINTS = ("license", "access requested", "access removal", "shared mailbox", "need access", "request")
INCIDENT_HINTS = ("failed", "rejected", "delayed", "blank", "missing", "stale", "stopped", "backlog", "breach", "not arriving", "pending")


def classify_work_type(t):
    txt = (t["Summary"] + " " + t["Description"]).lower()
    if "title reads like an urgent incident" in txt or "title sounds like an outage" in txt:
        return "Service Request"
    if any(h in txt for h in ("license", "access requested", "access removal", "starter access", "new user")):
        return "Service Request"
    if any(h in txt for h in INCIDENT_HINTS):
        return "Incident"
    return t["Work type"]


def estimate_ui(t, service, work_type):
    """Rough heuristic: SRs are low, incidents scale with service criticality and
    blocking language. The real system should let an LLM judge this against the
    matrix definitions."""
    txt = (t["Summary"] + " " + t["Description"] + " " + " ".join(t["All Comments"])).lower()
    crit = service in CRITICAL
    if work_type == "Service Request":
        urgent = any(w in txt for w in ("before the end of the day", "today", "must not retain"))
        return ("medium" if urgent else "low"), "low"
    blocked = any(w in txt for w in ("blocked", "cannot process", "did not publish", "at risk", "stale input", "unsuitable for release"))
    workaround = any(w in txt for w in ("workaround", "can still", "manually"))
    urgency = "high" if (crit and blocked and not workaround) else ("medium" if crit else "low")
    if crit and blocked:
        impact = "high"
    elif crit:
        impact = "medium"
    else:
        impact = "low"
    return urgency, impact


def guess_resolution(t, work_type, match_score):
    txt = (t["Summary"] + " " + t["Description"]).lower()
    if "unclear" in t.get("Request type", "").lower() or "short and unclear" in txt:
        return "clarification" if match_score < 0.2 else "done"
    return "done"


challenge = json.load(open(CHALLENGE))
records = challenge["records"]
triaged = []
for i, t in enumerate(records, 1):
    q = t["Summary"] + " " + t["Description"] + " " + " ".join(body(c) for c in t["All Comments"])
    qv = vec(C.Counter(tokens(q)))
    scored = sorted(((cosine(qv, dv), j) for j, dv in enumerate(doc_vecs)), reverse=True)
    best_score, best_j = scored[0]
    best = docs[best_j]
    service = best["service"]
    # nearest rich precedent within the chosen service (if any)
    precedent = next(
        (docs[j] | {"score": round(s, 3)} for s, j in scored if docs[j]["service"] == service and docs[j]["resolver"]),
        None,
    )
    work_type = classify_work_type(t)
    urgency, impact = estimate_ui(t, service, work_type)
    team = service_team[service].most_common(1)[0][0]
    resolver = precedent["resolver"] if precedent and precedent["score"] > 0.12 else None
    alt = [{"service": docs[j]["service"], "score": round(s, 3)} for s, j in scored[:6]]
    seen, alts = set(), []
    for a in alt:
        if a["service"] not in seen:
            seen.add(a["service"])
            alts.append(a)
    flags = []
    if service not in t["Affected Business or IT Services"]:
        flags.append("service-mismatch")
    if work_type != t["Work type"]:
        flags.append("work-type-flip")
    u, im = (t["Urgency"] or "").lower(), (t["Impact"] or "").lower()
    if u in MATRIX and im in MATRIX and priority(u, im) != (t["Priority"] or "").lower():
        flags.append("priority-inconsistent")
    if "unclear" in (t.get("Request type") or "").lower():
        flags.append("unclear-input")
    triaged.append({
        "id": i,
        "input": {k: t.get(k) for k in (
            "Work type", "Request type", "Summary", "Description", "Affected Business or IT Services",
            "Business Entity", "Priority", "Urgency", "Impact", "All Comments")},
        "baseline": {
            "workType": work_type,
            "service": service,
            "serviceCritical": service in CRITICAL,
            "team": team,
            "assignee": resolver,
            "urgency": urgency,
            "impact": impact,
            "priority": priority(urgency, impact),
            "resolution": guess_resolution(t, work_type, best_score),
            "confidence": round(best_score, 3),
            "precedent": precedent,
            "alternatives": alts[:3],
        },
        "flags": flags,
    })

out = {
    "meta": {
        "trainingTickets": len(train),
        "challengeTickets": len(records),
        "challengeRunId": challenge.get("runId"),
        "assigneePoolSize": len(assignee_pool),
        "matrixConsistentInTraining": consistent,
    },
    "distributions": {
        f: counter(f) for f in (
            "Work type", "Affected Business or IT Services", "Service Team(s)", "Business Entity",
            "Priority", "Urgency", "Impact", "Status", "Resolution")
    },
    "commentTiers": [{"name": k, "count": v} for k, v in tiers.most_common()],
    "families": [
        {"name": k, "total": sum(v.values()), "incident": v["Incident"], "serviceRequest": v["Service Request"]}
        for k, v in sorted(families.items(), key=lambda x: -sum(x[1].values()))
    ],
    "services": services,
    "matrix": MATRIX,
    "triaged": triaged,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w"), indent=1)
print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")
for t in triaged:
    b = t["baseline"]
    print(f"#{t['id']:2} {b['service']:<28} {b['team']:<24} {str(b['assignee']):<28} {b['priority']:<7} {b['confidence']:.2f} {t['flags']}")
