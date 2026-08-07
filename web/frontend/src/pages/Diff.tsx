export function Diff() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-16 flex flex-col items-center text-center gap-4">
      <div className="w-12 h-12 rounded-2xl bg-brand/10 flex items-center justify-center">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
          <path d="M4 11h14M11 4l7 7-7 7" stroke="#6366F1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div>
        <h1 className="text-xl font-semibold text-ink">Diff</h1>
        <p className="text-sm text-slate mt-1 max-w-xs">
          Compare two adapter versions on the same test suite.
          Coming in a future release.
        </p>
      </div>
    </div>
  )
}
