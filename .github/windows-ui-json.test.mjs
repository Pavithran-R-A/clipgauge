import assert from 'node:assert/strict'
import test from 'node:test'
import { parseWinAppJsonText, readWinAppJsonTextUntil } from './windows-ui-json.mjs'

test('accepts a non-empty machine-readable text envelope', () => {
  assert.equal(parseWinAppJsonText('{"text":"Remove the saved OpenRouter Free credential."}'), 'Remove the saved OpenRouter Free credential.')
})

test('rejects malformed JSON', () => {
  assert.throws(() => parseWinAppJsonText('{"text":'), /invalid JSON/)
})

test('rejects a missing or empty text field', () => {
  assert.throws(() => parseWinAppJsonText('{}'), /no non-empty text field/)
  assert.throws(() => parseWinAppJsonText('{"text":"   "}'), /no non-empty text field/)
})

test('rejects a non-string text field', () => {
  assert.throws(() => parseWinAppJsonText('{"text":42}'), /no non-empty text field/)
})

test('waits for complete native confirmation text', async () => {
  const observations = [
    '{"text":"Remove the saved OpenRouter Free credential from this computer? This removes only"}',
    '{"text":"Remove the saved OpenRouter Free credential from this computer? This removes only ClipGauge’s saved credential and does not revoke the provider key."}',
  ]
  let attempts = 0
  const result = await readWinAppJsonTextUntil(
    () => observations[attempts++],
    {
      expectedProvider: 'OpenRouter Free',
      expectedPhrase: 'does not revoke the provider key',
      timeoutMs: 100,
      intervalMs: 1,
      sleep: async () => {},
    },
  )

  assert.equal(result.phraseObserved, true)
  assert.equal(attempts, 2)
})
