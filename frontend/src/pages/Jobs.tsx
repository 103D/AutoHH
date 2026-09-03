import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { jobsApi, sourcesApi } from '../api/client'
import type { Job, JobSource, MatchResult, ManualJobImportResponse } from '../types'
import ManualImportModal from '../components/ManualImportModal'
import MatchResultCard from '../components/MatchResultCard'

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('')
  const [sources, setSources] = useState<JobSource[]>([])
  const [limit, setLimit] = useState(20)
  const [showImport, setShowImport] = useState(false)
  const [matchResults, setMatchResults] = useState<Record<string, MatchResult>>({})
  const [analyzing, setAnalyzing] = useState<Record<string, boolean>>({})

  useEffect(() => {
    async function loadJobs() {
      setLoading(true)
      try {
        const params: Record<string, any> = { limit }
        if (source) params.source = source
        if (search) params.search = search
        const data = await jobsApi.list(params)
        setJobs(data)
      } catch (e: any) {
        setError(e.message || 'Failed to load jobs')
      } finally {
        setLoading(false)
      }
    }
    loadJobs()
  }, [search, source, limit])

  useEffect(() => {
    const loadSources = async () => {
      try {
        const data = await sourcesApi.list({ enabled_only: true })
        setSources(data)
      } catch {
        setSources([])
      }
    }
    loadSources()
  }, [])

  const handleAnalyze = async (jobId: string) => {
    setAnalyzing((prev) => ({ ...prev, [jobId]: true }))
    try {
      const result = await jobsApi.analyzeNew(jobId)
      setMatchResults((prev) => ({ ...prev, [jobId]: result }))
    } catch {
      setMatchResults((prev) => {
        const next = { ...prev }
        delete next[jobId]
        return next
      })
    } finally {
      setAnalyzing((prev) => ({ ...prev, [jobId]: false }))
    }
  }

  const handleImportSuccess = (result: ManualJobImportResponse) => {
    setShowImport(false)
    setJobs((prev) => [result.job, ...prev])
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] px-3 py-2 border border-gray-300 rounded-md text-sm"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm"
        >
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s.id} value={s.type}>{s.name}</option>
          ))}
        </select>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="px-3 py-2 border border-gray-300 rounded-md text-sm"
        >
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
        </select>
        <button
          type="button"
          onClick={() => setShowImport(true)}
          className="px-3 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700"
        >
          + Import Vacancy
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Jobs list */}
      {loading ? (
        <div className="text-center py-8 text-gray-500">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No jobs found.
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow divide-y divide-gray-200">
          {jobs.map((job) => (
            <div key={job.id} className="px-4 py-3 hover:bg-gray-50">
              <Link to={`/jobs/${job.id}`} className="block">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-gray-900">
                      {job.title}
                    </h3>
                    <p className="text-sm text-gray-500">{job.company}</p>
                    <div className="flex gap-3 mt-1 text-xs text-gray-400">
                      <span>{job.source}</span>
                      {job.location && <span>• {job.location}</span>}
                      {job.work_format && <span>• {job.work_format}</span>}
                    </div>
                  </div>
                  <div className="text-right">
                    {job.salary_min && (
                      <p className="text-sm text-gray-600">
                        {job.salary_min}
                        {job.salary_max ? `–${job.salary_max}` : ''}{' '}
                        {job.currency || ''}
                      </p>
                    )}
                    <p className="text-xs text-gray-400">
                      {job.published_at
                        ? new Date(job.published_at).toLocaleDateString()
                        : ''}
                    </p>
                  </div>
                </div>
              </Link>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    handleAnalyze(job.id)
                  }}
                  disabled={analyzing[job.id]}
                  className="px-2 py-1 text-xs font-medium text-indigo-600 border border-indigo-300 rounded hover:bg-indigo-50 disabled:opacity-50"
                >
                  {analyzing[job.id] ? 'Analyzing...' : '⚡ Analyze'}
                </button>
                {matchResults[job.id] && (
                  <MatchResultCard result={matchResults[job.id]} />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {showImport && (
        <ManualImportModal
          onClose={() => setShowImport(false)}
          onSuccess={handleImportSuccess}
        />
      )}
    </div>
  )
}
