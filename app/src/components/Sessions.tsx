import { AlertTriangle, Clock3, FolderOpen, MoreHorizontal, Play, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import type { JobSummary } from '../types'
import { sessionPresentation } from '../sessionPresentation'

interface Props {
  jobs: JobSummary[]
  onBack: () => void
  onOpenJob: (id: string) => void
  onResume: (id: string) => void
  onRefresh?: () => void
}

function SessionCard({ job, onOpenJob, onResume, onRefresh }: Omit<Props, 'jobs' | 'onBack'> & { job: JobSummary }) {
  const view = sessionPresentation(job)
  const [menuOpen, setMenuOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function deleteFailedSession() {
    setMenuOpen(false)
    setError(null)
    setDeleting(true)
    try {
      const preview = await api.storagePreview('failed-session', job.id)
      const confirmed = window.confirm(`Remove this failed session? ${preview.bytes.toLocaleString()} bytes will be released. User files outside ClipGauge stay untouched.`)
      if (!confirmed) return
      await api.storageCleanup('failed-session', job.id)
      onRefresh?.()
    } catch {
      setError('The failed session could not be removed.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <article className={`session-row card-surface ${view.ready ? 'session-row-ready' : 'session-row-stopped'}`}>
      <span className={`session-status large ${view.ready ? 'ready' : 'partial'}`} aria-hidden="true" />
      <div className="session-copy">
        <div className="session-kicker"><span>{job.source_label || (job.source_type === 'file' ? 'Local video' : 'Online video')}</span><span>#{job.id.slice(-6)}</span></div>
        <h2>{view.title}</h2>
        <p><Clock3 size={14} aria-hidden="true" /> {view.state}</p>
        <p className="session-detail">{view.detail}</p>
        {error && <p className="session-error" role="alert"><AlertTriangle size={14} aria-hidden="true" /> {error}</p>}
      </div>
      <div className="session-actions">
        {view.action === 'Resume' ? <button type="button" className="button button-secondary" onClick={() => onResume(job.id)} disabled={deleting}><RotateCcw size={15} aria-hidden="true" /> Resume</button> : <button type="button" className="button button-primary" onClick={() => onOpenJob(job.id)}><Play size={15} aria-hidden="true" /> {view.action}</button>}
        {!view.ready && <div className="session-menu-wrap"><button type="button" className="icon-button" aria-label={`Session actions for ${view.title}`} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><MoreHorizontal size={18} aria-hidden="true" /></button>{menuOpen && <div className="session-menu" role="menu"><button type="button" role="menuitem" onClick={() => void deleteFailedSession()} disabled={deleting}><Trash2 size={15} aria-hidden="true" /> {deleting ? 'Removing…' : 'Remove failed session'}</button></div>}</div>}
      </div>
    </article>
  )
}

export default function Sessions({ jobs, onBack, onOpenJob, onResume, onRefresh }: Props) {
  return <div className="page-frame sessions-page"><header className="page-header"><div><p className="section-eyebrow">Sessions</p><h1>Your recent work.</h1><p className="page-lede">Open finished clips or resume stopped analysis.</p></div><button type="button" className="button button-primary" onClick={onBack}><Play size={16} fill="currentColor" aria-hidden="true" /> Create new clips</button></header>{jobs.length === 0 ? <section className="empty-sessions card-surface"><span className="empty-icon"><FolderOpen size={24} aria-hidden="true" /></span><h2>No sessions yet</h2><p>Each video stays here for later review.</p><button type="button" className="button button-primary" onClick={onBack}>Add your first video</button></section> : <div className="session-list">{jobs.map((job) => <SessionCard key={job.id} job={job} onOpenJob={onOpenJob} onResume={onResume} onRefresh={onRefresh} />)}</div>}</div>
}
