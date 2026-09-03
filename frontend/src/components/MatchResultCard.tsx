import type { MatchResult } from '../types'
import { CATEGORY_LABELS_RU } from '../types'

interface Props {
  result: MatchResult
}

export default function MatchResultCard({ result }: Props) {
  const categoryLabel = CATEGORY_LABELS_RU[result.recommendation] || result.recommendation
  const scorePercent = Math.round(result.score * 100)

  return (
    <div className="flex-1 flex flex-wrap items-center gap-2 text-xs">
      <span className="font-semibold text-gray-700">
        {categoryLabel} · {scorePercent}%
      </span>

      {result.matched_skills.length > 0 && (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-green-50 text-green-700 rounded">
          ✓ {result.matched_skills.slice(0, 3).map((s) => s.skill).join(', ')}
          {result.matched_skills.length > 3 && ` +${result.matched_skills.length - 3}`}
        </span>
      )}

      {result.missing_skills.length > 0 && (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded">
          ✗ {result.missing_skills.slice(0, 3).join(', ')}
          {result.missing_skills.length > 3 && ` +${result.missing_skills.length - 3}`}
        </span>
      )}

      {result.hard_failures.length > 0 && (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-red-50 text-red-700 rounded">
          ⛔ {result.hard_failures[0]}
          {result.hard_failures.length > 1 && ` +${result.hard_failures.length - 1}`}
        </span>
      )}
    </div>
  )
}
