import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const config = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src-tauri/tauri.conf.json'), 'utf8')
) as {
  app: { security: { csp: string | null; devCsp: string | null; assetProtocol: { scope: string[] } } }
}

describe('desktop security configuration', () => {
  it('uses a restrictive production CSP with the exact Tauri IPC and asset origins', () => {
    const csp = config.app.security.csp ?? ''
    expect(csp).toContain('ipc:')
    expect(csp).toContain('http://ipc.localhost')
    expect(csp).toContain('asset:')
    expect(csp).toContain('http://asset.localhost')
    expect(csp).toMatch(/img-src[^;]*asset:[^;]*http:\/\/asset\.localhost/)
    expect(csp).toMatch(/media-src[^;]*asset:[^;]*http:\/\/asset\.localhost/)
    expect(csp).toContain('http://127.0.0.1:*')
    expect(csp).not.toContain('localhost:1430')
    expect(csp).not.toContain('ws://localhost:1430')
    expect(csp).not.toContain("'unsafe-eval'")
    expect(csp).not.toMatch(/(?:^|[\s;])\*(?:[\s;]|$)/)
  })

  it('keeps Vite and HMR origins in development CSP only', () => {
    const devCsp = config.app.security.devCsp ?? ''
    expect(devCsp).toContain('http://localhost:1430')
    expect(devCsp).toContain('ws://localhost:1430')
    expect(devCsp).toContain('http://ipc.localhost')
    expect(devCsp).toContain('http://asset.localhost')
    expect(devCsp).not.toContain("'unsafe-eval'")
    expect(devCsp).not.toMatch(/(?:^|[\s;])\*(?:[\s;]|$)/)
  })

  it('scopes assets to media directories rather than whole application state', () => {
    const scope = config.app.security.assetProtocol.scope
    expect(scope).toContain('$HOME/.clipgauge/jobs/*/clips/**/*')
    expect(scope).toContain('$HOME/.clipgauge/jobs/*/media*.mp4')
    expect(scope).toContain('$HOME/.clipgauge/jobs/*/overlays/**/*')
    expect(scope).toContain('$HOME/.clipgauge/ig_thumbs/**/*')
    expect(scope).not.toContain('$HOME/.clipgauge/**')
    expect(scope.join('\n')).not.toMatch(/secrets|instagram\.json|diagnostics|models|bin/)
  })

  it('exposes no frontend source-path export primitive', () => {
    const api = readFileSync(resolve(process.cwd(), 'src/api.ts'), 'utf8')
    const exportDestination = readFileSync(resolve(process.cwd(), 'src/exportDestination.ts'), 'utf8')
    const artifact = readFileSync(resolve(process.cwd(), 'src-tauri/src/artifact.rs'), 'utf8')
    const main = readFileSync(resolve(process.cwd(), 'src-tauri/src/main.rs'), 'utf8')
    expect(api).toContain("invoke<string>('export_clip', { jobId, clip, title, destination })")
    expect(api).not.toMatch(/exportClip\([^)]*path/)
    expect(api).not.toContain('{ path, title }')
    expect(exportDestination).toContain("save({")
    expect(exportDestination).toContain('defaultPath:')
    expect(exportDestination).toContain('filters: [{ name: \'MP4 video\', extensions: [\'mp4\'] }]')
    expect(artifact).toContain('pub fn export_clip_to(')
    expect(artifact).toContain('render_artifact(home, job_id, clip)')
    expect(artifact).toContain('destination cannot overwrite the managed source artifact')
    expect(main).toMatch(/async fn export_clip\(\s*job_id: String,\s*clip: u32,\s*title: Option<String>,\s*destination: Option<String>/s)
    expect(main).toContain('artifact::export_clip_to')
    expect(main).not.toContain('fs::copy(Path::new(&source)')
  })
})
