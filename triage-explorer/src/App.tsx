import { useEffect, useState } from 'react'
import './App.css'
import raw from './data/insights.json'
import type { Insights } from './types'
import { Challenge, Matrix, Overview, Services } from './views'
import { Plan } from './Plan'
import { Assist } from './Assist'
import { Queue } from './Queue'
import { Curation } from './Curation'
import { api, type Catalog } from './api'

const data = raw as unknown as Insights

const TABS = ['Get help', 'Agent queue', 'Data curation', 'Overview', 'Services & experts', 'Priority matrix', 'Challenge tickets', 'Plan'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('Get help')
  const [catalog, setCatalog] = useState<Catalog | null>(null)

  useEffect(() => { api.catalog().then(setCatalog).catch(() => setCatalog(null)) }, [])

  return (
    <div className="app">
      <header className="header">
        <div>
          <div className="eyebrow">Swiss AI Weeks · SwissLife 2026</div>
          <h1>Ticket Triage Assistant</h1>
          <p>
            Describe a problem and get help straight away; if a ticket is needed, it arrives already triaged. Every ticket
            an agent resolves goes back into the knowledge base.
          </p>
        </div>
      </header>
      <nav className="tabs" role="tablist">
        {TABS.map((t, i) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}
            style={i === 3 ? { marginLeft: 16 } : undefined}>
            {t}
          </button>
        ))}
      </nav>
      {tab === 'Get help' && <Assist catalog={catalog} />}
      {tab === 'Agent queue' && <Queue catalog={catalog} />}
      {tab === 'Data curation' && <Curation />}
      {tab === 'Overview' && <Overview data={data} />}
      {tab === 'Services & experts' && <Services data={data} />}
      {tab === 'Priority matrix' && <Matrix data={data} />}
      {tab === 'Challenge tickets' && <Challenge data={data} />}
      {tab === 'Plan' && <Plan />}
    </div>
  )
}
