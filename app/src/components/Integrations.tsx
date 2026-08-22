import { useEffect, useState } from 'react'
import { Check, ExternalLink, Instagram, Link2, PictureInPicture2, ShieldCheck, Unplug } from 'lucide-react'
import { api } from '../api'
import type { SetupState } from '../types'

interface Props { onBack: () => void; onOpenLoop: () => void }

export default function Integrations({ onBack, onOpenLoop }: Props) {
  const [setup, setSetup] = useState<SetupState | null>(null)
  const [pexelsKey, setPexelsKey] = useState('')
  const [saved, setSaved] = useState(false)
  const [instagramConnected, setInstagramConnected] = useState(false)
  const [instagramUser, setInstagramUser] = useState<string | undefined>()
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.setupState().then((value) => setSetup(value)).catch(() => undefined)
    api.igStatus().then((status) => { setInstagramConnected(status.connected); setInstagramUser(status.username) }).catch(() => undefined)
  }, [])

  async function savePexels() {
    if (!pexelsKey.trim()) return
    try {
      await api.savePexelsKey(pexelsKey.trim())
      setPexelsKey('')
      setSaved(true)
      setSetup((current) => current ? { ...current, provider_keys: { ...(current.provider_keys ?? {}), pexels: true } } : current)
      setMessage('Pexels is connected. The key stays in your operating-system vault.')
    } catch (error) {
      setMessage(`Pexels could not be connected: ${String(error)}`)
    }
  }

  const pexelsConnected = Boolean(setup?.provider_keys?.pexels)

  return (
    <div className="page-frame integrations-page">
      <header className="page-header"><div><p className="section-eyebrow">Integrations</p><h1>Bring the tools you already use.</h1><p className="page-lede">Stock visuals and performance feedback live here—not beside your AI provider settings.</p></div><button type="button" className="button button-quiet" onClick={onBack}>Back to Create</button></header>
      <div className="integration-grid">
        <section className="integration-card card-surface"><div className="integration-card-top"><span className="integration-icon"><PictureInPicture2 size={21} aria-hidden="true" /></span><span className={`status-pill tone-${pexelsConnected || saved ? 'ready' : 'neutral'}`}><span className="status-dot" aria-hidden="true" />{pexelsConnected || saved ? 'Connected' : 'Not configured'}</span></div><p className="section-eyebrow">Stock visuals</p><h2>Pexels</h2><p>Find optional stock images for overlays while you edit. ClipGauge only contacts Pexels when you ask for a search.</p><div className="integration-privacy"><ShieldCheck size={16} aria-hidden="true" /><span>Optional. Your key is stored in the operating-system vault.</span></div><div className="integration-actions">{!pexelsConnected && <div className="input-with-action"><input type="password" value={pexelsKey} onChange={(event) => setPexelsKey(event.target.value)} placeholder="Pexels API key" autoComplete="off" /><button type="button" className="button button-secondary" onClick={savePexels} disabled={!pexelsKey.trim()}><Check size={15} aria-hidden="true" />{saved ? 'Saved' : 'Connect'}</button></div>}{pexelsConnected && <button type="button" className="button button-secondary" onClick={() => setMessage('To remove a stored key, use your operating-system password manager.') }><Unplug size={15} aria-hidden="true" /> Manage key</button>}<a className="text-link" href="https://www.pexels.com/api/" target="_blank" rel="noreferrer">Get a free Pexels key <ExternalLink size={14} aria-hidden="true" /></a></div></section>
        <section className="integration-card card-surface"><div className="integration-card-top"><span className="integration-icon instagram-icon"><Instagram size={21} aria-hidden="true" /></span><span className={`status-pill tone-${instagramConnected ? 'ready' : 'neutral'}`}><span className="status-dot" aria-hidden="true" />{instagramConnected ? `Connected${instagramUser ? ` as ${instagramUser}` : ''}` : 'Not connected'}</span></div><p className="section-eyebrow">Performance feedback</p><h2>Instagram</h2><p>Link published reels to the clips that inspired them and compare real performance with ClipGauge’s local score.</p><div className="integration-privacy"><ShieldCheck size={16} aria-hidden="true" /><span>Optional. Sync is started by you and shown in Privacy.</span></div><div className="integration-actions"><button type="button" className="button button-primary" onClick={onOpenLoop}><Link2 size={15} aria-hidden="true" />{instagramConnected ? 'Open feedback' : 'Connect Instagram'}</button><button type="button" className="button button-quiet" onClick={() => setMessage('Instagram connection is optional. Your clips remain usable without it.')}>Why connect?</button></div></section>
      </div>
      {message && <p className="inline-message" role="status">{message}</p>}
    </div>
  )
}
