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
  fallbackReadValue = null,
  fallbackSource = 'fallback',
  timeoutMs = 5_000,
  intervalMs = 250,
  sleep = (delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs)),
} = {}) {
  const deadline = Date.now() + timeoutMs
  let attempts = 0
  let text = ''
  let lastError

  while (true) {
    const readers = fallbackReadValue
      ? [[readValue, 'winapp-cli-json'], [fallbackReadValue, fallbackSource]]
      : [[readValue, 'winapp-cli-json']]
    for (const [reader, source] of readers) {
      attempts += 1
      try {
        text = parseWinAppJsonText(await reader(), 'ContentText')
      } catch (error) {
        lastError = error
        continue
      }

      const providerObserved = !expectedProvider || text.includes(expectedProvider)
      const phraseObserved = !expectedPhrase || text.toLowerCase().includes(expectedPhrase.toLowerCase())
      if (providerObserved && phraseObserved) return { text, attempts, providerObserved, phraseObserved, source }
    }
    if (Date.now() >= deadline) break
    await sleep(intervalMs)
  }

  if (!text && lastError) throw lastError
  return {
    text,
    attempts,
    providerObserved: !expectedProvider || text.includes(expectedProvider),
    phraseObserved: !expectedPhrase || text.toLowerCase().includes(expectedPhrase.toLowerCase()),
    source: 'incomplete',
  }
}
