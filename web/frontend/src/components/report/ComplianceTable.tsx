import { useState } from 'react'
import type { ComplianceArtifact, ControlResult } from '../../types/api'
import { Badge } from '../ui/Badge'

interface ComplianceTableProps {
  artifact: ComplianceArtifact
  markdown: string
}

function download(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function ControlRow({ ctrl }: { ctrl: ControlResult }) {
  const [open, setOpen] = useState(false)
  const hasEvidence = ctrl.evidence.length > 0

  return (
    <div className="border border-line rounded-lg overflow-hidden">
      {/* Header row */}
      <button
        className="w-full flex items-start gap-3 p-4 text-left hover:bg-white/70 transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <div className="pt-0.5 flex-shrink-0">
          <Badge status={ctrl.overall_status} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-slate">{ctrl.id}</span>
            {ctrl.overall_pass_rate != null && (
              <span className="text-xs text-slate">
                {Math.round(ctrl.overall_pass_rate * 100)}%
                {ctrl.overall_ci_low != null && ctrl.overall_ci_high != null && (
                  <span className="text-slate/60 ml-1">
                    CI {Math.round(ctrl.overall_ci_low * 100)}–{Math.round(ctrl.overall_ci_high * 100)}%
                  </span>
                )}
              </span>
            )}
          </div>
          <p className="text-sm text-ink mt-0.5 leading-snug line-clamp-2">{ctrl.title}</p>
        </div>
        <span className="text-slate text-sm flex-shrink-0 pt-0.5">{open ? '−' : '+'}</span>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-line bg-cloud px-4 py-3 space-y-3">
          <p className="text-xs text-slate leading-relaxed">{ctrl.description}</p>
          <p className="text-xs text-slate/60 font-mono">{ctrl.reference}</p>

          {hasEvidence ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line">
                    <th className="text-left py-1.5 pr-3 font-medium text-slate">Source</th>
                    <th className="text-right py-1.5 pr-3 font-medium text-slate">Tests</th>
                    <th className="text-right py-1.5 pr-3 font-medium text-slate">Passed</th>
                    <th className="text-right py-1.5 pr-3 font-medium text-slate">Rate</th>
                    <th className="text-left py-1.5 font-medium text-slate">Strength</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/40">
                  {ctrl.evidence.map((ev, i) => (
                    <tr key={i}>
                      <td className="py-1.5 pr-3 font-mono text-ink/80 max-w-[180px] truncate">{ev.source}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-slate">{ev.tests_run}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-slate">{ev.tests_passed}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums text-ink">{Math.round(ev.pass_rate * 100)}%</td>
                      <td className="py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          ev.evidence_strength === 'high'     ? 'bg-pass/10 text-pass' :
                          ev.evidence_strength === 'moderate' ? 'bg-brand/10 text-brand' :
                                                                'bg-slate/10 text-slate'
                        }`}>
                          {ev.evidence_strength}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-slate/60 italic">
              No evidence from this evaluation. Run with relevant categories to generate evidence for this control.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function FrameworkSection({ name, controls }: { name: string; controls: ControlResult[] }) {
  const counts = {
    pass:              controls.filter(c => c.overall_status === 'pass').length,
    partial:           controls.filter(c => c.overall_status === 'partial').length,
    fail:              controls.filter(c => c.overall_status === 'fail').length,
    insufficient_data: controls.filter(c => c.overall_status === 'insufficient_data').length,
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">{name}</h3>
        <div className="flex gap-2 text-xs text-slate">
          {counts.pass > 0              && <span className="text-pass font-medium">{counts.pass} pass</span>}
          {counts.partial > 0           && <span className="text-caution font-medium">{counts.partial} partial</span>}
          {counts.fail > 0              && <span className="text-fail font-medium">{counts.fail} fail</span>}
          {counts.insufficient_data > 0 && <span>{counts.insufficient_data} insufficient</span>}
        </div>
      </div>
      <div className="space-y-2">
        {controls.map(ctrl => <ControlRow key={ctrl.id} ctrl={ctrl} />)}
      </div>
    </div>
  )
}

export function ComplianceTable({ artifact, markdown }: ComplianceTableProps) {
  const byFramework: Record<string, ControlResult[]> = {}
  for (const ctrl of artifact.controls) {
    if (!byFramework[ctrl.framework]) byFramework[ctrl.framework] = []
    byFramework[ctrl.framework].push(ctrl)
  }

  const allStatuses = artifact.controls.map(c => c.overall_status)
  const summary = {
    pass:    allStatuses.filter(s => s === 'pass').length,
    partial: allStatuses.filter(s => s === 'partial').length,
    fail:    allStatuses.filter(s => s === 'fail').length,
    insuf:   allStatuses.filter(s => s === 'insufficient_data').length,
  }

  return (
    <div className="space-y-6">
      {/* Summary + downloads */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-4 text-sm">
          <span><span className="font-semibold text-pass">{summary.pass}</span> <span className="text-slate">pass</span></span>
          <span><span className="font-semibold text-caution">{summary.partial}</span> <span className="text-slate">partial</span></span>
          <span><span className="font-semibold text-fail">{summary.fail}</span> <span className="text-slate">fail</span></span>
          <span><span className="font-semibold text-slate">{summary.insuf}</span> <span className="text-slate">insufficient</span></span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => download(JSON.stringify(artifact, null, 2), `compliance_${artifact.eval_run.run_id.slice(0, 8)}.json`, 'application/json')}
            className="text-xs font-medium text-brand border border-brand/30 rounded-lg px-3 py-1.5 hover:bg-brand/5 transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
          >
            Download JSON
          </button>
          <button
            onClick={() => download(markdown, `compliance_${artifact.eval_run.run_id.slice(0, 8)}.md`, 'text/markdown')}
            className="text-xs font-medium text-slate border border-line rounded-lg px-3 py-1.5 hover:bg-white transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
          >
            Download Markdown
          </button>
        </div>
      </div>

      {/* Per-framework sections */}
      {Object.entries(byFramework).map(([fw, ctrls]) => (
        <FrameworkSection key={fw} name={fw} controls={ctrls} />
      ))}
    </div>
  )
}
