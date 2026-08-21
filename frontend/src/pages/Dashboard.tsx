import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { applicationsApi, jobsApi } from '../api/client'
import type { ApplicationStatistics, Job } from '../types'

export default function Dashboard() {
  const [stats, setStats] = useState<ApplicationStatistics | null>(null)
  const [recentJobs, setRecentJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadData() {
      try {
        const [jobList, appStats] = await Promise.all([
          jobsApi.list({ limit: 5 }),
          applicationsApi.statistics().catch(() => null),
        ])
        setRecentJobs(jobList)
        setStats(appStats)
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