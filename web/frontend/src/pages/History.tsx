import { useEffect, useRef, useState } from 'react'
import type { EvalReport, RunListItem } from '../types/api'
import * as api from '../api/client'
import { ReportView } from '../components/eval/ReportView'
import { Spinner } from '../components/ui/Spinner'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function passRateBadge(rate: number): string {
  if (rate >= 0.8) return 'text-pass bg-pass/10'
  if (rate >= 0.6) return 'text-caution bg-caution/10'
  return 'text-fail bg-fail/10'
}

// ---------------------------------------------------------------------------
// LabelEditor — inline click-to-edit label
// ---------------------------------------------------------------------------

function LabelEditor({
  runId,
  initial,
  onSaved,
}: {
  runId: string
  initial: string | null
  onSaved: (label: string | null) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(initial ?? '')
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const save = async () => {
    setSaving(true)
    try {
      const label = value.trim() || null
      await api.setRunLabel(runId, { label })
      onSaved(label)
    } finally {
      setSaving(false)
      setEditing(false)
    }
  }

  const cancel = () => {
    setValue(initial ?? '')
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1.5 mt-1" onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') save()
            if (e.key === 'Escape') cancel()
          }}
          onBlur={save}
          maxLength={60}
          placeholder="Add label…"
          className="text-xs border border-brand/40 rounded px-2 py-0.5 text-ink w-40
            focus:outline-none focus:ring-1 focus:ring-brand"
        />
        {saving && <Spinner size={12} className="text-brand" />}
      </div>
    )
  }

  return (
    <button
      onClick={e => { e.stopPropagation(); setEditing(true) }}
      className="mt-1 block text-xs text-left focus:outline-none focus-visible:ring-1
        focus-visible:ring-brand rounded"
    >
      {initial
        ? <span className="text-brand font-medium">{initial}</span>
        : <span className="text-slate/40 hover:text-slate transition-colors">+ add label</span>
      }
    </button>
  )
}

// ---------------------------------------------------------------------------
// RunCard
// ---------------------------------------------------------------------------

function RunCard({
  item,
  onView,
  loading,
  onLabelSaved,
}: {
  item: RunListItem
  onView: () => void
  loading: boolean
  onLabelSaved: (label: string | null) => void
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
        <LabelEditor
          runId={item.run_id}
          initial={item.label}
          onSaved={onLabelSaved}
        />
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

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

  const handleLabelSaved = (runId: string, label: string | null) => {
    setRuns(prev => prev?.map(r => r.run_id === runId ? { ...r, label } : r) ?? prev)
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
              onLabelSaved={label => handleLabelSaved(item.run_id, label)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
