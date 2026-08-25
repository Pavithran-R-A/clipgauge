export type CreatorRunState = 'IDLE' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'

const HEADLINES: Record<CreatorRunState, string> = {
  IDLE: 'Choose a video to begin.',
  RUNNING: 'Finding the moments worth sharing.',
  SUCCEEDED: 'Your clips are ready to review.',
  FAILED: "We couldn't create clips.",
  CANCELLED: 'Clip creation was cancelled.'
}

export function creatorHeadline(state: CreatorRunState): string {
  return HEADLINES[state]
}

export function providerHelperCopy(provider: string): string {
  switch (provider) {
    case 'clipgauge-local':
      return 'Runs on this computer. No API key required.'
    case 'openrouter':
      return 'Uses your OpenRouter connection and current free-route availability.'
    case 'gemini':
      return 'Uses your Gemini connection for scoring.'
    case 'groq':
      return 'Uses your Groq connection for scoring.'
    case 'ollama':
    case 'lmstudio':
      return 'Runs through your local app.'
    default:
      return 'Uses the selected AI provider for scoring.'
  }
}

export function sourceKind(source: string): 'youtube' | 'local' {
  return /^https?:\/\/(?:www\.)?(?:youtube\.com|youtu\.be)\//i.test(source.trim()) ? 'youtube' : 'local'
}
