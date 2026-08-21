import { useEffect, useState } from 'react'
import { applicationsApi } from '../api/client'
import type { Application, StatusHistory } from '../types'

const STATUSES = [
  'DRAFT', 'READY', 'APPLIED', 'SCREENING', 'INTERVIEW',
  'TECHNICAL_INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN', 'NO_RESPONSE',
]

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'bg-gray-100 text-gray-700',
  READY: 'bg-blue-100 text-blue-700',
  APPLIED: 'bg-indigo-100 text-indigo-700',
  SCREENING: 'bg-purple-100 text-purple-700',
  INTERVIEW: 'bg-yellow-100 text-yellow-700',
  TECHNICAL_INTERVIEW: 'bg-orange-100 text-orange-700',
  OFFER: 'bg-green-100 text-green-700',
  REJECTED: 'bg-red-100 text-red-700',
  WITHDRAWN: 'bg-gray-100 text-gray-500',
  NO_RESPONSE: 'bg-gray-100 text-gray-500',
}

export default function Applications() {
  const [apps, setApps] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<StatusHistory[]>([])

  useEffect(() => {
    loadApps()
  }, [])

  async function loadApps() {
    setLoading(true)
    try {
      const data = await applicationsApi.list({ limit: 100 })
      setApps(data)
    } catch (e: any) {
      setError(e.message || 'Failed to load applications')
    } finally {
      setLoading(false)
    }
  }

  async function handleStatusChange(appId: string, newStatus: string) {
    try {
      await applicationsApi.update(appId, { status: newStatus })
      await loadApps()
    } catch (e: any) {
      setError(e.message || 'Failed to update status')
    }
  }

  async function loadHistory(appId: string) {
    try {
      const data = await applicationsApi.history(appId)
      setHistory(data)
      setSelectedId(appId)
    } catch (e: any) {
      setError(e.message || 'Failed to load history')
    }
  }

  if (loading) return <div className="text-center py-8 text-gray-500">Loading...</div>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Applications</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {apps.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No applications yet. Create one from a job details page.
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Job ID
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Applied
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Updated
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {apps.map((app) => (
                <tr key={app.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-sm text-gray-900">
                    {app.job_id.slice(0, 8)}...
                  </td>
                  <td className="px-4 py-2">
                    <select
                      value={app.status}
                      onChange={(e) => handleStatusChange(app.id, e.target.value)}
                      className={`px-2 py-1 rounded text-xs font-medium border-0 cursor-pointer ${STATUS_COLORS[app.status] || 'bg-gray-100'}`}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2 text-sm text-gray-500">
                    {app.applied_at
                      ? new Date(app.applied_at).toLocaleDateString()
                      : '—'}
                  </td>
                  <td className="px-4 py-2 text-sm text-gray-500">
                    {new Date(app.updated_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => loadHistory(app.id)}
                      className="text-xs text-indigo-600 hover:text-indigo-800"
                    >
                      History
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* History modal */}
      {selectedId && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg p-6 max-w-lg w-full mx-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Status History</h2>
              <button
                onClick={() => setSelectedId(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            {history.length === 0 ? (
              <p className="text-sm text-gray-500">No history available.</p>
            ) : (
              <div className="space-y-3">
                {history.map((h) => (
                  <div key={h.id} className="flex items-start gap-3">
                    <div className="flex flex-col items-center">
                      <div className="w-2 h-2 bg-indigo-500 rounded-full" />
                      {history.indexOf(h) < history.length - 1 && (
                        <div className="w-px h-6 bg-gray-200" />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {h.from_status || '—'} → {h.to_status}
                      </p>
                      {h.comment && (
                        <p className="text-xs text-gray-500">{h.comment}</p>
                      )}
                      <p className="text-xs text-gray-400">
                        {new Date(h.changed_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}