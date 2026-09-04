import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const capability = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src-tauri/capabilities/default.json'), 'utf8'),
) as { permissions: string[] }
const exportSource = readFileSync(
  resolve(process.cwd(), 'src/exportDestination.ts'),
  'utf8',
)

describe('native export capability contract', () => {
  it('grants only the permission required by the Save As implementation', () => {
    expect(exportSource).toMatch(/import\s*{\s*save\s*}\s*from\s*['"]@tauri-apps\/plugin-dialog['"]/
    )
    expect(exportSource).toContain('save({')
    expect(capability.permissions).toContain('dialog:allow-save')
    expect(capability.permissions).not.toContain('dialog:default')
    expect(capability.permissions).not.toEqual(expect.arrayContaining([
      'fs:allow-write-file',
      'fs:allow-write',
      'fs:default',
    ]))
  })
})
