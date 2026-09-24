"""Verify the dataset claims behind TriageMate before any product code is written.

Input:  data/jira.json (20k synthetic Jira tickets from the challenge repo).
Output: printed report -> docs/dataset_findings.md (written by hand from this output).
Answers: text templates and their share, service->team cardinality, whether Priority is
learnable at all, and how much of a classifier's apparent skill is just memorised duplicates.
Failure mode it prevents: building ML on leaked duplicates and shipping a priority model
that is really predicting noise.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

DATA = Path(__file__).parent / "data" / "jira.json"
PRIORITIES = ["lowest", "low", "medium", "high", "highest"]


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def load() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def first(v):
    """Multi-valued Jira fields are lists; tickets here carry exactly one value."""
    return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)


def templatize(text: str, services: set[str], entities: set[str]) -> str:
    """Mask service/entity names and numbers so repeated boilerplate collapses to one key."""
    for s in sorted(services, key=len, reverse=True):
        text = text.replace(s, "<SERVICE>")
    for e in sorted(entities, key=len, reverse=True):
        text = text.replace(e, "<ENTITY>")
    return re.sub(r"\d+", "<N>", text).strip()


def category(template: str) -> str:
    """Bucket a description template into the ticket-mix classes the pitch claims."""
    t = template.lower()
    if "automated monitoring alert" in t or "automated alert" in t:
        return "automated alert"
    if "email" in t and ("third party" in t or "external" in t or "sent an email" in t):
        return "external email"
    # Traps: the title/body disagree, or the text is too vague to action.
    if "title suggests" in t or "not aligned with the expected" in t or "unclear" in t:
        return "unclear / contradictory (trap)"
    return "normal actionable ticket"


def section_text_variety(d: list[dict], services: set[str], entities: set[str]) -> dict:
    rule("1. TEXT VARIETY: how many genuinely distinct tickets are there?")
    summaries = [r["Summary"] for r in d]
    descs = [r["Description"] for r in d]
    print(f"records                      : {len(d)}")
    print(f"unique Summary               : {len(set(summaries)):>6}  ({len(set(summaries)) / len(d):.2%})")
    print(f"unique Description           : {len(set(descs)):>6}  ({len(set(descs)) / len(d):.2%})")
    print(f"unique (Summary+Description) : {len(set(zip(summaries, descs))):>6}")

    desc_tpl = [templatize(x, services, entities) for x in descs]
    sum_tpl = [templatize(x, services, entities) for x in summaries]
    print(f"\nSummary templates (service/entity/number masked): {len(set(sum_tpl))}")
    print(f"Description templates                          : {len(set(desc_tpl))}\n")
    for tpl, n in Counter(desc_tpl).most_common():
        print(f"  {n:>6}  {n / len(d):>6.2%}  [{category(tpl)}]  {tpl[:95]}...")

    rule("1b. TICKET MIX vs the claimed 17% normal / 37% alerts / 27% email / 18% traps")
    mix = Counter(category(t) for t in desc_tpl)
    for cat, n in mix.most_common():
        print(f"  {cat:<26} {n:>6}  {n / len(d):>7.2%}")
    return {"desc_tpl": desc_tpl, "mix": mix}


def section_routing(d: list[dict]) -> None:
    rule("2. ROUTING: is service -> team strictly 1:1?")
    s2t, t2s = defaultdict(Counter), defaultdict(Counter)
    for r in d:
        s, t = first(r["Affected Business or IT Services"]), first(r["Service Team(s)"])
        s2t[s][t] += 1
        t2s[t][s] += 1
    multi = {s: dict(c) for s, c in s2t.items() if len(c) > 1}
    print(f"services: {len(s2t)}   teams: {len(t2s)}")
    print(f"services mapping to >1 team: {len(multi)}  {multi if multi else '(none - service->team is a function)'}")
    print(f"teams owning >1 service    : {sum(1 for c in t2s.values() if len(c) > 1)} (many-to-one is fine for a lookup table)\n")
    print(f"  {'SERVICE':<32} -> TEAM")
    for s in sorted(s2t):
        print(f"  {s:<32} -> {s2t[s].most_common(1)[0][0]}")

    ents = Counter(first(r["Business Entity"]) for r in d)
    print(f"\nBusiness entities: {dict(ents)}")


def section_priority(d: list[dict]) -> None:
    rule("3. PRIORITY: is it predictable at all?")
    by_desc = defaultdict(Counter)
    for r in d:
        by_desc[r["Description"]][r["Priority"]] += 1
    all_five = [k for k, c in by_desc.items() if len(c) == 5]
    print(f"distinct Descriptions                      : {len(by_desc)}")
    print(f"...carrying ALL FIVE priority values       : {len(all_five)}")
    print(f"...carrying >1 priority value              : {sum(1 for c in by_desc.values() if len(c) > 1)}")
    print("=> identical text carries every priority, so Priority is not a function of text.\n")

    pair = defaultdict(Counter)
    for r in d:
        pair[(r["Urgency"], r["Impact"])][r["Priority"]] += 1
    deterministic = sum(1 for c in pair.values() if len(c) == 1)
    print(f"distinct (Urgency, Impact) pairs           : {len(pair)}")
    print(f"...mapping to exactly one Priority         : {deterministic}")
    agree = sum(1 for r in d if r["Priority"] == r["Urgency"])
    print(f"rows where Priority == Urgency             : {agree} ({agree / len(d):.2%})")
    print("\n  (Urgency, Impact) -> Priority spread, top 8 pairs:")
    for k, c in sorted(pair.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
        print(f"   {str(k):<24} n={sum(c.values()):>5}  {dict(c)}")

    print("\n  median days-to-resolve by Priority:")
    days = defaultdict(list)
    for r in d:
        if r.get("Resolution date") and r.get("Created date"):
            try:
                t0 = datetime.strptime(r["Created date"], "%Y-%m-%d %H:%M")
                t1 = datetime.strptime(r["Resolution date"], "%Y-%m-%d %H:%M")
                days[r["Priority"]].append((t1 - t0).total_seconds() / 86400)
            except ValueError:
                pass
    for p in PRIORITIES:
        v = days.get(p, [])
        if v:
            print(f"   {p:<8} n={len(v):>5}  median {statistics.median(v):>6.2f} d   mean {statistics.mean(v):>6.2f} d")
    print("  => if medians are flat across priorities, Priority does not drive real-world handling time.")


def section_leakage(d: list[dict]) -> None:
    rule("4. LEAKAGE CHECK: TF-IDF + logistic regression, random 80/20")
    texts = [f"{r['Summary']} {r['Description']}" for r in d]
    targets = {
        "service": [first(r["Affected Business or IT Services"]) for r in d],
        "work type": [r["Work type"] for r in d],
        "priority": [r["Priority"] for r in d],
    }
    idx = list(range(len(d)))
    tr, te = train_test_split(idx, test_size=0.2, random_state=42)
    train_texts = {texts[i] for i in tr}
    dup = sum(1 for i in te if texts[i] in train_texts)
    print(f"test rows whose exact text also appears in TRAIN: {dup}/{len(te)} = {dup / len(te):.2%}")
    print("=> at this duplication rate the split is not honest; accuracy below is mostly recall of memorised rows.\n")

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    Xtr = vec.fit_transform([texts[i] for i in tr])
    Xte = vec.transform([texts[i] for i in te])
    print(f"{'TARGET':<12} {'ACCURACY':>9} {'MAJORITY':>9} {'LIFT':>8} {'MACRO-F1':>9}  {'CLASSES':>7}")
    for name, y in targets.items():
        ytr, yte = [y[i] for i in tr], [y[i] for i in te]
        clf = LogisticRegression(max_iter=2000).fit(Xtr, ytr)
        pred = clf.predict(Xte)
        acc = accuracy_score(yte, pred)
        base = Counter(ytr).most_common(1)[0][1] / len(ytr)
        print(f"{name:<12} {acc:>9.3f} {base:>9.3f} {acc - base:>+8.3f} {f1_score(yte, pred, average='macro'):>9.3f}  {len(set(y)):>7}")
    print("\nRead: big lift over majority = learnable from text. ~zero lift = the field is noise.")


def main() -> None:
    d = load()
    services = {s for r in d for s in r["Affected Business or IT Services"]}
    entities = {e for r in d for e in r["Business Entity"]}
    section_text_variety(d, services, entities)
    section_routing(d)
    section_priority(d)
    section_leakage(d)
    rule("DONE")


if __name__ == "__main__":
    main()
