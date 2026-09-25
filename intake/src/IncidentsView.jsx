import { Button } from '@base-ui/react/button';

const statusText = { 'awaiting client': 'Waiting for your reply', open: 'Handed over', done: 'Resolved' };

function displayedValue(value) {
  if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
  if (value == null || value === '') return '—';
  return String(value);
}

function IncidentDetail({ record, account, onBack, onReviewFix }) {
  const incident = record.incident;
  const expert = record.enriched?.expertResolution;
  const client = record.enriched?.clientResolution;
  const otherFields = Object.entries(incident).filter(([key]) => !['Summary', 'Description', 'All Comments'].includes(key));
  return <section className="incident-detail enter" aria-label={`Incident ${record.id}`}>
    <Button type="button" className="back-link" onClick={onBack}>← My Incidents</Button>
    <div className="detail-heading"><div><span className="detail-id">{record.id}</span><h1>{incident.Summary || 'Untitled incident'}</h1></div>
      <span className="status-pill">{statusText[incident.Status] || incident.Status}</span></div>
    <div className="detail-layout"><div className="detail-main">
      <section className="detail-section"><h2>Description</h2><p className="detail-description">{incident.Description}</p></section>
      <section className="detail-section"><h2>Incident details</h2><dl className="field-grid">
        {otherFields.map(([key, value]) => <div key={key} className="field-pair"><dt>{key}</dt><dd>{displayedValue(value)}</dd></div>)}
      </dl></section>
      <section className="detail-section"><h2>Comments</h2>
        {incident['All Comments']?.length ? <div className="comment-list">{incident['All Comments'].map((comment, index) => <p key={`${index}-${comment}`}>{comment}</p>)}</div>
          : <p className="detail-muted">No comments yet.</p>}
      </section>
    </div><aside className="detail-aside">
      <section className="detail-section"><h2>Proposed expert fix</h2>
        {expert ? <><p className="detail-description">{expert.note || expert.jiraComment}</p>
          {expert.steps?.length > 0 && <ol className="expert-steps">{expert.steps.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol>}
          {expert.team && <p className="detail-muted">For {expert.team}</p>}</>
          : <p className="detail-muted">No expert fix was proposed.</p>}
      </section>
      {client && <section className="detail-section"><h2>Client fix</h2><p className="detail-description">{client.title}</p>
        {client.steps?.length > 0 && <ol className="expert-steps">{client.steps.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol>}
        {incident.Status === 'awaiting client' && account === 'client' &&
          <Button type="button" className="detail-action" onClick={() => onReviewFix(record)}>Respond to suggestion</Button>}
      </section>}
    </aside></div>
  </section>;
}

export default function IncidentsView({ account, records, loading, error, onRetry, selectedId, onSelect, onReviewFix }) {
  const selected = records.find(record => record.id === selectedId);
  if (selected) return <IncidentDetail record={selected} account={account} onBack={() => onSelect(null)} onReviewFix={onReviewFix} />;
  return <section className="incidents-view enter">
    <div className="incidents-heading"><div><h1>My Incidents</h1><p>{account === 'client' ? 'Your reports and their latest outcome.' : `Incidents routed to ${account}.`}</p></div>
      {!loading && !error && <span className="incident-count">{records.length} {records.length === 1 ? 'incident' : 'incidents'}</span>}</div>
    {loading && <div className="list-state" role="status"><span className="list-spinner" aria-hidden="true" />Loading incidents…</div>}
    {error && <div className="list-state" role="alert">{error}<Button type="button" className="text-button" onClick={onRetry}>Retry</Button></div>}
    {!loading && !error && (records.length ? <div className="incident-grid">
      {records.map(record => { const item = record.incident; return <button key={record.id} type="button" className="incident-card" onClick={() => onSelect(record.id)}>
        <span className="card-top"><span>{record.id}</span><span className="card-status">{statusText[item.Status] || item.Status}</span></span>
        <strong>{item.Summary || item.Description}</strong>
        <span className="card-description">{item.Description}</span>
        <span className="card-bottom"><span>{item['Service Team(s)']?.[0] || 'Unassigned'}</span><span>{item['Created date'] || ''}</span></span>
      </button>; })}
    </div> : <div className="empty-incidents"><h2>No incidents yet</h2><p>{account === 'client' ? 'Your submitted incidents will appear here.' : `Incidents handed to ${account} will appear here.`}</p></div>)}
  </section>;
}
