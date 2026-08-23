import { describe, expect, it } from 'vitest'
import { summarizeSetupQueue } from './setupState'

describe('setup queue aggregation', () => {
  it('reports complete only when every operation succeeds', () => {
    expect(summarizeSetupQueue(['success', 'success'], 0).state).toBe('complete')
  })

  it('reports partial failure when a later operation fails', () => {
    expect(summarizeSetupQueue(['success', 'failed', 'success'], 0)).toMatchObject({ state: 'partial_failure', completed: 2, failed: 1 })
  })

  it('reports failed when the first operation fails', () => {
    expect(summarizeSetupQueue(['failed'], 0).state).toBe('failed')
  })

  it('reports cancellation independently of successful earlier operations', () => {
    expect(summarizeSetupQueue(['success', 'cancelled'], 0).state).toBe('cancelled')
  })

  it('keeps an active queue running until the final terminal event', () => {
    expect(summarizeSetupQueue(['success'], 1).state).toBe('running')
  })
})
