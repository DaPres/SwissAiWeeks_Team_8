import { useEffect, useRef, useState } from 'react'
import type { LlmProvider } from './api'

// Brand marks: Azure AI + OpenAI from Lobe Icons (MIT), Apertus from apertus.ai
const MARKS: Record<string, { logo: string; tagline: string }> = {
  foundry: { logo: '/brands/azure-ai.svg', tagline: 'Microsoft Azure deployment' },
  openai: { logo: '/brands/openai.svg', tagline: 'OpenAI API' },
  apertus: { logo: '/brands/apertus.png', tagline: 'Swiss open model · Swisscom' },
}

export function ModelMark({ id }: { id: string }) {
  const logo = MARKS[id]?.logo
  return (
    <span className="model-mark" aria-hidden="true">
      {logo ? <img src={logo} alt="" /> : id[0]?.toUpperCase()}
    </span>
  )
}

export function ModelPicker({ providers, value, onChange, disabled, embeddingModel }: {
  providers: LlmProvider[]
  value: string | null
  onChange: (id: string) => void
  disabled?: boolean
  embeddingModel?: string
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const current = providers.find((p) => p.id === value) ?? providers[0]

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!rootRef.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  function toggle() {
    if (open) { setOpen(false); return }
    setActive(Math.max(0, providers.findIndex((p) => p.id === current?.id)))
    setOpen(true)
  }

  function choose(id: string) {
    onChange(id)
    setOpen(false)
    buttonRef.current?.focus()
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); toggle() }
      return
    }
    if (e.key === 'Escape') { e.preventDefault(); setOpen(false); buttonRef.current?.focus() }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % providers.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + providers.length) % providers.length) }
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(providers[active].id) }
  }

  if (!current) return null

  return (
    <div className="model-picker" ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        className={`model-trigger${open ? ' open' : ''}`}
        onClick={toggle}
        disabled={disabled || providers.length < 2}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Language model: ${current.label}`}
      >
        <ModelMark id={current.id} />
        <span className="model-trigger-text">
          <span className="model-trigger-label">{current.label}</span>
          <span className="model-trigger-model">{current.model}</span>
        </span>
        {providers.length > 1 && <span className="model-chevron" aria-hidden="true">▾</span>}
      </button>
      {open && (
        <div className="model-menu" role="listbox" aria-label="Language model" aria-activedescendant={`model-${providers[active].id}`} tabIndex={-1}>
          <div className="model-menu-head">Choose the assistant’s model</div>
          {providers.map((p, i) => (
            <div
              key={p.id}
              id={`model-${p.id}`}
              role="option"
              aria-selected={p.id === current.id}
              className={`model-option${p.id === current.id ? ' selected' : ''}${i === active ? ' active' : ''}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(p.id)}
            >
              <ModelMark id={p.id} />
              <span className="model-option-text">
                <span className="model-option-label">{p.label}</span>
                <span className="model-option-sub">{MARKS[p.id]?.tagline ?? p.model}</span>
                <span className="model-option-tags">
                  <span className="model-tag mono">{p.model}</span>
                  <span className={`model-tag${p.vision ? ' good' : ''}`}>{p.vision ? 'Reads screenshots' : 'Text only'}</span>
                </span>
              </span>
              <span className="model-check" aria-hidden="true">{p.id === current.id ? '✓' : ''}</span>
            </div>
          ))}
          {embeddingModel && <div className="model-menu-foot">Knowledge search always uses <span className="mono">{embeddingModel.split(':').pop()}</span></div>}
        </div>
      )}
    </div>
  )
}
