import { useEffect, useState } from 'react'
import type { EvalReport, RunListItem } from '../types/api'
import * as api from '../api/client'
import { ReportView } from '../components/eval/ReportView'
import { Spinner } from '../components/ui/Spinner'

function passRateBadge(rate: number): string {
  if (rate >= 0.8) return 'text-pass bg-pass/10'
  if (rate >= 0.6) return 'text-caution bg-caution/10'
  return 'text-fail bg-fail/10'
}

function RunCard({
  item,
  onView,
  loading,
}: {
  item: RunListItem
  onView: () => void
  loading: boolean
}) {
  const ts = new Date(item.timestamp).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
  const pct = Math.round(item.pass_rate * 100)

  return (
    <div className="flex items-center justify-between gap-4 p-4 bg-white border border-line rounded-xl hover:border-brand/30 transition-colors">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink truncate">{item.target_system}</p>
        <p className="text-xs text-slate mt-0.5">
          <span className="font-mono">{item.run_id.slice(0, 8)}</span>
          {' · '}{ts}
        </p>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${passRateBadge(item.pass_rate)}`}>
          {pct}%
        </span>
        <span className="text-xs text-slate hidden sm:block">{item.total_tests} tests</span>
        <button
          onClick={onView}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm font-medium text-brand hover:underline
            focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none rounded
            disabled:opacity-50 disabled:no-underline"
        >
          {loading ? <Spinner size={14} className="text-brand" /> : 'View'}
        </button>
      </div>
    </div>
  )
}

export function History() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [selected, setSelected] = useState<EvalReport | null>(null)
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    api.fetchRuns()
      .then(setRuns)
      .catch(e => setFetchError(String(e)))
  }, [])

  const handleView = async (runId: string) => {
    setLoadingId(runId)
    setLoadError(null)
    try {
      const report = await api.fetchRun(runId)
      setSelected(report)
    } catch (e) {
      setLoadError(String(e))
    } finally {
      setLoadingId(null)
    }
  }

  if (selected) {
    return (
      <div>
        <div className="max-w-3xl mx-auto px-6 pt-6">
          <button
            onClick={() => setSelected(null)}
            className="text-sm font-medium text-slate hover:text-ink transition-colors
              focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none rounded"
          >
            ← History
          </button>
        </div>
        <ReportView report={selected} onRunAgain={() => setSelected(null)} />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">History</h1>
        <p className="text-sm text-slate mt-1">Past evaluation runs, newest first.</p>
      </div>

      {(fetchError || loadError) && (
        <div className="rounded-xl border border-fail/20 bg-fail/5 p-4 text-sm text-fail">
          {fetchError ?? loadError}
        </div>
      )}

      {!runs && !fetchError && (
        <div className="flex items-center justify-center gap-3 text-slate py-16">
          <Spinner size={18} className="text-brand" />
          <span className="text-sm">Loading…</span>
        </div>
      )}

      {runs && runs.length === 0 && (
        <div className="text-center py-16 text-sm text-slate">
          No runs yet — complete an evaluation to see it here.
        </div>
      )}

      {runs && runs.length > 0 && (
        <div className="space-y-3">
          {runs.map(item => (
            <RunCard
              key={item.run_id}
              item={item}
              onView={() => handleView(item.run_id)}
              loading={loadingId === item.run_id}
            />
          ))}
        </div>
      )}
    </div>
  )
}
