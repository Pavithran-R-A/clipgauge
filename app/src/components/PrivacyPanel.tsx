import { useEffect, useState } from 'react'
import { ArrowDownToLine, CheckCircle2, Globe2, LockKeyhole, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import type { PrivacySummary } from '../types'

interface Props { provider: string; onBack: () => void }

function PrivacyCard({ icon, title, children, tone }: { icon: React.ReactNode; title: string; children: React.ReactNode; tone: string }) {
  return <article className={`privacy-card privacy-${tone}`}><span className="privacy-card-icon">{icon}</span><div><h2>{title}</h2><div className="privacy-card-content">{children}</div></div></article>
}

export default function PrivacyPanel({ provider, onBack }: Props) {
  const [privacy, setPrivacy] = useState<PrivacySummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.privacySummary(provider).then(setPrivacy).catch((reason) => setError(String(reason))) }, [provider])

  return <div className="page-frame privacy-page"><header className="page-header"><div><p className="section-eyebrow">Privacy</p><h1>Know what leaves this computer.</h1><p className="page-lede">ClipGauge is local-first. This view explains the network activity for the AI choice you made.</p></div><button type="button" className="button button-quiet" onClick={onBack}>Back to Create</button></header>{error && <p className="error-message" role="alert">Privacy details could not be loaded: {error}</p>}{privacy ? <><div className="privacy-summary-banner"><ShieldCheck size={22} aria-hidden="true" /><span><strong>{privacy.local_first ? 'Local-first mode' : 'Provider-aware mode'}</strong><small>{privacy.llm.provider}</small></span><span className="status-pill tone-ready"><span className="status-dot" aria-hidden="true" />No default telemetry</span></div><div className="privacy-grid"><PrivacyCard tone="local" icon={<LockKeyhole size={21} aria-hidden="true" />} title="Stays on this computer"><ul>{privacy.llm.device.map((item) => <li key={item}><CheckCircle2 size={15} aria-hidden="true" />{item}</li>)}</ul></PrivacyCard><PrivacyCard tone="network" icon={<ArrowDownToLine size={21} aria-hidden="true" />} title="Sent to your AI provider"><ul>{privacy.llm.network.map((item) => <li key={item}><Globe2 size={15} aria-hidden="true" />{item}</li>)}</ul><p className="privacy-provider-note">{privacy.llm.provider}</p></PrivacyCard><PrivacyCard tone="other" icon={<Globe2 size={21} aria-hidden="true" />} title="Other network activity"><p>{privacy.instagram}</p><p>{privacy.telemetry}</p></PrivacyCard></div><details className="advanced-panel"><summary>Show technical details</summary><div className="technical-grid"><span>AI mode</span><code>{privacy.llm.mode}</code><span>Provider</span><code>{privacy.llm.provider}</code><span>Model</span><code>{privacy.llm.model ?? 'provider-managed'}</code><span>Endpoint</span><code>{privacy.llm.endpoint ?? 'provider-managed'}</code><span>Source</span><code>{privacy.source}</code></div></details></> : !error && <div className="loading-card"><span className="loading-line" /><span className="loading-line short" /><span className="loading-line" /></div>}</div>
}
