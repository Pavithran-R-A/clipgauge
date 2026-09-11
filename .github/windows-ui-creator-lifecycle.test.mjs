import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const lifecycleScript = readFileSync(new URL('./windows-ui-creator-lifecycle.mjs', import.meta.url), 'utf8')

test('creator lifecycle accepts the native Save As dialog', () => {
  assert.match(lifecycleScript, /Save ClipGauge clip/)
  assert.match(lifecycleScript, /FileNameControlHost/)
  assert.match(lifecycleScript, /\['ui', 'set-value'/)
  assert.match(lifecycleScript, /\['ui', 'inspect'/)
  assert.match(lifecycleScript, /saveButton = tree\.match/)
  assert.match(lifecycleScript, /const okButton = confirmationTree\.match/)
  assert.match(lifecycleScript, /resolve\(output \?\? ''\)/)
})
