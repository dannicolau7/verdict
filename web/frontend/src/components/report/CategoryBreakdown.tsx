import type { CategoryStats } from '../../types/api'

interface CategoryBreakdownProps {
  breakdown: Record<string, CategoryStats>
}

const LABELS: Record<string, string> = {
  correctness: 'Correctness',
  safety:      'Safety',
  injection:   'Injection',
  edge_case:   'Edge case',
  compliance:  'Compliance',
}

function RateBar({ rate }: { rate: number }) {
  const color = rate >= 0.8 ? 'bg-pass' : rate >= 0.5 ? 'bg-caution' : 'bg-fail'
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="flex-1 h-1.5 bg-line rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${rate * 100}%` }} />
      </div>
      <span className="text-xs font-mono text-ink tabular-nums w-9 text-right">
        {Math.round(rate * 100)}%
      </span>
    </div>
  )
}

export function CategoryBreakdown({ breakdown }: CategoryBreakdownProps) {
  const rows = Object.entries(breakdown)

  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line">
            <th className="text-left py-2 px-1 font-medium text-slate text-xs uppercase tracking-wide">Category</th>
            <th className="text-right py-2 px-1 font-medium text-slate text-xs uppercase tracking-wide">Tests</th>
            <th className="text-right py-2 px-1 font-medium text-slate text-xs uppercase tracking-wide">Passed</th>
            <th className="py-2 px-1 font-medium text-slate text-xs uppercase tracking-wide min-w-[140px]">Rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line/60">
          {rows.map(([cat, stats]) => (
            <tr key={cat} className="hover:bg-white/50 transition-colors">
              <td className="py-3 px-1 font-medium text-ink">{LABELS[cat] ?? cat}</td>
              <td className="py-3 px-1 text-right tabular-nums text-slate">{stats.total}</td>
              <td className="py-3 px-1 text-right tabular-nums text-slate">{stats.passed}</td>
              <td className="py-3 px-1"><RateBar rate={stats.pass_rate} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
