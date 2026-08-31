import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const workflow = fs.readFileSync(new URL('./workflows/release.yml', import.meta.url), 'utf8')
const heredocStart = 'cat > RELEASE_NOTES.md <<EOF'
const heredocEnd = '\n          EOF'

function releaseNotesTemplate() {
  const start = workflow.indexOf(heredocStart)
  assert.notEqual(start, -1, 'release-note heredoc is missing')
  const bodyStart = start + heredocStart.length
  const end = workflow.indexOf(heredocEnd, bodyStart)
  assert.notEqual(end, -1, 'release-note heredoc terminator is missing')
  return workflow.slice(bodyStart, end)
}

test('preserves literal Markdown filenames in generated notes', () => {
  const template = releaseNotesTemplate()
  const markdownTick = String.fromCharCode(96)
  for (let index = template.indexOf(markdownTick); index !== -1; index = template.indexOf(markdownTick, index + 1)) {
    assert.equal(template[index - 1], '\\', `backtick at offset ${index} must be escaped`)
  }

  const notes = template.replaceAll('\\`', markdownTick).replaceAll('${RELEASE_TAG}', 'v0.5.4')
  assert.match(notes, /## ClipGauge v0\.5\.4/)
  for (const filename of ['MODEL_E2E_SUMMARY.json', 'SHA256SUMS', 'RELEASE_PROVENANCE.md', 'ATTESTATION_STATUS.md']) {
    assert.ok(notes.includes(markdownTick + filename + markdownTick), `${filename} must remain a literal Markdown filename`)
  }
  assert.doesNotMatch(notes, /its summary is attached as \./)
})
