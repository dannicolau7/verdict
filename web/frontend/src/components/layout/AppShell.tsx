import { NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/',        label: 'Run evaluation', exact: true },
  { to: '/diff',    label: 'Diff' },
  { to: '/history', label: 'History' },
]

function VerdictLogo() {
  return (
    <div className="flex items-center gap-2 px-5 py-5 select-none">
      {/* Signature mini-arc */}
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="7" stroke="#E2E8F0" strokeWidth="2.5" strokeLinecap="round"
          strokeDasharray="32 12" strokeDashoffset="8" />
        <path d="M4.05 14.5 A7 7 0 1 1 15.95 14.5"
          stroke="#6366F1" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      </svg>
      <span className="font-mono text-[15px] font-medium tracking-tight text-ink">verdict</span>
    </div>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      {/* Left nav */}
      <nav className="hidden md:flex w-[220px] flex-shrink-0 flex-col bg-white border-r border-line">
        <VerdictLogo />

        <div className="flex-1 px-3 py-2 space-y-0.5">
          {NAV_ITEMS.map(({ to, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ` +
                (isActive
                  ? 'bg-brand/8 text-brand'
                  : 'text-slate hover:bg-cloud hover:text-ink')
              }
            >
              {label}
            </NavLink>
          ))}
        </div>

        <div className="px-5 pb-5 mt-auto">
          <span className="text-xs text-slate/50 font-mono">v0.3.1</span>
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 min-w-0 bg-cloud">
        {children}
      </main>
    </div>
  )
}
