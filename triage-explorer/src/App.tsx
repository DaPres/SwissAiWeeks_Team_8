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

const PAGE_COPY: Record<Tab, { title: string; description: string }> = {
  'Get help': {
    title: 'Help starts here',
    description: 'Describe what’s happening and get a useful answer straight away. If you need a ticket, we’ll prepare it and route it to the right team.',
  },
  'Agent queue': { title: 'The agent workspace', description: 'Review incoming tickets, resolve issues, and turn each answer into shared knowledge.' },
  'Data curation': { title: 'Knowledge that gets better', description: 'Explore and publish the resolution patterns that make support more useful over time.' },
  Overview: { title: 'The support landscape', description: 'A clear view of ticket patterns, data quality, and the opportunities behind the challenge.' },
  'Services & experts': { title: 'Find the right expertise', description: 'See how services connect to teams and the people who know how to resolve them.' },
  'Priority matrix': { title: 'Priority, made consistent', description: 'Explore the urgency and impact rules behind a dependable triage decision.' },
  'Challenge tickets': { title: 'Learn from the tricky cases', description: 'Inspect challenge tickets and compare the original labels with their triage signals.' },
  Plan: { title: 'From insight to impact', description: 'Follow the path from data curation to useful answers and smarter ticket routing.' },
}

export default function App() {
  const [tab, setTab] = useState<Tab>('Get help')
  const [catalog, setCatalog] = useState<Catalog | null>(null)

  useEffect(() => { api.catalog().then(setCatalog).catch(() => setCatalog(null)) }, [])

  return (
    <div className="app">
      <div className="brandbar">
        <div className="brand">
          <img src="/ai-weeks-support-logo.webp" alt="" className="brand-logo" />
          <div className="brand-wordmark">
            <span>Swiss <b>{'{ai}'}</b> Weeks</span>
            <small>Support Agent</small>
          </div>
        </div>
        <span className="event-badge">SwissLife · 2026</span>
      </div>
      <header className={`header hero${tab === 'Get help' ? '' : ' hero-compact'}`}>
        <div className="hero-copy">
          <div className="hero-eyebrow"><span className="hero-spark" /> Intelligent support, beautifully simple</div>
          <h1>{PAGE_COPY[tab].title}<span>.</span></h1>
          <p>{PAGE_COPY[tab].description}</p>
          {tab === 'Get help' && <div className="hero-flow" aria-label="How it works">
            <span>01 &nbsp; Describe</span><i aria-hidden="true" />
            <span>02 &nbsp; Get guidance</span><i aria-hidden="true" />
            <span>03 &nbsp; Resolve</span>
          </div>}
        </div>
      </header>
      <nav className="tabs" role="tablist">
        {TABS.map((t, i) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`tab${tab === t ? ' active' : ''}${i === 3 ? ' tab-divider' : ''}`} onClick={() => setTab(t)}>
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
