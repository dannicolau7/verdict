const LABELS: Record<string, string> = {
  correctness: 'Correctness',
  safety:      'Safety',
  injection:   'Injection',
  edge_case:   'Edge case',
  compliance:  'Compliance',
}

interface CategorySelectProps {
  available: string[]
  selected: string[]
  onChange: (selected: string[]) => void
}

export function CategorySelect({ available, selected, onChange }: CategorySelectProps) {
  const toggle = (cat: string) => {
    if (selected.includes(cat)) {
      if (selected.length === 1) return // keep at least one
      onChange(selected.filter(c => c !== cat))
    } else {
      onChange([...selected, cat])
    }
  }

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Test categories">
      {available.map(cat => {
        const active = selected.includes(cat)
        return (
          <button
            key={cat}
            type="button"
            onClick={() => toggle(cat)}
            aria-pressed={active}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium border transition-all focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none ${
              active
                ? 'bg-brand text-white border-brand shadow-sm'
                : 'bg-white text-slate border-line hover:border-brand/40 hover:text-ink'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${active ? 'bg-white/60' : 'bg-line'}`} />
            {LABELS[cat] ?? cat}
          </button>
        )
      })}
    </div>
  )
}
