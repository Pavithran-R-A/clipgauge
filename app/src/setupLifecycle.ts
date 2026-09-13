export type SetupLoadPhase = 'loading' | 'ready' | 'error'

export interface SetupLoadState<T> {
  phase: SetupLoadPhase
  value?: T
  message?: string
}

export function setupPhaseLabel(phase: SetupLoadPhase): string {
  if (phase === 'loading') return 'Loading setup information…'
  if (phase === 'ready') return 'Setup information ready.'
  return 'Setup information unavailable.'
}

function errorCode(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    return String(error.code)
  }
  return ''
}

export function loadErrorMessage(error: unknown): string {
  const code = errorCode(error)
  if (code.includes('PIPELINE_NOT_INITIALIZED')) {
    return 'ClipGauge is preparing its local runtime. Retry shortly.'
  }
  if (code.includes('TIMED_OUT') || code.includes('TIMEOUT')) {
    return 'Setup information timed out. Retry the check.'
  }
  return 'Setup information is temporarily unavailable.'
}
