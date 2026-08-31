import { save } from '@tauri-apps/plugin-dialog'
import { api } from './api'

type ExportDestinationInput = {
  jobId: string
  clip: number
  suggestedTitle: string
}

function safeFilenameStem(title: string): string {
  const cleaned = title
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 100)
  return cleaned || 'clipgauge-clip'
}

export async function chooseExportDestination({
  jobId,
  clip,
  suggestedTitle,
}: ExportDestinationInput): Promise<string | null> {
  const destination = await save({
    title: 'Save ClipGauge clip',
    defaultPath: `${safeFilenameStem(suggestedTitle)}.mp4`,
    filters: [{ name: 'MP4 video', extensions: ['mp4'] }],
  })
  if (!destination) return null
  return api.exportClip(jobId, clip, suggestedTitle, destination)
}
