import { convertFileSrc, invoke } from '@tauri-apps/api/core'
import type { JobResults, JobSummary, LoopOverview, PreflightResult, PrivacySummary, SaveClipEditsInput, SetupState, SyncSummary, ProviderTestResult } from './types'

function legacyMode(provider: string): string | undefined {
  return provider === 'gemini' || provider === 'ollama' ? provider : undefined
}

type ProviderOptions = {
  model?: string
  endpoint?: string
  auth?: string
  secretHeader?: string
}

export const api = {
  preflight: (provider: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string) =>
    invoke<PreflightResult>('preflight', { llm: legacyMode(provider), provider, model, endpoint, auth, secret_header: secretHeader }),
  privacySummary: (provider: string, model?: string, endpoint?: string) =>
    invoke<PrivacySummary>('privacy_summary', { llm: legacyMode(provider), provider, model, endpoint }),
  generateSupportBundle: (jobId?: string, diagnosticId?: string) => invoke<string>('generate_support_bundle', { jobId, diagnosticId }),
  runJob: (source: string, provider: string, captions: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string) =>
    invoke<void>('run_job', {
      request: { source, llm: legacyMode(provider), provider, model, endpoint, auth, secret_header: secretHeader, captions },
    }),
  resumeJob: (jobId: string, provider?: string, captions?: string, camera?: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string) =>
    invoke<void>('resume_job', {
      request: { job_id: jobId, llm: provider ? legacyMode(provider) : undefined, provider, model, endpoint, auth, secret_header: secretHeader, captions, camera },
    }),
  testConnection: (provider: string, model?: string, endpoint?: string, auth?: string, secretHeader?: string) =>
    invoke<ProviderTestResult>('test_connection', { llm: legacyMode(provider), provider, model, endpoint, auth, secret_header: secretHeader }),
  saveProviderKey: (profileId: string, key: string) => invoke<boolean>('save_provider_key', { profileId, key }),
  cancelJob: (jobId: string) => invoke<void>('cancel_job', { jobId }),
  jobResults: (jobId: string) => invoke<JobResults>('job_results', { jobId }),
  listJobs: () => invoke<JobSummary[]>('list_job_dirs'),
  saveGeminiKey: (key: string) => invoke<boolean>('save_gemini_key', { key }),
  setupState: () => invoke<SetupState>('get_setup_state'),
  markOnboarded: () => invoke<void>('mark_onboarded'),
  checkOllama: () => invoke<{ state: 'service-stopped' | 'model-missing' | 'service-healthy'; running: boolean; models: string[]; message?: string }>('check_ollama'),
  saveClipEdits: (jobId: string, input: SaveClipEditsInput) => invoke<void>('save_clip_edits', { jobId, input }),
  exportClip: (jobId: string, clip: number, title?: string) => invoke<string>('export_clip', { jobId, clip, title }),
  igStatus: () => invoke<{ connected: boolean; username?: string }>('ig_status'),
  igSync: () => invoke<SyncSummary>('ig_tool', { args: ['sync'] }),
  igOverview: () => invoke<LoopOverview>('ig_tool', { args: ['overview'] }),
  igLink: (jobId: string, clip: number, mediaId: string, source: 'manual' | 'match_confirmed') =>
    invoke<{ ok: boolean }>('ig_tool', { args: ['link', jobId, String(clip), mediaId, '--source', source] }),
  igUnlink: (mediaId: string) => invoke<{ ok: boolean }>('ig_tool', { args: ['unlink', mediaId] }),
  igReject: (mediaId: string, jobId: string, clip: number) => invoke<{ ok: boolean }>('ig_tool', { args: ['reject', mediaId, jobId, String(clip)] }),
  fileUrl: (path: string) => convertFileSrc(path)
}

export type { ProviderOptions }
