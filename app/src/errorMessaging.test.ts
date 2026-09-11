import { describe, expect, it } from 'vitest'

import { friendlyErrorMessage } from './errorMessaging'

describe('friendlyErrorMessage', () => {
  it('never exposes raw error text', () => {
    expect(friendlyErrorMessage(new Error('token=secret-value'), 'Retry the action.')).toBe('Retry the action.')
    expect(friendlyErrorMessage('provider response included secret-value', 'Retry the action.')).toBe('Retry the action.')
  })

  it('keeps timeout guidance actionable without exposing details', () => {
    expect(friendlyErrorMessage({ code: 'REQUEST_TIMEOUT', message: 'secret-value' }, 'Retry the action.')).toBe('Retry the action. The request timed out.')
  })
})
