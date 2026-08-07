export function History() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16 flex flex-col items-center text-center gap-4">
      <div className="w-12 h-12 rounded-2xl bg-brand/10 flex items-center justify-center">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="8" stroke="#6366F1" strokeWidth="2" />
          <path d="M11 7v4l3 3" stroke="#6366F1" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
      <div>
        <h1 className="text-xl font-semibold text-ink">History</h1>
        <p className="text-sm text-slate mt-1 max-w-xs">
          Browse and compare past evaluation runs.
          Coming in a future release.
        </p>
      </div>
    </div>
  )
}
