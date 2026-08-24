import { execFileSync } from 'node:child_process'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'
const args = new Map()
for (let index = 2; index < process.argv.length; index += 2) args.set(process.argv[index].replace(/^--/, ''), process.argv[index + 1])
const state = args.get('state')
const suffix = args.get('suffix')
const outputDir = args.get('output')
const hwnd = args.get('hwnd')
const pid = args.get('pid')
const sentinel = args.get('sentinel')
const port = Number(args.get('port') || '9222')
const windowProbe = fileURLToPath(new URL('./windows-window-probe.ps1', import.meta.url))
if (!state || !suffix || !outputDir || !hwnd || !pid || !sentinel) throw new Error('state, suffix, output, hwnd, pid, and sentinel are required')
let lastNativeWindowList = ''

async function connect() {
  const deadline = Date.now() + 120_000
  let lastError = 'not attempted'
  while (Date.now() < deadline) {
    try {
      const browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`)
      const pages = browser.contexts().flatMap((context) => context.pages())
      const page = pages.find((candidate) => !candidate.isClosed())
      if (page) return { browser, page }
      lastError = 'CDP connected but no page was exposed'
      await browser.close()
    } catch (error) {
      lastError = String(error)
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error(`WebView2 state automation unavailable: ${lastError}`)
}

async function visible(locator, label) {
  await locator.waitFor({ state: 'visible', timeout: 120_000 })
  if (!(await locator.isVisible())) throw new Error(`${label} was not visible`)
  return locator
}

async function text(page, value, label = value) {
  return visible(page.getByText(value, { exact: true }).first(), label)
}

async function clickNav(page, name) {
  await visible(page.getByRole('button', { name, exact: true }).first(), `navigation ${name}`)
  await page.getByRole('button', { name, exact: true }).first().click()
}

async function clickProvider(page, name) {
  const card = page.locator('button.provider-card').filter({ hasText: name }).first()
  await visible(card, `provider card ${name}`)
  await card.click()
}

async function capture(name, selector = ['-w', hwnd]) {
  const target = `${outputDir}/${name}.png`
  let lastError
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      execFileSync('winapp', ['ui', 'screenshot', ...selector, '--output', target], { stdio: 'inherit' })
      console.log(`CAPTURED ${target}`)
      return
    } catch (error) {
      lastError = error
      if (attempt < 5) await new Promise((resolve) => setTimeout(resolve, 1000))
    }
  }
  throw lastError
}

async function setupState(page) {
  await clickNav(page, 'Setup & Storage')
  const inventoryDiagnostic = await page.evaluate(async () => {
    const invoke = window.__TAURI_INTERNALS__?.invoke
    if (typeof invoke !== 'function') return { available: false }
    const value = await invoke('setup_tool', { args: ['inventory'] })
    const video = value?.video_tools ?? {}
    return {
      available: true,
      ready: Boolean(video.ready),
      source: String(video.source ?? ''),
      managedDownloadNeeded: Boolean(video.managed_download_needed),
      subtitles: Boolean(video.capabilities?.subtitles),
    }
  })
  console.log(`SETUP_INVENTORY_DIAGNOSTIC ${JSON.stringify(inventoryDiagnostic)}`)
  const heading = await visible(page.locator('.setup-page h1').first(), 'Setup heading')
  let headingText = ''
  const setupDeadline = Date.now() + 180_000
  while (Date.now() < setupDeadline) {
    headingText = (await heading.innerText()).trim()
    console.log(`SETUP_HEADING ${headingText}`)
    if (headingText === 'Ready to create clips') break
    await page.waitForTimeout(500)
  }
  if (headingText !== 'Ready to create clips') {
    const bodyText = (await page.locator('.setup-page').innerText()).replaceAll(sentinel, '[REDACTED]')
    throw new Error(`Setup is not ready: ${headingText}; page=${bodyText.slice(0, 2400)}`)
  }
  await text(page, 'Ready · System', 'system-ready marker')
  await text(page, 'System component reused', 'system reuse marker')
  await text(page, 'Everything needed is here.', 'setup completion marker')
  await capture(`setup-${suffix}`)
}

async function localState(page) {
  await clickNav(page, 'Setup & Storage')
  const heading = await visible(page.locator('.setup-page h1').first(), 'Setup heading for Local AI')
  let headingText = ''
  const localSetupDeadline = Date.now() + 180_000
  while (Date.now() < localSetupDeadline) {
    headingText = (await heading.innerText()).trim()
    console.log(`LOCAL_SETUP_HEADING ${headingText}`)
    if (headingText === 'Ready to create clips') break
    await page.waitForTimeout(500)
  }
  if (headingText !== 'Ready to create clips') {
    const bodyText = (await page.locator('.setup-page').innerText()).replaceAll(sentinel, '[REDACTED]')
    throw new Error(`Local-AI setup is not ready: ${headingText}; page=${bodyText.slice(0, 2400)}`)
  }
  await visible(page.getByText('Optional local AI', { exact: true }).first(), 'optional Local AI section')
  await visible(page.getByRole('heading', { name: 'Choose one model', exact: true }), 'local model choices heading')
  const choices = page.locator('input[name="local-model"]:checked')
  if (await choices.count() !== 1) throw new Error(`expected exactly one selected local model, found ${await choices.count()}`)
  const action = page.getByRole('button', { name: 'Install ClipGauge Local', exact: true })
  await action.scrollIntoViewIfNeeded()
  await visible(action, 'Install ClipGauge Local action')
  await text(page, 'Run scoring locally', 'local scoring heading')
  await capture(`local-ai-${suffix}`)
}

async function providersBaseline(page) {
  await clickNav(page, 'AI Providers')
  await visible(page.getByRole('heading', { name: 'Choose where scoring runs.', exact: true }), 'provider page heading')
  await clickProvider(page, 'OpenRouter Free')
  await text(page, 'OpenRouter Free', 'OpenRouter provider')
  await text(page, 'Gemini', 'Gemini provider')
  const body = await page.locator('body').innerText()
  if ((body.match(/Not configured/g) || []).length < 2) throw new Error('provider baseline did not show both providers as not configured')
  if (body.includes(sentinel)) throw new Error('sentinel appeared in provider baseline DOM')
  await capture(`providers-${suffix}`)
}

async function openRouterSaved(page) {
  await clickProvider(page, 'OpenRouter Free')
  const input = page.locator('#provider-credential')
  await visible(input, 'OpenRouter credential input')
  await input.fill(sentinel)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await text(page, 'Credential saved', 'OpenRouter saved state')
  const body = await page.locator('body').innerText()
  if (body.includes(sentinel)) throw new Error('sentinel appeared in saved-credential DOM')
  await capture(`openrouter-saved-${suffix}`)
}

async function openRouterConnected(page) {
  await page.getByRole('button', { name: 'Test connection', exact: true }).click()
  await text(page, 'Connected', 'OpenRouter connected state')
  const body = await page.locator('body').innerText()
  if (body.includes(sentinel)) throw new Error('sentinel appeared in connected DOM')
  await capture(`openrouter-connected-${suffix}`)
}

async function geminiSaved(page) {
  await clickProvider(page, 'Gemini')
  const input = page.locator('#provider-credential')
  await visible(input, 'Gemini credential input')
  await input.fill(sentinel)
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await text(page, 'Credential saved', 'Gemini saved-unverified state')
  const body = await page.locator('body').innerText()
  if (body.includes(sentinel)) throw new Error('sentinel appeared in Gemini saved DOM')
  await capture(`gemini-saved-unverified-${suffix}`)
}

function nativeWindowHandles() {
  const raw = execFileSync('powershell.exe', ['-NoProfile', '-File', windowProbe, '-ProcessId', pid, '-AllVisible'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  if (!raw) return []
  const parsed = JSON.parse(raw)
  const records = (Array.isArray(parsed) ? parsed : [parsed]).map(String).filter(Boolean)
  const listing = records.join(' || ')
  if (listing !== lastNativeWindowList) {
    lastNativeWindowList = listing
    console.log(`NATIVE_WINDOW_LIST ${listing}`)
  }
  return records.map((record) => record.split('|', 1)[0]).filter(Boolean)
}

async function removalConfirmation(page) {
  const confirmRuntime = await page.evaluate(() => ({
    type: typeof window.confirm,
    own: Object.prototype.hasOwnProperty.call(window, 'confirm'),
    source: String(window.confirm).replace(/\s+/g, ' ').slice(0, 240),
  }))
  console.log(`CONFIRM_RUNTIME ${JSON.stringify(confirmRuntime)}`)
  const deadline = Date.now() + 30_000
  let dialogHandle = ''
  let dialogText = ''
  await page.getByRole('button', { name: 'Remove', exact: true }).click()
  while (Date.now() < deadline) {
    for (const handle of nativeWindowHandles()) {
      try {
        const inspected = execFileSync('winapp', ['ui', 'inspect', '-w', handle], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
        if (inspected.includes('does not revoke the provider key')) {
          dialogHandle = handle
          dialogText = inspected
          break
        }
        dialogText = inspected
      } catch {}
    }
    if (dialogHandle) break
    await page.waitForTimeout(500)
  }
  if (!dialogHandle) {
    console.log(`NATIVE_CONFIRMATION_UIA_SAMPLE ${dialogText.replaceAll(sentinel, '[REDACTED]').slice(0, 1200)}`)
    throw new Error('credential-removal confirmation was not observed through native UIA')
  }
  console.log(`NATIVE_CONFIRMATION_WINDOW_PASS ${dialogHandle}`)
  await capture(`credential-removal-confirmation-${suffix}`)
  execFileSync('powershell.exe', ['-NoProfile', '-Command', 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")'], { stdio: 'inherit' })
  await text(page, 'Not configured', 'post-removal state')
}

async function removeOpenRouter(page) {
  await clickProvider(page, 'OpenRouter Free')
  await page.getByRole('button', { name: 'Remove', exact: true }).click()
  await text(page, 'Not configured', 'OpenRouter post-removal state')
}

const { browser, page } = await connect()
try {
  page.setDefaultTimeout(120_000)
  await visible(page.getByRole('button', { name: 'Setup & Storage', exact: true }).first(), 'application navigation')
  if (state === 'setup') await setupState(page)
  else if (state === 'local-ai') await localState(page)
  else if (state === 'providers') await providersBaseline(page)
  else if (state === 'openrouter-saved') await openRouterSaved(page)
  else if (state === 'openrouter-connected') await openRouterConnected(page)
  else if (state === 'gemini-saved-unverified') await geminiSaved(page)
  else if (state === 'credential-removal-confirmation') await removalConfirmation(page)
  else if (state === 'openrouter-remove') await removeOpenRouter(page)
  else throw new Error(`unknown state: ${state}`)
  console.log(`STATE_ASSERTION_PASS ${state} ${suffix}`)
} finally {
  await browser.close()
}
