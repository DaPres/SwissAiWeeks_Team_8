# Final pitch — 60 seconds

| Time | Show | Exact script |
|---|---|---|
| 0–8s | Intake with a vague report | “The best ticket is the one that never gets created. And when support is needed, it should arrive with everything needed to act.” |
| 8–23s | Paste prepared details; show guidance, readiness and inferred fields update | “That’s our ambition. Our live intake partner helps people describe what failed, when it started and who is affected. As they type, it spots missing information and asks focused questions—before the ticket reaches support.” |
| 23–30s | Architecture below | “To solve this properly, our team de-risked delivery with a rapid end-to-end prototype as a safety fallback, while parallel streams specialized deeply: an intelligent Intake Partner to eliminate vague tickets, and TriageMate to calculate priority and route with absolute consistency.” |
| 30–48s | Switch to the same report, preloaded in Main2; highlight routing, evidence and proposal | “Here is the same report in our triage engine. It identifies the responsible team, retrieves relevant precedents and proposes a resolution. The analyst sees the supporting evidence and can edit or approve the response.” |
| 48–60s | Keep the proposal and approval control visible | “Clearer requests for employees. Less back-and-forth for support. AI proposes; people approve. Our goal: resolve it before submission—or give support a head start.” |

---

## One architecture slide

**Guided intake (`intake/`) → TriageMate engine (`Main2/`) → Evidence-backed proposal → Human approval**
*(Rapid E2E prototype & dashboard remains active as the operational fallback safety net)*

*Triage engine draws on **deterministic business rules + knowledge base + Swisscom Apertus/LLMs**.*

*Intake and triage are built as modular, decoupled micro-frontends/services; the arrow shows the production connection.*

---

## Our Team's Development Journey (Rapid Baseline & Deep Specialization)

> **Core Jury Narrative:** We didn't build a fragile monolithic prompt wrapper. We de-risked the challenge immediately with a rapid end-to-end prototype, then specialized in deep domain tracks to create a production-grade compound system:

```
                             ┌──► 1. Rapid E2E Baseline (Day 1 PoC & Fallback) ──┐
                             │    (Intake, triage, resolve & reporting dash)     │
[ 20k Dataset Forensics ] ───┼──► 2. Specialized Intake Partner (intake/)        ├──► [ Flagship Solution ]
(Only 173 unique texts;      │    (Progressive disclosure & live enrichment)     │    (Intake Partner +
 83% noise / misleading      └──► 3. Deep TriageMate Engine (Main2/)             │     TriageMate Core)
 titles)                          (Deterministic ITIL 5x5, PII gate, KB notes)   ─┘    [+ PoC Fallback]
```

### 1. Phase 1: Rapid E2E Baseline & Data Forensics
* **Rapid Prototyping (`main` root):** One team member immediately engineered a complete, functioning end-to-end prototype covering intake, evaluation, triaging, resolution proposal, and a reporting dashboard. This proved feasibility on day one and established a battle-tested operational fallback.
* **Dataset Forensics:** 20,000 synthetic tickets collapsed into only 173 unique texts (11 templates). Priority and assignee were statistically independent noise, proving naive fine-tuning or end-to-end LLM prompts would hallucinate.

### 2. Phase 2: Parallel Deep Specialization
With the fallback baseline secured, dedicated team streams specialized on the critical enterprise bottlenecks:
* **Track A — Specialized Intake Partner (`intake/`):**
  * **Focus:** Ticket prevention at the source (Front-of-House).
  * **Innovation:** Progressive disclosure. As employees type, live evaluation detects missing dimensions (who, what, when, severity, diagnostic evidence) and guides them to provide actionable information *before* reaching support.
* **Track B — Deep-Thinking Triage Engine (`Main2` / TriageMate):**
  * **Focus:** Auditability, deterministic security, and enterprise routing (Back-of-House).
  * **Innovation:**
    * **Zero-Leak Safety Gate:** Pre-LLM PII redaction (IBANs, emails, names) and prompt injection defense.
    * **Deterministic 5×5 ITIL Priority:** LLM extracts quoted evidence; pure deterministic code maps urgency & impact to priority (100% mathematical consistency).
    * **Multi-Model Portability:** Swisscom Apertus (Swiss AI Platform), Azure, Claude, and full offline fallback.
    * **Cited Resolution Playbooks:** Mined historical knowledge base (`[KB-01]` to `[KB-26]`) with mandatory citation evidence.

### 3. Phase 3: Flagship Convergence
* The specialized **Intake Partner** (`intake/`) is wired directly to the **TriageMate Engine** (`Main2/`) to form the primary, production-ready solution.
* The original **Rapid E2E Prototype** remains integrated as a robust fallback and operational analytics dashboard.

---

## Jury Q&A Talking Points

### Q: "How did your team organize the work and development process?"
> *"We started with a rapid end-to-end prototype on day one to de-risk the full lifecycle—from intake to resolution and dashboard reporting. With that safety net in place, our team split into deep specializations: one track perfected the live Intake Partner to stop poor tickets at the source, while another engineered TriageMate for enterprise-grade triage, PII masking, and deterministic ITIL priority. Finally, we merged both into our unified flagship solution."*

### Q: "Why do you have two distinct prototypes/interfaces?"
> *"Because enterprise support serves two distinct personas with fundamentally different workflows:*
> 1. *The **Requester** needs a frictionless, guidance-driven intake that prevents incomplete tickets.*
> 2. *The **L2 Support Analyst** needs an audit-ready cockpit with decision traces, PII masking, and evidence citations.*
> *By decoupling the Intake Partner from the Triage Core Engine, either module can integrate into Swiss Life's existing ecosystem (e.g. Jira Service Management, ServiceNow) independently."*

### Q: "What role does the original prototype play now?"
> *"It serves as our operational fallback and reporting dashboard. Having an independent baseline ensures zero-downtime resilience and gave us a reference benchmark to validate the superior accuracy of our specialized triage engine."*

---

## Demo preparation

- Use one verified ticket example in both prototypes; preload its Main2 result.
- Open two tabs; prepare the extra description to paste. Show one intake update.
- Keep a recording ready for API delays. Rehearse to 55 seconds.
- Skip JSON, code, model names and accuracy claims in the 60s pitch. Ticket prevention is the ambition; this demo shows better intake and triage.
