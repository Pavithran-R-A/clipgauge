export function physicalCandidates(logical, scaleFactor) {
  const exact = logical * scaleFactor
  const lower = Math.floor(exact)
  const upper = Math.ceil(exact)
  return [...new Set([lower, upper])]
}

export const REQUIRED_EMULATED_SCALE_FACTORS = [1, 1.25, 1.5, 1.75, 2]

export function validateEmulatedDisplayFacts(facts) {
  const errors = []
  const scale = Number(facts.emulated_scale_factor)
  const dpr = Number(facts.device_pixel_ratio)
  const css = facts.css_viewport
  const documentClient = facts.document_client
  if (!Number.isFinite(scale) || !REQUIRED_EMULATED_SCALE_FACTORS.includes(scale)) errors.push('emulated scale factor is not in the required set')
  if (!Number.isFinite(dpr) || Math.abs(dpr - scale) > 1e-6) errors.push('emulated device pixel ratio mismatch')
  if (!css || !documentClient) errors.push('emulated display facts are incomplete')
  if (css && documentClient && (documentClient.width > css.width || documentClient.height > css.height)) errors.push('emulated document client exceeds CSS viewport')
  return { pass: errors.length === 0, errors }
}

export function validateDisplayFacts(facts) {
  const requested = facts.requested_logical_size
  const css = facts.css_viewport
  const documentClient = facts.document_client
  const inner = facts.actual_native_inner_size
  const client = facts.native_client_rect
  const capture = facts.client_capture
  const scale = Number(facts.tauri_scale_factor)
  const dpi = Number(facts.dpi_for_window)
  const errors = []
  if (!requested || !css || !documentClient || !inner || !client || !capture) errors.push('display facts are incomplete')
  if (!Number.isFinite(scale) || scale <= 0) errors.push('Tauri scale factor is invalid')
  if (!Number.isFinite(dpi) || dpi <= 0) errors.push('Windows DPI is invalid')
  if (Number.isFinite(scale) && Number.isFinite(dpi) && Math.abs(scale - dpi / 96) > 1e-9) errors.push('Tauri and Windows scale factors disagree')
  if (requested && css && (css.width !== requested.width || css.height !== requested.height)) errors.push('logical browser viewport mismatch')
  if (css && documentClient && (documentClient.width > css.width || documentClient.height > css.height)) errors.push('document client viewport exceeds CSS viewport')
  if (inner && client && (inner.width !== client.width || inner.height !== client.height)) errors.push('Tauri inner size differs from native client size')
  if (inner && Number.isFinite(scale)) {
    for (const dimension of ['width', 'height']) {
      if (!physicalCandidates(requested[dimension], scale).includes(inner[dimension])) errors.push(`physical ${dimension} is outside explicit floor/ceil conversion`)
    }
  }
  if (capture && client && (capture.width !== client.width || capture.height !== client.height)) errors.push('client capture dimensions mismatch native client')
  return { pass: errors.length === 0, errors, physical_candidates: requested && Number.isFinite(scale) ? { width: physicalCandidates(requested.width, scale), height: physicalCandidates(requested.height, scale) } : null }
}

if (process.argv[2] === '--validate') {
  const input = await new Promise((resolve, reject) => {
    let value = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (chunk) => { value += chunk })
    process.stdin.on('end', () => resolve(value))
    process.stdin.on('error', reject)
  })
  const facts = JSON.parse(input.replace(/^\uFEFF/, ''))
  const result = validateDisplayFacts(facts)
  process.stdout.write(`${JSON.stringify(result)}\n`)
  if (!result.pass) process.exitCode = 1
}
