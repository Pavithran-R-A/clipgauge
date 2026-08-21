import { useEffect, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'

/** Post-onboarding key management — the onboarding-only input was a gap. */

interface Props {
  onClose: () => void
}

function PexelsField() {
  const [key, setKey] = useState('')
  const [saved, setSaved] = useState(false)
  return (
    <div className="ig-form">
      <input
        placeholder="Pexels API key (free — pexels.com/api)"
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        className="mono"
      />
      <button
        className="btn-secondary"
        disabled={!key.trim()}
        onClick={async () => {
          await invoke('save_pexels_key', { key })
          setSaved(true)
        }}
      >
        {saved ? 'saved ✓' : 'save'}
      </button>
    </div>
  )
}

export default function KeyModal({ onClose }: Props) {
  const [key, setKey] = useState('')
  const [hasKey, setHasKey] = useState<boolean | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    invoke<{ has_gemini_key: boolean }>('get_setup_state').then((s) =>
      setHasKey(s.has_gemini_key)
    )
  }, [])

  async function save() {
    if (!key.trim()) return
    await invoke('save_gemini_key', { key })
    setSaved(true)
    setHasKey(true)
  }

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="key-modal-title" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <p id="key-modal-title" className="audit-kicker">PROVIDER SETTINGS</p>
          <button className="btn-ghost" onClick={onClose}>close ✕</button>
        </header>
        <p className="ig-intro">
          Provider prices, quotas, and model limits change over time. Credentials are stored in your operating system’s vault and supplied only to the operation that needs them.{' '}
          {hasKey && <strong>A Gemini key is currently saved{saved ? ' — updated ✓' : ''}.</strong>}
        </p>
        <div className="ig-form">
          <input
            placeholder="AIza… (aistudio.google.com → Get API key)"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && save()}
            className="mono"
          />
          <button className="btn-primary" onClick={save} disabled={!key.trim()}>
            {saved ? 'SAVED ✓' : 'SAVE KEY'}
          </button>
        </div>
        <p className="audit-label" style={{ marginTop: 22 }}>OPTIONAL STOCK VISUALS</p>
        <PexelsField />
        <p className="ig-message mono">
          Applies to new runs; a job mid-flight keeps the brain it started with.
        </p>
      </div>
    </div>
  )
}
