import { useEffect, useRef } from 'react'
import { EvidenceArc } from '../report/EvidenceArc'

interface ProgressLine {
  stage: string
  detail: string
}

const STAGE_LABELS: Record<string, string> = {
  generate: 'Generating',
  execute:  'Executing',
  adaptive: 'Probing',
  judge:    'Judging',
  report:   'Building report',
}

interface RunningStateProps {
  progress: ProgressLine[]
  currentStage: string
}

export function RunningState({ progress, currentStage }: RunningStateProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [progress.length])

  return (
    <div className="flex flex-col items-center justify-center min-h-[480px] py-12 gap-8">
      {/* Arc */}
      <div className="relative">
        <EvidenceArc passRate={0} indeterminate size={128} />
        <p className="absolute inset-0 flex items-center justify-center text-xs font-medium text-brand/60 mt-6">
          running
        </p>
      </div>

      {/* Stage label */}
      <div className="text-center space-y-1">
        <p className="text-base font-semibold text-ink">
          {STAGE_LABELS[currentStage] ?? 'Running evaluation'}
        </p>
        {progress.length > 0 && (
          <p className="text-sm text-slate">{progress[progress.length - 1]?.detail}</p>
        )}
      </div>

      {/* Log lines */}
      {progress.length > 0 && (
        <div className="w-full max-w-md bg-white border border-line rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-line flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-pass animate-pulse" />
            <span className="text-xs text-slate font-medium">Evaluation log</span>
          </div>
          <div className="px-4 py-3 space-y-2 max-h-48 overflow-y-auto scrollbar-thin">
            {progress.map((p, i) => (
              <div key={i} className="flex items-start gap-2 text-sm animate-fade-up">
                <span className="text-pass mt-0.5 flex-shrink-0 text-xs">✓</span>
                <span className="text-ink/80">{p.detail}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </div>
  )
}
