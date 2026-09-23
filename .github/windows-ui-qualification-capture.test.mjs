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

test('v0.6.2 Create qualification uses semantic controls', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /What should ClipGauge find\?/)
  assert.match(qualificationScript, /Content intent/)
  assert.match(qualificationScript, /Choose the balance/)
  assert.match(qualificationScript, /Scoring mode/)
  assert.match(qualificationScript, /Advanced creation settings/)
  assert.match(qualificationScript, /Choose how many options/)
  assert.doesNotMatch(qualificationScript, /Create Step 2/)
  assert.doesNotMatch(qualificationScript, /Create Step 3/)
})

test('v0.6.2 Create qualification accepts descriptive radio names', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /getByRole\('radio'\)\.filter\(\{ hasText: label \}\)\.first\(\)/)
  assert.doesNotMatch(qualificationScript, /getByRole\('radio', \{ name: label, exact: true \}\)/)
})

test('v0.6.2 Setup qualification avoids removed local-AI copy contracts', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /Core components are ready\./)
  assert.match(qualificationScript, /Everything needed is installed/)
  assert.match(qualificationScript, /\.local-model-section/)
  assert.match(qualificationScript, /\.local-install-action/)
  assert.doesNotMatch(qualificationScript, /Ready to create clips/)
  assert.doesNotMatch(qualificationScript, /Choose one model/)
  assert.doesNotMatch(qualificationScript, /Run scoring locally/)
  assert.doesNotMatch(qualificationScript, /ClipGauge Local is ready/)
})

test('v0.6.2 Sessions qualification seeds mixed supported fixtures', () => {
  const powershell = readFileSync(new URL('./windows-ui-qualification.ps1', import.meta.url), 'utf8')
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(powershell, /function Seed-SessionFixtures/)
  assert.match(powershell, /ClipGauge QA\\Interview with Alex\.mp4/)
  assert.match(powershell, /YTDLP_TRANSFER_FAILED/)
  assert.match(qualificationScript, /SESSIONS_MIXED_FIXTURES/)
  assert.match(qualificationScript, /Remove failed session/)
})

test('hostile sidebar fixtures use the supported session metadata contract', () => {
  const powershell = readFileSync(new URL('./windows-ui-qualification.ps1', import.meta.url), 'utf8')
  const hostileSeed = powershell.match(/function Seed-HostileSessions[\s\S]*?\n}\r?\n\r?\nfunction Remove-HostileSessions/)
  assert.ok(hostileSeed, 'hostile session seeding must remain discoverable')
  assert.match(hostileSeed[0], /input\.json/)
  assert.match(hostileSeed[0], /source_type = 'file'/)
  assert.match(hostileSeed[0], /lifecycle\.json/)
  assert.match(hostileSeed[0], /state = 'RESUMABLE'/)
})

test('no-recommendation fixture matches the v0.6.2 session presentation', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /Analysis complete\.\*no recommended clips\/i/)
  assert.match(qualificationScript, /quality bar was not met\/i/)
  assert.doesNotMatch(qualificationScript, /detail: \/no recommended clips\//)
})

test('each packaged viewport resets scroll before layout evidence', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /window\.scrollTo\(0, 0\)/)
  assert.match(qualificationScript, /document\.scrollingElement\.scrollTop = 0/)
  assert.match(qualificationScript, /document\.documentElement\.scrollTop = 0/)
  assert.match(qualificationScript, /document\.querySelector\(selector\)\?\.scrollTo\(0, 0\)/)
  assert.match(qualificationScript, /async function assertLayout\(page, state\) \{\s+await resetScrollPosition\(page\)/)
  assert.match(qualificationScript, /await page\.getByRole\('button', \{ name, exact: true \}\)\.first\(\)\.click\(\)\s+await resetScrollPosition\(page\)/)
})

test('fresh Windows qualification canonicalizes its isolated home path', () => {
  const outputRoot = qualificationScript.indexOf('$OutputDir = [IO.Path]::GetFullPath($OutputDir)')
  const homeSelection = qualificationScript.indexOf('$qualificationHome =')
  assert.ok(outputRoot >= 0, 'qualification output root must be absolute')
  assert.ok(homeSelection > outputRoot, 'isolated home must use the absolute output root')
})

test('full qualification reuses its clean, bootstrapped isolated home', () => {
  assert.match(qualificationScript, /\[string\] \$QualificationHome/)
  const workflow = readFileSync(new URL('./workflows/windows.yml', import.meta.url), 'utf8')
  assert.match(workflow, /windows-ui-qualification\.ps1.*-QualificationHome \$nativeHome/)
  assert.match(workflow, /Remove-Item -Recurse -Force -ErrorAction SilentlyContinue \$nativeHome/)
  assert.match(workflow, /New-Item -ItemType File -Force \(Join-Path \$nativeHome "onboarded"\)/)
})

test('Groq picker state tests selected-model refresh and restart persistence', () => {
  const qualificationScript = readFileSync(new URL('./windows-ui-qualification.mjs', import.meta.url), 'utf8')
  assert.match(qualificationScript, /async function groqModelSwitch\(page, restart = false\)/)
  assert.match(qualificationScript, /Refresh models/)
  assert.match(qualificationScript, /openai\/gpt-oss-120b/)
  assert.match(qualificationScript, /Connection ready/)
  assert.match(qualificationScript, /groq-model-switch-restart/)
})
