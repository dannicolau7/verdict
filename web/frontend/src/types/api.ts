// Mirror of web/backend/models/api_models.py — keep in sync.

export interface CategoryStats {
  total: number
  passed: number
  failed: number
  pass_rate: number
  failure_modes: Record<string, number>
  critical_failures: string[]
}

export interface EvalReport {
  run_id: string
  target_system: string
  total_tests: number
  pass_rate: number
  pass_rate_ci_low: number | null
  pass_rate_ci_high: number | null
  bootstrap_iterations: number | null
  category_breakdown: Record<string, CategoryStats>
  timestamp: string
  verdict_version: string | null
  cost_breakdown: {
    target?: { input_tokens: number; output_tokens: number; estimated_cost_usd: number | null }
    harness?: { estimated_cost_usd: number | null }
    total_cost_usd?: number | null
    [key: string]: unknown
  } | null
}

export interface ConfigResponse {
  categories: string[]
  attack_families: string[]
  judge_models: string[]
  default_judge_model: string
}

export interface EvalRunRequest {
  target: string
  categories: string[]
  attack_mode: 'standard' | 'adaptive'
  enable_ci: boolean
  enable_flakiness: boolean
  judge_model: string
  num_per_category: number
  custom_prompts: string[]
  custom_category: string
}

export type EvalEvent =
  | { type: 'progress'; stage: string; detail: string }
  | { type: 'complete'; report: EvalReport }
  | { type: 'error'; message: string }

export interface RunListItem {
  run_id: string
  target_system: string
  timestamp: string
  pass_rate: number
  total_tests: number
  label: string | null
}

export interface LabelRequest {
  label: string | null
}

export interface DiffCompareRequest {
  run_id_a: string
  run_id_b: string
}

export interface CategoryDiff {
  category: string
  a_pass_rate: number | null
  b_pass_rate: number | null
  delta: number | null
  a_total: number
  b_total: number
}

export interface DiffCompareResponse {
  run_id_a: string
  run_id_b: string
  target_a: string
  target_b: string
  timestamp_a: string
  timestamp_b: string
  a_pass_rate: number
  b_pass_rate: number
  pass_rate_delta: number
  a_total_tests: number
  b_total_tests: number
  categories: CategoryDiff[]
}

export interface DiffRunRequest {
  model_a: string
  model_b: string
  categories: string[]
  num_per_category: number
  judge_model: string
}

export interface PerPromptRow {
  prompt_id: string
  prompt_text: string
  category: string
  severity: string
  a_passed: boolean
  b_passed: boolean
  a_failure_mode: string | null
  b_failure_mode: string | null
  a_reasoning: string
  b_reasoning: string
}

export interface DiffRunResponse {
  run_id: string
  model_a: string
  model_b: string
  timestamp: string
  total_tests: number
  a_pass_rate: number
  b_pass_rate: number
  pass_rate_delta: number
  regression_count: number
  improvement_count: number
  unchanged: number
  categories: CategoryDiff[]
  regressions: PerPromptRow[]
  improvements: PerPromptRow[]
}

export type DiffRunEvent =
  | { type: 'progress'; stage: string; detail: string }
  | { type: 'complete'; result: DiffRunResponse }
  | { type: 'error'; message: string }

// ---------------------------------------------------------------------------
// Trace evaluation
// ---------------------------------------------------------------------------

export interface TraceStepOut {
  step_id: number
  step_type: 'llm_call' | 'tool_call' | 'tool_result' | 'observation' | 'final_answer'
  tool_name: string | null
  tool_arguments: Record<string, unknown> | null
  tool_result: string | null
  llm_input: string | null
  llm_output: string | null
  latency_ms: number | null
  error: string | null
}

export interface AgentTraceOut {
  trace_id: string
  agent_name: string
  task: string
  expected_behavior: string
  tools_available: string[]
  steps: TraceStepOut[]
  final_output: string | null
  total_latency_ms: number | null
  timestamp: string
}

export interface StepJudgmentOut {
  step_id: number
  passed: boolean
  score: number | null
  reasoning: string
  failure_mode: string | null
}

export interface TraceJudgmentOut {
  trace_id: string
  overall_passed: boolean
  overall_score: number | null
  reasoning: string
  step_judgments: StepJudgmentOut[]
  failure_modes: string[]
  judge_model: string
}

export interface TraceEvalReportOut {
  run_id: string
  agent_name: string
  total_traces: number
  pass_rate: number
  pass_rate_ci_low: number | null
  pass_rate_ci_high: number | null
  bootstrap_iterations: number | null
  failure_mode_counts: Record<string, number>
  trace_judgments: TraceJudgmentOut[]
  timestamp: string
  verdict_version: string | null
}

export type TraceEvalEvent =
  | { type: 'parse'; detail: string }
  | { type: 'judge'; detail: string }
  | { type: 'build'; detail: string }
  | { type: 'complete'; report: TraceEvalReportOut; traces: AgentTraceOut[] }
  | { type: 'error'; message: string }

export interface TraceRunRequest {
  judge_model: string
}

// ---------------------------------------------------------------------------
// Compliance
// ---------------------------------------------------------------------------

export interface ComplianceRequest {
  run_id: string
  frameworks: ('hipaa' | 'nist')[]
}

export interface ControlEvidence {
  source: string
  tests_run: number
  tests_passed: number
  pass_rate: number
  ci_low: number
  ci_high: number
  evidence_strength: string
  flakiness_flag: boolean
  notable_failure_modes: string[]
}

export interface ControlResult {
  id: string
  framework: string
  function: string
  title: string
  description: string
  reference: string
  overall_status: 'pass' | 'partial' | 'fail' | 'insufficient_data'
  overall_pass_rate: number | null
  overall_ci_low: number | null
  overall_ci_high: number | null
  confidence: string
  flakiness_flag: boolean
  evidence: ControlEvidence[]
}

export interface ComplianceArtifact {
  artifact_id: string
  schema_version: string
  generated_at: string
  eval_run: {
    run_id: string
    target_system: string
    total_tests: number
    pass_rate: number
    timestamp: string
  }
  controls: ControlResult[]
}

export interface ComplianceResponse {
  artifact: ComplianceArtifact
  markdown: string
}
