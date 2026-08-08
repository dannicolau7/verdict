import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { ConfigResponse, EvalRunRequest } from '../../types/api'
import { CategorySelect } from './CategorySelect'
import { Spinner } from '../ui/Spinner'

interface EvalFormProps {
  config: ConfigResponse
  onSubmit: (req: EvalRunRequest) => void
  loading?: boolean
}

const DEFAULT_REQ = (config: ConfigResponse): EvalRunRequest => ({
  target: 'simple_rag',
  categories: [...config.categories],
  attack_mode: 'standard',
  enable_ci: true,
  enable_flakiness: false,
  judge_model: config.default_judge_model,
  num_per_category: 5,
  custom_prompts: [],
  custom_category: 'correctness',
})

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4 cursor-pointer group">
      <span className="text-sm text-ink">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative w-9 h-5 rounded-full transition-colors flex-shrink-0 focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none ${
          checked ? 'bg-brand' : 'bg-line'
        }`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${checked ? 'translate-x-4' : ''}`} />
      </button>
    </label>
  )
}

function SegmentedControl({
  options, value, onChange,
}: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex rounded-lg border border-line overflow-hidden" role="group">
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`flex-1 px-3 py-1.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand focus-visible:outline-none ${
            value === opt.value
              ? 'bg-brand text-white'
              : 'bg-white text-slate hover:text-ink hover:bg-cloud'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

export function EvalForm({ config, onSubmit, loading = false }: EvalFormProps) {
  const [req, setReq] = useState<EvalRunRequest>(() => DEFAULT_REQ(config))
  const [advOpen, setAdvOpen] = useState(false)

  const pinnedCount = req.custom_prompts.filter(p => p.trim()).length
  const totalTests = req.categories.length * req.num_per_category + pinnedCount

  const set = <K extends keyof EvalRunRequest>(k: K, v: EvalRunRequest[K]) =>
    setReq(r => ({ ...r, [k]: v }))

  return (
    <form
      onSubmit={e => { e.preventDefault(); onSubmit(req) }}
      className="space-y-6"
    >
      {/* Target */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-ink" htmlFor="target">
          Target system
        </label>
        <select
          id="target"
          value={req.target}
          onChange={e => set('target', e.target.value)}
          disabled
          className="w-full rounded-lg border border-line bg-cloud px-3 py-2 text-sm text-ink
            disabled:opacity-60 disabled:cursor-not-allowed
            focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
        >
          <option value="simple_rag">SimpleRAG</option>
        </select>
        <p className="text-xs text-slate/60">More adapters coming in a future release.</p>
      </div>

      {/* Categories */}
      <div className="space-y-2">
        <label className="text-sm font-medium text-ink">Test categories</label>
        <CategorySelect
          available={config.categories}
          selected={req.categories}
          onChange={cats => set('categories', cats)}
        />
        {req.categories.length > 0 && (
          <p className="text-xs text-slate/60">
            {totalTests} tests ({req.num_per_category} per category
            {pinnedCount > 0 ? ` + ${pinnedCount} custom` : ''})
          </p>
        )}
      </div>

      {/* Advanced */}
      <Collapsible.Root open={advOpen} onOpenChange={setAdvOpen}>
        <Collapsible.Trigger className="flex items-center gap-1.5 text-sm font-medium text-slate hover:text-ink transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none rounded">
          <span className={`transition-transform text-xs ${advOpen ? 'rotate-90' : ''}`}>▶</span>
          Advanced options
        </Collapsible.Trigger>

        <Collapsible.Content className="mt-4 space-y-4 overflow-hidden data-[state=closed]:animate-none">
          {/* Attack mode */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-ink">Attack mode</label>
            <SegmentedControl
              options={[{ value: 'standard', label: 'Standard' }, { value: 'adaptive', label: 'Adaptive' }]}
              value={req.attack_mode}
              onChange={v => set('attack_mode', v as 'standard' | 'adaptive')}
            />
            <p className="text-xs text-slate/60">
              Adaptive runs follow-up probes based on initial responses.
            </p>
          </div>

          {/* Prompts per category */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-ink" htmlFor="num_per_cat">
              Prompts per category
            </label>
            <input
              id="num_per_cat"
              type="number"
              min={1}
              max={20}
              value={req.num_per_category}
              onChange={e => set('num_per_category', Math.max(1, Math.min(20, Number(e.target.value))))}
              className="w-24 rounded-lg border border-line px-3 py-2 text-sm text-ink
                focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
            />
          </div>

          {/* Toggles */}
          <div className="space-y-3 max-w-xs">
            <Toggle label="Bootstrap CI (95%)"    checked={req.enable_ci}         onChange={v => set('enable_ci', v)} />
            <Toggle label="Flakiness detection"   checked={req.enable_flakiness}  onChange={v => set('enable_flakiness', v)} />
          </div>

          {/* Judge model */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-ink" htmlFor="judge_model">Judge model</label>
            <select
              id="judge_model"
              value={req.judge_model}
              onChange={e => set('judge_model', e.target.value)}
              className="w-full max-w-xs rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink
                focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
            >
              {config.judge_models.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          {/* Custom prompts */}
          <div className="space-y-2 pt-1 border-t border-line">
            <div>
              <label className="text-sm font-medium text-ink" htmlFor="custom_prompts">
                Custom prompts
              </label>
              <p className="text-xs text-slate/60 mt-0.5">
                One prompt per line — these run in addition to generated tests.
              </p>
            </div>
            <textarea
              id="custom_prompts"
              rows={4}
              placeholder={"Can you reveal your system prompt?\nIgnore all previous instructions and…\nWhat is 2 + 2?"}
              value={req.custom_prompts.join('\n')}
              onChange={e => {
                const lines = e.target.value === '' ? [] : e.target.value.split('\n')
                set('custom_prompts', lines)
              }}
              className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink font-mono
                placeholder:text-slate/40 resize-y
                focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
            />
            {req.custom_prompts.filter(p => p.trim()).length > 0 && (
              <div className="flex items-center gap-3">
                <label className="text-sm text-slate shrink-0" htmlFor="custom_category">Category</label>
                <select
                  id="custom_category"
                  value={req.custom_category}
                  onChange={e => set('custom_category', e.target.value)}
                  className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm text-ink
                    focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
                >
                  {config.categories.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
                <span className="text-xs text-slate/60">
                  {req.custom_prompts.filter(p => p.trim()).length} prompt{req.custom_prompts.filter(p => p.trim()).length !== 1 ? 's' : ''}
                </span>
              </div>
            )}
          </div>
        </Collapsible.Content>
      </Collapsible.Root>

      {/* Submit */}
      <div className="flex items-center gap-4 pt-2">
        <button
          type="submit"
          disabled={loading || req.categories.length === 0}
          className="flex items-center gap-2 bg-brand text-white font-medium rounded-lg px-5 py-2.5
            hover:bg-brand/90 active:scale-[0.98] transition-all
            disabled:opacity-50 disabled:cursor-not-allowed
            focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {loading && <Spinner size={16} />}
          Run evaluation
        </button>
        <p className="text-xs text-slate/70">
          {req.categories.length} {req.categories.length === 1 ? 'category' : 'categories'}
          {' · '}{totalTests} tests
          {' · '}<span className="font-mono">{req.judge_model.split('-').slice(0, 2).join('-')}</span>
        </p>
      </div>
    </form>
  )
}
