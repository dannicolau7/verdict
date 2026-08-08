import { useRef, useState } from 'react'
import type { AgentTraceOut, TraceEvalReportOut, TraceJudgmentOut, TraceStepOut } from '../types/api'
import * as api from '../api/client'
import { Spinner } from '../components/ui/Spinner'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STEP_TYPE_LABEL: Record<string, string> = {
  llm_call:     'LLM',
  tool_call:    'Call',
  tool_result:  'Result',
  observation:  'Obs',
  final_answer: 'Answer',
}

const STEP_TYPE_COLOR: Record<string, string> = {
  llm_call:     'bg-brand/10 text-brand',
  tool_call:    'bg-slate/10 text-slate',
  tool_result:  'bg-slate/5 text-slate/70',
  observation:  'bg-slate/5 text-slate/70',
  final_answer: 'bg-pass/10 text-pass',
}

function fm(s: string): string {
  return s.replace(/_/g, ' ')
}

function ScorePips({ score }: { score: number | null }) {
  if (score == null) return null
  return (
    <span className="flex items-center gap-0.5" title={`Score: ${score}/5`}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={`w-1.5 h-1.5 rounded-full ${i <= score ? 'bg-brand' : 'bg-line'}`} />
      ))}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Step timeline
// ---------------------------------------------------------------------------

function StepRow({ step, judgment }: { step: TraceStepOut; judgment: TraceStepOut & { passed?: boolean; failure_mode?: string | null; reasoning?: string } | null }) {
  const [open, setOpen] = useState(false)
  const passed = judgment?.passed
  const hasDetail = step.tool_arguments || step.tool_result || step.llm_input || step.llm_output || step.error || judgment?.reasoning

  return (
    <div className="border-b border-line last:border-0">
      <button
        onClick={() => hasDetail && setOpen(o => !o)}
        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand ${hasDetail ? 'hover:bg-cloud cursor-pointer' : 'cursor-default'}`}
      >
        <span className={`flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded ${STEP_TYPE_COLOR[step.step_type] ?? 'bg-cloud text-slate'}`}>
          {STEP_TYPE_LABEL[step.step_type] ?? step.step_type}
        </span>
        <span className="flex-1 text-sm text-ink truncate">
          {step.tool_name ? (
            <><span className="font-mono">{step.tool_name}</span>{step.tool_arguments && <span className="text-slate/60 ml-1 font-normal">{JSON.stringify(step.tool_arguments).slice(0, 60)}</span>}</>
          ) : (
            step.llm_output?.slice(0, 80) ?? step.tool_result?.slice(0, 80) ?? `Step ${step.step_id}`
          )}
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          {step.latency_ms != null && (
            <span className="text-[10px] text-slate/50 font-mono">{Math.round(step.latency_ms)}ms</span>
          )}
          {step.error && <span className="text-[10px] text-fail font-medium">error</span>}
          {passed != null && (
            <span className={passed ? 'text-pass' : 'text-fail'}>{passed ? '✓' : '✗'}</span>
          )}
          {judgment?.failure_mode && (
            <span className="text-[10px] font-medium text-fail/80 bg-fail/5 px-1.5 py-0.5 rounded">{fm(judgment.failure_mode)}</span>
          )}
          {hasDetail && (
            <span className="text-[10px] text-slate/40">{open ? '▲' : '▼'}</span>
          )}
        </div>
      </button>

      {open && hasDetail && (
        <div className="px-4 pb-3 pt-1 space-y-2 bg-cloud/50 text-xs text-slate">
          {step.tool_arguments && (
            <div>
              <p className="font-semibold text-ink mb-0.5">Arguments</p>
              <pre className="font-mono text-[11px] bg-white border border-line rounded p-2 overflow-auto">{JSON.stringify(step.tool_arguments, null, 2)}</pre>
            </div>
          )}
          {step.tool_result && (
            <div>
              <p className="font-semibold text-ink mb-0.5">Result</p>
              <p className="leading-relaxed">{step.tool_result}</p>
            </div>
          )}
          {step.llm_input && (
            <div>
              <p className="font-semibold text-ink mb-0.5">LLM input</p>
              <p className="leading-relaxed">{step.llm_input}</p>
            </div>
          )}
          {step.llm_output && (
            <div>
              <p className="font-semibold text-ink mb-0.5">LLM output</p>
              <p className="leading-relaxed">{step.llm_output}</p>
            </div>
          )}
          {step.error && (
            <div>
              <p className="font-semibold text-fail mb-0.5">Error</p>
              <p className="font-mono text-fail">{step.error}</p>
            </div>
          )}
          {judgment?.reasoning && (
            <div className="pt-1 border-t border-line">
              <p className="font-semibold text-ink mb-0.5">Judge reasoning</p>
              <p className="leading-relaxed">{judgment.reasoning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Trace card
// ---------------------------------------------------------------------------

function TraceCard({
  trace,
  judgment,
}: {
  trace: AgentTraceOut
  judgment: TraceJudgmentOut
}) {
  const [open, setOpen] = useState(false)
  const stepJudgmentMap = Object.fromEntries(judgment.step_judgments.map(sj => [sj.step_id, sj]))

  return (
    <div className="rounded-xl border border-line bg-white overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start gap-4 px-5 py-4 text-left hover:bg-cloud/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
      >
        <div className="flex-1 min-w-0 space-y-1">
          <p className="text-sm font-medium text-ink leading-snug">{trace.task}</p>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-mono text-slate/50">{trace.trace_id.slice(0, 8)}…</span>
            {trace.tools_available.length > 0 && (
              <span className="text-[10px] text-slate/50">{trace.tools_available.join(', ')}</span>
            )}
            {trace.total_latency_ms != null && (
              <span className="text-[10px] text-slate/50 font-mono">{(trace.total_latency_ms / 1000).toFixed(2)}s</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 pt-0.5">
          <ScorePips score={judgment.overall_score} />
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${judgment.overall_passed ? 'text-pass bg-pass/10' : 'text-fail bg-fail/10'}`}>
            {judgment.overall_passed ? 'PASS' : 'FAIL'}
          </span>
          <span className="text-slate/40 text-xs">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {open && (
        <div className="border-t border-line">
          {/* Overall reasoning */}
          <div className="px-5 py-3 bg-cloud/30 space-y-1">
            <p className="text-xs font-semibold text-slate uppercase tracking-wide">Overall reasoning</p>
            <p className="text-sm text-ink leading-relaxed">{judgment.reasoning}</p>
            {judgment.failure_modes.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {judgment.failure_modes.map(fm_str => (
                  <span key={fm_str} className="text-[10px] font-medium text-fail/80 bg-fail/5 border border-fail/10 px-1.5 py-0.5 rounded">
                    {fm(fm_str)}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Step timeline */}
          {trace.steps.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate uppercase tracking-wide px-5 py-2 border-t border-line bg-white">
                Steps ({trace.steps.length})
              </p>
              <div className="divide-y divide-line border-t border-line">
                {trace.steps.map(step => (
                  <StepRow
                    key={step.step_id}
                    step={step}
                    judgment={stepJudgmentMap[step.step_id] as any ?? null}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Report view
// ---------------------------------------------------------------------------

function TraceReportView({
  report,
  traces,
  onReset,
}: {
  report: TraceEvalReportOut
  traces: AgentTraceOut[]
  onReset: () => void
}) {
  const traceMap = Object.fromEntries(traces.map(t => [t.trace_id, t]))
  const ts = new Date(report.timestamp).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })

  const fmEntries = Object.entries(report.failure_mode_counts).sort((a, b) => b[1] - a[1])
  const passed = report.trace_judgments.filter(j => j.overall_passed).length

  return (
    <div className="space-y-8 animate-fade-up">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">Trace eval — {report.agent_name}</h2>
          <p className="text-sm text-slate mt-0.5">{ts} · {report.verdict_version ? `v${report.verdict_version}` : ''}</p>
        </div>
        <button onClick={onReset}
          className="flex-shrink-0 text-sm font-medium text-slate border border-line rounded-lg px-3 py-1.5 hover:bg-white transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none">
          New eval
        </button>
      </div>

      {/* Hero */}
      <div className="bg-white border border-line rounded-2xl p-6 flex flex-wrap gap-8 items-center">
        <div className="space-y-1">
          <p className="text-xs font-semibold text-slate uppercase tracking-wide">Pass rate</p>
          <p className="text-5xl font-bold tabular-nums text-ink">{Math.round(report.pass_rate * 100)}%</p>
          {report.pass_rate_ci_low != null && (
            <p className="text-xs text-slate/60">
              95% CI: {Math.round(report.pass_rate_ci_low * 100)}% – {Math.round(report.pass_rate_ci_high! * 100)}%
            </p>
          )}
        </div>
        <div className="flex gap-6 text-sm">
          <div className="space-y-0.5">
            <p className="text-xs text-slate">Traces</p>
            <p className="text-2xl font-bold text-ink">{report.total_traces}</p>
          </div>
          <div className="space-y-0.5">
            <p className="text-xs text-slate">Passed</p>
            <p className="text-2xl font-bold text-pass">{passed}</p>
          </div>
          <div className="space-y-0.5">
            <p className="text-xs text-slate">Failed</p>
            <p className="text-2xl font-bold text-fail">{report.total_traces - passed}</p>
          </div>
        </div>
      </div>

      {/* Failure modes */}
      {fmEntries.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">Failure modes</h3>
          <div className="flex flex-wrap gap-2">
            {fmEntries.map(([mode, count]) => (
              <span key={mode} className="inline-flex items-center gap-1.5 text-xs font-medium text-fail/80 bg-fail/5 border border-fail/10 px-3 py-1.5 rounded-full">
                {fm(mode)}
                <span className="text-[10px] font-bold bg-fail/10 text-fail rounded-full px-1.5 py-0.5">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Per-trace list */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">
          Per-trace results ({report.total_traces})
        </h3>
        <div className="space-y-2">
          {report.trace_judgments.map(judgment => {
            const trace = traceMap[judgment.trace_id]
            if (!trace) return null
            return <TraceCard key={judgment.trace_id} trace={trace} judgment={judgment} />
          })}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Upload zone
// ---------------------------------------------------------------------------

function UploadZone({
  file,
  onFile,
}: {
  file: File | null
  onFile: (f: File) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handle = (f: File | null) => {
    if (f && f.name.endsWith('.json')) onFile(f)
  }

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files[0] ?? null) }}
      className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 cursor-pointer transition-colors
        ${dragging ? 'border-brand bg-brand/5' : file ? 'border-pass/40 bg-pass/5' : 'border-line hover:border-brand/40 hover:bg-cloud'}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".json,application/json"
        className="sr-only"
        onChange={e => handle(e.target.files?.[0] ?? null)}
      />
      {file ? (
        <>
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <circle cx="16" cy="16" r="15" stroke="currentColor" strokeWidth="1.5" className="text-pass" />
            <path d="M10 16l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-pass" />
          </svg>
          <p className="text-sm font-medium text-ink">{file.name}</p>
          <p className="text-xs text-slate">{(file.size / 1024).toFixed(1)} KB · click to replace</p>
        </>
      ) : (
        <>
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true" className="text-slate/40">
            <path d="M16 21V11M11 16l5-5 5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 22v2a2 2 0 002 2h18a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <p className="text-sm font-medium text-ink">Drop an AgentTrace JSON file</p>
          <p className="text-xs text-slate">or click to browse · one or more AgentTrace objects</p>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const JUDGE_MODELS = [
  'claude-sonnet-4-6',
  'claude-haiku-4-5-20251001',
  'claude-opus-4-6',
]

export function TraceEval() {
  const [file, setFile] = useState<File | null>(null)
  const [judgeModel, setJudgeModel] = useState('claude-sonnet-4-6')
  const [progress, setProgress] = useState<{ type: string; detail: string }[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ report: TraceEvalReportOut; traces: AgentTraceOut[] } | null>(null)

  const STAGE_LABELS: Record<string, string> = { parse: 'Parse', judge: 'Judge', build: 'Build' }

  const handleRun = async () => {
    if (!file) return
    setRunning(true)
    setProgress([])
    setError(null)
    try {
      for await (const event of api.runTraceEval(file, judgeModel)) {
        if (event.type === 'complete') {
          setResult({ report: event.report, traces: event.traces })
        } else if (event.type === 'error') {
          setError(event.message)
        } else {
          setProgress(p => [...p, { type: event.type, detail: event.detail }])
        }
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }

  const handleReset = () => {
    setResult(null)
    setFile(null)
    setProgress([])
    setError(null)
  }

  if (result) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <TraceReportView report={result.report} traces={result.traces} onReset={handleReset} />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Trace eval</h1>
        <p className="text-sm text-slate mt-1">
          Upload an <span className="font-mono">AgentTrace</span> JSON file and run the step-level judge.
        </p>
      </div>

      {!running ? (
        <div className="space-y-4">
          <UploadZone file={file} onFile={setFile} />

          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="trace-judge-model">Judge model</label>
              <select
                id="trace-judge-model"
                value={judgeModel}
                onChange={e => setJudgeModel(e.target.value)}
                className="rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
              >
                {JUDGE_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>

            <button
              onClick={handleRun}
              disabled={!file}
              className="flex items-center gap-2 bg-brand text-white font-medium rounded-lg px-5 py-2.5
                hover:bg-brand/90 active:scale-[0.98] transition-all
                disabled:opacity-50 disabled:cursor-not-allowed
                focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              Run trace eval
            </button>
          </div>

          {error && (
            <div className="rounded-lg border border-fail/20 bg-fail/5 p-3 text-sm text-fail">{error}</div>
          )}

          <div className="rounded-xl border border-line bg-white p-4 space-y-2">
            <p className="text-xs font-semibold text-slate">Expected JSON format</p>
            <pre className="text-[11px] font-mono text-slate/70 leading-relaxed overflow-auto">{`// Single trace or array of traces
{
  "trace_id": "...",          // optional, auto-generated if missing
  "agent_name": "my-agent",
  "task": "Do X given Y",
  "expected_behavior": "Should call tool A then B...",
  "tools_available": ["tool_a", "tool_b"],
  "steps": [
    { "step_id": 0, "step_type": "llm_call",  "llm_output": "..." },
    { "step_id": 1, "step_type": "tool_call", "tool_name": "tool_a", "tool_arguments": {} },
    { "step_id": 2, "step_type": "tool_result", "tool_result": "..." },
    { "step_id": 3, "step_type": "final_answer", "llm_output": "..." }
  ]
}`}</pre>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-line rounded-2xl p-6 space-y-4">
          <div className="flex items-center gap-3 text-slate">
            <Spinner size={18} className="text-brand" />
            <span className="text-sm font-medium">Running trace eval…</span>
          </div>
          <div className="space-y-2">
            {progress.map((p, i) => (
              <div key={i} className="flex items-start gap-3 text-xs">
                <span className="text-brand font-semibold w-12 flex-shrink-0">{STAGE_LABELS[p.type] ?? p.type}</span>
                <span className="text-slate">{p.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
