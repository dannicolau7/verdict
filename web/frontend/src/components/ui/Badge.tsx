interface BadgeProps {
  status: 'pass' | 'partial' | 'fail' | 'insufficient_data'
  size?: 'sm' | 'md'
}

const CONFIG = {
  pass:              { label: 'Pass',         classes: 'bg-pass/10 text-pass border-pass/20' },
  partial:           { label: 'Partial',      classes: 'bg-caution/10 text-caution border-caution/20' },
  fail:              { label: 'Fail',         classes: 'bg-fail/10 text-fail border-fail/20' },
  insufficient_data: { label: 'Insufficient', classes: 'bg-slate/10 text-slate border-slate/20' },
}

export function Badge({ status, size = 'sm' }: BadgeProps) {
  const { label, classes } = CONFIG[status]
  const sizeClasses = size === 'md' ? 'px-2.5 py-1 text-sm' : 'px-2 py-0.5 text-xs'
  return (
    <span className={`inline-flex items-center rounded border font-medium ${sizeClasses} ${classes}`}>
      {label}
    </span>
  )
}
