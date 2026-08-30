import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const hookPath = join(repoRoot, 'app', 'src-tauri', 'windows', 'hooks.nsh')
const configPath = join(repoRoot, 'app', 'src-tauri', 'tauri.conf.json')

describe('Windows uninstall cleanup contract', () => {
  it('registers the scoped NSIS hook', () => {
    const config = JSON.parse(readFileSync(configPath, 'utf8')) as {
      bundle?: { windows?: { nsis?: { installerHooks?: string } } }
    }
    const hook = readFileSync(hookPath, 'utf8')

    expect(config.bundle?.windows?.nsis?.installerHooks).toBe('./windows/hooks.nsh')
    expect(hook).toContain('!macro NSIS_HOOK_POSTUNINSTALL')
    expect(hook).toContain('RMDir /r "$INSTDIR\\resources"')
    expect(hook).toContain('RMDir "$INSTDIR"')
    expect(hook).not.toContain('$APPDATA\\.clipgauge')
    expect(hook).not.toContain('$LOCALAPPDATA\\ClipGauge')
  })
})
