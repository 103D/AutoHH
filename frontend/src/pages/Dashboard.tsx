import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { analyticsApi, applicationsApi, jobsApi } from '../api/client'
import { CATEGORY_LABELS_RU } from '../types'
import type { ApplicationStatistics, DreamJobs, Job, LearningRoadmap, MarketOverview } from '../types'

export default function Dashboard() {
  const [stats, setStats] = useState<ApplicationStatistics | null>(null)
  const [recentJobs, setRecentJobs] = useState<Job[]>([])
  const [market, setMarket] = useState<MarketOverview | null>(null)
  const [dreamJobs, setDreamJobs] = useState<DreamJobs | null>(null)
  const [roadmap, setRoadmap] = useState<LearningRoadmap | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadData() {
      try {
        const [jobList, appStats, marketData, dreamData, roadmapData] = await Promise.all([
          jobsApi.list({ limit: 5 }),
          applicationsApi.statistics().catch(() => null),
          analyticsApi.marketOverview().catch(() => null),
          analyticsApi.dreamJobs().catch(() => null),
          analyticsApi.learningRoadmap().catch(() => null),
        ])
        setRecentJobs(jobList)
        setStats(appStats)
        setMarket(marketData)
        setDreamJobs(dreamData)
        setRoadmap(roadmapData)
      } catch (e: any) {
        setError(e.message || 'Failed to load data')
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  if (loading) {
    return <div className="text-center py-8 text-gray-500">Loading...</div>
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Statistics cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Jobs"
          value={recentJobs.length}
          color="bg-blue-500"
        />
        <StatCard
          label="Applications"
          value={stats?.total ?? 0}
          color="bg-green-500"
        />
        <StatCard
          label="Interview Rate"
          value={`${stats?.interview_rate ?? 0}%`}
          color="bg-purple-500"
        />
        <StatCard
          label="Response Rate"
          value={`${stats?.response_rate ?? 0}%`}
          color="bg-orange-500"
        />
      </div>

      {/* Career intelligence: market overview + dream jobs + roadmap */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-3">Market Overview</h2>
          {!market || market.total_analyzed === 0 ? (
            <p className="text-sm text-gray-500">Analyze vacancies to see market insights.</p>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {Object.entries(market.by_category).map(([category, count]) => (
                  <span
                    key={category}
                    className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-700"
                  >
                    {CATEGORY_LABELS_RU[category] || category}: {count}
                  </span>
                ))}
              </div>
              {market.salary.avg_max != null && (
                <p className="text-sm text-gray-600">
                  Средняя вилка: {market.salary.avg_min?.toLocaleString('ru-RU')}–
                  {market.salary.avg_max?.toLocaleString('ru-RU')}
                </p>
              )}
              {market.demanded_skills.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase mb-1">
                    Востребованные навыки
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {market.demanded_skills.slice(0, 6).map((s) => (
                      <span key={s.skill} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded text-xs">
                        {s.skill} ×{s.count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-3">Dream Jobs</h2>
          {!dreamJobs || dreamJobs.jobs.length === 0 ? (
            <p className="text-sm text-gray-500">
              Пока нет вакансий мечты. Анализируйте вакансии или отмечайте их ⭐.
            </p>
          ) : (
            <div className="space-y-2">
              {dreamJobs.jobs.slice(0, 5).map((item) => (
                <Link
                  key={item.match_id}
                  to={`/jobs/${item.job_id}`}
                  className="block p-2 bg-red-50 rounded hover:bg-red-100"
                >
                  <p className="text-sm font-medium text-gray-900">
                    {item.is_override && '⭐ '}
                    {item.title}
                  </p>
                  <p className="text-xs text-gray-500">
                    {item.company} · {item.score}/100
                  </p>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-3">Learning Roadmap</h2>
          {!roadmap || roadmap.steps.length === 0 ? (
            <p className="text-sm text-gray-500">
              Пробелы в навыках появятся после анализа вакансий.
            </p>
          ) : (
            <div className="space-y-2">
              {roadmap.steps.slice(0, 5).map((step) => (
                <div key={step.skill} className="flex justify-between items-center">
                  <span className="text-sm text-gray-800">
                    {step.position}. {step.skill}
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      step.priority === 'high'
                        ? 'bg-red-100 text-red-700'
                        : step.priority === 'medium'
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {step.in_jobs} jobs
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent jobs */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-semibold">Recent Jobs</h2>
        </div>
        <div className="divide-y divide-gray-200">
          {recentJobs.length === 0 ? (
            <div className="px-4 py-6 text-center text-gray-500">
              No jobs found. Run the fetch task to get jobs.
            </div>
          ) : (
            recentJobs.map((job) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="block px-4 py-3 hover:bg-gray-50"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900">
                      {job.title}
                    </h3>
                    <p className="text-sm text-gray-500">{job.company}</p>
                  </div>
                  <div className="text-right">
                    {job.salary_min && (
                      <p className="text-sm text-gray-600">
                        {job.salary_min}
                        {job.salary_max ? `–${job.salary_max}` : ''}{' '}
                        {job.currency || ''}
                      </p>
                    )}
                    <p className="text-xs text-gray-400">{job.location || '—'}</p>
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>
        <div className="px-4 py-2 border-t border-gray-200">
          <Link
            to="/jobs"
            className="text-sm text-indigo-600 hover:text-indigo-800"
          >
            View all jobs →
          </Link>
        </div>
      </div>

      {/* Application status breakdown */}
      {stats && Object.keys(stats.by_status).length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-lg font-semibold">Applications by Status</h2>
          </div>
          <div className="px-4 py-3 space-y-2">
            {Object.entries(stats.by_status).map(([status, count]) => (
              <div key={status} className="flex justify-between items-center">
                <span className="text-sm text-gray-700">{status}</span>
                <span className="text-sm font-medium text-gray-900">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string
  value: string | number
  color: string
}) {
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className={`w-2 h-2 rounded-full ${color} mb-2`} />
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  )
}