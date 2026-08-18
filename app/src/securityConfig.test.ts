import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const config = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src-tauri/tauri.conf.json'), 'utf8')
) as {
  app: { security: { csp: string | null; assetProtocol: { scope: string[] } } }
}

describe('desktop security configuration', () => {
  it('uses a restrictive CSP without wildcard or unsafe-eval sources', () => {
    expect(config.app.security.csp).toBeTruthy()
    expect(config.app.security.csp).not.toContain("'unsafe-eval'")
    expect(config.app.security.csp).not.toContain('*')
  })

  it('scopes assets to media directories rather than whole application state', () => {
    const scope = config.app.security.assetProtocol.scope
    expect(scope).toContain('$HOME/.publikclip/jobs/*/clips/**')
    expect(scope).toContain('$HOME/.publikclip/jobs/*/media*.mp4')
    expect(scope).toContain('$HOME/.publikclip/jobs/*/overlays/**')
    expect(scope).toContain('$HOME/.publikclip/ig_thumbs/**')
    expect(scope).not.toContain('$HOME/.publikclip/**')
    expect(scope.join('\n')).not.toMatch(/secrets|instagram\.json|diagnostics|models|bin/)
  })

  it('exposes no frontend source-path export primitive', () => {
    const api = readFileSync(resolve(process.cwd(), 'src/api.ts'), 'utf8')
    expect(api).toContain("invoke<string>('export_clip', { jobId, clip, title })")
    expect(api).not.toContain("{ path, title }")
  })
})
