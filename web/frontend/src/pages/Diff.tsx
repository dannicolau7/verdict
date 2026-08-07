import { useEffect, useState } from 'react'
import type { CategoryDiff, DiffCompareResponse, RunListItem } from '../types/api'
import * as api from '../api/client'
import { Spinner } from '../components/ui/Spinner'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v: number | null): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`
}

function deltaClass(d: number | null): string {
  if (d == null) return 'text-slate'
  if (d > 0) return 'text-pass'
  if (d < 0) return 'text-fail'
  return 'text-slate'
}

function deltaLabel(d: number | null): string {
  if (d == null) return '—'
  const sign = d > 0 ? '+' : ''
  return `${sign}${Math.round(d * 100)}pp`
}

function Bar({ rate, color }: { rate: number | null; color: 'a' | 'b' }) {
  if (rate == null) return <div className="h-1.5 w-full rounded-full bg-line" />
  const bg = color === 'a' ? 'bg-brand/40' : 'bg-brand'
  return (
    <div className="h-1.5 w-full rounded-full bg-line overflow-hidden">
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${rate * 100}%` }} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RunSelect({
  id,
  label,
  runs,
  value,
  onChange,
  exclude,
}: {
  id: string
  label: string
  runs: RunListItem[]
  value: string
  onChange: (v: string) => void
  exclude: string
}) {
  return (
    <div className="space-y-1.5 flex-1 min-w-0">
      <label className="text-sm font-medium text-ink" htmlFor={id}>{label}</label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink
          focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
      >
        <option value="">Select a run…</option>
        {runs.filter(r => r.run_id !== exclude).map(r => {
          const ts = new Date(r.timestamp).toLocaleString('en-US', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
          })
          return (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id.slice(0, 8)} · {r.target_system} · {Math.round(r.pass_rate * 100)}% · {ts}
            </option>
          )
        })}
      </select>
    </div>
  )
}

function HeroDelta({ delta }: { delta: number }) {
  const sign = delta > 0 ? '+' : ''
  const color = delta > 0 ? 'text-pass' : delta < 0 ? 'text-fail' : 'text-slate'
  return (
    <div className={`text-5xl font-bold tabular-nums ${color}`}>
      {sign}{Math.round(delta * 100)}pp
    </div>
  )
}

function CategoryTable({ categories }: { categories: CategoryDiff[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs font-semibold text-slate uppercase tracking-wide">
            <th className="text-left px-4 py-3">Category</th>
            <th className="text-right px-4 py-3">A</th>
            <th className="text-right px-4 py-3">B</th>
            <th className="text-right px-4 py-3">Delta</th>
            <th className="w-28 px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {categories.map(cat => (
            <tr key={cat.category} className="hover:bg-cloud transition-colors">
              <td className="px-4 py-3 font-medium text-ink capitalize">{cat.category}</td>
              <td className="px-4 py-3 text-right tabular-nums text-slate">{pct(cat.a_pass_rate)}</td>
              <td className="px-4 py-3 text-right tabular-nums font-medium text-ink">{pct(cat.b_pass_rate)}</td>
              <td className={`px-4 py-3 text-right tabular-nums font-semibold ${deltaClass(cat.delta)}`}>
                {deltaLabel(cat.delta)}
              </td>
              <td className="px-4 py-3">
                <div className="space-y-1">
                  <Bar rate={cat.a_pass_rate} color="a" />
                  <Bar rate={cat.b_pass_rate} color="b" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ResultView({
  result,
  onReset,
}: {
  result: DiffCompareResponse
  onReset: () => void
}) {
  const tsA = new Date(result.timestamp_a).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
  const tsB = new Date(result.timestamp_b).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })

  return (
    <div className="space-y-8 animate-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">Diff result</h2>
          <p className="text-sm text-slate mt-0.5">
            <span className="font-mono">{result.run_id_a.slice(0, 8)}</span>
            {' '}vs{' '}
            <span className="font-mono">{result.run_id_b.slice(0, 8)}</span>
          </p>
        </div>
        <button
          onClick={onReset}
          className="flex-shrink-0 text-sm font-medium text-slate border border-line rounded-lg
            px-3 py-1.5 hover:bg-white transition-colors
            focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
        >
          New diff
        </button>
      </div>

      {/* Hero */}
      <div className="bg-white border border-line rounded-2xl p-6 flex flex-wrap items-center gap-8">
        <div className="space-y-1">
          <p className="text-xs font-semibold text-slate uppercase tracking-wide">Overall delta</p>
          <HeroDelta delta={result.pass_rate_delta} />
          <p className="text-xs text-slate/70">
            {result.pass_rate_delta > 0 ? 'B improved over A' : result.pass_rate_delta < 0 ? 'B regressed vs A' : 'No change'}
          </p>
        </div>
        <div className="flex gap-8">
          <div className="space-y-0.5">
            <p className="text-xs text-slate">A · {result.target_a}</p>
            <p className="text-xs text-slate/60 font-mono">{result.run_id_a.slice(0, 8)} · {tsA}</p>
            <p className="text-2xl font-bold text-ink tabular-nums">{pct(result.a_pass_rate)}</p>
            <p className="text-xs text-slate">{result.a_total_tests} tests</p>
          </div>
          <div className="space-y-0.5">
            <p className="text-xs text-slate">B · {result.target_b}</p>
            <p className="text-xs text-slate/60 font-mono">{result.run_id_b.slice(0, 8)} · {tsB}</p>
            <p className="text-2xl font-bold text-ink tabular-nums">{pct(result.b_pass_rate)}</p>
            <p className="text-xs text-slate">{result.b_total_tests} tests</p>
          </div>
        </div>
      </div>

      {/* Category breakdown */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">By category</h3>
        <CategoryTable categories={result.categories} />
        <div className="flex items-center gap-4 text-xs text-slate/60 px-1">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-brand/40 inline-block" />A (baseline)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-brand inline-block" />B (candidate)
          </span>
        </div>
      </div>

      <p className="text-xs text-slate/50">
        These runs used independently generated test suites — per-prompt
        comparison is not available for historical diffs.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Diff() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [runIdA, setRunIdA] = useState('')
  const [runIdB, setRunIdB] = useState('')
  const [loading, setLoading] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [result, setResult] = useState<DiffCompareResponse | null>(null)

  useEffect(() => {
    api.fetchRuns()
      .then(setRuns)
      .catch(e => setRunsError(String(e)))
  }, [])

  const canSubmit = runIdA && runIdB && runIdA !== runIdB && !loading

  const handleCompare = async () => {
    if (!canSubmit) return
    setLoading(true)
    setCompareError(null)
    try {
      const res = await api.compareRuns({ run_id_a: runIdA, run_id_b: runIdB })
      setResult(res)
    } catch (e) {
      setCompareError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setResult(null)
    setCompareError(null)
  }

  if (result) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <ResultView result={result} onReset={handleReset} />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Diff</h1>
        <p className="text-sm text-slate mt-1">
          Compare two evaluation runs side by side.
        </p>
      </div>

      {runsError && (
        <div className="rounded-xl border border-fail/20 bg-fail/5 p-4 text-sm text-fail">
          {runsError}
        </div>
      )}

      {!runs && !runsError && (
        <div className="flex items-center justify-center gap-3 text-slate py-16">
          <Spinner size={18} className="text-brand" />
          <span className="text-sm">Loading runs…</span>
        </div>
      )}

      {runs && runs.length < 2 && (
        <div className="text-center py-16 text-sm text-slate">
          You need at least two completed runs to diff.
          <br />
          <a href="#/" className="text-brand hover:underline mt-1 inline-block">Run an evaluation →</a>
        </div>
      )}

      {runs && runs.length >= 2 && (
        <div className="bg-white border border-line rounded-2xl p-6 space-y-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <RunSelect
              id="run-a"
              label="Baseline (A)"
              runs={runs}
              value={runIdA}
              onChange={setRunIdA}
              exclude={runIdB}
            />
            <div className="flex items-end pb-2 text-slate self-center sm:self-auto">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M4 10h12M12 5l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <RunSelect
              id="run-b"
              label="Candidate (B)"
              runs={runs}
              value={runIdB}
              onChange={setRunIdB}
              exclude={runIdA}
            />
          </div>

          {compareError && (
            <div className="rounded-lg border border-fail/20 bg-fail/5 p-3 text-sm text-fail">
              {compareError}
            </div>
          )}

          <button
            onClick={handleCompare}
            disabled={!canSubmit}
            className="flex items-center gap-2 bg-brand text-white font-medium rounded-lg px-5 py-2.5
              hover:bg-brand/90 active:scale-[0.98] transition-all
              disabled:opacity-50 disabled:cursor-not-allowed
              focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {loading && <Spinner size={16} />}
            Compare runs
          </button>
        </div>
      )}
    </div>
  )
}
