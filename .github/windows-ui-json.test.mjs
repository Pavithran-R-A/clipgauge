import assert from 'node:assert/strict'
import test from 'node:test'
import { parseWinAppJsonText } from './windows-ui-json.mjs'

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
