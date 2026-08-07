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
  cost_breakdown: Record<string, unknown> | null
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
}

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
