import type { StageProgress } from './types'

const MACROS = [
  { id: 'prepare', label: 'Preparing video', stages: ['ingest', 'asr', 'diarize'] },
  { id: 'find', label: 'Finding moments', stages: ['events', 'candidates', 'score'] },
  { id: 'finish', label: 'Finishing clips', stages: ['enrich', 'collections', 'camera', 'render'] },
] as const

export type ProgressMacroState = 'pending' | 'active' | 'done' | 'failed'

export function progressMacros(stages: Record<string, StageProgress>, running: boolean, failed: boolean) {
  let previousComplete = true
  return MACROS.map((macro) => {
    const completed = macro.stages.filter((stage) => stages[stage]?.fraction >= 1).length
    const touched = macro.stages.some((stage) => stages[stage])
    const active = macro.stages.some((stage) => stages[stage] && stages[stage].fraction < 1)
    const state: ProgressMacroState = failed && active ? 'failed' : completed === macro.stages.length ? 'done' : active || (running && previousComplete && !touched) ? 'active' : 'pending'
    previousComplete = completed === macro.stages.length
    return { ...macro, state, completed, total: macro.stages.length }
  })
}
