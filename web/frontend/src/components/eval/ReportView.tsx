import { useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import type { ComplianceResponse, EvalReport } from '../../types/api'
import { EvidenceArc } from '../report/EvidenceArc'
import { CategoryBreakdown } from '../report/CategoryBreakdown'
import { FailureModeTags } from '../report/FailureModeTags'
import { ComplianceTable } from '../report/ComplianceTable'
import { Spinner } from '../ui/Spinner'
import * as api from '../../api/client'
import { downloadReportJson, downloadReportMarkdown } from '../../utils/export'

interface ReportViewProps {
  report: EvalReport
  onRunAgain: () => void
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold text-slate uppercase tracking-wide">{title}</h3>
      {children}
    </div>
  )
}

export function ReportView({ report, onRunAgain }: ReportViewProps) {
  const [compliance, setCompliance] = useState<ComplianceResponse | null>(null)
  const [loadingCompliance, setLoadingCompliance] = useState(false)
  const [complianceError, setComplianceError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('overview')

  const allFailureModes: Record<string, number> = {}
  for (const stats of Object.values(report.category_breakdown)) {
    for (const [mode, count] of Object.entries(stats.failure_modes)) {
      allFailureModes[mode] = (allFailureModes[mode] ?? 0) + count
    }
  }

  const ts = new Date(report.timestamp).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

  const handleComplianceTabClick = async () => {
    setActiveTab('compliance')
    if (compliance || loadingCompliance) return
    setLoadingCompliance(true)
    setComplianceError(null)
    try {
      const result = await api.generateCompliance({ run_id: report.run_id, frameworks: ['hipaa', 'nist'] })
      setCompliance(result)
    } catch (e) {
      setComplianceError(String(e))
    } finally {
      setLoadingCompliance(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      {/* Run header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-ink">{report.target_system}</h2>
          <p className="text-sm text-slate mt-0.5">
            <span className="font-mono">{report.run_id.slice(0, 8)}</span>
            {' · '}{ts}
            {report.verdict_version && <span className="ml-2 opacity-50">v{report.verdict_version}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => downloadReportJson(report)}
            title="Download JSON"
            className="text-sm font-medium text-slate border border-line rounded-lg px-3 py-1.5
              hover:bg-white transition-colors
              focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
          >
            ↓ JSON
          </button>
          <button
            onClick={() => downloadReportMarkdown(report)}
            title="Download Markdown"
            className="text-sm font-medium text-slate border border-line rounded-lg px-3 py-1.5
              hover:bg-white transition-colors
              focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
          >
            ↓ MD
          </button>
          <button
            onClick={onRunAgain}
            className="text-sm font-medium text-slate border border-line rounded-lg px-3 py-1.5
              hover:bg-white transition-colors
              focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
          >
            Run again
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs.Root value={activeTab} onValueChange={v => v === 'compliance' ? handleComplianceTabClick() : setActiveTab(v)}>
        <Tabs.List className="flex gap-0 border-b border-line" aria-label="Report sections">
          {(['overview', 'compliance'] as const).map(tab => (
            <Tabs.Trigger
              key={tab}
              value={tab}
              className="relative px-4 py-2.5 text-sm font-medium capitalize text-slate transition-colors
                hover:text-ink
                data-[state=active]:text-brand
                focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none
                after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5
                after:rounded-full after:bg-brand after:scale-x-0 data-[state=active]:after:scale-x-100
                after:transition-transform"
            >
              {tab}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {/* Overview tab */}
        <Tabs.Content value="overview" className="pt-6 space-y-8 focus:outline-none">
          {/* Arc + stats */}
          <div className="flex items-center gap-8 flex-wrap">
            <EvidenceArc
              passRate={report.pass_rate}
              ciLow={report.pass_rate_ci_low}
              ciHigh={report.pass_rate_ci_high}
              size={140}
            />
            <div className="space-y-1">
              <p className="text-4xl font-bold text-ink tabular-nums">
                {Math.round(report.pass_rate * 100)}%
              </p>
              <p className="text-sm text-slate">
                {report.total_tests} tests · {Math.round(report.pass_rate * report.total_tests)} passed
              </p>
              {report.pass_rate_ci_low != null && report.pass_rate_ci_high != null && (
                <p className="text-xs text-slate/70">
                  95% CI: {Math.round(report.pass_rate_ci_low * 100)}%–{Math.round(report.pass_rate_ci_high * 100)}%
                </p>
              )}
            </div>
          </div>

          <Section title="By category">
            <div className="bg-white border border-line rounded-xl p-4">
              <CategoryBreakdown breakdown={report.category_breakdown} />
            </div>
          </Section>

          <Section title="Failure modes">
            <FailureModeTags failureModes={allFailureModes} />
          </Section>
        </Tabs.Content>

        {/* Compliance tab */}
        <Tabs.Content value="compliance" className="pt-6 focus:outline-none">
          {loadingCompliance && (
            <div className="flex items-center gap-3 text-slate py-12 justify-center">
              <Spinner size={18} className="text-brand" />
              <span className="text-sm">Mapping to compliance controls…</span>
            </div>
          )}
          {complianceError && (
            <div className="rounded-xl border border-fail/20 bg-fail/5 p-4 text-sm text-fail">
              {complianceError}
            </div>
          )}
          {compliance && (
            <ComplianceTable artifact={compliance.artifact} markdown={compliance.markdown} />
          )}
        </Tabs.Content>
      </Tabs.Root>
    </div>
  )
}
