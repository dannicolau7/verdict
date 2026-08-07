interface FailureModeTagsProps {
  failureModes: Record<string, number>
}

const HIGH_SEVERITY = new Set(['prompt_injection_success', 'pii_leak', 'compliance_when_should_refuse'])

function fmt(mode: string) {
  return mode.replace(/_/g, ' ')
}

export function FailureModeTags({ failureModes }: FailureModeTagsProps) {
  const entries = Object.entries(failureModes)
    .filter(([, n]) => n > 0)
    .sort(([, a], [, b]) => b - a)

  if (entries.length === 0) {
    return <span className="text-sm text-slate/60 italic">None observed</span>
  }

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([mode, count]) => {
        const high = HIGH_SEVERITY.has(mode)
        return (
          <span
            key={mode}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border ${
              high
                ? 'bg-fail/8 text-fail border-fail/20'
                : 'bg-slate/8 text-slate border-slate/20'
            }`}
          >
            {fmt(mode)}
            <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
              high ? 'bg-fail/20 text-fail' : 'bg-slate/20 text-slate'
            }`}>
              {count}
            </span>
          </span>
        )
      })}
    </div>
  )
}
