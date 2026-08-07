import { useEffect, useState } from 'react'
import type {
  CategoryDiff,
  DiffCompareResponse,
  DiffRunRequest,
  DiffRunResponse,
  PerPromptRow,
  RunListItem,
} from '../types/api'
import * as api from '../api/client'
import { Spinner } from '../components/ui/Spinner'

// ---------------------------------------------------------------------------
// Shared helpers
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

// ---------------------------------------------------------------------------
// Prompt list (regressions / improvements)
// ---------------------------------------------------------------------------

function PromptList({ rows, kind }: { rows: PerPromptRow[]; kind: 'regression' | 'improvement' }) {
  const [open, setOpen] = useState(false)
  if (rows.length === 0) return null

  const color = kind === 'regression' ? 'text-fail bg-fail/10' : 'text-pass bg-pass/10'
  const label = kind === 'regression'
    ? `${rows.length} regression${rows.length !== 1 ? 's' : ''}`
    : `${rows.length} improvement${rows.length !== 1 ? 's' : ''}`

  return (
    <div className="space-y-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left focus-visible:outline-none
          focus-visible:ring-2 focus-visible:ring-brand rounded"
      >
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>{label}</span>
        <span className="text-xs text-slate">{open ? '▲ hide' : '▼ show'}</span>
      </button>

      {open && (
        <div className="space-y-2">
          {rows.map(row => (
            <div key={row.prompt_id} className="rounded-xl border border-line bg-white p-4 space-y-2 text-sm">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-medium text-slate capitalize">{row.category}</span>
                <span className="text-xs text-slate/50">·</span>
                <span className="text-xs text-slate/60">{row.severity}</span>
                {(kind === 'regression' ? row.b_failure_mode : row.a_failure_mode) && (
                  <>
                    <span className="text-xs text-slate/50">·</span>
                    <span className="text-xs font-mono text-fail/80">
                      {kind === 'regression' ? row.b_failure_mode : row.a_failure_mode}
                    </span>
                  </>
                )}
              </div>
              <p className="text-ink font-medium leading-snug">{row.prompt_text}</p>
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <p className="text-xs font-semibold text-slate mb-1">A reasoning</p>
                  <p className="text-xs text-slate/80 leading-relaxed">{row.a_reasoning}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate mb-1">B reasoning</p>
                  <p className="text-xs text-slate/80 leading-relaxed">{row.b_reasoning}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Result views
// ---------------------------------------------------------------------------

function HistoricalResultView({ result, onReset }: { result: DiffCompareResponse; onReset: () => void }) {
  const tsA = new Date(result.timestamp_a).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  const tsB = new Date(result.timestamp_b).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

  return (
    <div className="space-y-8 animate-fade-up">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">Historical diff</h2>
          <p className="text-sm text-slate mt-0.5">
            <span className="font-mono">{result.run_id_a.slice(0, 8)}</span>{' '}vs{' '}
            <span className="font-mono">{result.run_id_b.slice(0, 8)}</span>
          </p>
        </div>
        <button onClick={onReset} className="flex-shrink-0 text-sm font-medium text-slate border border-line rounded-lg px-3 py-1.5 hover:bg-white transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
          New diff
        </button>
      </div>

      <div className="bg-white border border-line rounded-2xl p-6 flex flex-wrap items-center gap-8">
        <div className="space-y-1">
          <p className="text-xs font-semibold text-slate uppercase tracking-wide">Overall delta</p>
          <HeroDelta delta={result.pass_rate_delta} />
          <p className="text-xs text-slate/70">{result.pass_rate_delta > 0 ? 'B improved over A' : result.pass_rate_delta < 0 ? 'B regressed vs A' : 'No change'}</p>
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

      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">By category</h3>
        <CategoryTable categories={result.categories} />
        <div className="flex items-center gap-4 text-xs text-slate/60 px-1">
          <span className="flex items-center gap-1.5"><span className="w-3 h-1.5 rounded-full bg-brand/40 inline-block" />A (baseline)</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-1.5 rounded-full bg-brand inline-block" />B (candidate)</span>
        </div>
      </div>

      <p className="text-xs text-slate/50">These runs used independently generated test suites — per-prompt comparison is not available for historical diffs.</p>
    </div>
  )
}

function FreshResultView({ result, onReset }: { result: DiffRunResponse; onReset: () => void }) {
  const modelA = result.model_a.split('-').slice(1, 3).join('-')
  const modelB = result.model_b.split('-').slice(1, 3).join('-')

  return (
    <div className="space-y-8 animate-fade-up">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">Fresh diff result</h2>
          <p className="text-sm text-slate mt-0.5">
            {modelA} vs {modelB} · {result.total_tests} shared prompts
          </p>
        </div>
        <button onClick={onReset} className="flex-shrink-0 text-sm font-medium text-slate border border-line rounded-lg px-3 py-1.5 hover:bg-white transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
          New diff
        </button>
      </div>

      <div className="bg-white border border-line rounded-2xl p-6 flex flex-wrap items-center gap-8">
        <div className="space-y-1">
          <p className="text-xs font-semibold text-slate uppercase tracking-wide">Overall delta</p>
          <HeroDelta delta={result.pass_rate_delta} />
          <p className="text-xs text-slate/70">{result.pass_rate_delta > 0 ? 'B improved over A' : result.pass_rate_delta < 0 ? 'B regressed vs A' : 'No change'}</p>
        </div>
        <div className="flex gap-8">
          <div className="space-y-0.5">
            <p className="text-xs text-slate">A · {modelA}</p>
            <p className="text-2xl font-bold text-ink tabular-nums">{pct(result.a_pass_rate)}</p>
          </div>
          <div className="space-y-0.5">
            <p className="text-xs text-slate">B · {modelB}</p>
            <p className="text-2xl font-bold text-ink tabular-nums">{pct(result.b_pass_rate)}</p>
          </div>
        </div>
        <div className="flex gap-4 text-xs ml-auto self-start pt-1">
          <span className={`px-2 py-0.5 rounded-full font-semibold ${result.regression_count > 0 ? 'text-fail bg-fail/10' : 'text-slate bg-cloud'}`}>
            {result.regression_count} regression{result.regression_count !== 1 ? 's' : ''}
          </span>
          <span className={`px-2 py-0.5 rounded-full font-semibold ${result.improvement_count > 0 ? 'text-pass bg-pass/10' : 'text-slate bg-cloud'}`}>
            {result.improvement_count} improvement{result.improvement_count !== 1 ? 's' : ''}
          </span>
          <span className="px-2 py-0.5 rounded-full font-semibold text-slate bg-cloud">
            {result.unchanged} unchanged
          </span>
        </div>
      </div>

      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">By category</h3>
        <CategoryTable categories={result.categories} />
        <div className="flex items-center gap-4 text-xs text-slate/60 px-1">
          <span className="flex items-center gap-1.5"><span className="w-3 h-1.5 rounded-full bg-brand/40 inline-block" />A · {modelA}</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-1.5 rounded-full bg-brand inline-block" />B · {modelB}</span>
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">Per-prompt</h3>
        <PromptList rows={result.regressions} kind="regression" />
        <PromptList rows={result.improvements} kind="improvement" />
        {result.regressions.length === 0 && result.improvements.length === 0 && (
          <p className="text-sm text-slate">Both models agreed on every prompt.</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fresh run form
// ---------------------------------------------------------------------------

const MODELS = [
  'claude-haiku-4-5-20251001',
  'claude-sonnet-4-6',
  'claude-opus-4-6',
]
const ALL_CATEGORIES = ['correctness', 'safety', 'injection', 'edge_case', 'compliance']

function FreshRunForm({ onResult }: { onResult: (r: DiffRunResponse) => void }) {
  const [req, setReq] = useState<DiffRunRequest>({
    model_a: 'claude-haiku-4-5-20251001',
    model_b: 'claude-sonnet-4-6',
    categories: [...ALL_CATEGORIES],
    num_per_category: 3,
    judge_model: 'claude-sonnet-4-6',
  })
  const [progress, setProgress] = useState<{ stage: string; detail: string }[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof DiffRunRequest>(k: K, v: DiffRunRequest[K]) =>
    setReq(r => ({ ...r, [k]: v }))

  const handleRun = async () => {
    setRunning(true)
    setProgress([])
    setError(null)
    try {
      for await (const event of api.runDiff(req)) {
        if (event.type === 'progress') {
          setProgress(p => [...p, { stage: event.stage, detail: event.detail }])
        } else if (event.type === 'complete') {
          onResult(event.result)
        } else if (event.type === 'error') {
          setError(event.message)
        }
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }

  const STAGE_LABELS: Record<string, string> = {
    generate: 'Generate', execute: 'Execute', judge: 'Judge', report: 'Report',
  }

  if (running) {
    return (
      <div className="bg-white border border-line rounded-2xl p-6 space-y-4">
        <div className="flex items-center gap-3 text-slate">
          <Spinner size={18} className="text-brand" />
          <span className="text-sm font-medium">Running diff…</span>
        </div>
        <div className="space-y-2">
          {progress.map((p, i) => (
            <div key={i} className="flex items-start gap-3 text-xs">
              <span className="text-brand font-semibold w-16 flex-shrink-0">{STAGE_LABELS[p.stage] ?? p.stage}</span>
              <span className="text-slate">{p.detail}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white border border-line rounded-2xl p-6 space-y-6">
      <p className="text-xs text-slate/70">
        Runs a single shared test suite against both models simultaneously — results are per-prompt comparable.
      </p>

      <div className="flex flex-col sm:flex-row gap-4">
        <div className="space-y-1.5 flex-1">
          <label className="text-sm font-medium text-ink" htmlFor="model-a">Model A (baseline)</label>
          <select id="model-a" value={req.model_a} onChange={e => set('model_a', e.target.value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
            {MODELS.filter(m => m !== req.model_b).map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <div className="flex items-end pb-2 text-slate self-center sm:self-auto">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M4 10h12M12 5l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        <div className="space-y-1.5 flex-1">
          <label className="text-sm font-medium text-ink" htmlFor="model-b">Model B (candidate)</label>
          <select id="model-b" value={req.model_b} onChange={e => set('model_b', e.target.value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
            {MODELS.filter(m => m !== req.model_a).map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 items-end">
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-ink" htmlFor="num-per-cat">Prompts per category</label>
          <input id="num-per-cat" type="number" min={1} max={10} value={req.num_per_category}
            onChange={e => set('num_per_category', Math.max(1, Math.min(10, Number(e.target.value))))}
            className="w-20 rounded-lg border border-line px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none" />
        </div>

        <div className="space-y-1.5 flex-1 min-w-40">
          <label className="text-sm font-medium text-ink" htmlFor="judge-model">Judge model</label>
          <select id="judge-model" value={req.judge_model} onChange={e => set('judge_model', e.target.value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-fail/20 bg-fail/5 p-3 text-sm text-fail">{error}</div>
      )}

      <button onClick={handleRun}
        className="flex items-center gap-2 bg-brand text-white font-medium rounded-lg px-5 py-2.5
          hover:bg-brand/90 active:scale-[0.98] transition-all
          focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:outline-none">
        Run fresh diff
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Historical form
// ---------------------------------------------------------------------------

function RunSelect({ id, label, runs, value, onChange, exclude }: {
  id: string; label: string; runs: RunListItem[]
  value: string; onChange: (v: string) => void; exclude: string
}) {
  return (
    <div className="space-y-1.5 flex-1 min-w-0">
      <label className="text-sm font-medium text-ink" htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
        <option value="">Select a run…</option>
        {runs.filter(r => r.run_id !== exclude).map(r => {
          const ts = new Date(r.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
          const prefix = r.label ? `[${r.label}] ` : ''
          return (
            <option key={r.run_id} value={r.run_id}>
              {prefix}{r.run_id.slice(0, 8)} · {r.target_system} · {Math.round(r.pass_rate * 100)}% · {ts}
            </option>
          )
        })}
      </select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type DiffMode = 'historical' | 'fresh'

export function Diff() {
  const [mode, setMode] = useState<DiffMode>('fresh')
  const [runs, setRuns] = useState<RunListItem[] | null>(null)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [runIdA, setRunIdA] = useState('')
  const [runIdB, setRunIdB] = useState('')
  const [comparing, setComparing] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [historicalResult, setHistoricalResult] = useState<DiffCompareResponse | null>(null)
  const [freshResult, setFreshResult] = useState<DiffRunResponse | null>(null)

  useEffect(() => {
    api.fetchRuns().then(setRuns).catch(e => setRunsError(String(e)))
  }, [])

  const handleCompare = async () => {
    setComparing(true)
    setCompareError(null)
    try {
      const res = await api.compareRuns({ run_id_a: runIdA, run_id_b: runIdB })
      setHistoricalResult(res)
    } catch (e) {
      setCompareError(String(e))
    } finally {
      setComparing(false)
    }
  }

  const handleReset = () => {
    setHistoricalResult(null)
    setFreshResult(null)
    setCompareError(null)
  }

  if (historicalResult) return <div className="max-w-3xl mx-auto px-6 py-8"><HistoricalResultView result={historicalResult} onReset={handleReset} /></div>
  if (freshResult) return <div className="max-w-3xl mx-auto px-6 py-8"><FreshResultView result={freshResult} onReset={handleReset} /></div>

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Diff</h1>
        <p className="text-sm text-slate mt-1">Compare two adapter configurations side by side.</p>
      </div>

      {/* Mode toggle */}
      <div className="flex rounded-lg border border-line overflow-hidden w-fit" role="group">
        {([['fresh', 'Fresh run'], ['historical', 'Historical']] as [DiffMode, string][]).map(([val, lbl]) => (
          <button key={val} onClick={() => setMode(val)}
            className={`px-4 py-2 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand focus-visible:outline-none
              ${mode === val ? 'bg-brand text-white' : 'bg-white text-slate hover:text-ink hover:bg-cloud'}`}>
            {lbl}
          </button>
        ))}
      </div>

      {mode === 'fresh' && (
        <FreshRunForm onResult={setFreshResult} />
      )}

      {mode === 'historical' && (
        <>
          {runsError && <div className="rounded-xl border border-fail/20 bg-fail/5 p-4 text-sm text-fail">{runsError}</div>}
          {!runs && !runsError && (
            <div className="flex items-center justify-center gap-3 text-slate py-16">
              <Spinner size={18} className="text-brand" /><span className="text-sm">Loading runs…</span>
            </div>
          )}
          {runs && runs.length < 2 && (
            <div className="text-center py-16 text-sm text-slate">
              You need at least two completed runs to diff.<br />
              <a href="#/" className="text-brand hover:underline mt-1 inline-block">Run an evaluation →</a>
            </div>
          )}
          {runs && runs.length >= 2 && (
            <div className="bg-white border border-line rounded-2xl p-6 space-y-6">
              <p className="text-xs text-slate/70">Compares aggregate stats from two past runs — test suites differ.</p>
              <div className="flex flex-col sm:flex-row gap-4">
                <RunSelect id="run-a" label="Baseline (A)" runs={runs} value={runIdA} onChange={setRunIdA} exclude={runIdB} />
                <div className="flex items-end pb-2 text-slate self-center sm:self-auto">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <path d="M4 10h12M12 5l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <RunSelect id="run-b" label="Candidate (B)" runs={runs} value={runIdB} onChange={setRunIdB} exclude={runIdA} />
              </div>
              {compareError && <div className="rounded-lg border border-fail/20 bg-fail/5 p-3 text-sm text-fail">{compareError}</div>}
              <button onClick={handleCompare} disabled={!runIdA || !runIdB || runIdA === runIdB || comparing}
                className="flex items-center gap-2 bg-brand text-white font-medium rounded-lg px-5 py-2.5
                  hover:bg-brand/90 active:scale-[0.98] transition-all
                  disabled:opacity-50 disabled:cursor-not-allowed
                  focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:outline-none">
                {comparing && <Spinner size={16} />}
                Compare runs
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
