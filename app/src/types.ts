export interface PipelineEvent {
  event: string
  protocol_version?: number
  stage?: string
  fraction?: number
  message?: string
  job_id?: string
  ok?: boolean
  code?: string
  error?: string
  retryable?: boolean
  diagnostic_id?: string
  exit_code?: number | null
  [key: string]: unknown
}

export interface Adjustment {
  rule: string
  factor: number
  reason: string
}

export interface MusicBrief {
  genre: string
  instruments: string[]
  mood: string
  theme: string
  energy: string
  bpm_range: string
  duck_intensity: string
  mood_prior?: string
  alternatives: { genre: string; mood: string; bpm_range: string }[]
}

export interface ClipLedger {
  score: number
  composition: {
    subscores: Record<string, number>
    curve_score: number
    arousal_pct: number
    heatmap_pct: number | null
    visual_evidence: boolean
  }
  platform_scores: Record<string, number>
  adjustments: Adjustment[]
  signals_fired: string[]
  signals_missing: string[]
  provenance: {
    llm_mode: string
    model: string
    scoring_config_version: number
    arousal_source: string
    visual_pass: boolean
  }
}

export interface Clip {
  start: number
  end: number
  score: number
  best_platform: string
  platform_scores: Record<string, number>
  subscores: Record<string, number>
  adjustments: Adjustment[]
  signals_fired: string[]
  signals_missing: string[]
  confidence: string
  summary: string
  arousal_pct: number
  heatmap_pct: number | null
  curve_score: number
  music: MusicBrief | null
  t1_raw?: Record<string, unknown>
  ledger?: ClipLedger
}

export type ArtifactStatus =
  | 'available'
  | 'missing'
  | 'invalid'
  | 'outside_managed_root'
  | 'unreadable'

export interface RenderOutput {
  clip: number
  path: string | null
  artifact_status?: ArtifactStatus
  score: number
  best_platform: string
  duration: number
  words: number
  event_tags: number
}

export interface JobResults {
  job_id: string
  dir?: string
  ingest: {
    title: string
    heatmap: unknown[] | null
    probe: { duration_sec: number; width: number; height: number }
  } | null
  score: { clips: Clip[]; llm_mode: string; model: string; scored_count: number } | null
  render: { outputs: RenderOutput[]; emoji_ok: boolean; caption_preset: string } | null
  events: { counts: Record<string, number>; timeline: unknown[]; arousal_source: string } | null
  candidates: { count: number; effective_weights: Record<string, number>; heatmap_present: boolean } | null
}

export interface ClipEditOverlay {
  id: string
  query: string
  source: 'pexels' | 'gemini' | 'upload'
  image_path: string
  start: number
  end: number
  x: number
  y: number
  scale: number
  animation: 'none' | 'pop' | 'ping'
  phrase: string
}

export interface ClipEdit {
  start: number
  end: number
  caption_preset?: 'classic' | 'bold' | 'karaoke' | null
  camera_mode?: 'cut' | 'pan' | 'locked' | null
  remove_dead_space: boolean
  disabled_cuts: number[]
  overlays: ClipEditOverlay[]
}

export interface SaveClipEditsInput {
  clip: number
  edit: ClipEdit
}

export interface JobSummary {
  id: string
  title: string | null
  ingested: boolean
  rendered: boolean
  lifecycle_state?: string
  last_stage?: string | null
  resume_safe?: boolean
}

export interface PreflightCheck {
  name: string
  state: 'ready' | 'warning' | 'blocked'
  message: string
  remediation?: string
  details?: Record<string, unknown>
}

export interface PrivacySummary {
  local_first: boolean
  telemetry: string
  llm: {
    mode: string
    device: string[]
    network: string[]
    provider: string
  }
  instagram: string
  source: string
}

export interface PreflightResult {
  state: 'ready' | 'warning' | 'blocked'
  selected_llm: string
  checks: PreflightCheck[]
}

export interface SetupState {
  has_gemini_key: boolean
  onboarded: boolean
}

/* ---------- the Instagram loop ---------- */

export interface LoopMetrics {
  views?: number | null
  reach?: number | null
  likes?: number | null
  comments?: number | null
  saved?: number | null
  shares?: number | null
  reposts?: number | null
  total_interactions?: number | null
  ig_reels_avg_watch_time?: number | null
  ig_reels_video_view_total_time?: number | null
  reels_skip_rate?: number | null
}

export interface LoopLinked {
  job_id: string
  clip_index: number
  media_id: string | null
  link_source: string
  linked_at: number
  score: number
  reels_score: number
  config_version: number
  subscores: Record<string, number> | null
  adjustments: Adjustment[] | null
  signals_fired: string[] | null
  signals_missing: string[] | null
  summary: string
  clip_duration: number | null
  clip_thumb: string | null
  ig_thumb: string | null
  permalink: string | null
  caption: string | null
  posted_at: number | null
  media_deleted: boolean
  media_age_hours: number | null
  settling: boolean
  metrics: LoopMetrics | null
  snapshots: { age_hours: number | null; views: number | null }[]
  snapshot_count: number
}

export interface LoopSuggestion {
  media_id: string
  job_id: string
  clip_index: number
  confidence: number
  clip_summary: string
  clip_duration: number | null
  clip_thumb: string | null
  clip_reels_score: number | null
}

export interface LoopUnlinked {
  media_id: string
  thumb: string | null
  permalink: string | null
  caption: string
  posted_at: number | null
  duration_s: number | null
  copyright_flagged: boolean
  suggestion: LoopSuggestion | null
}

export interface LoopClip {
  job_id: string
  clip_index: number
  summary: string
  duration: number | null
  reels_score: number | null
  thumb: string | null
  linked: boolean
}

export interface CalibrationVersion {
  version: number
  constants: Record<string, number>
  fitted_from_n?: number | null
  spearman_rho?: number | null
  pairwise_acc?: number | null
  note?: string | null
  created_at?: number | null
}

export interface LoopReport {
  pairs: number
  ready: boolean
  note?: string
  spearman_rho?: number | null
  pairwise_accuracy?: number | null
  kendall_tau?: number | null
}

export interface LoopOverview {
  connected: boolean
  username: string | null
  last_synced_at: number | null
  linked: LoopLinked[]
  unlinked: LoopUnlinked[]
  clip_library: LoopClip[]
  report: LoopReport
  calibration: {
    active: CalibrationVersion
    history: CalibrationVersion[]
    qualifying_outcomes: number
    recomputable_outcomes: number
    threshold: number
  }
}

export interface SyncSummary {
  ok: boolean
  error?: string
  username?: string
  new_media?: number
  thumbs_cached?: number
  snapshots_pulled?: number
  tombstoned?: number
  fit?: { applied: boolean; version?: number; reason?: string }
}
