import { useEffect, useRef, useState } from 'react'
import { FileText, LifeBuoy, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import type { PreflightResult, YouTubeReadiness } from '../types'
import { readDisplayDiagnostics, type DisplayDiagnostics } from '../displayDiagnostics'
import { isPreflightResult, isYouTubeReadiness } from '../nativeValidation'
import { friendlyErrorMessage } from '../errorMessaging'

interface Props {
  onBack: () => void
  onNavigate?: (section: 'setup' | 'providers') => void
  provider?: string
  currentJobId?: string | null
  currentDiagnosticId?: string | null
}

type HealthRow = { name: string; state: string; message: string }

export default function SupportPage({ onBack, onNavigate, provider = 'clipgauge-local', currentJobId, currentDiagnosticId }: Props) {
  const [message, setMessage] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthRow[]>([])
  const [youtube, setYoutube] = useState<YouTubeReadiness | null>(null)
  const [display, setDisplay] = useState<DisplayDiagnostics | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    let active = true
    void readDisplayDiagnostics().then((value) => { if (active) setDisplay(value) }).catch(() => { if (active) setMessage('Display diagnostics are unavailable. Restart ClipGauge and retry.') })
    void Promise.allSettled([api.preflight(provider), api.youtubeReadiness()]).then(([preflightResult, youtubeResult]) => {
      if (!active) return
      if (preflightResult.status === 'rejected' || youtubeResult.status === 'rejected') setMessage('Health checks are unavailable. Open Setup and retry.')
      if (preflightResult.status === 'fulfilled') {
        if (!isPreflightResult(preflightResult.value)) { setMessage('Health checks are malformed. Open Setup and retry.'); return }
        const result = preflightResult.value as PreflightResult
        setHealth(result.checks.filter((check) => ['ffmpeg', 'clipgauge-local', 'provider', 'managed-data'].includes(check.name)).map((check) => ({ name: check.name, state: check.state === 'ready' ? 'Ready' : check.state === 'warning' ? 'Needs attention' : 'Setup needed', message: check.message })))
      }
      if (youtubeResult.status === 'fulfilled') {
        if (youtubeResult.value !== null && !isYouTubeReadiness(youtubeResult.value)) { setMessage('YouTube status is malformed. Open Setup and retry.'); return }
        setYoutube(youtubeResult.value as YouTubeReadiness | null)
      }
    })
    return () => { active = false }
  }, [provider])

  async function makeBundle() {
    setMessage('Preparing a redacted support bundle…')
    try {
      await api.generateSupportBundle(currentJobId ?? undefined, currentDiagnosticId ?? undefined)
      if (mountedRef.current) setMessage('Support bundle created. Review it before sharing.')
    } catch (error) {
      if (mountedRef.current) setMessage(friendlyErrorMessage(error, 'The support bundle could not be created. Retry the action.'))
    }
  }

  return <div className="page-frame support-page"><header className="page-header"><div><p className="section-eyebrow">Help & Diagnostics</p><h1>Get unstuck without guessing.</h1><p className="page-lede">ClipGauge keeps technical details available when you need them and out of the way when you don’t.</p></div><button type="button" className="button button-quiet" onClick={onBack}>Back to Create</button></header><section className="support-health card-surface"><div className="section-heading"><div><p className="section-eyebrow">ClipGauge health</p><h2>Local system check</h2><p className="section-caption">Read-only checks use friendly statuses and never display provider keys.</p></div><ShieldCheck size={22} aria-hidden="true" /></div><div className="health-grid">{health.map((row) => <div className="health-row" key={row.name}><span><strong>{row.name === 'ffmpeg' ? 'Video tools' : row.name === 'clipgauge-local' ? 'ClipGauge Local' : row.name}</strong><small>{row.message}</small></span><b className={`health-state health-${row.state.toLowerCase().replace(' ', '-')}`}>{row.state}</b></div>)}{youtube && <div className="health-row"><span><strong>YouTube support</strong><small>{youtube.reason} Local-file import remains available if a public link is rejected.</small></span><b className={`health-state health-${youtube.ready ? (youtube.public_download_verified ? 'ready' : 'needs-attention') : 'needs-attention'}`}>{youtube.public_download_verified ? 'Public download tested' : youtube.ready ? 'Tools ready' : 'Needs attention'}</b></div>}</div><div className="support-context-actions"><button type="button" className="button button-secondary" onClick={() => onNavigate?.('setup')}>Open Setup</button><button type="button" className="button button-secondary" onClick={() => onNavigate?.('providers')}>Open AI Providers</button></div></section>{display && <section className="support-display card-surface"><div className="section-heading"><div><p className="section-eyebrow">Display diagnostics</p><h2>Logical layout facts</h2><p className="section-caption">CSS viewport and native window measurements are intentionally reported separately.</p></div></div><div className="display-facts"><div><span>CSS viewport</span><strong>{display.cssViewport.width} × {display.cssViewport.height}</strong></div><div><span>Physical inner window</span><strong>{display.innerPhysical ? `${display.innerPhysical.width} × ${display.innerPhysical.height}` : 'Unavailable'}</strong></div><div><span>Scale factor</span><strong>{display.scaleFactor ?? 'Unavailable'}</strong></div><div><span>Device pixel ratio</span><strong>{display.devicePixelRatio}</strong></div></div></section>}<div className="support-grid"><section className="support-card card-surface"><span className="support-icon"><LifeBuoy size={22} aria-hidden="true" /></span><h2>Make a support bundle</h2><p>Creates a redacted package with the job details a maintainer needs. API keys and unrelated files are left out.</p><button type="button" className="button button-primary" onClick={makeBundle}><FileText size={16} aria-hidden="true" /> Create support bundle</button>{message && <p className="inline-message" role="status">{message}</p>}</section><section className="support-card card-surface"><span className="support-icon"><ShieldCheck size={22} aria-hidden="true" /></span><h2>Before you send anything</h2><p>Open the bundle folder and check the files yourself. Remove anything you do not want to share before attaching it to an issue.</p><a className="text-link" href="https://github.com/Pavithran-R-A/clipgauge/issues" target="_blank" rel="noreferrer">Open GitHub issues <span aria-hidden="true">→</span></a></section></div></div>
}
