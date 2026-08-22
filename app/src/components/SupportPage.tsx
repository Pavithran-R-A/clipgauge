import { FileText, LifeBuoy, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'

interface Props { onBack: () => void }

export default function SupportPage({ onBack }: Props) {
  const [message, setMessage] = useState<string | null>(null)
  async function makeBundle() {
    setMessage('Preparing a redacted support bundle…')
    try { const path = await api.generateSupportBundle(); setMessage(`Support bundle saved locally: ${path}`) } catch (error) { setMessage(`The support bundle could not be created: ${String(error)}`) }
  }
  return <div className="page-frame support-page"><header className="page-header"><div><p className="section-eyebrow">Help & Diagnostics</p><h1>Get unstuck without guessing.</h1><p className="page-lede">ClipGauge keeps technical details available when you need them and out of the way when you don’t.</p></div><button type="button" className="button button-quiet" onClick={onBack}>Back to Create</button></header><div className="support-grid"><section className="support-card card-surface"><span className="support-icon"><LifeBuoy size={22} aria-hidden="true" /></span><h2>Make a support bundle</h2><p>Creates a redacted package with the job details a maintainer needs. API keys and unrelated files are left out.</p><button type="button" className="button button-primary" onClick={makeBundle}><FileText size={16} aria-hidden="true" /> Create support bundle</button>{message && <p className="inline-message" role="status">{message}</p>}</section><section className="support-card card-surface"><span className="support-icon"><ShieldCheck size={22} aria-hidden="true" /></span><h2>Before you send anything</h2><p>Open the bundle folder and check the files yourself. Remove anything you do not want to share before attaching it to an issue.</p><a className="text-link" href="https://github.com/Pavithran-R-A/clipgauge/issues" target="_blank" rel="noreferrer">Open GitHub issues <span aria-hidden="true">→</span></a></section></div></div>
}
