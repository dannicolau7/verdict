/**
 * Verdict API client.
 *
 * ┌─────────────────────────────────────────────────────────────────┐
 * │  MOCK BOUNDARY — flip this one constant to go live             │
 * │                                                                 │
 * │  MOCK_MODE = true   →  realistic mock data, no backend needed  │
 * │  MOCK_MODE = false  →  real FastAPI backend at /api/*          │
 * └─────────────────────────────────────────────────────────────────┘
 */

import type {
  CategoryDiff,
  ComplianceRequest,
  ComplianceResponse,
  ConfigResponse,
  DiffCompareRequest,
  DiffCompareResponse,
  EvalEvent,
  EvalReport,
  EvalRunRequest,
  LabelRequest,
  RunListItem,
} from '../types/api'

const MOCK_MODE = true // ← the only line to change

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_REPORT: EvalReport = {
  run_id: 'b4e2f1a0-8c3d-4e5f-9b2a-1c3d5e7f9a0b',
  target_system: 'SimpleRAG',
  total_tests: 25,
  pass_rate: 0.72,
  pass_rate_ci_low: 0.54,
  pass_rate_ci_high: 0.86,
  bootstrap_iterations: 1000,
  category_breakdown: {
    correctness: { total: 5, passed: 4, failed: 1, pass_rate: 0.8,  failure_modes: { hallucination: 1 },                           critical_failures: [] },
    safety:      { total: 5, passed: 5, failed: 0, pass_rate: 1.0,  failure_modes: {},                                             critical_failures: [] },
    injection:   { total: 5, passed: 3, failed: 2, pass_rate: 0.6,  failure_modes: { prompt_injection_success: 2 },                critical_failures: ['p-i1', 'p-i2'] },
    edge_case:   { total: 5, passed: 3, failed: 2, pass_rate: 0.6,  failure_modes: { format_error: 1, hallucination: 1 },         critical_failures: [] },
    compliance:  { total: 5, passed: 3, failed: 2, pass_rate: 0.6,  failure_modes: { pii_leak: 1, compliance_violation: 1 },      critical_failures: ['p-c1'] },
  },
  timestamp: new Date().toISOString(),
  verdict_version: '0.3.1',
  cost_breakdown: null,
}

const MOCK_CONFIG: ConfigResponse = {
  categories: ['correctness', 'safety', 'injection', 'edge_case', 'compliance'],
  attack_families: ['standard', 'adaptive'],
  judge_models: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'],
  default_judge_model: 'claude-sonnet-4-6',
}

const MOCK_RUNS: RunListItem[] = [
  { run_id: MOCK_REPORT.run_id, target_system: 'SimpleRAG', timestamp: MOCK_REPORT.timestamp, pass_rate: 0.72, total_tests: 25, label: null },
  { run_id: 'prev-run-001',     target_system: 'SimpleRAG', timestamp: new Date(Date.now() - 86_400_000).toISOString(), pass_rate: 0.68, total_tests: 25, label: 'before fix' },
  { run_id: 'prev-run-002',     target_system: 'SimpleRAG', timestamp: new Date(Date.now() - 172_800_000).toISOString(), pass_rate: 0.80, total_tests: 25, label: null },
]

const MOCK_COMPLIANCE: ComplianceResponse = {
  artifact: {
    artifact_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    schema_version: '1.0',
    generated_at: new Date().toISOString(),
    eval_run: { run_id: MOCK_REPORT.run_id, target_system: 'SimpleRAG', total_tests: 25, pass_rate: 0.72, timestamp: MOCK_REPORT.timestamp },
    controls: [
      {
        id: 'HIPAA-164.306(a)(2)', framework: 'HIPAA Security Rule', function: 'General',
        title: 'Protection from reasonably anticipated threats',
        description: 'Covered entities must protect against any reasonably anticipated threats or hazards to the security or integrity of ePHI.',
        reference: '45 CFR § 164.306(a)(2)',
        overall_status: 'partial', overall_pass_rate: 0.8, overall_ci_low: 0.49, overall_ci_high: 0.94, confidence: 'moderate', flakiness_flag: false,
        evidence: [
          { source: 'category:safety',    tests_run: 5, tests_passed: 5, pass_rate: 1.0, ci_low: 0.61, ci_high: 1.0,  evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: [] },
          { source: 'category:injection', tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2,  ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['prompt_injection_success'] },
        ],
      },
      {
        id: 'HIPAA-164.308(a)(1)(ii)(A)', framework: 'HIPAA Security Rule', function: 'Administrative',
        title: 'Risk Analysis',
        description: 'Conduct an accurate and thorough assessment of the potential risks and vulnerabilities to the confidentiality, integrity, and availability of ePHI.',
        reference: '45 CFR § 164.308(a)(1)(ii)(A)',
        overall_status: 'partial', overall_pass_rate: 0.6, overall_ci_low: 0.34, overall_ci_high: 0.82, confidence: 'low', flakiness_flag: false,
        evidence: [
          { source: 'category:compliance', tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2, ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['pii_leak'] },
        ],
      },
      {
        id: 'HIPAA-164.308(a)(5)(ii)(B)', framework: 'HIPAA Security Rule', function: 'Administrative',
        title: 'Protection from Malicious Software',
        description: 'Implement procedures for guarding against, detecting, and reporting malicious software. Prompt injection attacks are the functional equivalent in LLM pipelines.',
        reference: '45 CFR § 164.308(a)(5)(ii)(B)',
        overall_status: 'partial', overall_pass_rate: 0.6, overall_ci_low: 0.2, overall_ci_high: 0.88, confidence: 'low', flakiness_flag: false,
        evidence: [
          { source: 'category:injection', tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2, ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['prompt_injection_success'] },
        ],
      },
      {
        id: 'HIPAA-164.312(a)(1)', framework: 'HIPAA Security Rule', function: 'Technical',
        title: 'Access Control',
        description: 'Implement technical policies and procedures that allow only authorized persons or software programs to access ePHI.',
        reference: '45 CFR § 164.312(a)(1)',
        overall_status: 'insufficient_data', overall_pass_rate: null, overall_ci_low: null, overall_ci_high: null, confidence: 'low', flakiness_flag: false,
        evidence: [],
      },
      {
        id: 'HIPAA-164.312(e)(2)(ii)', framework: 'HIPAA Security Rule', function: 'Technical',
        title: 'Encryption and Decryption',
        description: 'Implement a mechanism to encrypt and decrypt ePHI.',
        reference: '45 CFR § 164.312(e)(2)(ii)',
        overall_status: 'insufficient_data', overall_pass_rate: null, overall_ci_low: null, overall_ci_high: null, confidence: 'low', flakiness_flag: false,
        evidence: [],
      },
      {
        id: 'NIST-MEASURE-2.5', framework: 'NIST AI RMF', function: 'MEASURE',
        title: 'The AI system to be deployed is demonstrated to be valid and reliable through tools and techniques such as external audits, red-teaming, or assessments by domain experts.',
        description: 'Correctness and edge_case test categories provide evidence relevant to output validity.',
        reference: 'NIST AI RMF 1.0 — MEASURE 2.5',
        overall_status: 'pass', overall_pass_rate: 0.80, overall_ci_low: 0.59, overall_ci_high: 0.93, confidence: 'moderate', flakiness_flag: false,
        evidence: [
          { source: 'category:correctness', tests_run: 5, tests_passed: 4, pass_rate: 0.8, ci_low: 0.38, ci_high: 0.97, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['hallucination'] },
          { source: 'category:edge_case',   tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2,  ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['format_error'] },
        ],
      },
      {
        id: 'NIST-MEASURE-2.7', framework: 'NIST AI RMF', function: 'MEASURE',
        title: 'AI system security and resilience – as identified in the MAP function – are evaluated and documented.',
        description: 'Injection and compliance test categories provide evidence relevant to resilience against adversarial inputs.',
        reference: 'NIST AI RMF 1.0 — MEASURE 2.7',
        overall_status: 'partial', overall_pass_rate: 0.7, overall_ci_low: 0.5, overall_ci_high: 0.85, confidence: 'moderate', flakiness_flag: false,
        evidence: [
          { source: 'category:injection', tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2,  ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['prompt_injection_success'] },
          { source: 'category:safety',    tests_run: 5, tests_passed: 5, pass_rate: 1.0, ci_low: 0.61, ci_high: 1.0,  evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: [] },
        ],
      },
      {
        id: 'NIST-MEASURE-4.1', framework: 'NIST AI RMF', function: 'MEASURE',
        title: 'Measurement approaches for identifying AI risks are connected to deployment context(s) and informed by risk categories identified and prioritized in the MAP function.',
        description: 'Every Verdict run produces a JSON artifact with run_id, timestamp, per-control evidence, CIs, and provenance.',
        reference: 'NIST AI RMF 1.0 — MEASURE 4.1',
        overall_status: 'pass', overall_pass_rate: 0.76, overall_ci_low: 0.58, overall_ci_high: 0.90, confidence: 'high', flakiness_flag: false,
        evidence: [
          { source: 'category:correctness', tests_run: 5, tests_passed: 4, pass_rate: 0.8, ci_low: 0.38, ci_high: 0.97, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: [] },
          { source: 'category:safety',      tests_run: 5, tests_passed: 5, pass_rate: 1.0, ci_low: 0.61, ci_high: 1.0,  evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: [] },
          { source: 'category:injection',   tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2,  ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['prompt_injection_success'] },
          { source: 'category:compliance',  tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2,  ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['pii_leak'] },
        ],
      },
      {
        id: 'NIST-MANAGE-1.3', framework: 'NIST AI RMF', function: 'MANAGE',
        title: 'Responses to the AI risks deemed high priority, as identified by the MAP function, are developed, planned, and documented.',
        description: 'Safety category failures surface as critical_failures in the audit artifact to drive prioritised response.',
        reference: 'NIST AI RMF 1.0 — MANAGE 1.3',
        overall_status: 'fail', overall_pass_rate: 0.4, overall_ci_low: 0.14, overall_ci_high: 0.7, confidence: 'low', flakiness_flag: false,
        evidence: [
          { source: 'category:safety',      tests_run: 5, tests_passed: 5, pass_rate: 1.0, ci_low: 0.61, ci_high: 1.0,  evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: [] },
          { source: 'category:compliance',  tests_run: 5, tests_passed: 3, pass_rate: 0.6, ci_low: 0.2,  ci_high: 0.88, evidence_strength: 'moderate', flakiness_flag: false, notable_failure_modes: ['compliance_violation'] },
          { source: 'failure_mode:compliance_when_should_refuse', tests_run: 5, tests_passed: 1, pass_rate: 0.2, ci_low: 0.01, ci_high: 0.6, evidence_strength: 'low', flakiness_flag: false, notable_failure_modes: ['compliance_when_should_refuse'] },
        ],
      },
      {
        id: 'NIST-MANAGE-2.2', framework: 'NIST AI RMF', function: 'MANAGE',
        title: 'Mechanisms are in place and applied to sustain the value of deployed AI systems.',
        description: 'Continuous evaluation via Verdict — differential testing, flakiness detection, adaptive attack composition — provides evidence relevant to operational mechanisms.',
        reference: 'NIST AI RMF 1.0 — MANAGE 2.2',
        overall_status: 'insufficient_data', overall_pass_rate: null, overall_ci_low: null, overall_ci_high: null, confidence: 'low', flakiness_flag: false,
        evidence: [],
      },
    ],
  },
  markdown: '# Compliance Report\n\nThis is a placeholder markdown report.',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const delay = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

async function* parseSSEStream(response: Response): AsyncGenerator<EvalEvent> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const raw = line.slice(6).trim()
        if (raw) yield JSON.parse(raw) as EvalEvent
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Public API — identical signatures in both modes
// ---------------------------------------------------------------------------

export async function fetchConfig(): Promise<ConfigResponse> {
  if (MOCK_MODE) {
    await delay(200)
    return MOCK_CONFIG
  }
  const res = await fetch('/api/config')
  if (!res.ok) throw new Error(`Config fetch failed: ${res.status}`)
  return res.json() as Promise<ConfigResponse>
}

export async function* runEval(req: EvalRunRequest): AsyncGenerator<EvalEvent> {
  if (MOCK_MODE) {
    const steps = [
      { stage: 'generate',  detail: `Generating ${req.num_per_category} test prompts per category…` },
      { stage: 'execute',   detail: 'Executing against SimpleRAG adapter…' },
      { stage: 'judge',     detail: 'Judging results with ' + req.judge_model + '…' },
      { stage: 'report',    detail: 'Building evaluation report…' },
    ]
    for (const s of steps) {
      await delay(900)
      yield { type: 'progress', stage: s.stage, detail: s.detail }
    }
    await delay(600)
    // Return a report shaped by the requested categories
    const report: EvalReport = {
      ...MOCK_REPORT,
      run_id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      category_breakdown: Object.fromEntries(
        req.categories.map(cat => [cat, MOCK_REPORT.category_breakdown[cat] ?? MOCK_REPORT.category_breakdown['correctness']])
      ),
      total_tests: req.categories.length * req.num_per_category,
    }
    yield { type: 'complete', report }
    return
  }

  const res = await fetch('/api/eval/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    yield { type: 'error', message: (err as { detail: string }).detail }
    return
  }
  yield* parseSSEStream(res)
}

export async function generateCompliance(req: ComplianceRequest): Promise<ComplianceResponse> {
  if (MOCK_MODE) {
    await delay(800)
    return {
      ...MOCK_COMPLIANCE,
      artifact: {
        ...MOCK_COMPLIANCE.artifact,
        artifact_id: crypto.randomUUID(),
        generated_at: new Date().toISOString(),
        eval_run: { ...MOCK_COMPLIANCE.artifact.eval_run, run_id: req.run_id },
      },
    }
  }
  const res = await fetch('/api/compliance/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail: string }).detail)
  }
  return res.json() as Promise<ComplianceResponse>
}

export async function setRunLabel(runId: string, req: LabelRequest): Promise<RunListItem> {
  if (MOCK_MODE) {
    await delay(150)
    const run = MOCK_RUNS.find(r => r.run_id === runId)
    if (!run) throw new Error(`Run ${runId} not found`)
    run.label = req.label
    return { ...run }
  }
  const res = await fetch(`/api/runs/${runId}/label`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail: string }).detail)
  }
  return res.json() as Promise<RunListItem>
}

export async function fetchRuns(): Promise<RunListItem[]> {
  if (MOCK_MODE) {
    await delay(300)
    return MOCK_RUNS
  }
  const res = await fetch('/api/runs')
  if (!res.ok) throw new Error(`Runs fetch failed: ${res.status}`)
  return res.json() as Promise<RunListItem[]>
}

export async function compareRuns(req: DiffCompareRequest): Promise<DiffCompareResponse> {
  if (MOCK_MODE) {
    await delay(500)
    const runA = MOCK_RUNS.find(r => r.run_id === req.run_id_a) ?? MOCK_RUNS[1]
    const runB = MOCK_RUNS.find(r => r.run_id === req.run_id_b) ?? MOCK_RUNS[0]
    const CATS = ['correctness', 'safety', 'injection', 'edge_case', 'compliance']
    const ratesA = [0.8, 1.0, 0.6, 0.6, 0.6]
    const ratesB = [0.8, 0.8, 0.8, 0.4, 0.8]
    const categories: CategoryDiff[] = CATS.map((cat, i) => ({
      category: cat,
      a_pass_rate: ratesA[i],
      b_pass_rate: ratesB[i],
      delta: Math.round((ratesB[i] - ratesA[i]) * 100) / 100,
      a_total: 5,
      b_total: 5,
    }))
    return {
      run_id_a: runA.run_id,
      run_id_b: runB.run_id,
      target_a: runA.target_system,
      target_b: runB.target_system,
      timestamp_a: runA.timestamp,
      timestamp_b: runB.timestamp,
      a_pass_rate: runA.pass_rate,
      b_pass_rate: runB.pass_rate,
      pass_rate_delta: Math.round((runB.pass_rate - runA.pass_rate) * 100) / 100,
      a_total_tests: runA.total_tests,
      b_total_tests: runB.total_tests,
      categories,
    }
  }
  const res = await fetch('/api/diff/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error((err as { detail: string }).detail)
  }
  return res.json() as Promise<DiffCompareResponse>
}

export async function fetchRun(runId: string): Promise<EvalReport> {
  if (MOCK_MODE) {
    await delay(200)
    if (runId === MOCK_REPORT.run_id) return MOCK_REPORT
    throw new Error(`Run ${runId} not found`)
  }
  const res = await fetch(`/api/runs/${runId}`)
  if (!res.ok) throw new Error(`Run ${runId} not found`)
  return res.json() as Promise<EvalReport>
}
