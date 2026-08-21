export interface PipelineEvent {
  event: string
  protocol_version?: number
  stage?: string
  stage_id?: string
  display_stage?: string
  operation?: string
  fraction?: number
  indeterminate?: boolean
  message?: string
  elapsed_seconds?: number
  stage_elapsed_seconds?: number
  eta_seconds?: number
  bytes_done?: number
  bytes_total?: number
  bytes_per_second?: number
  accelerator?: string
  one_time_download?: boolean
  job_id?: string
  ok?: boolean
  code?: string
  error?: string
  retryable?: boolean
  diagnostic_id?: string
  exit_code?: number | null
  [key: string]: unknown
}

export interface StageProgress {
  fraction: number
  message: string
  displayStage?: string
  operation?: string
  indeterminate?: boolean
  elapsedSeconds?: number
  stageElapsedSeconds?: number
  etaSeconds?: number
  bytesDone?: number
  bytesTotal?: number
  bytesPerSecond?: number
  accelerator?: string
  oneTimeDownload?: boolean
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

export type CapabilityValue = boolean | null

export interface ProviderCapabilities {
  text: CapabilityValue
  structured_json: CapabilityValue
  json_schema: CapabilityValue
  vision: CapabilityValue
  model_listing: CapabilityValue
  local: CapabilityValue
  cloud: CapabilityValue
  streaming?: CapabilityValue
  context_window?: number | null
  max_images?: number | null
}

export interface ProviderProfile {
  id: string
  kind: string
  display_name: string
  model: string
  endpoint_identity?: string
  locality: 'local' | 'cloud' | string
  auth_strategy?: string
  capabilities?: ProviderCapabilities
}

export interface ProviderTestResult {
  state: 'PASS' | 'WARNING' | 'FAIL'
  provider?: string
  model?: string
  code?: string
  message?: string
  models?: string[]
  capabilities?: Record<string, unknown>
  degraded_signals?: string[]
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
    provider_profile_id?: string
    provider_kind?: string
    endpoint_identity?: string
    capabilities?: ProviderCapabilities
    structured_level?: string
    degraded_signals?: string[]
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
  score: { clips: Clip[]; llm_mode: string; model: string; scored_count: number; provider_profile_id?: string; provider_kind?: string; capabilities?: ProviderCapabilities } | null
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
    model?: string
    endpoint?: string
  }
  instagram: string
  source: string
}

export interface PreflightStorage {
  required_bytes: number
  optional_bytes?: number
  available_bytes?: number | null
  consent_required: boolean
  assets: Array<Record<string, unknown>>
}

export interface PreflightResult {
  state: 'ready' | 'warning' | 'blocked'
  selected_llm: string
  checks: PreflightCheck[]
  provider?: ProviderProfile
  hardware?: Record<string, unknown>
  storage?: PreflightStorage
}

export interface ManagedAssetRow {
  asset_id: string
  display_name: string
  purpose: string
  destination: string
  url: string
  size_bytes: number
  required: boolean
  one_time: boolean
  license: string
  source: string
  consent_group: string
  installed?: boolean
  cached?: boolean
  status?: string
  state?: string
  installed_sha256?: string | null
  managed_path?: string
  consent_granted?: boolean
}

export interface SetupProgressEvent {
  event?: string
  asset_id?: string
  display_name?: string
  operation?: string
  bytes_done?: number
  bytes_total?: number | null
  bytes_per_second?: number
  fraction?: number | null
  eta_seconds?: number | null
  elapsed_seconds?: number
  one_time_download?: boolean
  cached?: boolean
  state?: string
  status?: string
  code?: string
  ok?: boolean
  message?: string
}

export interface LocalSetupInventory {
  state: 'ready' | 'setup-required' | string
  runtime: Record<string, unknown> & { installed?: boolean; display_name?: string; size_bytes?: number }
  models: Array<Record<string, unknown> & { asset_id?: string; installed?: boolean; display_name?: string; size_bytes?: number; license?: string }>
  core_assets: Array<Record<string, unknown> & { asset_id?: string; installed?: boolean; display_name?: string; purpose?: string; integrity?: string; license?: string }>
  managed_assets?: ManagedAssetRow[]
  storage: PreflightStorage
  catalog: Array<Record<string, unknown>>
}

export interface SetupState {
  has_gemini_key: boolean
  onboarded: boolean
  provider_keys?: Record<string, boolean>
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
