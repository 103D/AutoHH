import { useState } from 'react'
import { jobsApi } from '../api/client'
import type { ManualJobCreate, ManualJobImportResponse } from '../types'

interface Props {
  onClose: () => void
  onSuccess: (result: ManualJobImportResponse) => void
}

const EMPTY_FORM: ManualJobCreate = {
  title: '',
  company: '',
  description: '',
  location: '',
  salary_min: null,
  salary_max: null,
  currency: 'KZT',
  employment_type: 'full_time',
  work_format: 'remote',
  experience_required: null,
  url: '',
}

export default function ManualImportModal({ onClose, onSuccess }: Props) {
  const [form, setForm] = useState<ManualJobCreate>(EMPTY_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const update = (field: keyof ManualJobCreate, value: string | number | null) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!form.title.trim() || !form.company.trim() || !form.description.trim()) {
      setError('Title, company, and description are required')
      return
    }
    setLoading(true)
    try {
      const payload: ManualJobCreate = {
        ...form,
        location: form.location || null,
        url: form.url || null,
        salary_min: form.salary_min || null,
        salary_max: form.salary_max || null,
        currency: form.currency || null,
        employment_type: form.employment_type || null,
        work_format: form.work_format || null,
        experience_required: form.experience_required || null,
      }
      const result = await jobsApi.createManual(payload)
      onSuccess(result)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg || d).join(', '))
      } else {
        setError(detail || err.message || 'Failed to import job')
      }
    } finally {
      setLoading(false)
    }
  }


  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-gray-900">Import Vacancy Manually</h2>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            >
              ×
            </button>
          </div>

          <div className="px-6 py-4 space-y-3">
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => update('title', e.target.value)}
                placeholder="Data Analyst"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Company *</label>
              <input
                type="text"
                value={form.company}
                onChange={(e) => update('company', e.target.value)}
                placeholder="Kaspi Bank"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description *</label>
              <textarea
                value={form.description}
                onChange={(e) => update('description', e.target.value)}
                placeholder="Job responsibilities and requirements..."
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                <input
                  type="text"
                  value={form.location || ''}
                  onChange={(e) => update('location', e.target.value)}
                  placeholder="Almaty"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Work format</label>
                <select
                  value={form.work_format || ''}
                  onChange={(e) => update('work_format', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="remote">Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="office">Office</option>
                </select>
              </div>
            </div>


            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Salary min</label>
                <input
                  type="number"
                  value={form.salary_min ?? ''}
                  onChange={(e) => update('salary_min', e.target.value ? Number(e.target.value) : null)}
                  placeholder="500000"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Salary max</label>
                <input
                  type="number"
                  value={form.salary_max ?? ''}
                  onChange={(e) => update('salary_max', e.target.value ? Number(e.target.value) : null)}
                  placeholder="800000"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Currency</label>
                <select
                  value={form.currency || ''}
                  onChange={(e) => update('currency', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="KZT">KZT</option>
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="RUB">RUB</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Employment</label>
                <select
                  value={form.employment_type || ''}
                  onChange={(e) => update('employment_type', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="full_time">Full-time</option>
                  <option value="part_time">Part-time</option>
                  <option value="contract">Contract</option>
                  <option value="internship">Internship</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Experience (yrs)</label>
                <input
                  type="number"
                  value={form.experience_required ?? ''}
                  onChange={(e) => update('experience_required', e.target.value ? Number(e.target.value) : null)}
                  placeholder="3"
                  min={0}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
              <input
                type="url"
                value={form.url || ''}
                onChange={(e) => update('url', e.target.value)}
                placeholder="https://hh.kz/vacancy/123"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              />
            </div>
          </div>

          <div className="px-6 py-3 border-t border-gray-200 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? 'Importing...' : 'Import'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
