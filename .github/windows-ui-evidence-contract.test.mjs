import test from 'node:test'
import assert from 'node:assert/strict'
import { finalizeEvidence, isLocalAiActionLabel, isLocalAiHeading, isSetupReadyLabel, isSetupReuseLabel } from './windows-ui-evidence-contract.mjs'

test('accepts ready setup labels for managed and system video tools', () => {
  assert.equal(isSetupReadyLabel('Ready'), true)
  assert.equal(isSetupReadyLabel('Ready · System'), true)
  assert.equal(isSetupReadyLabel('Core setup needed'), false)
})

test('accepts reuse labels for managed and system video tools', () => {
  assert.equal(isSetupReuseLabel('Reused for future videos'), true)
  assert.equal(isSetupReuseLabel('System component reused'), true)
  assert.equal(isSetupReuseLabel('Download required'), false)
})

test('accepts local AI install and ready actions', () => {
  assert.equal(isLocalAiActionLabel('Install ClipGauge Local'), true)
  assert.equal(isLocalAiActionLabel('Use ClipGauge Local'), true)
  assert.equal(isLocalAiActionLabel('Retry component'), false)
})

test('accepts local AI setup and ready headings', () => {
  assert.equal(isLocalAiHeading('Run scoring locally'), true)
  assert.equal(isLocalAiHeading('ClipGauge Local is ready'), true)
  assert.equal(isLocalAiHeading('Local AI unavailable'), false)
})

test('finalizes semantic metadata with PowerShell-measured image facts', () => {
  const provisional = {
    provider: 'OpenRouter Free',
    target_viewport: { width: 1366, height: 768 },
    owner_screenshot: 'credential-removal-confirmation-1366x768.png',
    native_dialog_screenshot: 'credential-removal-confirmation-dialog-1366x768.png',
    content_text_read_method: 'winapp-ui-get-value-json',
  }
  const result = finalizeEvidence(
    provisional,
    { width: 1366, height: 768, sha256: 'owner-sha' },
    { width: 572, height: 140, sha256: 'dialog-sha' },
  )
  assert.equal(result.owner_width, 1366)
  assert.equal(result.owner_height, 768)
  assert.equal(result.owner_sha256, 'owner-sha')
  assert.equal(result.native_dialog_width, 572)
  assert.equal(result.native_dialog_height, 140)
  assert.equal(result.native_dialog_sha256, 'dialog-sha')
})

test('rejects missing image facts at the enrichment boundary', () => {
  assert.throws(() => finalizeEvidence({}, {}, { width: 1, height: 1, sha256: 'dialog' }), /owner image width is required/)
})
