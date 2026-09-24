"""Node 6 - Retrieval (Sec. 4.4-4.7, 6.6): hybrid BM25 + dense search, mined resolution playbook,
similar historical tickets and related open tickets.

Three data sources, three tools:
  * ``search_kb``            - chunks of the (synthetic) knowledge base, hybrid ranked, with citation ids
  * ``find_similar_tickets`` - unique historical ticket texts from the 20k training set (context only)
  * ``resolution_playbook``  - service-bound, information-carrying comments *mined from the training data*;
                               this is where the dataset hides how classes of problems are really resolved
  * ``find_open_related``    - open tickets on the same service in a time window (duplicate / storm linking)
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np

from .catalogue import CHANNEL_SERVICE, SERVICE_NAMES, SERVICES, TEAMS
from .config import get_settings
from .models import Citation, Ticket

# ------------------------------------------------------------------ text utils
_TOKEN = re.compile(r"[^\W_][\w'&\-]*", re.UNICODE)
_STOP = set("""a an the and or of to in on for with without by from at as is are was were be been being it its this that these those
there here we you they he she i our your their my me us not no but if then than so such can could should would will may might must
has have had do does did done into over under about after before during while when where which who whom what please kindly hi hello
dear regards thanks thank also just very more most some any all each per via up down out off again once only own same too
der die das den dem des ein eine einer einem und oder von zu im in auf für mit ohne bei aus als ist sind war waren wird werden nicht
le la les un une des du de et ou en pour avec sans par sur dans est sont pas que qui il elle nous vous ils elles ce cette ces
""".split())
_SUFFIXES = ("ations", "ation", "ions", "ion", "ments", "ment", "ings", "ing", "ies", "ied", "ed", "es", "s", "ly")


def stem(w: str) -> str:
    if len(w) <= 4 or w.isdigit():
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for m in _TOKEN.finditer((text or "").lower()):
        w = m.group(0).strip("'-&")
        if len(w) < 2 or (not keep_stop and w in _STOP):
            continue
        out.append(stem(w))
    return out


# ------------------------------------------------------------------ BM25
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.doc_len = np.array([len(d) for d in docs], dtype=float)
        self.avgdl = float(self.doc_len.mean()) if self.n else 1.0
        self.tf: list[Counter] = [Counter(d) for d in docs]
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        self.idf = {t: math.log(1 + (self.n - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.inv: dict[str, list[int]] = defaultdict(list)
        for i, c in enumerate(self.tf):
            for t in c:
                self.inv[t].append(i)

    def scores(self, query: list[str]) -> np.ndarray:
        s = np.zeros(self.n)
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.inv[t]:
                f = self.tf[i][t]
                s[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl))
        return s

    def upper_bound(self, query: list[str]) -> float:
        """Best possible score of a document for this query: used to squash BM25 into [0, 1] so it can be fused
        with cosine similarity and compared to a fixed confidence floor."""
        max_idf = math.log(1 + (self.n + 0.5) / 0.5)
        ub = sum(self.idf.get(t, max_idf) * (self.k1 + 1) for t in set(query))   # unseen terms count as maximally informative
        return ub or 1.0


# ------------------------------------------------------------------ embedders
class Embedder:
    name = "base"

    def fit(self, texts: list[str]) -> "Embedder":
        return self

    def embed(self, texts: list[str]) -> np.ndarray:  # L2-normalised rows
        raise NotImplementedError


class LsaEmbedder(Embedder):
    """Offline 'dense' model: word + char-n-gram TF-IDF projected with truncated SVD (LSA). No network, no GPU.
    Char n-grams give partial robustness to inflection and cognates across EN/DE/FR."""
    name = "tfidf-lsa"

    def __init__(self, dims: int = 96):
        self.dims = dims
        self.word = None
        self.char = None
        self.svd = None

    def _prep(self, texts):
        return [" ".join(tokens(t)) for t in texts]

    def fit(self, texts: list[str]) -> "LsaEmbedder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        prepped = self._prep(texts)
        self.word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, token_pattern=r"\S+")
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        from scipy.sparse import hstack
        X = hstack([self.word.fit_transform(prepped) * 0.6, self.char.fit_transform(prepped) * 0.4]).tocsr()
        k = max(2, min(self.dims, X.shape[0] - 1, X.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=k, random_state=0)
        self.svd.fit(X)
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        from scipy.sparse import hstack
        prepped = self._prep(texts)
        X = hstack([self.word.transform(prepped) * 0.6, self.char.transform(prepped) * 0.4]).tocsr()
        Z = self.svd.transform(X)
        n = np.linalg.norm(Z, axis=1, keepdims=True)
        return Z / np.where(n == 0, 1, n)


class ApiEmbedder(Embedder):
    """OpenAI-compatible /embeddings with an on-disk cache. Multilingual models make DE/FR tickets match English KB."""
    name = "api"

    def __init__(self, fallback: Embedder):
        from .llm import get_client
        self.client = get_client()
        self.fallback = fallback
        self.ok = True
        self.name = f"api:{get_settings().embed_model}"

    def fit(self, texts: list[str]) -> "ApiEmbedder":
        self.fallback.fit(texts)
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self.ok:
            return self.fallback.embed(texts)
        try:
            vecs = self.client.embed(texts)
            M = np.array(vecs, dtype=float)
            n = np.linalg.norm(M, axis=1, keepdims=True)
            return M / np.where(n == 0, 1, n)
        except Exception:
            self.ok = False
            self.name = "tfidf-lsa (api embeddings unavailable)"
            return self.fallback.embed(texts)


def make_embedder() -> Embedder:
    s = get_settings()
    base = LsaEmbedder()
    if s.llm_enabled and (s.embed_base_url or s.llm_provider.lower() in ("openai", "azure", "local")) and s.embed_model:
        return ApiEmbedder(base)
    return base


# ------------------------------------------------------------------ hybrid index
@dataclass
class Doc:
    id: str
    title: str
    text: str
    meta: dict = field(default_factory=dict)


@dataclass
class Hit:
    id: str
    title: str
    text: str
    score: float
    cos: float = 0.0
    bm25: float = 0.0
    meta: dict = field(default_factory=dict)

    def as_citation(self, n: int = 200) -> Citation:
        snip = re.sub(r"\s+", " ", self.text).strip()
        return Citation(id=self.meta.get("cite", self.id), title=self.title, snippet=snip[:n], score=round(self.score, 3))


class HybridIndex:
    """score = alpha * cosine + (1 - alpha) * BM25_norm ; top-20 -> service filter -> top-k (Sec. 4.6)."""

    def __init__(self, docs: list[Doc], embedder: Embedder, alpha: float = 0.6, fit: bool = False):
        self.docs = docs
        self.alpha = alpha
        self.embedder = embedder
        texts = [d.title + "\n" + d.text for d in docs]
        if fit:
            embedder.fit(texts)
        self.bm25 = BM25([tokens(t) for t in texts])
        self.vecs = embedder.embed(texts) if docs else np.zeros((0, 1))

    def search(self, query: str, k: int = 5, service: str | None = None, prefilter: int = 20,
               allow: Callable[[Doc], bool] | None = None) -> list[Hit]:
        if not self.docs:
            return []
        q_tok = tokens(query)
        bm = self.bm25.scores(q_tok) / self.bm25.upper_bound(q_tok)
        qv = self.embedder.embed([query])[0]
        cos = np.clip(self.vecs @ qv, 0, 1)
        fused = self.alpha * cos + (1 - self.alpha) * bm
        order = np.argsort(-fused)[:prefilter]
        hits: list[Hit] = []
        for i in order:
            d = self.docs[int(i)]
            if allow and not allow(d):
                continue
            hits.append(Hit(d.id, d.title, d.text, float(fused[i]), float(cos[i]), float(bm[i]), d.meta))
        if service:
            def match(h: Hit) -> bool:
                sv = h.meta.get("services") or []
                return service in sv or not sv          # service-specific or generic policy
            pref = [h for h in hits if match(h)]
            if len(pref) < k:
                pref += [h for h in hits if not match(h)]
            hits = pref
        return hits[:k]


# ------------------------------------------------------------------ knowledge base
def _parse_front_matter(raw: str) -> tuple[dict, str]:
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        meta = {}
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, body.strip()
    return {}, raw


def load_kb(kb_dir: Path | None = None) -> list[Doc]:
    kb_dir = kb_dir or get_settings().kb_dir
    docs: list[Doc] = []
    for p in sorted(Path(kb_dir).glob("KB-*.md")):
        meta, body = _parse_front_matter(p.read_text(encoding="utf-8"))
        aid = meta.get("id", p.stem)
        title = meta.get("title", p.stem)
        services = [s.strip() for s in meta.get("services", "[]").strip("[]").split(",") if s.strip()]
        parts = re.split(r"^##\s+", body, flags=re.M)
        for j, part in enumerate(parts[1:], start=1):
            head, _, text = part.partition("\n")
            docs.append(Doc(
                id=f"{aid}#{j}", title=title, text=f"{head.strip()}: {text.strip()}",
                meta={"cite": aid, "article": aid, "section": head.strip().lower(), "services": services,
                      "type": meta.get("type", "procedure"), "synthetic": True},
            ))
    return docs


# ------------------------------------------------------------------ playbook mined from training comments
@dataclass
class PlaybookEntry:
    id: str
    text: str
    service: str
    count: int
    top_share: float
    services: dict[str, int]
    teams: list[str]


def _normalise_comment(body: str) -> str:
    out = body
    for s in sorted(SERVICE_NAMES + TEAMS, key=len, reverse=True):
        out = out.replace(s, "<X>")
    return out


def mine_playbook(tickets: Iterable[Ticket], min_count: int = 5, min_share: float = 0.90, min_len: int = 60,
                  boiler_variants: int = 5) -> list[PlaybookEntry]:
    """Find comments that *carry information*: long, repeated, and bound to a single service.

    Boilerplate ("Initial triage assigned to <team>...") is a template stamped across many services/teams and is
    recognised by having many name-substitution variants; generic sentences are spread over all services.
    What remains are the human-written resolution notes hidden in the data.
    """
    by_body: dict[str, Counter] = defaultdict(Counter)
    for t in tickets:
        svc = t.service or "?"
        for _, body in t.comment_bodies():
            by_body[body][svc] += 1
    norm_variants: dict[str, set[str]] = defaultdict(set)
    for body in by_body:
        norm_variants[_normalise_comment(body)].add(body)
    entries = []
    for body, svc_counts in by_body.items():
        n = sum(svc_counts.values())
        if n < min_count or len(body) < min_len:
            continue
        if len(norm_variants[_normalise_comment(body)]) >= boiler_variants:
            continue
        top_svc, top_n = svc_counts.most_common(1)[0]
        if top_n / n < min_share or top_svc in ("?", CHANNEL_SERVICE):
            continue
        entries.append((top_svc, body, n, top_n / n, dict(svc_counts)))
    entries.sort(key=lambda e: (e[0], -e[2], e[1]))
    out = []
    for i, (svc, body, n, share, sc) in enumerate(entries, start=1):
        out.append(PlaybookEntry(id=f"HIST-{i:02d}", text=body, service=svc, count=n, top_share=round(share, 3),
                                 services=sc, teams=[SERVICES[svc].team] if svc in SERVICES else []))
    return out


# ------------------------------------------------------------------ retriever facade
def _parse_dt(s: str | None) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19] if "T" in s else s, fmt)
        except ValueError:
            continue
    return None


class Retriever:
    """Built once at startup (Sec. 4.6 'Indexing - once, at startup')."""

    def __init__(self, training: list[Ticket] | None = None, kb_dir: Path | None = None,
                 embedder: Embedder | None = None):
        t0 = time.perf_counter()
        self.training = training or []
        self.kb_docs = load_kb(kb_dir)
        self.playbook = mine_playbook(self.training) if self.training else []

        # unique historical ticket texts (only ~173 exist: templates x services)
        uniq: dict[str, dict] = {}
        for t in self.training:
            key = t.summary + "␟" + t.description
            u = uniq.setdefault(key, {"summary": t.summary, "description": t.description, "service": t.service,
                                      "work_type": t.work_type, "n": 0, "resolutions": Counter()})
            u["n"] += 1
            if t.resolution:
                u["resolutions"][t.resolution] += 1
        self.uniq = list(uniq.values())

        corpus = [d.title + "\n" + d.text for d in self.kb_docs] + \
                 [e.text for e in self.playbook] + \
                 [u["summary"] + "\n" + u["description"] for u in self.uniq]
        self.embedder = embedder or make_embedder()
        self.embedder.fit(corpus)
        self.kb = HybridIndex(self.kb_docs, self.embedder)
        self.pb_docs = [Doc(e.id, e.service, e.text, {"services": [e.service], "cite": e.id, "count": e.count})
                        for e in self.playbook]
        self.pb = HybridIndex(self.pb_docs, self.embedder) if self.pb_docs else None
        self.sim_docs = [Doc(f"H{i}", u["summary"], u["description"], {"services": [u["service"]], **{k: u[k] for k in ("work_type", "n")}})
                         for i, u in enumerate(self.uniq)]
        self.sim = HybridIndex(self.sim_docs, self.embedder) if self.sim_docs else None

        # open pool for correlation (training open/in-progress) - extended at runtime with the current batch
        self.open_pool: dict[str, list[tuple[datetime, str, str, str]]] = defaultdict(list)
        for t in self.training:
            if (t.status or "").lower() in ("open", "in progress"):
                dt = _parse_dt(t.created)
                if dt and t.service:
                    self.open_pool[t.service].append((dt, t.id, t.summary, f"{t.summary}\n{t.description}"))
        self.build_seconds = time.perf_counter() - t0

    # ------------------------------------------------------------ tools
    def search_kb(self, query: str, service: str | None = None, k: int = 5) -> list[Hit]:
        return self.kb.search(query, k=k, service=service)

    def find_similar_tickets(self, query: str, service: str | None = None, k: int = 3) -> list[dict]:
        if not self.sim:
            return []
        out = []
        for h in self.sim.search(query, k=k, service=service):
            out.append({"id": h.id, "summary": h.title, "score": round(h.score, 3), "service": (h.meta.get("services") or [None])[0],
                        "work_type": h.meta.get("work_type"), "tickets_with_same_text": h.meta.get("n")})
        return out

    def resolution_playbook(self, query: str, service: str | None = None, k: int = 3) -> list[Hit]:
        """Historical human resolution notes ranked against the ticket. ``service`` prefers (not forces) same-service notes."""
        if not self.pb:
            return []
        return self.pb.search(query, k=k, service=service)

    def playbook_service_votes(self, query: str, k: int = 3) -> dict[str, float]:
        """Evidence for the *service* from historical resolutions: similar resolved scenarios vote for their service."""
        votes: dict[str, float] = defaultdict(float)
        if not self.pb:
            return votes
        for h in self.pb.search(query, k=k):
            svc = (h.meta.get("services") or [None])[0]
            # a vote needs real lexical overlap (BM25), not just char-n-gram/LSA proximity on short or foreign text
            if svc and h.bm25 >= 0.12:
                votes[svc] = max(votes[svc], h.score)
        return votes

    DUP_SIM = 0.55

    def find_open_related(self, service: str, created: str | None, window_hours: float = 4.0, exclude_id: str | None = None,
                          extra_pool: list[tuple[datetime, str, str, str]] | None = None, query_text: str | None = None) -> list[dict]:
        """Earlier open tickets on the same service within ``window_hours`` whose text is also similar.

        Directional on purpose: the *first* ticket of an alert storm is the parent; later ones link to it. Requiring text
        similarity stops two unrelated same-service tickets from being wrongly merged."""
        dt = _parse_dt(created)
        if not dt:
            return []
        cands = []
        for odt, oid, summ, text in list(self.open_pool.get(service, [])) + list(extra_pool or []):
            if oid == exclude_id or odt > dt:
                continue
            gap = (dt - odt).total_seconds() / 3600.0
            if gap <= window_hours:
                cands.append((odt, oid, summ, text, gap))
        if not cands:
            return []
        sims = [1.0] * len(cands)
        if query_text:
            qv = self.embedder.embed([query_text])[0]
            cv = self.embedder.embed([c[3] for c in cands])
            sims = [float(x) for x in (cv @ qv)]
        out = [{"id": oid, "summary": summ, "gap_hours": round(gap, 2), "similarity": round(sim, 3), "created": odt.strftime("%Y-%m-%d %H:%M")}
               for (odt, oid, summ, _t, gap), sim in zip(cands, sims) if sim >= self.DUP_SIM]
        out.sort(key=lambda r: r["created"])          # earliest first = the root of the storm
        return out[:5]


_RETRIEVER: Retriever | None = None


def get_retriever(force: bool = False) -> Retriever:
    global _RETRIEVER
    if _RETRIEVER is None or force:
        from .data import load_training
        _RETRIEVER = Retriever(load_training())
    return _RETRIEVER
