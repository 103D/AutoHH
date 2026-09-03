import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { applicationsApi, jobsApi, matchingApi } from '../api/client'
import { CATEGORY_LABELS_RU, MATCH_CATEGORIES } from '../types'
import type { ApplicationPackage, GapAnalysis, Job, MatchResult } from '../types'

function categoryBadgeClass(category: string): string {
  switch (category) {
    case 'DREAM_JOB':
      return 'bg-red-100 text-red-700'
    case 'STRETCH':
      return 'bg-purple-100 text-purple-700'
    case 'SOLID_MATCH':
      return 'bg-green-100 text-green-700'
    case 'MARKET_RESEARCH':
      return 'bg-blue-100 text-blue-700'
    case 'LEARNING_OPPORTUNITY':
      return 'bg-yellow-100 text-yellow-700'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

function gapBadgeClass(priority: string): string {
  switch (priority) {
    case 'high':
      return 'bg-red-50 text-red-700'
    case 'medium':
      return 'bg-yellow-50 text-yellow-700'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

export default function JobDetails() {
  const { id } = useParams<{ id: string }>()
  const [job, setJob] = useState<Job | null>(null)
  const [match, setMatch] = useState<MatchResult | null>(null)
  const [gaps, setGaps] = useState<GapAnalysis | null>(null)
  const [pkg, setPkg] = useState<ApplicationPackage | null>(null)
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [preparing, setPreparing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadData() {
      if (!id) return
      try {
        const jobData = await jobsApi.get(id)
        setJob(jobData)
        const matchData = await jobsApi.getMatch(id).catch(() => null)
        setMatch(matchData)
        if (matchData) {
          setGaps(await matchingApi.gaps(id).catch(() => null))
        }
        const app = await applicationsApi.getByJob(id).catch(() => null)
        if (app) {
          setPkg(await applicationsApi.getPackage(app.id).catch(() => null))
        }
      } catch (e: any) {
        setError(e.message || 'Failed to load job')
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [id])

  async function handleAnalyze() {
    if (!id) return
    setAnalyzing(true)
    try {
      const result = await jobsApi.analyze(id)
      setMatch(result)
      setGaps(await matchingApi.gaps(id).catch(() => null))
    } catch (e: any) {
      setError(e.message || 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleOverride(category: string) {
    if (!id) return
    try {
      const result = await matchingApi.overrideRecommendation(id, category)
      setMatch(result)
      setGaps(await matchingApi.gaps(id).catch(() => null))
    } catch (e: any) {
      setError(e.message || 'Override failed')
    }
  }

  async function handleClearOverride() {
    if (!id) return
    try {
      const result = await matchingApi.clearRecommendationOverride(id)
      setMatch(result)
    } catch (e: any) {
      setError(e.message || 'Failed to reset override')
    }
  }

  async function handleCreateApplication() {
    if (!id) return
    try {
      const existing = await applicationsApi.getByJob(id).catch(() => null)
      if (!existing) {
        await applicationsApi.create({ job_id: id })
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Failed to create application')
    }
  }

  async function handlePreparePackage() {
    if (!id) return
    setPreparing(true)
    try {
      let app = await applicationsApi.getByJob(id).catch(() => null)
      if (!app) {
        app = await applicationsApi.create({ job_id: id })
      }
      const generated = await applicationsApi.preparePackage(app.id)
      setPkg(generated)
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Package preparation failed')
    } finally {
      setPreparing(false)
    }
  }

  if (loading) return <div className="text-center py-8 text-gray-500">Loading...</div>
  if (!job) return <div className="text-red-500">Job not found</div>

  const effectiveCategory = match?.user_override_recommendation || match?.recommendation || ''
  const isOverridden = Boolean(match?.user_override_recommendation)
  const stretch = match?.stretch_analysis ?? gaps?.stretch_analysis ?? null

  return (
    <div className="space-y-4">
      <Link to="/jobs" className="text-sm text-indigo-600 hover:text-indigo-800">
        ← Back to Jobs
      </Link>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Job info */}
      <div className="bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>
        <p className="text-lg text-gray-600">{job.company}</p>
        <div className="flex flex-wrap gap-4 mt-2 text-sm text-gray-500">
          {job.location && <span>📍 {job.location}</span>}
          {job.salary_min && (
            <span>
              💰 {job.salary_min}
              {job.salary_max ? `–${job.salary_max}` : ''} {job.currency || ''}
            </span>
          )}
          {job.work_format && <span>💼 {job.work_format}</span>}
          {job.employment_type && <span>📋 {job.employment_type}</span>}
        </div>
        {job.url && (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-3 text-sm text-indigo-600 hover:text-indigo-800"
          >
            View original →
          </a>
        )}
      </div>

      {/* Job description */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-2">Description</h2>
        <div className="prose max-w-none text-sm text-gray-700 whitespace-pre-wrap">
          {job.description}
        </div>
      </div>

      {/* AI Analysis */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">AI Analysis</h2>
          <div className="flex gap-2">
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="px-3 py-1.5 bg-indigo-600 text-white rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              {analyzing ? 'Analyzing...' : 'Analyze'}
            </button>
            <button
              onClick={handlePreparePackage}
              disabled={preparing}
              className="px-3 py-1.5 bg-purple-600 text-white rounded-md text-sm hover:bg-purple-700 disabled:opacity-50"
            >
              {preparing ? 'Preparing...' : 'Prepare package'}
            </button>
            <button
              onClick={handleCreateApplication}
              className="px-3 py-1.5 bg-green-600 text-white rounded-md text-sm hover:bg-green-700"
            >
              Create Application
            </button>
          </div>
        </div>

        {match ? (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="text-3xl font-bold text-indigo-600">{match.score}%</div>
              <span
                className={`px-3 py-1 rounded-full text-sm font-medium ${categoryBadgeClass(effectiveCategory)}`}
              >
                {CATEGORY_LABELS_RU[effectiveCategory] || effectiveCategory}
              </span>
              {isOverridden && (
                <button
                  onClick={handleClearOverride}
                  className="text-xs text-gray-500 underline hover:text-gray-700"
                >
                  сбросить мою оценку
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600">Моя оценка:</label>
              <select
                value={effectiveCategory}
                onChange={(e) => handleOverride(e.target.value)}
                className="text-sm border border-gray-300 rounded-md px-2 py-1"
              >
                {MATCH_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS_RU[c] || c}
                  </option>
                ))}
              </select>
            </div>

            <p className="text-sm text-gray-600">{match.reasoning_summary}</p>

            {/* Stretch analysis */}
            {stretch && stretch.is_stretch && (
              <div className="bg-purple-50 border border-purple-200 rounded-md p-3">
                <h3 className="text-sm font-medium text-purple-900 mb-1">🚀 Растущая роль</h3>
                {stretch.reasons.length > 0 && (
                  <ul className="list-disc list-inside text-sm text-purple-800">
                    {stretch.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
                {stretch.blockers.length > 0 && (
                  <div className="mt-2">
                    <span className="text-xs font-medium text-purple-900">Блокеры:</span>
                    <ul className="list-disc list-inside text-sm text-purple-800">
                      {stretch.blockers.map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {stretch.missing_key_skills.length > 0 && (
                  <p className="text-xs text-purple-700 mt-2">
                    Навыки, которые стоит подтянуть: {stretch.missing_key_skills.join(', ')}
                  </p>
                )}
                {stretch.required_experience_years != null && (
                  <p className="text-xs text-purple-700">
                    Требуемый опыт: ~{stretch.required_experience_years} лет
                  </p>
                )}
              </div>
            )}

            {/* Skill gaps */}
            {gaps && gaps.gaps.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-1">Skill gaps</h3>
                <div className="flex flex-wrap gap-2">
                  {gaps.gaps.map((g) => (
                    <span
                      key={g.skill}
                      className={`px-2 py-1 rounded text-sm ${gapBadgeClass(g.priority)}`}
                    >
                      {g.skill} · {g.gap_type} · {g.priority}
                    </span>
                  ))}
                </div>
                {gaps.summary && <p className="text-xs text-gray-500 mt-1">{gaps.summary}</p>}
              </div>
            )}

            {match.strong_matches.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-1">Strong Matches</h3>
                <div className="flex flex-wrap gap-2">
                  {match.strong_matches.map((s, i) => (
                    <span key={i} className="px-2 py-1 bg-green-50 text-green-700 rounded text-sm">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {match.missing_skills.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-1">Missing Skills</h3>
                <div className="flex flex-wrap gap-2">
                  {match.missing_skills.map((s, i) => (
                    <span key={i} className="px-2 py-1 bg-red-50 text-red-700 rounded text-sm">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {match.concerns.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-1">Concerns</h3>
                <ul className="list-disc list-inside text-sm text-gray-600">
                  {match.concerns.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            No analysis yet. Click "Analyze" to run AI matching.
          </p>
        )}
      </div>
      {/* Application package */}
      {pkg && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Application Package</h2>

          <div className="flex flex-wrap gap-6 mb-4 text-sm text-gray-600">
            <span>
              Diff: <span className="text-green-600">+{pkg.diff.added_lines}</span> /{' '}
              <span className="text-red-600">−{pkg.diff.removed_lines}</span>
            </span>
            <span>
              Keyword coverage: {pkg.keyword_coverage.before ?? '—'}% →{' '}
              {pkg.keyword_coverage.after ?? '—'}%
            </span>
            <span>
              Improvement:{' '}
              <span className="font-medium text-indigo-600">+{pkg.improvement_score}pp</span>
            </span>
            <span>Model: {pkg.ai_model || '—'}</span>
          </div>

          {pkg.validation && Object.values(pkg.validation).some((v) => v && !v.is_valid) && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 mb-4">
              <h3 className="text-sm font-medium text-yellow-900 mb-1">Validation warnings</h3>
              <ul className="list-disc list-inside text-sm text-yellow-800">
                {Object.entries(pkg.validation).flatMap(([section, v]) =>
                  (v?.issues ?? []).map((issue, i) => (
                    <li key={`${section}-${i}`}>
                      <span className="font-medium">{section}:</span> {issue}
                    </li>
                  )),
                )}
              </ul>
            </div>
          )}

          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-900 mb-1">Cover letter</h3>
            <pre className="whitespace-pre-wrap text-sm bg-gray-50 rounded-md p-3">
              {pkg.cover_letter}
            </pre>
          </div>

          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-900 mb-1">Adapted resume</h3>
            <pre className="whitespace-pre-wrap text-sm bg-gray-50 rounded-md p-3">
              {pkg.adapted_resume}
            </pre>
          </div>

          {pkg.diff.unified_diff && (
            <details>
              <summary className="text-sm font-medium text-gray-900 cursor-pointer">
                Resume diff (+{pkg.diff.added_lines} / −{pkg.diff.removed_lines})
              </summary>
              <pre className="text-xs bg-gray-900 text-gray-100 rounded-md p-3 mt-2 overflow-x-auto">
                {pkg.diff.unified_diff}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}