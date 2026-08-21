import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { applicationsApi, jobsApi } from '../api/client'
import type { Job, MatchResult } from '../types'

export default function JobDetails() {
  const { id } = useParams<{ id: string }>()
  const [job, setJob] = useState<Job | null>(null)
  const [match, setMatch] = useState<MatchResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadData() {
      if (!id) return
      try {
        const jobData = await jobsApi.get(id)
        setJob(jobData)
        const matchData = await jobsApi.getMatch(id).catch(() => null)
        setMatch(matchData)
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
    } catch (e: any) {
      setError(e.message || 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleCreateApplication() {
    if (!id) return
    try {
      await applicationsApi.create({ job_id: id })
      alert('Application created!')
    } catch (e: any) {
      setError(e.message || 'Failed to create application')
    }
  }

  if (loading) return <div className="text-center py-8 text-gray-500">Loading...</div>
  if (!job) return <div className="text-red-500">Job not found</div>

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
              <div className="text-3xl font-bold text-indigo-600">
                {match.score}%
              </div>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                match.recommendation === 'HIGH_PRIORITY' ? 'bg-red-100 text-red-700' :
                match.recommendation === 'APPLY' ? 'bg-green-100 text-green-700' :
                match.recommendation === 'REVIEW' ? 'bg-yellow-100 text-yellow-700' :
                'bg-gray-100 text-gray-700'
              }`}>
                {match.recommendation}
              </span>
            </div>

            <p className="text-sm text-gray-600">{match.reasoning_summary}</p>

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
    </div>
  )
}