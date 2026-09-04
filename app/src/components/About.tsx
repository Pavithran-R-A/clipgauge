import { ArrowLeft, ExternalLink, FileText, Github, Scale, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'

interface Props { onBack: () => void }

function friendlyPlatform(): string {
  const platform = navigator.platform || ''
  const userAgent = navigator.userAgent || ''
  if (/^Win/i.test(platform)) return /Win64|WOW64|x64/i.test(userAgent) ? 'Windows x64' : 'Windows'
  if (/Mac/i.test(platform)) return /arm64|aarch64/i.test(userAgent) ? 'macOS arm64' : 'macOS x86_64'
  if (/Linux/i.test(platform)) return /aarch64|arm64/i.test(userAgent) ? 'Linux arm64' : 'Linux x86_64'
  return 'Desktop'
}

export default function About({ onBack }: Props) {
  const [platform, setPlatform] = useState('Desktop')
  useEffect(() => { setPlatform(friendlyPlatform()) }, [])
  return (
    <div className="page-frame about-page">
      <header className="page-header">
        <div>
          <p className="section-eyebrow">About</p>
          <h1>ClipGauge, made for making.</h1>
          <p className="page-lede">A local-first desktop app for finding, framing, captioning, and reviewing short vertical clips.</p>
        </div>
        <button type="button" className="button button-quiet" onClick={onBack}><ArrowLeft size={16} aria-hidden="true" /> Back to Create</button>
      </header>
      <div className="about-grid">
        <section className="about-identity card-surface">
          <span className="about-mark" aria-hidden="true"><span /></span>
          <h2>ClipGauge</h2>
          <p>Turn long videos into vertical clips worth sharing.</p>
          <div className="about-meta"><span>Version</span><strong>ClipGauge v0.5.6</strong><span>Platform</span><strong>{platform}</strong></div>
        </section>
        <section className="about-section card-surface"><div className="about-section-icon"><Scale size={19} aria-hidden="true" /></div><div><h2>License</h2><p>ClipGauge is distributed under the <strong>GNU Affero General Public License, version 3 or later</strong>.</p><a className="text-link" href="https://github.com/Pavithran-R-A/clipgauge/blob/main/LICENSE" target="_blank" rel="noreferrer">Read the license <ExternalLink size={14} aria-hidden="true" /></a></div></section>
        <section className="about-section card-surface"><div className="about-section-icon"><Github size={19} aria-hidden="true" /></div><div><h2>Source and attribution</h2><p>ClipGauge is maintained as an independent open-source project and preserves attribution to its upstream project, <strong>Blueturboguy07/publikclip</strong>.</p><div className="about-links"><a className="text-link" href="https://github.com/Pavithran-R-A/clipgauge" target="_blank" rel="noreferrer">Source code <ExternalLink size={14} aria-hidden="true" /></a><a className="text-link" href="https://github.com/Blueturboguy07/publikclip" target="_blank" rel="noreferrer">Upstream project <ExternalLink size={14} aria-hidden="true" /></a></div></div></section>
        <section className="about-section card-surface"><div className="about-section-icon"><FileText size={19} aria-hidden="true" /></div><div><h2>Third-party notices</h2><p>ClipGauge includes and downloads software and model assets under their own licenses. The complete notices include the runtime, fonts, model sources, and the GPL-3.0-only bgutil component.</p><a className="text-link" href="https://github.com/Pavithran-R-A/clipgauge/blob/main/THIRD_PARTY_NOTICES.md" target="_blank" rel="noreferrer">View notices <ExternalLink size={14} aria-hidden="true" /></a></div></section>
      </div>
      <div className="about-footer-note"><ShieldCheck size={16} aria-hidden="true" /><span>ClipGauge has no mandatory account and no default telemetry. See Privacy for the details of the provider you choose.</span></div>
    </div>
  )
}
