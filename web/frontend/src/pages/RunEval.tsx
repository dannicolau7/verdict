import { useEffect, useState } from 'react'
import type { ConfigResponse, EvalReport, EvalRunRequest } from '../types/api'
import * as api from '../api/client'
import { EvalForm } from '../components/eval/EvalForm'
import { RunningState } from '../components/eval/RunningState'
import { ReportView } from '../components/eval/ReportView'
import { Spinner } from '../components/ui/Spinner'

type Phase = 'config' | 'running' | 'report' | 'error'

interface ProgressLine {
  stage: string
  detail: string
}

export function RunEval() {
  const [appConfig, setAppConfig] = useState<ConfigResponse | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)

  const [phase, setPhase] = useState<Phase>('config')
  const [progress, setProgress] = useState<ProgressLine[]>([])
  const [currentStage, setCurrentStage] = useState('')
  const [report, setReport] = useState<EvalReport | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    api.fetchConfig()
      .then(setAppConfig)
      .catch(e => setConfigError(String(e)))
  }, [])

  const handleRun = async (req: EvalRunRequest) => {
    setPhase('running')
    setProgress([])
    setCurrentStage('generate')
    setRunError(null)
    setReport(null)

    try {
      for await (const event of api.runEval(req)) {
        if (event.type === 'progress') {
          setCurrentStage(event.stage)
          setProgress(prev => [...prev, { stage: event.stage, detail: event.detail }])
        } else if (event.type === 'complete') {
          setReport(event.report)
          setPhase('report')
        } else if (event.type === 'error') {
          setRunError(event.message)
          setPhase('error')
        }
      }
    } catch (e) {
      setRunError(String(e))
      setPhase('error')
    }
  }

  const handleReset = () => {
    setPhase('config')
    setReport(null)
    setProgress([])
    setRunError(null)
  }

  // Config loading
  if (!appConfig && !configError) {
    return (
      <div className="flex items-center justify-center min-h-screen gap-3 text-slate">
        <Spinner size={20} className="text-brand" />
        <span className="text-sm">Loading…</span>
      </div>
    )
  }

  if (configError) {
    return (
      <div className="max-w-lg mx-auto px-6 py-16">
        <div className="rounded-xl border border-fail/20 bg-fail/5 p-5 text-sm text-fail space-y-2">
          <p className="font-medium">Failed to load configuration</p>
          <p className="opacity-80">{configError}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      {phase === 'config' && (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Run evaluation</h1>
            <p className="text-sm text-slate mt-1">
              Evaluate an AI target against structured test suites and map results to compliance controls.
            </p>
          </div>
          <div className="bg-white border border-line rounded-2xl p-6">
            <EvalForm config={appConfig!} onSubmit={handleRun} />
          </div>
        </div>
      )}

      {phase === 'running' && (
        <RunningState progress={progress} currentStage={currentStage} />
      )}

      {phase === 'report' && report && (
        <ReportView report={report} onRunAgain={handleReset} />
      )}

      {phase === 'error' && (
        <div className="space-y-4 py-12">
          <div className="rounded-xl border border-fail/20 bg-fail/5 p-5 text-sm text-fail space-y-2">
            <p className="font-medium">Evaluation failed</p>
            <p className="opacity-80 font-mono text-xs">{runError}</p>
          </div>
          <button
            onClick={handleReset}
            className="text-sm font-medium text-brand hover:underline focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none rounded"
          >
            ← Try again
          </button>
        </div>
      )}
    </div>
  )
}
