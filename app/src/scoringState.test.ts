import { describe, expect, it } from 'vitest'
import { createDisabledReason, executionSelection } from './scoringState'

describe('scoring roles', () => {
  const selection = {
    selectedLocalProvider: 'clipgauge-local',
    selectedLocalModel: 'clipgauge-local/qwen3-1.7b-q8_0',
    selectedCloudProvider: 'groq',
    selectedCloudModel: 'openai/gpt-oss-20b',
  }

  it('preserves local discovery and cloud scoring roles', () => {
    expect(executionSelection({ ...selection, qualityMode: 'private' })).toEqual({ provider: 'clipgauge-local', model: 'clipgauge-local/qwen3-1.7b-q8_0' })
    expect(executionSelection({ ...selection, qualityMode: 'balanced' })).toEqual({ provider: 'groq', model: 'openai/gpt-oss-20b' })
    expect(executionSelection({ ...selection, qualityMode: 'best' })).toEqual({ provider: 'groq', model: 'openai/gpt-oss-20b' })
  })

  it('never returns presentation placeholders as execution models', () => {
    expect(executionSelection({ ...selection, selectedLocalModel: null, qualityMode: 'private' })).toEqual({ provider: 'clipgauge-local', model: undefined })
    expect(createDisabledReason({ source: 'C:\\Videos\\source.mp4', qualityMode: 'private', localModelId: null, localModelReady: false, cloudModelId: selection.selectedCloudModel, cloudReady: true })).toBe('Choose an installed local model.')
  })

  it('explains missing cloud setup while keeping modes selectable', () => {
    expect(createDisabledReason({ source: 'C:\\Videos\\source.mp4', qualityMode: 'balanced', localModelId: selection.selectedLocalModel, localModelReady: true, cloudModelId: null, cloudReady: false })).toBe('Choose a cloud provider for Hybrid scoring.')
    expect(createDisabledReason({ source: 'C:\\Videos\\source.mp4', qualityMode: 'best', localModelId: selection.selectedLocalModel, localModelReady: true, cloudModelId: selection.selectedCloudModel, cloudReady: false })).toBe('Choose a configured cloud provider for Best Quality.')
  })

})
