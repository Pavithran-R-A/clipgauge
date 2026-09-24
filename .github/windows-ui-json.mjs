export function parseWinAppJsonText(stdout, label = 'WinAppCLI UIA value') {
  let payload
  try {
    payload = JSON.parse(stdout)
  } catch (error) {
    throw new Error(`${label} returned invalid JSON: ${String(error).slice(0, 240)}`)
  }
  if (typeof payload?.text !== 'string' || payload.text.trim() === '') {
    throw new Error(`${label} returned no non-empty text field`)
  }
  return payload.text
}

export async function readWinAppJsonTextUntil(readValue, {
  expectedProvider = '',
  expectedPhrase = '',
  timeoutMs = 5_000,
  intervalMs = 250,
  sleep = (delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs)),
} = {}) {
  const deadline = Date.now() + timeoutMs
  let attempts = 0
  let text = ''
  let lastError

  while (true) {
    attempts += 1
    try {
      text = parseWinAppJsonText(await readValue(), 'ContentText')
    } catch (error) {
      lastError = error
    }

    const providerObserved = !expectedProvider || text.includes(expectedProvider)
    const phraseObserved = !expectedPhrase || text.toLowerCase().includes(expectedPhrase.toLowerCase())
    if (providerObserved && phraseObserved) return { text, attempts, providerObserved, phraseObserved }
    if (Date.now() >= deadline) break
    await sleep(intervalMs)
  }

  if (!text && lastError) throw lastError
  return {
    text,
    attempts,
    providerObserved: !expectedProvider || text.includes(expectedProvider),
    phraseObserved: !expectedPhrase || text.toLowerCase().includes(expectedPhrase.toLowerCase()),
  }
}
