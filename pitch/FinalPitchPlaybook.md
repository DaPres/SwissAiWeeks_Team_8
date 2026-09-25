# Final pitch — 60 seconds

| Time | Show | Exact script |
|---|---|---|
| 0–8s | Intake with a vague report | “The best ticket is the one that never gets created. And when support is needed, it should arrive with everything needed to act.” |
| 8–23s | Paste prepared details; show guidance, readiness and inferred fields update | “That’s our ambition. Our live intake partner helps people describe what failed, when it started and who is affected. As they type, it spots missing information and asks focused questions—before the ticket reaches support.” |
| 23–30s | Architecture below | “To solve this properly, our team split into two parallel streams: one engineering the smart intake partner to eliminate vague tickets, and another building a deep enterprise triage engine that calculates priority and routes with absolute consistency.” |
| 30–48s | Switch to the same report, preloaded in Main2; highlight routing, evidence and proposal | “Here is the same report in our triage engine. It identifies the responsible team, retrieves relevant precedents and proposes a resolution. The analyst sees the supporting evidence and can edit or approve the response.” |
| 48–60s | Keep the proposal and approval control visible | “Clearer requests for employees. Less back-and-forth for support. AI proposes; people approve. Our goal: resolve it before submission—or give support a head start.” |

---

## One architecture slide

**Guided intake → Triage engine → Evidence-backed proposal → Human approval**

*Triage engine draws on **deterministic business rules + knowledge base + Swisscom Apertus/LLMs**.*

*Intake and triage are built as modular, decoupled micro-frontends/services; the arrow shows the production connection.*

---

## Our Team's Development Journey (Dual-Track Engineering)

> **Core Jury Narrative:** We didn't waste time on monolithic debates or build a superficial prompt wrapper. We attacked both ends of the enterprise service desk problem simultaneously using an intentional **Dual-Track Agile Sprint**:

```
                              ┌── Track A: Front-of-House (Intake Partner) ──┐
[ 20k Dataset Forensics ] ────┤                                              ├──► [ Unified Enterprise Solution ]
(Only 173 unique texts;       └── Track B: Back-of-House (Triage Core Engine)┘
 83% noise / misleading titles)
```

### 1. Phase 1: Data Forensics & Reality Check
* **The Finding:** 20,000 synthetic tickets collapse into only 173 unique texts (11 templates). Priority and assignee are statistically independent noise.
* **The Decision:** Reject naive LLM fine-tuning or raw classification. Build a **Compound AI System** where AI handles semantic reasoning and code handles business rules.

### 2. Phase 2: Parallel Specialization
* **Track A — Front-of-House: The Guided Intake Partner (`intake/` & `main`)**
  * **Focus:** Ticket prevention at the source.
  * **Innovation:** Real-time progressive disclosure. As the employee types, the AI detects missing dimensions (who, what, when, severity) and asks clarifying questions *before* submission.
* **Track B — Back-of-House: The Production Triage Engine (`Main2` / TriageMate)**
  * **Focus:** Security, accuracy, and enterprise resilience.
  * **Innovation:** 
    * **Zero-Leak Safety Gate:** Pre-LLM PII redaction (IBANs, emails, names) & multilingual prompt injection defense.
    * **Deterministic 5×5 ITIL Priority:** LLM extracts quoted evidence; code computes matrix priority (100% mathematical consistency).
    * **Multi-Model Portability:** Swisscom Apertus (Swiss AI Platform), Azure, Claude, and full offline fallback.
    * **Cited Resolution Notes:** Grounded in mined historical playbooks with mandatory `[KB-xx]` citation tokens.

---

## Jury Q&A Talking Points

### Q: "Why do you have two distinct prototypes/interfaces?"
> *"Because enterprise support has two distinct personas with opposing needs:*
> 1. *The **Requester** needs a frictionless, guidance-driven intake that prevents bad tickets.*
> 2. *The **L2 Support Analyst** needs an audit-ready, high-density cockpit showing decision traces, PII masking, and evidence citations.*
> *By decoupling the Intake Partner from the Triage Core Engine, either piece can be integrated into existing Swiss Life tools (e.g. Jira Service Management, ServiceNow, or custom portals) independently."*

### Q: "How did your team organize the work?"
> *"We operated in cross-functional streams from hour one: two engineers focused on data forensics and the backend triage engine (Main2), while others built the interactive intake UX, evaluation harness, and presentation flow. This allowed us to achieve deep technical rigor without sacrificing user experience."*

---

## Demo preparation

- Use one verified ticket example in both prototypes; preload its Main2 result.
- Open two tabs; prepare the extra description to paste. Show one intake update.
- Keep a recording ready for API delays. Rehearse to 55 seconds.
- Skip JSON, code, model names and accuracy claims in the 60s pitch. Ticket prevention is the ambition; this demo shows better intake and triage.
