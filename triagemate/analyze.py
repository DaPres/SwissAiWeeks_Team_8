"""Reproducible dataset analysis (the plan's ``analyze_data.py``): every number quoted in the README comes from here.

Run:  python -m triagemate.cli analyze        ->  eval/dataset_analysis.json  (+ printed summary)
"""
from __future__ import annotations

import json
import math
import warnings
import re
from collections import Counter, defaultdict
from pathlib import Path

from .catalogue import TEAM_OF, verify_against_training
from .config import ROOT
from .data import load_training
from .models import Ticket
from .priority import is_consistent
from .retrieve import mine_playbook


def cramers_v(pairs: list[tuple]) -> dict:
    a, b, ab = Counter(p[0] for p in pairs), Counter(p[1] for p in pairs), Counter(pairs)
    n = len(pairs)
    chi = 0.0
    for x in a:
        for y in b:
            e = a[x] * b[y] / n
            chi += (ab.get((x, y), 0) - e) ** 2 / e
    k = min(len(a), len(b)) - 1
    df = (len(a) - 1) * (len(b) - 1)
    return {"cramers_v": round(math.sqrt(chi / (n * k)), 4), "chi2": round(chi, 1), "df": df,
            "independent": bool(chi < df + 3 * math.sqrt(2 * df))}


def _template(t: Ticket) -> str:
    s = t.summary
    for svc in t.services:
        s = s.replace(svc, "<SVC>")
    return s


warnings.filterwarnings("ignore", message=".*iprint.*")


def baselines(tickets: list[Ticket], seed: int = 0) -> dict:
    """TF-IDF + logistic regression, random 80/20 split (the leakage demonstration from the plan, Sec. 3.5)."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(tickets))
    cut = int(0.8 * len(idx))
    tr, te = idx[:cut], idx[cut:]
    texts = [t.text for t in tickets]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
    Xtr = vec.fit_transform([texts[i] for i in tr])
    Xte = vec.transform([texts[i] for i in te])
    out = {}
    train_texts = {texts[i] for i in tr}
    out["test_texts_seen_in_training_share"] = round(sum(texts[i] in train_texts for i in te) / len(te), 4)
    for name, getter in (("service", lambda t: t.service), ("work_type", lambda t: t.work_type), ("priority", lambda t: t.priority)):
        y = [getter(t) for t in tickets]
        clf = LogisticRegression(max_iter=300, C=5.0).fit(Xtr, [y[i] for i in tr])
        acc = float((clf.predict(Xte) == np.array([y[i] for i in te])).mean())
        maj = Counter(y[i] for i in tr).most_common(1)[0][0]
        base = float(np.mean([y[i] == maj for i in te]))
        out[name] = {"tfidf_logreg_accuracy": round(acc, 4), "majority_baseline": round(base, 4)}
    # work type from title keywords only
    kw = re.compile(r"\b(?:alert|warning|issue|unclear|incident|mislabelled)\b", re.I)
    kw_pred = ["Incident" if kw.search(t.summary) else "Service Request" for t in tickets]
    out["work_type_from_title_keywords"] = round(sum(p == t.work_type for p, t in zip(kw_pred, tickets)) / len(tickets), 4)
    return out


def analyze(path: str | Path | None = None, out_path: str | Path | None = None, with_models: bool = True) -> dict:
    tickets = load_training(path)
    n = len(tickets)
    res: dict = {"tickets": n}
    res["work_type"] = dict(Counter(t.work_type for t in tickets))
    res["status"] = dict(Counter(t.status for t in tickets))
    res["resolution"] = dict(Counter(t.resolution for t in tickets))
    res["unique_summaries"] = len({t.summary for t in tickets})
    res["unique_descriptions"] = len({t.description for t in tickets})
    bodies = Counter(b for t in tickets for _, b in t.comment_bodies())
    res["comments_total"] = sum(bodies.values())
    res["unique_comment_bodies"] = len(bodies)
    res["assignees"] = len({t.assignee for t in tickets})
    res["reporters"] = len({t.reporter for t in tickets})
    res["services"] = len({t.service for t in tickets})
    res["teams"] = len({t.teams[0] for t in tickets if t.teams})
    res["service_team_mapping"] = verify_against_training(tickets)

    # patterns (template = summary with the service name removed)
    pat = Counter((t.work_type, _template(t)) for t in tickets)
    res["patterns"] = [{"work_type": w, "template": s, "count": c, "share": round(c / n, 4)} for (w, s), c in pat.most_common()]

    # priority / urgency / impact are noise
    res["priority_equals_urgency"] = round(sum(t.priority == t.urgency for t in tickets) / n, 4)
    res["priority_equals_impact"] = round(sum(t.priority == t.impact for t in tickets) / n, 4)
    res["priority_consistent_with_matrix"] = round(sum(is_consistent(t.priority, t.urgency, t.impact) for t in tickets) / n, 4)
    by_desc = defaultdict(set)
    for t in tickets:
        by_desc[t.description].add(t.priority)
    res["descriptions_carrying_all_5_priorities"] = sum(1 for s in by_desc.values() if len(s) == 5)

    # resolution outcomes are noise too
    by_pat = defaultdict(Counter)
    for t in tickets:
        if t.resolution:
            by_pat[_template(t)][t.resolution] += 1
    res["resolution_share_by_pattern"] = {p: {k: round(v / sum(c.values()), 3) for k, v in c.items()} for p, c in by_pat.items()}

    # assignee independence
    res["assignee_independence"] = {
        name: cramers_v([(t.assignee, f(t)) for t in tickets])
        for name, f in (("service", lambda t: t.service), ("team", lambda t: t.teams[0]), ("entity", lambda t: t.entity),
                        ("work_type", lambda t: t.work_type), ("resolution", lambda t: t.resolution), ("priority", lambda t: t.priority))
    }
    hours = [int(t.created[11:13]) for t in tickets if t.created]
    res["created_22_to_06_share"] = round(sum(h >= 22 or h < 6 for h in hours) / len(hours), 4)

    # playbook (the real signal hidden in the comments)
    pb = mine_playbook(tickets)
    res["playbook"] = {"entries": len(pb), "services": sorted({e.service for e in pb}),
                       "items": [{"id": e.id, "service": e.service, "count": e.count, "top_share": e.top_share, "text": e.text} for e in pb]}
    if with_models:
        res["baselines"] = baselines(tickets)
    out = Path(out_path) if out_path else ROOT / "eval" / "dataset_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res


def print_summary(r: dict) -> None:
    print(f"tickets={r['tickets']}  unique summaries/descriptions={r['unique_summaries']}/{r['unique_descriptions']}  "
          f"unique comment bodies={r['unique_comment_bodies']} of {r['comments_total']}")
    print(f"service->team mapping 1:1 with catalogue: {r['service_team_mapping']['ok']}")
    print(f"priority == urgency {r['priority_equals_urgency']:.1%}, == impact {r['priority_equals_impact']:.1%}, "
          f"consistent with README matrix {r['priority_consistent_with_matrix']:.1%} (chance-level)")
    print(f"descriptions carrying all 5 priorities: {r['descriptions_carrying_all_5_priorities']} of {r['unique_descriptions']}")
    print("assignee independence (Cramer's V, chi2 vs df):")
    for k, v in r["assignee_independence"].items():
        print(f"   assignee x {k:10} V={v['cramers_v']:.3f} chi2={v['chi2']:.0f} df={v['df']}  independent={v['independent']}")
    print(f"mined resolution playbook: {r['playbook']['entries']} notes across {len(r['playbook']['services'])} services")
    if "baselines" in r:
        b = r["baselines"]
        print("leakage baselines (TF-IDF + LogReg, random 80/20):", {k: v for k, v in b.items() if k != 'test_texts_seen_in_training_share'})
        print(f"   share of test texts also present in training: {b['test_texts_seen_in_training_share']:.1%}")
