import type { QualityMode } from './providerContract'
import { isExecutionModel } from './localModelState'

export type ScoringRoleState = {
  selectedLocalProvider: string
  selectedLocalModel: string | null
  selectedCloudProvider: string | null
  selectedCloudModel: string | null
  qualityMode: QualityMode
}

export type ExecutionSelection = { provider: string; model: string | undefined }

export function executionSelection(state: ScoringRoleState): ExecutionSelection {
  const local = state.qualityMode === 'private'
  return {
    provider: local ? state.selectedLocalProvider : state.selectedCloudProvider ?? '',
    model: isExecutionModel(local ? state.selectedLocalModel : state.selectedCloudModel) ? (local ? state.selectedLocalModel ?? undefined : state.selectedCloudModel ?? undefined) : undefined,
  }
}

export type CreateDisabledInput = {
  running?: boolean
  source: string
  qualityMode: QualityMode
  localModelId: string | null | undefined
  localModelReady: boolean
  localModelLoading?: boolean
  localModelError?: string | null
  cloudProvider?: string | null
  cloudModelId?: string | null
  cloudReady: boolean
}

export function createDisabledReason(input: CreateDisabledInput): string | null {
  if (input.running) return 'Creation is already running.'
  if (!input.source.trim()) return 'Add a video first.'
  if (input.qualityMode === 'private' && input.localModelLoading) return 'Checking local model readiness.'
  if (input.qualityMode === 'private' && input.localModelError) return 'Local model state needs a refresh.'
  if (input.qualityMode === 'private' && (!isExecutionModel(input.localModelId) || !input.localModelReady)) return 'Choose an installed local model.'
  if (input.qualityMode === 'balanced' && (!input.cloudProvider || !isExecutionModel(input.cloudModelId) || !input.cloudReady)) return 'Choose a cloud provider for Hybrid scoring.'
  if (input.qualityMode === 'best' && (!input.cloudProvider || !isExecutionModel(input.cloudModelId) || !input.cloudReady)) return 'Choose a configured cloud provider for Best Quality.'
  return null
}
