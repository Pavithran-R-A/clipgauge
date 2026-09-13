import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const qualificationScript = readFileSync(new URL('./windows-ui-qualification.ps1', import.meta.url), 'utf8')

test('client capture uses the ClipGauge HWND before cropping client pixels', () => {
  const captureBody = qualificationScript.match(/function Invoke-ClientCapture[\s\S]*?\n}\r?\n\r?\nfunction Validate-DisplayEvidence/)
  assert.ok(captureBody, 'Invoke-ClientCapture function must remain discoverable')
  const body = captureBody[0]
  assert.match(body, /SetForegroundWindow\(\[IntPtr\]\$proc\.MainWindowHandle\)/)
  assert.match(body, /ui screenshot -w/)
  assert.doesNotMatch(body, /CopyFromScreen/)
})

test('packaged qualification records native bridge authorization and denial', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /chromium\.connectOverCDP\(`http:\/\/127\.0\.0\.1:\$\{port\}`\)/)
  assert.match(qualificationScript, /invoke\('vault_scope'\)/)
  assert.match(qualificationScript, /invoke\('get_setup_state'\)/)
  assert.match(qualificationScript, /invoke\('b02_out_of_scope_probe'\)/)
  assert.match(qualificationScript, /credential_values_exposed: false/)
})

test('production setup-only qualification accepts the production vault scope explicitly', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /verifyNativeBridgeContract\(page, outputDir, state, suffix, vaultScope, productionSetupOnly\)/)
  assert.match(qualificationScript, /allowProductionScope/)
  assert.match(qualificationScript, /!allowProductionScope && evidence\.vault_scope !== 'qualification'/)
  assert.match(qualificationScript, /allowProductionScope && evidence\.vault_scope !== 'production'/)
})

test('full Windows qualification requires a local OpenRouter fixture endpoint', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.ps1', import.meta.url), 'utf8')
  assert.match(qualificationScript, /-not \$FreshOnly -and -not \$SetupOnly/)
  assert.match(qualificationScript, /CLIPGAUGE_QA_OPENROUTER_ENDPOINT/)
  assert.match(qualificationScript, /127\\\.0\\\.0\\\.1:\\d\{1,5\}\/v1/)
})

test('fresh Windows qualification canonicalizes its isolated home path', () => {
  const outputRoot = qualificationScript.indexOf('$OutputDir = [IO.Path]::GetFullPath($OutputDir)')
  const homeSelection = qualificationScript.indexOf('$qualificationHome =')
  assert.ok(outputRoot >= 0, 'qualification output root must be absolute')
  assert.ok(homeSelection > outputRoot, 'isolated home must use the absolute output root')
})

test('Groq picker state tests selected-model refresh and restart persistence', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /async function groqModelSwitch\(page, restart = false\)/)
  assert.match(qualificationScript, /Refresh models/)
  assert.match(qualificationScript, /openai\/gpt-oss-120b/)
  assert.match(qualificationScript, /Connection ready/)
  assert.match(qualificationScript, /groq-model-switch-restart/)
})
