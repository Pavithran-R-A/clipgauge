function errorCode(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = (error as { code?: unknown }).code
    return typeof code === 'string' ? code : ''
  }
  return ''
}

export function friendlyErrorMessage(error: unknown, fallback: string): string {
  const code = errorCode(error).toUpperCase()
  if (code.includes('TIMEOUT')) return `${fallback} The request timed out.`
  if (code.includes('CANCEL')) return `${fallback} The request was cancelled.`
  return fallback
}
