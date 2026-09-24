const PIPELINE = [
  ['1 · Normalise', 'Merge summary, description, comments; strip channel noise (“Mail copied into Jira”).'],
  ['2 · Retrieve', 'Embed ticket; kNN over training tickets + rich resolution patterns (BM25 + embeddings).'],
  ['3 · Classify', 'LLM with catalog + top-k precedents → work type & real service (JSON schema).'],
  ['4 · Route', 'Service → team via lookup table; assignee = precedent resolver, else team default.'],
  ['5 · Assess', 'LLM rates Urgency & Impact against matrix definitions + criticality list.'],
  ['6 · Prioritise', 'Priority = matrix[U][I] in code — always consistent.'],
  ['7 · Resolve', 'LLM writes resolution note grounded in precedent, in resolver’s voice; picks label.'],
]

const PHASES: { title: string; time: string; items: string[] }[] = [
  {
    title: 'Understand the data (done here)',
    time: '≈ 1 h',
    items: [
      'Service → Team is a strict 1:1 lookup; the only hard routing call is the service.',
      '27% of training sits in the “Emailed Support Tickets” bucket — never a final answer for a routed ticket.',
      'Priority / Urgency / Impact and the Resolution label are random in training — do not train on them.',
      'Assignee is random, but each rich resolution pattern has a single consistent author → use it as the expert.',
      'Work type is determined by content, not the title (“Production outage … shared mailbox” = Service Request).',
    ],
  },
  {
    title: 'Build the knowledge base',
    time: '≈ 2 h',
    items: [
      'Service catalog card per service: owning team, criticality, typical symptoms, keywords, known root causes.',
      'Precedent index: every distinct rich resolution pattern with its resolver, service and example tickets.',
      'Embed both (e.g. voyage / text-embedding) and keep a BM25 index for IDs like MT536, SCD_POS_SYNC, CAEV.',
      'Few-shot bank of mislabelled examples (“Incorrect incident title…”, “Incident mislabelled…”).',
    ],
  },
  {
    title: 'LLM triage agent',
    time: '≈ 3 h',
    items: [
      'One structured-output call per ticket (Claude, JSON schema) with: ticket, catalog, top-5 precedents, matrix text.',
      'Ask for reasoning fields first (symptom → process stage → service), then the decision fields.',
      'Deterministic post-processing: team lookup, matrix priority, assignee from precedent, enum validation.',
      'Guardrails: service must be one of the 19 real services; resolution ∈ {done, cancelled, clarification, cannot reproduce}.',
    ],
  },
  {
    title: 'Evaluate without the answer key',
    time: '≈ 2 h',
    items: [
      'Hold-out set from training: take rich tickets, corrupt service/title like the challenge does, score routing accuracy.',
      'Self-consistency: run 3–5 samples, flag tickets where service or U/I disagree for review.',
      'LLM-as-judge rubric on resolution notes: specific? grounded in precedent? mentions verification step?',
      'Compare against the baseline in this explorer — the LLM must beat it on the low-confidence tickets.',
    ],
  },
  {
    title: 'Ship & present',
    time: '≈ 1 h',
    items: [
      'Export the 20 triaged tickets in the challenge JSON shape (fill Service Team(s), Assignee, Priority, Resolution, comment).',
      'Show this explorer + per-ticket rationale in the demo: why the service changed, which precedent was used.',
      'Pipeline is re-runnable on a freshly generated challenge file — no ticket-specific hardcoding.',
    ],
  },
]

const RISKS = [
  ['Resolver not in assignee pool', 'ursula.klassen, tara.singh, victor.hamon, vincent.lange write resolutions but never appear as Assignee. Decide: use them anyway (they are the de-facto experts) or fall back to team default — test both.'],
  ['Services without rich precedents', 'Rimes, NAV, Fund Pricing, IAM, SharePoint, CRM, Portfolio Accounting, Trading Platform, Risk & Compliance have no expert signal. Assignee is guesswork; invest in note quality instead.'],
  ['Channel vs. process confusion', 'Vendor mails land on SharePoint/CRM because of the channel. Train the prompt to route by the process stage described (benchmark file → Rimes, LEI rejection → Regulatory Reporting).'],
  ['Over-escalation', 'Unclear or shouty tickets (“pls fix asap”) are not automatically Critical. Anchor U/I on the matrix wording and service criticality.'],
]

export function Plan() {
  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Target pipeline</h3>
        <p className="sub">Retrieval-grounded LLM for judgement calls; code for everything deterministic.</p>
        <div className="pipeline">
          {PIPELINE.map(([t, d], k) => (
            <div key={t} style={{ display: 'contents' }}>
              <div className="step"><b>{t}</b>{d}</div>
              {k < PIPELINE.length - 1 && <div className="arrow" aria-hidden>→</div>}
            </div>
          ))}
        </div>
      </div>

      <div className="grid">
        {PHASES.map((p, k) => (
          <div className="card phase" key={p.title}>
            <div className="n">{k + 1}</div>
            <div>
              <h3>{p.title} <span className="pill" style={{ marginLeft: 6 }}>{p.time}</span></h3>
              <ul>{p.items.map((i) => <li key={i}>{i}</li>)}</ul>
            </div>
          </div>
        ))}
      </div>

      <h2 className="section-title">Risks & open decisions</h2>
      <div className="grid cols-2">
        {RISKS.map(([t, d]) => (
          <div className="card" key={t}>
            <h3><span className="pill warn">⚠</span> {t}</h3>
            <p style={{ margin: '6px 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>{d}</p>
          </div>
        ))}
      </div>

      <h2 className="section-title">Scoring focus</h2>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Field</th><th>Signal source</th><th>Approach</th></tr></thead>
          <tbody>
            <tr><td>Work type</td><td>Description body, not title</td><td>LLM + few-shot mislabelled examples</td></tr>
            <tr><td>Service</td><td>Process stage in text, IDs, vendor names</td><td>Retrieval + LLM, constrained enum</td></tr>
            <tr><td>Team</td><td>Service</td><td>Lookup table (100% in training)</td></tr>
            <tr><td>Assignee</td><td>Resolver of nearest rich precedent</td><td>Retrieval; team default fallback</td></tr>
            <tr><td>Priority</td><td>Urgency × Impact</td><td>LLM rates U/I → matrix in code</td></tr>
            <tr><td>Resolution</td><td>Ticket clarity + outcome</td><td>LLM; clarification only for genuinely unclear asks</td></tr>
            <tr><td>Resolution text</td><td>Precedent pattern + ticket specifics</td><td>LLM rewrite in resolver voice</td></tr>
          </tbody>
        </table>
      </div>
    </>
  )
}
