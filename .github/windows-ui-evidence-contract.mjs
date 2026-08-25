import { readFileSync } from 'node:fs'

function requireImageFacts(facts, label) {
  if (!facts || typeof facts !== 'object') throw new Error(`${label} image facts are required`)
  if (!Number.isInteger(facts.width) || facts.width <= 0) throw new Error(`${label} image width is required`)
  if (!Number.isInteger(facts.height) || facts.height <= 0) throw new Error(`${label} image height is required`)
  if (typeof facts.sha256 !== 'string' || !facts.sha256) throw new Error(`${label} image SHA-256 is required`)
}

export function finalizeEvidence(provisional, ownerFacts, dialogFacts) {
  if (!provisional || typeof provisional !== 'object') throw new Error('provisional semantic metadata is required')
  requireImageFacts(ownerFacts, 'owner')
  requireImageFacts(dialogFacts, 'native dialog')
  return {
    ...provisional,
    owner_width: ownerFacts.width,
    owner_height: ownerFacts.height,
    owner_sha256: ownerFacts.sha256,
    native_dialog_width: dialogFacts.width,
    native_dialog_height: dialogFacts.height,
    native_dialog_sha256: dialogFacts.sha256,
  }
}

if (process.argv[2] === '--finalize') {
  const input = JSON.parse(readFileSync(0, 'utf8'))
  process.stdout.write(`${JSON.stringify(finalizeEvidence(input.provisional, input.ownerFacts, input.dialogFacts))}\n`)
}
