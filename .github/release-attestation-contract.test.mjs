import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const workflow = fs.readFileSync(new URL('./workflows/release.yml', import.meta.url), 'utf8')

function attestationStep() {
  const start = workflow.indexOf('      - name: Generate GitHub build provenance attestation')
  const end = workflow.indexOf('\n      - name: Record attestation result without overclaiming', start)
  assert.notEqual(start, -1, 'build provenance attestation step is missing')
  assert.notEqual(end, -1, 'attestation result step is missing')
  return workflow.slice(start, end)
}

test('attests only stable release subjects', () => {
  const step = attestationStep()
  const subjectStart = step.indexOf('subject-path:')
  assert.notEqual(subjectStart, -1, 'attestation subject paths are missing')
  const subjects = step.slice(subjectStart)

  for (const subject of [
    'release-assets/ClipGauge_*.deb',
    'release-assets/ClipGauge_*.exe',
    'release-assets/SBOM.cyclonedx.json',
  ]) {
    assert.ok(subjects.includes(subject), `${subject} must be attested`)
  }

  for (const mutableSubject of [
    'release-assets/*',
    'RELEASE_PROVENANCE.md',
    'ATTESTATION_STATUS.md',
    'SHA256SUMS',
  ]) {
    assert.ok(!subjects.includes(mutableSubject), `${mutableSubject} must not be attested`)
  }

  const attestationIndex = workflow.indexOf('      - name: Generate GitHub build provenance attestation')
  const provenanceIndex = workflow.indexOf('      - name: Generate human-readable provenance')
  assert.ok(attestationIndex < provenanceIndex, 'attestation must precede mutable provenance generation')
})
