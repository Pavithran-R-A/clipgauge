import { beforeEach, describe, expect, it, vi } from 'vitest'

const { saveMock, exportClipMock } = vi.hoisted(() => ({
  saveMock: vi.fn(),
  exportClipMock: vi.fn(),
}))

vi.mock('@tauri-apps/plugin-dialog', () => ({
  save: saveMock,
}))

vi.mock('./api', () => ({
  api: {
    exportClip: exportClipMock,
  },
}))

import { chooseExportDestination } from './exportDestination'

describe('chooseExportDestination', () => {
  beforeEach(() => {
    saveMock.mockReset()
    exportClipMock.mockReset()
  })

  it('opens a native Save As dialog and exports to the chosen MP4 path', async () => {
    saveMock.mockResolvedValue('C:\\Users\\tester\\Videos\\My clip.mp4')
    exportClipMock.mockResolvedValue('C:\\Users\\tester\\Videos\\My clip.mp4')

    const exported = await chooseExportDestination({
      jobId: '20260831-120000-abcdef',
      clip: 2,
      suggestedTitle: 'My clip 5:55',
    })

    expect(saveMock).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Save ClipGauge clip',
      filters: [{ name: 'MP4 video', extensions: ['mp4'] }],
    }))
    expect(exportClipMock).toHaveBeenCalledWith(
      '20260831-120000-abcdef',
      2,
      'My clip 5:55',
      'C:\\Users\\tester\\Videos\\My clip.mp4',
    )
    expect(exported).toBe('C:\\Users\\tester\\Videos\\My clip.mp4')
  })

  it('does not copy anything when the Save As dialog is cancelled', async () => {
    saveMock.mockResolvedValue(null)

    const exported = await chooseExportDestination({
      jobId: '20260831-120000-abcdef',
      clip: 2,
      suggestedTitle: 'My clip 5:55',
    })

    expect(exportClipMock).not.toHaveBeenCalled()
    expect(exported).toBeNull()
  })
})
