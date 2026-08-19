import { invoke, convertFileSrc } from '@tauri-apps/api/core'
import type { JobResults, JobSummary, LoopOverview, PreflightResult, SaveClipEditsInput, SetupState, SyncSummary } from './types'

export const api = {
  preflight: (llm: string) => invoke<PreflightResult>('preflight', { llm }),
  runJob: (source: string, llm: string, captions: string) =>
    invoke<void>('run_job', { source, llm, captions }),
  resumeJob: (jobId: string, llm?: string, captions?: string, camera?: string) =>
    invoke<void>('resume_job', { jobId, llm, captions, camera }),
  cancelJob: (jobId: string) => invoke<void>('cancel_job', { jobId }),
  jobResults: (jobId: string) => invoke<JobResults>('job_results', { jobId }),
  listJobs: () => invoke<JobSummary[]>('list_job_dirs'),
  saveGeminiKey: (key: string) => invoke<boolean>('save_gemini_key', { key }),
  setupState: () => invoke<SetupState>('get_setup_state'),
  markOnboarded: () => invoke<void>('mark_onboarded'),
  checkOllama: () => invoke<{ state: 'service-stopped' | 'model-missing' | 'service-healthy'; running: boolean; models: string[]; message?: string }>('check_ollama'),
  saveClipEdits: (jobId: string, input: SaveClipEditsInput) => invoke<void>('save_clip_edits', { jobId, input }),
  exportClip: (jobId: string, clip: number, title?: string) =>
    invoke<string>('export_clip', { jobId, clip, title }),
  igStatus: () => invoke<{ connected: boolean; username?: string }>('ig_status'),
  igSync: () => invoke<SyncSummary>('ig_tool', { args: ['sync'] }),
  igOverview: () => invoke<LoopOverview>('ig_tool', { args: ['overview'] }),
  igLink: (jobId: string, clip: number, mediaId: string, source: 'manual' | 'match_confirmed') =>
    invoke<{ ok: boolean }>('ig_tool', {
      args: ['link', jobId, String(clip), mediaId, '--source', source]
    }),
  igUnlink: (mediaId: string) =>
    invoke<{ ok: boolean }>('ig_tool', { args: ['unlink', mediaId] }),
  igReject: (mediaId: string, jobId: string, clip: number) =>
    invoke<{ ok: boolean }>('ig_tool', { args: ['reject', mediaId, jobId, String(clip)] }),
  fileUrl: (path: string) => convertFileSrc(path)
}
