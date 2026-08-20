import { useEffect, useState } from 'react'
import { api } from '../api'

interface Props {
  onDone: () => void
}

export default function Onboarding({ onDone }: Props) {
  const [step, setStep] = useState(0)
  const [ollama, setOllama] = useState<{ running: boolean; models: string[] } | null>(null)

  useEffect(() => {
    api.checkOllama().then(setOllama).catch(() => setOllama({ running: false, models: [] }))
  }, [])

  return (
    <div className="onboarding">
      <div className="grain" />
      {step === 0 && (
        <section className="ob-step" key="s0">
          <p className="ob-kicker">ClipGauge</p>
          <h1 className="ob-title">THE CLIPPER<br />THAT SHOWS<br />ITS WORK<span className="amber">.</span></h1>
          <p className="ob-body">Long video in, vertical clips out. Speech, laughter, speakers, camera moves, and rendering are processed locally. A selected cloud provider may receive transcript excerpts, prompts, or sampled frames; ClipGauge never requires its own cloud account or telemetry.</p>
          <button className="btn-primary" onClick={() => setStep(1)}>Set it up</button>
        </section>
      )}
      {step === 1 && (
        <section className="ob-step" key="s1">
          <p className="ob-kicker">01 / choose an inference path</p>
          <h2 className="ob-h2">Start local, bring a key, or configure your endpoint</h2>
          <div className="ob-cards">
            <div className={`ob-card ${ollama?.running ? 'done' : ''}`}>
              <h3>Local inference <span className={`led ${ollama?.running ? 'led-on' : 'led-off'}`} /></h3>
              <p>{ollama === null ? 'Checking Ollama…' : ollama.running ? `Ollama is ready (${ollama.models.filter((m) => !m.includes('embed')).slice(0, 2).join(', ') || 'local models'}).` : 'Ollama is not detected. Install it and pull a compatible chat model when you are ready.'}</p>
              <p className="ob-fine">No paid API is required. URL retrieval and optional Pexels/Instagram features still use their own network paths.</p>
            </div>
            <div className="ob-card">
              <h3>Curated cloud / BYO key</h3>
              <p>Gemini, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, and Cerebras can be configured in Studio. Free access, quotas, models, and terms vary by provider and may change.</p>
            </div>
            <div className="ob-card">
              <h3>Custom compatible endpoint</h3>
              <p>Configure an OpenAI-compatible URL, model, and no-auth or header-based credential. HTTPS is required for remote endpoints; loopback HTTP is reserved for local services.</p>
            </div>
          </div>
          <p className="ob-fine">You can switch providers per run. Existing jobs retain their provider snapshot when resumed.</p>
          <button className="btn-primary" onClick={() => setStep(2)}>Continue</button>
        </section>
      )}
      {step === 2 && (
        <section className="ob-step" key="s2">
          <p className="ob-kicker">02 / one honest warning</p>
          <h2 className="ob-h2">First run downloads the local media models</h2>
          <p className="ob-body">ClipGauge stores downloaded speech and audio models under <span className="mono">~/.clipgauge</span>. Jobs checkpoint each stage so you can quit and resume. Provider credentials remain in the operating-system vault and are never written to job snapshots.</p>
          <button className="btn-primary" onClick={onDone}>Open the studio</button>
        </section>
      )}
    </div>
  )
}
