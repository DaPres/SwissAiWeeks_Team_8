"""Pipeline orchestrator (Sec. 5): R(t) = A( C(S(t)), P(S(t)), K(S(t)) ).

Ticket in -> safety gate -> quality gate + classifier -> router -> priority -> retrieval/agent -> resolution + draft
          -> assignee -> analyst review (human) -> feedback.

Every model-dependent component has a deterministic fallback: the system degrades, it does not fail.

Latency design (hybrid mode): independent model calls run concurrently -
   stage 1  LLM classification  ||  LLM urgency/impact (speculatively on the rules' service; recomputed only if it changes)
   stage 2  priority finalisation ||  agent loop (retrieval tools)
   stage 3  resolution note      ||  reply draft
and a batch processes several tickets at once (assignment stays sequential so results are deterministic).
"""
from __future__ import annotations

import contextvars
import functools
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from . import classify as C
from . import draft as D
from . import priority as P
from . import resolutions as R
from .agent import AgentState, run_agent
from .assign import Assigner
from .catalogue import CHANNEL_SERVICE, UNKNOWN, team_for
from .config import get_settings
from .llm import LLMError, LLMUnavailable, any_llm_enabled, track
from .models import Classification, Draft, Flags, PriorityResult, Ticket, TriageResult
from .retrieve import Retriever, _parse_dt, get_retriever
from .safety import TicketSafety, analyse_ticket, names_from_emails

PB_MIN = 0.28          # min fused score for a same-service playbook note to be used as the resolution basis
KB_GOOD = 0.5          # fused score treated as a "good" retrieval for confidence normalisation


_PERSONAL_TOKEN = re.compile(r"\[(PERSON|EMAIL_[A-Z]+|PHONE|IBAN|POLICY|ID)_\d+\]")


def _scrub_note(note: str) -> str:
    """A resolution note becomes a Jira comment: personal-data tokens are never restored into it (unlike the analyst-facing draft)."""
    return _PERSONAL_TOKEN.sub(lambda m: "the requester" if m.group(1).startswith(("PERSON", "EMAIL")) else "the reported account", note)


def _submit(ex: ThreadPoolExecutor, fn: Callable, *a, **kw):
    """Run in a worker thread while keeping the caller's contextvars (per-ticket usage / cost tracking)."""
    return ex.submit(contextvars.copy_context().run, functools.partial(fn, *a, **kw))


@dataclass
class Ctx:
    ticket: Ticket
    safety: TicketSafety
    rules: Classification
    cls: Classification
    votes: dict
    stage_ms: dict = field(default_factory=dict)
    prompt_versions: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    agreement: float = 0.6
    spec_priority: tuple | None = None       # ((PriorityResult, version), service, work_type) computed speculatively


class Triage:
    def __init__(self, retriever: Retriever | None = None, assigner: Assigner | None = None, store=None, use_llm: bool | None = None):
        self.s = get_settings()
        self.ret = retriever or get_retriever()
        self.assigner = assigner or Assigner.from_training(self.ret.training)
        self.store = store
        self._use_llm = use_llm

    # ------------------------------------------------------------ helpers
    @property
    def llm_on(self) -> bool:
        if self._use_llm is not None:
            return bool(self._use_llm) and any_llm_enabled()
        return any_llm_enabled()

    def _known_names(self, t: Ticket) -> set[str]:
        return names_from_emails(t.reporter, t.assignee, *[a for a, _ in t.comment_bodies()])

    @staticmethod
    def _text_all(safe: TicketSafety) -> str:
        return " ".join([safe.summary, safe.description, *[b for _, b in safe.comments]])

    # ------------------------------------------------------------ stage 1: safety + classification
    def prepare(self, t: Ticket) -> Ctx:
        stage: dict[str, float] = {}
        t0 = time.perf_counter()
        safe = analyse_ticket(t.summary, t.description, t.comment_bodies(), reporter=t.reporter, known_names=self._known_names(t))
        stage["safety"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        votes = self.ret.playbook_service_votes(safe.text)
        rules = C.classify_rules(t, safe.summary, safe.description, safe.comments, votes)
        stage["classify_rules"] = (time.perf_counter() - t0) * 1000

        cls, agreement, versions, notes, spec = rules, 0.6, {}, [], None
        if self.llm_on and not safe.injection:
            t0 = time.perf_counter()
            from .llm_tasks import llm_classify, llm_urgency_impact
            text_all = self._text_all(safe)
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_cls = _submit(ex, llm_classify, safe.summary, safe.description, " ".join(b for _, b in safe.comments),
                                selected_service=t.service, request_type=t.request_type, entity=t.entity or rules.entity,
                                given_work_type=t.work_type, advisory=rules.candidates)
                f_pri = _submit(ex, llm_urgency_impact, text_all, rules.service, rules.work_type)
                try:
                    llm_cls, ver = f_cls.result()
                    versions["classify"] = ver
                    cls, agreement, arb_notes = self._arbitrate(rules, llm_cls)
                    notes += arb_notes
                except (LLMError, LLMUnavailable) as e:
                    notes.append(f"LLM classification unavailable ({str(e)[:90]}): using deterministic rules")
                try:
                    spec = (f_pri.result(), rules.service, rules.work_type)
                except (LLMError, LLMUnavailable):
                    spec = None
            stage["classify_llm"] = (time.perf_counter() - t0) * 1000
        return Ctx(ticket=t, safety=safe, rules=rules, cls=cls, votes=votes, stage_ms=stage, prompt_versions=versions,
                   notes=notes, agreement=agreement, spec_priority=spec)

    def _arbitrate(self, rules: Classification, llm: Classification) -> tuple[Classification, float, list[str]]:
        notes: list[str] = []
        top_rules = rules.candidates[0] if rules.candidates else None
        rules_scores = {c.service: c.score for c in rules.candidates}
        service, source = llm.service, "ensemble"
        if llm.service == rules.service:
            agreement = 1.0
            notes.append("LLM and rules agree on the service")
        else:
            agreement = 0.3
            llm_support = rules_scores.get(llm.service, 0.0)
            strong_rules = top_rules is not None and top_rules.score >= 6.0 and llm_support < 0.25 * top_rules.score
            prefer_rules = self.s.arbitration == "rules_first" or (strong_rules and llm.confidence < 0.75)
            if prefer_rules:
                service = rules.service
                notes.append(f"LLM proposed {llm.service} but the ontology evidence for {rules.service} is much stronger; kept {rules.service}")
            else:
                notes.append(f"LLM overrode the rules ranking ({rules.service} -> {llm.service})")
        merged = llm.model_copy(update={
            "service": service, "team": team_for(service) if service != UNKNOWN else team_for(CHANNEL_SERVICE),
            "source": source, "candidates": rules.candidates,
            "reasons": (llm.reasons + [r for r in rules.reasons if r not in llm.reasons])[:6],
            "unclear": llm.unclear,
            "confidence": round(0.7 * llm.confidence + 0.3 * rules.confidence, 3) if service == llm.service == rules.service else
            round(min(llm.confidence, rules.confidence), 3),
        })
        return merged, agreement, notes

    # ------------------------------------------------------------ stage 2: everything else
    def finish(self, ctx: Ctx, batch_pool: dict | None = None, commit_assign: bool = True, assign: bool = True) -> TriageResult:
        t = ctx.ticket
        safe, cls = ctx.safety, ctx.cls
        stage = ctx.stage_ms
        notes = list(ctx.notes)
        versions = dict(ctx.prompt_versions)
        text_all = self._text_all(safe)
        llm_ok = self.llm_on and not safe.injection
        par = self.llm_on

        # ---- priority (evidence -> policy) --------------------------------------------------
        def priority_stage() -> PriorityResult:
            t0 = time.perf_counter()
            entities = t.entities or ([cls.entity] if cls.entity else [])
            pr_rules = P.rule_assess(P.AssessInput(text=text_all, service=cls.service, work_type=cls.work_type, request_type=t.request_type,
                                                   entities=entities, unclear=cls.unclear), overrides_enabled=self.s.enable_business_overrides)
            pr = pr_rules
            if llm_ok:
                try:
                    if ctx.spec_priority and (ctx.spec_priority[1], ctx.spec_priority[2]) == (cls.service, cls.work_type):
                        pr_llm, ver = ctx.spec_priority[0]
                    else:
                        from .llm_tasks import llm_urgency_impact
                        pr_llm, ver = llm_urgency_impact(text_all, cls.service, cls.work_type)
                    versions["urgency_impact"] = ver
                    pr = P.sanity_clamp(pr_llm, cls.service, cls.work_type)
                    if (pr.urgency, pr.impact) != (pr_rules.urgency, pr_rules.impact):
                        notes.append(f"urgency/impact: LLM {pr.urgency}/{pr.impact} vs rules {pr_rules.urgency}/{pr_rules.impact}")
                except (LLMError, LLMUnavailable) as e:
                    notes.append(f"LLM urgency/impact unavailable ({str(e)[:80]}): using rule-based extraction")
            stage["priority"] = (time.perf_counter() - t0) * 1000
            assert P.is_consistent(pr.priority, pr.urgency, pr.impact)
            return pr

        # ---- agent loop (retrieval tools, bounded) -------------------------------------------
        def agent_stage() -> AgentState:
            t0 = time.perf_counter()
            st = AgentState(ticket_id=t.id, masked_text=safe.text, summary=safe.summary, service=cls.service, team=cls.team,
                            work_type=cls.work_type, created=t.created, request_type=t.request_type, unclear=cls.unclear,
                            injection=safe.injection, injection_reasons=safe.injection_reasons,
                            extra_pool=[p for p in (batch_pool or {}).get(cls.service, []) if p[1] != t.id])
            run_agent(self.ret, st, use_llm=self.llm_on and self.s.agent_mode == "llm")
            stage["agent"] = (time.perf_counter() - t0) * 1000
            if st.mode.startswith("llm"):
                versions["agent"] = "agent.v1"
            return st

        if par:
            with ThreadPoolExecutor(max_workers=2) as ex:
                fp, fa = _submit(ex, priority_stage), _submit(ex, agent_stage)
                pr, st = fp.result(), fa.result()
        else:
            pr, st = priority_stage(), agent_stage()

        # ---- flags ----------------------------------------------------------------------------
        best_kb = st.kb_hits[0].score if st.kb_hits else 0.0
        dup_parent = st.related[0]["id"] if (st.related and cls.work_type == "Incident" and not cls.unclear) else None
        conf = round(0.4 * min(1.0, cls.confidence) + 0.4 * min(1.0, best_kb / KB_GOOD) + 0.2 * ctx.agreement, 3)
        flags = Flags(unclear=cls.unclear, mismatch=cls.title_mismatch or cls.work_type_changed or cls.service_changed,
                      duplicate=bool(dup_parent), injection=safe.injection, low_confidence=conf < self.s.confidence_floor,
                      pii=safe.redaction_count > 0)

        # ---- resolution (status policy + note) || draft --------------------------------------
        def resolution_stage() -> tuple[str, str, str, str]:
            t0 = time.perf_counter()
            pb_hits = self.ret.resolution_playbook(safe.text, service=cls.service, k=3)
            same = [h for h in pb_hits if cls.service in (h.meta.get("services") or [])]
            intent = R.detect_intent(text_all, cls.work_type)
            same = [h for h in same if R.playbook_fits_intent(h.text, intent)]
            best_pb = same[0] if same and same[0].score >= PB_MIN else None
            status, why = R.decide_status(cls, flags, text_all, bool(best_pb), dup_parent)
            refs = R.extract_refs(safe.text)
            note, src = self._resolution_note(t, cls, safe, status, best_pb, same, st, refs, dup_parent, versions, notes)
            stage["resolution"] = (time.perf_counter() - t0) * 1000
            return status, why, note, src

        def draft_stage() -> Draft:
            t0 = time.perf_counter()
            d = self._draft(t, cls, safe, st, flags, best_kb, versions, notes)
            stage["draft"] = (time.perf_counter() - t0) * 1000
            return d

        if par:
            with ThreadPoolExecutor(max_workers=2) as ex:
                fr, fd = _submit(ex, resolution_stage), _submit(ex, draft_stage)
                (status, status_why, note, note_src), draft = fr.result(), fd.result()
        else:
            (status, status_why, note, note_src), draft = resolution_stage(), draft_stage()

        # ---- assignee -------------------------------------------------------------------------
        assignee, why = (self.assigner.pick(cls.service, t.id + safe.text, commit=commit_assign) if assign else (None, ""))

        return TriageResult(
            ticket_id=t.id, work_type=cls.work_type, service=cls.service, team=cls.team, assignee=assignee, assignee_reason=why,
            urgency=pr.urgency, impact=pr.impact, priority=pr.priority, resolution=status,
            resolution_note=_scrub_note(note), resolution_source=note_src, confidence=conf, flags=flags,
            classification=cls, priority_detail=pr, draft=draft, duplicates=[r["id"] for r in st.related],
            similar=st.similar, trace=st.trace, redaction_count=safe.redaction_count,
            mode=("hybrid" if self.llm_on and cls.source != "rules" else "llm" if self.llm_on else "offline"),
            prompt_versions=versions, notes=notes + [f"status: {status_why}"] + safe.warnings, stage_ms={k: round(v, 1) for k, v in stage.items()},
        )

    # ------------------------------------------------------------ resolution note
    def _resolution_note(self, t, cls, safe, status, best_pb, same, st, refs, dup_parent, versions, notes) -> tuple[str, str]:
        if safe.injection:
            return ("Resolution: Escalated to a human analyst because the message contains instruction-like text aimed at the triage system; "
                    "the embedded instructions were treated as data and not followed."), "escalation"
        if dup_parent:
            return R.DUPLICATE_NOTE.format(parent=dup_parent, service=cls.service), "duplicate"
        if status == "clarification":
            asks = "account or system, date and expected outcome"
            return R.CLARIFY_NOTE.format(asks=asks), "clarification"
        if status == "cannot reproduce":
            return R.TRANSIENT_NOTE.format(service=cls.service), "template:transient"
        if self.llm_on:
            try:
                from .llm_tasks import llm_resolution_note
                kb_lines = [f"[{h.meta.get('cite')}] {h.text[:300]}" for h in st.kb_hits[:2]]
                pb_lines = [h.text for h in same[:3]] or [h.text for h in self.ret.resolution_playbook(safe.text, k=2)]
                text, ver = llm_resolution_note(safe.text, cls.service, cls.work_type, pb_lines, kb_lines, refs, status)
                versions["resolution"] = ver
                return text, "llm"
            except (LLMError, LLMUnavailable) as e:
                notes.append(f"LLM resolution note unavailable ({str(e)[:70]}): using playbook/template")
        if best_pb is not None:
            return R.with_refs(best_pb.text, refs), f"playbook:{best_pb.id}"
        text, tid = R.template_note(cls.service, cls.work_type, safe.text, cls.team, cls.entity)
        return R.with_refs(text, refs), f"template:{tid}"

    # ------------------------------------------------------------ draft
    def _draft(self, t, cls, safe, st: AgentState, flags: Flags, best_kb: float, versions, notes) -> Draft:
        lang = D.detect_language(safe.text)
        dec = st.decision
        if dec == "escalate":
            d = D.build_escalation(st.injection_reasons or [st.escalation or "escalation recommended"])
        elif dec == "clarify" or flags.unclear or cls.service == UNKNOWN:
            d = self._clarification(cls, safe, st, lang, versions, notes)
        elif flags.low_confidence and best_kb < self.s.confidence_floor * 0.5:
            d = D.build_reply(cls.service, cls.team, lang, st.kb_hits, floor=self.s.confidence_floor * 0.5)
        else:
            d = self._reply(t, cls, safe, st, lang, versions, notes)
        d.text = safe.restore(d.text)
        d.next_steps = [safe.restore(s) for s in d.next_steps]
        return d

    def _clarification(self, cls, safe, st, lang, versions, notes) -> Draft:
        base = D.build_clarification(cls.service, cls.team, lang, st.kb_hits)
        if self.llm_on:
            try:
                from .llm_tasks import llm_clarification
                text, ver = llm_clarification(safe.text, lang)
                versions["clarification"] = ver
                base.text = text
            except (LLMError, LLMUnavailable) as e:
                notes.append(f"LLM clarification unavailable ({str(e)[:70]}): template used")
        return base

    def _reply(self, t, cls, safe, st, lang, versions, notes) -> Draft:
        base = D.build_reply(cls.service, cls.team, lang, st.kb_hits, floor=self.s.confidence_floor * 0.25)
        examples = self.store.approved_examples(cls.service, cls.work_type) if self.store else []
        if self.llm_on and not base.insufficient_evidence:
            try:
                from .llm_tasks import llm_draft
                ctx_blocks = [f"[{h.meta.get('cite')}] {h.text[:400]}" for h in st.kb_hits[:4]]
                ctx_blocks += [f"(previously approved reply for the same pattern) {e[:400]}" for e in examples]
                text, steps, ver = llm_draft(safe.text, ctx_blocks, lang, cls.service)
                versions["draft"] = ver
                if text.strip() == "INSUFFICIENT_EVIDENCE":
                    base.insufficient_evidence, base.text = True, "INSUFFICIENT_EVIDENCE"
                else:
                    cov = D.citation_coverage(text)
                    if cov >= 0.9:
                        base.text, base.citation_coverage = text, cov
                        if steps:
                            base.next_steps = steps
                    else:
                        notes.append(f"LLM draft rejected: citation coverage {cov:.2f} < 0.9 after one repair pass; deterministic draft used")
            except (LLMError, LLMUnavailable) as e:
                notes.append(f"LLM draft unavailable ({str(e)[:70]}): deterministic draft used")
        elif examples and not base.insufficient_evidence:
            base.text = examples[0]                    # feedback loop: an accepted edit for the same pattern becomes the base
            notes.append("draft reused from an analyst-approved reply for the same service/work-type pattern")
        return base

    # ------------------------------------------------------------ public API
    def run_ticket(self, t: Ticket, batch_pool: dict | None = None, commit_assign: bool = True) -> TriageResult:
        t_start = time.perf_counter()
        with track() as usage:
            ctx = self.prepare(t)
            res = self.finish(ctx, batch_pool, commit_assign)
        res.latency_ms = round((time.perf_counter() - t_start) * 1000, 1)
        res.cost_usd, res.tokens_in, res.tokens_out, res.llm_calls = round(usage.cost_usd, 6), usage.tokens_in, usage.tokens_out, usage.log
        if self.store:
            self.store.save_ticket(t, redacted_text=ctx.safety.text)
            self.store.save_result(res)
        return res

    def run_batch(self, tickets: list[Ticket]) -> list[TriageResult]:
        """Two passes so alert storms inside the batch can be correlated (same predicted service, 4h window).
        With an LLM, several tickets run concurrently; assignment is applied afterwards in ticket order (deterministic)."""
        workers = max(1, self.s.batch_workers) if self.llm_on else 1

        def prep(t: Ticket):
            t0 = time.perf_counter()
            with track() as u:
                c = self.prepare(t)
            return c, u, time.perf_counter() - t0

        def run_map(fn, items):
            if workers == 1:
                return [fn(i) for i in items]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                return list(ex.map(lambda i: contextvars.copy_context().run(fn, i), items))

        prepped = run_map(prep, tickets)
        pool: dict = {}
        for (c, _u, _s), t in zip(prepped, tickets):
            dt = _parse_dt(t.created)
            if dt and (t.status or "open").lower() in ("open", "in progress"):
                pool.setdefault(c.cls.service, []).append((dt, t.id, t.summary, c.safety.text))

        def fin(item):
            c, u1, s1 = item
            t1 = time.perf_counter()
            with track() as u2:
                res = self.finish(c, pool, assign=False)
            res.latency_ms = round((s1 + (time.perf_counter() - t1)) * 1000, 1)
            res.cost_usd = round(u1.cost_usd + u2.cost_usd, 6)
            res.tokens_in, res.tokens_out = u1.tokens_in + u2.tokens_in, u1.tokens_out + u2.tokens_out
            res.llm_calls = u1.log + u2.log
            return res

        results = run_map(fin, prepped)
        for (c, _u, _s), res in zip(prepped, results):        # deterministic, in-order assignment
            res.assignee, res.assignee_reason = self.assigner.pick(res.service, c.ticket.id + c.safety.text)
            if self.store:
                self.store.save_ticket(c.ticket, redacted_text=c.safety.text)
                self.store.save_result(res)
        return results
