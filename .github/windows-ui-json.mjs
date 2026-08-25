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
