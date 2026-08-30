import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { chromium } from 'playwright-core'
import { join } from 'node:path'

const args = new Map()
for (let index = 2; index < process.argv.length; index += 2) args.set(process.argv[index].replace(/^--/, ''), process.argv[index + 1])
const output = args.get('output')
const port = Number(args.get('port') || '9222')
const jobId = args.get('job-id') || '20260829-202013-296b18'
const sessionTitle = args.get('session-title') || 'v041-controlled'
const fixture = args.get('fixture')
if (!output || !fixture) throw new Error('output and fixture are required')
const localFixture = fixture.replaceAll('\\', '/')

async function connect() {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    try {
      const browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`)
      const page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => !candidate.isClosed())
      if (page) return { browser, page }
      await browser.close()
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error('ClipGauge CDP page unavailable')
}

async function waitForVideo(page, testId) {
  const video = page.getByTestId(testId)
  await video.waitFor({ state: 'visible', timeout: 120_000 })
  await page.waitForFunction((id) => {
    const element = document.querySelector(`[data-testid="${id}"]`)
    return element instanceof HTMLVideoElement && element.readyState >= 1 && Number.isFinite(element.duration) && element.duration > 0
  }, testId, { timeout: 120_000 })
  return video
}

async function sampleUi(page, samples, action, timeoutMs = 120_000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const probeStarted = Date.now()
    await page.evaluate(() => document.visibilityState)
    samples.push(Date.now() - probeStarted)
    if (await action()) return
    await page.waitForTimeout(250)
  }
  throw new Error('timed out while sampling UI responsiveness')
}

function findRunningJob(minStartedAtMs = 0) {
  const root = join(process.env.USERPROFILE, '.clipgauge', 'jobs')
  const candidates = readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .sort((left, right) => right.name.localeCompare(left.name))
  for (const entry of candidates) {
    try {
      const runtime = JSON.parse(readFileSync(join(root, entry.name, 'runtime.json'), 'utf8'))
      if (runtime.state === 'RUNNING' && Number(runtime.started_at_ms ?? 0) >= minStartedAtMs) return runtime.job_id ?? entry.name
    } catch {}
  }
  return null
}

function responsiveness(samples) {
  const ordered = [...samples].sort((left, right) => left - right)
  return { samples: samples.length, max_ms: Math.max(...samples), p95_ms: ordered[Math.max(0, Math.ceil(ordered.length * 0.95) - 1)] }
}

async function playback(page, video) {
  const initial = await video.evaluate((element) => ({ duration: element.duration, currentTime: element.currentTime }))
  await video.evaluate(async (element) => { element.muted = true; await element.play() })
  await page.waitForTimeout(600)
  const playing = await video.evaluate((element) => ({ paused: element.paused, currentTime: element.currentTime }))
  await video.evaluate((element) => element.pause())
  const paused = await video.evaluate((element) => ({ paused: element.paused, currentTime: element.currentTime }))
  const target = Math.min(initial.duration - 0.1, Math.max(0.2, initial.currentTime + 0.5))
  await video.evaluate((element, value) => { element.currentTime = value }, target)
  await page.waitForFunction((value) => {
    const element = document.querySelector('[data-testid="review-video"]')
    return element instanceof HTMLVideoElement && Math.abs(element.currentTime - value) < 0.2
  }, target, { timeout: 30_000 })
  const sought = await video.evaluate((element) => element.currentTime)
  if (playing.paused || playing.currentTime <= initial.currentTime) throw new Error('review playback did not advance')
  if (!paused.paused) throw new Error('review pause did not take effect')
  if (Math.abs(sought - target) >= 0.2) throw new Error('review seek did not settle')
  return { initial, playing, paused, sought }
}

const { browser, page } = await connect()
page.setDefaultTimeout(120_000)
const startedAt = Date.now()
const evidence = { job_id: jobId, fixture, stages: {}, responsiveness: {}, process_states: [] }
try {
  const setupNav = page.getByRole('button', { name: 'Setup & Storage', exact: true })
  const studioBack = page.getByRole('button', { name: /studio/ }).first()
  if (await studioBack.count()) {
    await studioBack.click()
    await setupNav.waitFor({ state: 'visible', timeout: 30_000 })
  }
  try {
    await setupNav.waitFor({ state: 'visible', timeout: 10_000 })
  } catch {
    await page.getByRole('button', { name: /Set up ClipGauge/ }).click()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByRole('button', { name: /Open Create/ }).click()
    await setupNav.waitFor({ state: 'visible', timeout: 30_000 })
  }
  await page.getByRole('button', { name: 'Sessions', exact: true }).click()
  const row = page.locator('.session-row').filter({ hasText: sessionTitle }).first()
  await row.getByRole('button', { name: 'Open clips', exact: true }).click()
  const reviewVideo = await waitForVideo(page, 'review-video')
  evidence.process_states.push('REVIEW_OPEN')
  evidence.review = await playback(page, reviewVideo)

  await page.getByRole('button', { name: 'Edit clip', exact: true }).click()
  const editorVideo = await waitForVideo(page, 'editor-source-video')
  evidence.process_states.push('EDITOR_OPEN')
  const editorBefore = await editorVideo.evaluate((element) => ({ duration: element.duration, currentTime: element.currentTime }))
  await page.getByRole('button', { name: 'minimal', exact: true }).click()
  const renderButton = page.getByRole('button', { name: /Render updated clip|Rendering/, exact: false })
  await renderButton.click()
  await page.waitForFunction(() => {
    const button = [...document.querySelectorAll('button')].find((element) => element.textContent?.includes('Rendering'))
    return button instanceof HTMLButtonElement && button.disabled
  }, { timeout: 30_000 })
  const renderSamples = []
  const renderStarted = Date.now()
  await sampleUi(page, renderSamples, async () => await renderButton.isEnabled() && (await page.locator('.editor-err').count()) === 0)
  evidence.stages.rerender = { duration_ms: Date.now() - renderStarted, state: 'SUCCEEDED' }
  evidence.responsiveness.rerender = responsiveness(renderSamples)
  await page.getByRole('button', { name: /clips/ }).first().click()
  const reviewVideoAfter = await waitForVideo(page, 'review-video')
  evidence.process_states.push('RERENDERED_REVIEW')
  evidence.review_after_rerender = await playback(page, reviewVideoAfter)
  await page.getByRole('button', { name: 'EXPORT MP4', exact: true }).click()
  await page.locator('.export-path').waitFor({ state: 'visible', timeout: 120_000 })
  const exportPath = await page.locator('.export-path').innerText()
  evidence.export = { path_present: exportPath.trim().length > 0, exists: existsSync(exportPath.trim()) }
  if (!evidence.export.path_present || !evidence.export.exists) throw new Error('export path was not created')
  await page.getByRole('button', { name: /studio/ }).click()
  await page.getByRole('button', { name: 'Sessions', exact: true }).click()
  await page.locator('.session-row').filter({ hasText: sessionTitle }).first().getByRole('button', { name: 'Open clips', exact: true }).click()
  const reopenedVideo = await waitForVideo(page, 'review-video')
  evidence.process_states.push('REOPENED')
  evidence.reopen = await playback(page, reopenedVideo)

  await page.getByRole('button', { name: /studio/ }).click()
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  const source = page.locator('#source-link')
  await source.fill(localFixture)
  await page.getByRole('button', { name: /ClipGauge Local/ }).click()
  const runRequestedAt = Date.now()
  await page.getByRole('button', { name: 'Create clips', exact: true }).click()
  const cancelButton = page.getByRole('button', { name: 'Cancel', exact: true })
  const runningJobDeadline = Date.now() + 240_000
  let cancellationJobId = null
  while (Date.now() < runningJobDeadline && !cancellationJobId) {
    if (await cancelButton.isVisible().catch(() => false)) cancellationJobId = findRunningJob(runRequestedAt)
    const body = await page.locator('body').innerText()
    if (/couldn.t create clips|needs a setup step|stopped before finishing/i.test(body)) throw new Error('creator run failed before cancellation became available')
    if (!cancellationJobId) await page.waitForTimeout(500)
  }
  if (!cancellationJobId) throw new Error('cancel control appeared before a running job registered')
  evidence.cancellation_job_id = cancellationJobId
  evidence.process_states.push('RUNNING')
  const cancelSamples = []
  const cancelStarted = Date.now()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await sampleUi(page, cancelSamples, async () => {
    const body = await page.locator('body').innerText()
    return body.includes('Job cancelled') || body.includes('cancelled')
  }, 240_000)
  evidence.stages.cancellation = { duration_ms: Date.now() - cancelStarted, state: 'CANCELLED' }
  evidence.responsiveness.cancellation = responsiveness(cancelSamples)
  evidence.process_states.push('CANCELLED')
  evidence.editor = { before: editorBefore, style_changed: 'minimal' }
  evidence.total_duration_ms = Date.now() - startedAt
  writeFileSync(output, `${JSON.stringify(evidence, null, 2)}\n`)
  console.log(`CREATOR_LIFECYCLE_PASS ${output}`)
} finally {
  await browser.close()
}
