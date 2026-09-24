import { describe, expect, it } from 'vitest'
import { progressMacros } from './progressPresentation'

describe('progressMacros', () => {
  it('collapses internal stages into creator phases', () => {
    const phases = progressMacros({ ingest: { fraction: 1, message: 'done' }, asr: { fraction: 0.4, message: 'working' } }, true, false)
    expect(phases.map((phase) => phase.label)).toEqual(['Preparing video', 'Finding moments', 'Finishing clips'])
    expect(phases[0].state).toBe('active')
    expect(phases[1].state).toBe('pending')
  })

  it('marks the active failed phase clearly', () => {
    const phases = progressMacros({ ingest: { fraction: 0.2, message: 'failed' } }, false, true)
    expect(phases[0].state).toBe('failed')
  })
})
