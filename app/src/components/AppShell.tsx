import type { ReactNode } from 'react'
import {
  Bot,
  Clock3,
  HardDrive,
  Info,
  LifeBuoy,
  Menu,
  Play,
  Puzzle,
  ShieldCheck,
  X
} from 'lucide-react'
import type { JobSummary } from '../types'

export type AppSection = 'create' | 'sessions' | 'setup' | 'providers' | 'integrations' | 'privacy' | 'help' | 'about'

interface Props {
  active: AppSection
  onNavigate: (section: AppSection) => void
  jobs: JobSummary[]
  running?: boolean
  onOpenJob: (id: string) => void
  onResume: (id: string) => void
  onSupport: () => void
  children: ReactNode
}

const primary: Array<{ id: AppSection; label: string; hint: string; icon: typeof Play }> = [
  { id: 'create', label: 'Create', hint: 'Make vertical clips', icon: Play },
  { id: 'sessions', label: 'Sessions', hint: 'Open previous work', icon: Clock3 }
]

const workspace: Array<{ id: AppSection; label: string; hint: string; icon: typeof Play }> = [
  { id: 'setup', label: 'Setup & Storage', hint: 'Components and disk space', icon: HardDrive },
  { id: 'providers', label: 'AI Providers', hint: 'Choose where scoring runs', icon: Bot },
  { id: 'integrations', label: 'Integrations', hint: 'Pexels and Instagram', icon: Puzzle },
  { id: 'privacy', label: 'Privacy', hint: 'See what leaves this computer', icon: ShieldCheck }
]

const secondary: Array<{ id: AppSection; label: string; hint: string; icon: typeof Play }> = [
  { id: 'help', label: 'Help & Diagnostics', hint: 'Support bundle and troubleshooting', icon: LifeBuoy },
  { id: 'about', label: 'About', hint: 'Version, licenses, and notices', icon: Info }
]

function NavGroup({
  label,
  items,
  active,
  onNavigate
}: {
  label: string
  items: Array<{ id: AppSection; label: string; hint: string; icon: typeof Play }>
  active: AppSection
  onNavigate: (section: AppSection) => void
}) {
  return (
    <div className="nav-group">
      <p className="nav-group-label">{label}</p>
      <div className="nav-group-items">
        {items.map(({ id, label: itemLabel, hint, icon: Icon }) => (
          <button
            type="button"
            key={id}
            className={`nav-item ${active === id ? 'is-active' : ''}`}
            onClick={() => onNavigate(id)}
            aria-current={active === id ? 'page' : undefined}
            title={hint}
          >
            <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
            <span>{itemLabel}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function AppShell({ active, onNavigate, jobs, running, onOpenJob, onResume, onSupport, children }: Props) {
  return (
    <div className="app-shell">
      <input className="nav-drawer-toggle" id="nav-drawer-toggle" type="checkbox" aria-label="Toggle navigation" />
      <label className="mobile-nav-toggle" htmlFor="nav-drawer-toggle"><Menu size={19} aria-hidden="true" /><span>Menu</span></label>
      <aside className="app-sidebar">
        <div className="sidebar-topline">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true"><span /></span>
            <div><strong>ClipGauge</strong><small>make moments worth sharing</small></div>
          </div>
          <label className="mobile-nav-close" htmlFor="nav-drawer-toggle"><X size={19} aria-hidden="true" /><span>Close</span></label>
        </div>
        <nav className="app-nav" aria-label="Main navigation">
          <NavGroup label="Workspace" items={primary} active={active} onNavigate={onNavigate} />
          <NavGroup label="Manage" items={workspace} active={active} onNavigate={onNavigate} />
          <NavGroup label="Support" items={secondary} active={active} onNavigate={onNavigate} />
        </nav>
        <div className="sidebar-sessions">
          <div className="sidebar-section-head"><span>Recent sessions</span><button type="button" onClick={() => onNavigate('sessions')}>See all</button></div>
          {jobs.length === 0 ? <p className="sidebar-empty">Your finished clips will appear here.</p> : jobs.slice(0, 3).map((job) => (
            <button type="button" key={job.id} className="sidebar-session" onClick={() => job.rendered ? onOpenJob(job.id) : onResume(job.id)} disabled={running}>
              <span className={`session-status ${job.rendered ? 'ready' : 'partial'}`} aria-hidden="true" />
              <span><strong>{job.title ?? 'Untitled video'}</strong><small>{job.rendered ? 'Ready to review' : 'Continue setup'}</small></span>
            </button>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="privacy-prompt"><ShieldCheck size={16} aria-hidden="true" /><span><strong>Local-first by default</strong><small>You choose what leaves this computer.</small></span></div>
          <button type="button" className="sidebar-support" onClick={onSupport}><LifeBuoy size={15} aria-hidden="true" /> Get help</button>
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  )
}
