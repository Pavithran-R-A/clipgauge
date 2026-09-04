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

test('keeps production model setup retries bounded and verified', () => {
  const start = workflow.indexOf('  model-e2e-release:')
  const end = workflow.indexOf('  release-metadata:', start)
  assert.notEqual(start, -1, 'model E2E job is missing')
  assert.notEqual(end, -1, 'release metadata job is missing')
  const modelJob = workflow.slice(start, end)
  assert.match(modelJob, /for attempt in 1 2 3 4;/)
  for (const label of ['ASR assets', 'analysis assets', 'local runtime', 'local model']) {
    assert.match(modelJob, new RegExp(`install_verified "${label}"`))
  }
  assert.match(modelJob, /setup install-group --group core:asr/)
  assert.match(modelJob, /setup install-group --group core:analysis/)
  assert.match(modelJob, /setup install-runtime/)
  assert.match(modelJob, /setup download-model clipgauge-local\/qwen3-1\.7b-q8_0/)
  assert.doesNotMatch(modelJob, /while true|for \(;;\)/)
})

test('uploads model failure diagnostics without masking failures', () => {
  const start = workflow.indexOf('  model-e2e-release:')
  const end = workflow.indexOf('  release-metadata:', start)
  const modelJob = workflow.slice(start, end)
  assert.match(modelJob, /id: model-e2e-diagnostics/)
  assert.match(modelJob, /if: always\(\)/)
  for (const filename of [
    'model-e2e.jsonl',
    'setup-asr.jsonl',
    'setup-analysis.jsonl',
    'setup-runtime.jsonl',
    'setup-model.jsonl',
    'diagnostics',
  ]) {
    assert.match(modelJob, new RegExp(filename.replace('.', '\\.') ))
  }
  assert.match(modelJob, /failure-summary\.txt/)
})

test('uses a deterministic multi-segment genuine speech acceptance input', () => {
  const start = workflow.indexOf('  model-e2e-release:')
  const end = workflow.indexOf('  release-metadata:', start)
  const modelJob = workflow.slice(start, end)
  assert.match(modelJob, /anullsrc=r=16000:cl=mono:d=1/)
  assert.match(modelJob, /laughing-esc50\.wav/)
  assert.match(modelJob, /amix=inputs=2:duration=first/)
  assert.match(modelJob, /atrim=duration=3/)
  assert.match(modelJob, /concat=n=5:v=0:a=1/)
  assert.match(modelJob, /asplit=3\[speech1\]\[speech2\]\[speech3\]/)
  assert.match(modelJob, /acceptance\.flac/)
  assert.doesNotMatch(modelJob, /-stream_loop -1 -i tests\/fixtures\/v041-jfk\.flac/)
})
