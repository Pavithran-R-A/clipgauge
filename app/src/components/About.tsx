interface Props {
  onBack: () => void
}

const CODE_NOTICES = [
  ['WhisperX 3.8.6', 'BSD-2-Clause', 'Pinned transcription and diarization dependency'],
  ['clip-forge, clippyme, laughter-detection, PANNs, autoclip', 'MIT', 'Adapted or vendored processing components'],
  ['3D-Speaker CAM++', 'Apache-2.0', 'Vendored speaker-embedding model definition'],
  ['supoclip and ViralMint-derived caption logic', 'AGPL-3.0', 'Adapted captioning approaches']
]

export default function About({ onBack }: Props) {
  return (
    <div className="onboarding about-page">
      <div className="grain" />
      <main className="about-card" aria-labelledby="about-title">
        <header className="modal-head">
          <div>
            <p className="ob-kicker">ClipGauge v0.2.0</p>
            <h1 id="about-title" className="ob-h2">ABOUT / LICENSES</h1>
          </div>
          <button className="btn-ghost" onClick={onBack}>back</button>
        </header>

        <p className="ob-body">
          ClipGauge is a local-first desktop AI video clipper. It is a modified derivative of
          <a href="https://github.com/Blueturboguy07/publikclip" target="_blank" rel="noreferrer"> publikclip</a>,
          based on upstream commit <span className="mono">a53a359b985b1d2d666266062936cc186f02340b</span>.
        </p>

        <section className="about-section" aria-labelledby="license-heading">
          <p id="license-heading" className="audit-label">PRIMARY LICENSE</p>
          <p className="ig-message">
            ClipGauge is distributed under the <strong>GNU Affero General Public License, version 3 or later</strong>.
            Read the complete license in the repository’s <span className="mono">LICENSE</span> file.
          </p>
        </section>

        <section className="about-section" aria-labelledby="notice-heading">
          <p id="notice-heading" className="audit-label">THIRD-PARTY NOTICE SUMMARY</p>
          <div className="about-notices">
            {CODE_NOTICES.map(([name, license, purpose]) => (
              <div className="about-notice" key={name}>
                <strong>{name}</strong>
                <span className="chip chip-amber">{license}</span>
                <span>{purpose}</span>
              </div>
            ))}
          </div>
          <p className="ig-message">
            The complete inventory of adapted code, runtime-fetched model weights, bundled fonts,
            optional binaries, and deliberate exclusions is in <span className="mono">THIRD_PARTY_NOTICES.md</span>.
          </p>
        </section>

        <section className="about-section" aria-labelledby="privacy-heading">
          <p id="privacy-heading" className="audit-label">LOCAL-FIRST DISCLOSURE</p>
          <p className="ig-message">
            There is no default telemetry and no mandatory subscription. Source media and managed
            job state remain local unless you choose a URL download, runtime/model download, optional
            provider integration, or another network feature shown by the privacy activity view.
          </p>
        </section>

        <footer className="about-footer">
          <span className="mono">Data root: ~/.clipgauge</span>
          <span className="mono">Bundle: io.github.pavithranra.clipgauge</span>
          <span className="mono">Linux v0.2.0 artifact: unsigned</span>
        </footer>
      </main>
    </div>
  )
}
