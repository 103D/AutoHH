import { useEffect, useState } from 'react'
import { profileApi } from '../api/client'
import type { CandidateProfile, ResumeVersion } from '../types'

export default function Profile() {
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [resumes, setResumes] = useState<ResumeVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  // Form state
  const [desiredPositions, setDesiredPositions] = useState('')
  const [skills, setSkills] = useState('')
  const [location, setLocation] = useState('')
  const [experienceYears, setExperienceYears] = useState('')
  const [experienceLevel, setExperienceLevel] = useState('')

  // New resume form
  const [resumeName, setResumeName] = useState('')
  const [resumeContent, setResumeContent] = useState('')

  useEffect(() => {
    loadProfile()
  }, [])

  async function loadProfile() {
    try {
      // Try to get first profile (single user for now)
      const data = await profileApi.get(
        '00000000-0000-0000-0000-000000000000'
      ).catch(() => null)

      if (!data) {
        // Try listing via jobs API workaround - get any profile
        const profiles = await fetch('/api/v1/profile/?user_id=00000000-0000-0000-0000-000000000000')
        if (profiles.ok) {
          const p = await profiles.json()
          setProfile(p)
          setFormState(p)
          if (p.id) {
            const r = await profileApi.listResumes(p.id)
            setResumes(r)
          }
        }
      } else {
        setProfile(data)
        setFormState(data)
        const r = await profileApi.listResumes(data.id)
        setResumes(r)
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load profile')
    } finally {
      setLoading(false)
    }
  }

  function setFormState(p: CandidateProfile) {
    setDesiredPositions(p.desired_positions?.join(', ') || '')
    setSkills(p.skills?.join(', ') || '')
    setLocation(p.location || '')
    setExperienceYears(String(p.experience_years || ''))
    setExperienceLevel(p.experience_level || '')
  }

  async function handleSave() {
    if (!profile) return
    setSaving(true)
    try {
      const data = {
        desired_positions: desiredPositions.split(',').map((s) => s.trim()).filter(Boolean),
        skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
        location: location || null,
        experience_years: experienceYears ? parseInt(experienceYears) : null,
        experience_level: experienceLevel || null,
      }
      const updated = await profileApi.update(profile.id, data)
      setProfile(updated)
    } catch (e: any) {
      setError(e.message || 'Failed to save profile')
    } finally {
      setSaving(false)
    }
  }

  async function handleAddResume() {
    if (!profile || !resumeName || !resumeContent) return
    try {
      await profileApi.addResume(profile.id, {
        name: resumeName,
        content: resumeContent,
      })
      const r = await profileApi.listResumes(profile.id)
      setResumes(r)
      setResumeName('')
      setResumeContent('')
    } catch (e: any) {
      setError(e.message || 'Failed to add resume')
    }
  }

  async function handleDeleteResume(name: string) {
    if (!profile) return
    try {
      await profileApi.deleteResume(profile.id, name)
      const r = await profileApi.listResumes(profile.id)
      setResumes(r)
    } catch (e: any) {
      setError(e.message || 'Failed to delete resume')
    }
  }

  if (loading) return <div className="text-center py-8 text-gray-500">Loading...</div>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Profile</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {profile ? (
        <>
          {/* Profile form */}
          <div className="bg-white rounded-lg shadow p-6 space-y-4">
            <h2 className="text-lg font-semibold">Candidate Profile</h2>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Desired Positions (comma-separated)
              </label>
              <input
                type="text"
                value={desiredPositions}
                onChange={(e) => setDesiredPositions(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="Data Analyst, BI Analyst"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Skills (comma-separated)
              </label>
              <input
                type="text"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="Python, SQL, PostgreSQL"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Location
                </label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  placeholder="Almaty"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Experience Years
                </label>
                <input
                  type="number"
                  value={experienceYears}
                  onChange={(e) => setExperienceYears(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  placeholder="5"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Experience Level
              </label>
              <select
                value={experienceLevel}
                onChange={(e) => setExperienceLevel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="">Select level</option>
                <option value="junior">Junior</option>
                <option value="middle">Middle</option>
                <option value="senior">Senior</option>
                <option value="lead">Lead</option>
              </select>
            </div>

            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Profile'}
            </button>
          </div>

          {/* Resume versions */}
          <div className="bg-white rounded-lg shadow p-6 space-y-4">
            <h2 className="text-lg font-semibold">Resume Versions</h2>

            {resumes.length > 0 && (
              <div className="space-y-2">
                {resumes.map((r) => (
                  <div
                    key={r.name}
                    className="flex justify-between items-center p-3 bg-gray-50 rounded"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900">{r.name}</p>
                      <p className="text-xs text-gray-500">
                        {r.content.slice(0, 80)}...
                      </p>
                    </div>
                    <button
                      onClick={() => handleDeleteResume(r.name)}
                      className="text-xs text-red-600 hover:text-red-800"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="border-t border-gray-200 pt-4 space-y-2">
              <h3 className="text-sm font-medium text-gray-700">Add Resume Version</h3>
              <input
                type="text"
                value={resumeName}
                onChange={(e) => setResumeName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="Version name (e.g. data_analyst)"
              />
              <textarea
                value={resumeContent}
                onChange={(e) => setResumeContent(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="Resume content..."
              />
              <button
                onClick={handleAddResume}
                className="px-3 py-1.5 bg-green-600 text-white rounded-md text-sm hover:bg-green-700"
              >
                Add Resume
              </button>
            </div>
          </div>
        </>
      ) : (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          No profile found. Create a profile via API first.
        </div>
      )}
    </div>
  )
}