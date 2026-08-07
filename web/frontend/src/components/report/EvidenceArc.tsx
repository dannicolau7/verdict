/**
 * Verdict's signature element — a 270° gauge arc showing pass rate.
 * The gap is at the bottom. CI bounds render as tick marks on the arc.
 */

interface EvidenceArcProps {
  passRate: number          // 0–1
  ciLow?: number | null
  ciHigh?: number | null
  size?: number
  indeterminate?: boolean   // spinning state during run
}

const CX = 60, CY = 60, R = 46, STROKE = 7
const START_DEG = 135        // 8 o'clock
const TOTAL_DEG = 270        // spans to 4 o'clock

function polar(deg: number): [number, number] {
  const rad = (deg * Math.PI) / 180
  return [CX + R * Math.cos(rad), CY + R * Math.sin(rad)]
}

function arc(startDeg: number, spanDeg: number, inset = 0): string {
  const r = R - inset
  const endDeg = startDeg + spanDeg
  const [sx, sy] = [CX + r * Math.cos((startDeg * Math.PI) / 180), CY + r * Math.sin((startDeg * Math.PI) / 180)]
  const [ex, ey] = [CX + r * Math.cos((endDeg  * Math.PI) / 180), CY + r * Math.sin((endDeg  * Math.PI) / 180)]
  const large = spanDeg > 180 ? 1 : 0
  return `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`
}

function tick(deg: number): string {
  const inner = R - STROKE / 2 - 4
  const outer = R + STROKE / 2 + 1
  const rad = (deg * Math.PI) / 180
  const [x1, y1] = [CX + inner * Math.cos(rad), CY + inner * Math.sin(rad)]
  const [x2, y2] = [CX + outer * Math.cos(rad), CY + outer * Math.sin(rad)]
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} L ${x2.toFixed(2)} ${y2.toFixed(2)}`
}

export function EvidenceArc({ passRate, ciLow, ciHigh, size = 120, indeterminate = false }: EvidenceArcProps) {
  const fillSpan = Math.max(0, Math.min(1, passRate)) * TOTAL_DEG
  const ciLowDeg  = ciLow  != null ? START_DEG + ciLow  * TOTAL_DEG : null
  const ciHighDeg = ciHigh != null ? START_DEG + ciHigh * TOTAL_DEG : null

  const passColor = passRate >= 0.8 ? '#10B981' : passRate >= 0.5 ? '#F59E0B' : '#EF4444'

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      aria-label={`Pass rate: ${Math.round(passRate * 100)}%`}
      role="img"
    >
      {/* Background track */}
      <path
        d={arc(START_DEG, TOTAL_DEG)}
        fill="none"
        stroke="#E2E8F0"
        strokeWidth={STROKE}
        strokeLinecap="round"
      />

      {/* Fill arc */}
      {!indeterminate && fillSpan > 0 && (
        <path
          d={arc(START_DEG, fillSpan)}
          fill="none"
          stroke={passColor}
          strokeWidth={STROKE}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      )}

      {/* Indeterminate spinner segment */}
      {indeterminate && (
        <path
          d={arc(START_DEG, 80)}
          fill="none"
          stroke="#6366F1"
          strokeWidth={STROKE}
          strokeLinecap="round"
          className="animate-spin-slow origin-center"
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        />
      )}

      {/* CI bound ticks */}
      {ciLowDeg  != null && <path d={tick(ciLowDeg)}  stroke="#94A3B8" strokeWidth={2} strokeLinecap="round" />}
      {ciHighDeg != null && <path d={tick(ciHighDeg)} stroke="#94A3B8" strokeWidth={2} strokeLinecap="round" />}

      {/* Center text */}
      {!indeterminate && (
        <>
          <text x={CX} y={CY - 4} textAnchor="middle" className="font-sans" fontSize="18" fontWeight="700" fill="#1A1A2E">
            {Math.round(passRate * 100)}%
          </text>
          <text x={CX} y={CY + 14} textAnchor="middle" fontSize="10" fill="#64748B">
            pass rate
          </text>
        </>
      )}
    </svg>
  )
}
