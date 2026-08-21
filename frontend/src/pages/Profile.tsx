import { useEffect, useState } from 'react'
import { profileApi } from '../api/client'
import type { CandidateProfile, ResumeVersion } from '../types'

export default function Profile() {
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [resumes, setResumes] = useState<ResumeVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [creating, setCreating] = useState(false)

  // Form state
  const [desiredPositions, setDesiredPositions] = useState('')
  const [skills, setSkills] = useState('')
  const [location, setLocation] = useState('')
  const [experienceYears, setExperienceYears] = useState('')
  const [experienceLevel, setExperienceLevel] = useState('')
  const [baseResume, setBaseResume] = useState('')

  // New resume form
  const [resumeName, setResumeName] = useState('')
  const [resumeContent, setResumeContent] = useState('')

  useEffect(() => {
    loadProfile()
  }, [])

  async function loadProfile() {
    try {
      const data = await profileApi.get(
        '00000000-0000-0000-0000-000000000000'
      ).catch(() => null)

      if (!data) {
        const profiles = await fetch('/api/v1/profile/?user_id=00000000-0000-0000-0000-000000000000')
        if (profiles.ok) {
          const p = await profiles.json()
          setProfile(p)
          setFormState(p)
          if (p.id) {
            const r = await profileApi.listResumes(p.id)
            setResumes(r)
            const base = r.find((rv) => rv.name === 'base_resume')
            if (base) setBaseResume(base.content)
          }
        }
      } else {
        setProfile(data)
        setFormState(data)
        const r = await profileApi.listResumes(data.id)
        setResumes(r)
        const base = r.find((rv) => rv.name === 'base_resume')
        if (base) setBaseResume(base.content)
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

  async function handleCreateProfile() {
    setCreating(true)
    setError('')
    try {
      const userId = '00000000-0000-0000-0000-000000000001'
      const data: any = {
        user_id: userId,
        desired_positions: desiredPositions.split(',').map((s) => s.trim()).filter(Boolean),
        skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
        location: location || null,
        experience_years: experienceYears ? parseInt(experienceYears) : null,
        experience_level: experienceLevel || null,
      }

      const created = await profileApi.create(data)
      setProfile(created)

      // Save base resume if provided
      if (baseResume.trim()) {
        await profileApi.addResume(created.id, {
          name: 'base_resume',
          content: baseResume,
        })
        const r = await profileApi.listResumes(created.id)
        setResumes(r)
      }

      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to create profile')
    } finally {
      setCreating(false)
    }
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

      // Update base resume
      if (baseResume.trim()) {
        const existing = resumes.find((r) => r.name === 'base_resume')
        if (!existing) {
          await profileApi.addResume(profile.id, {
            name: 'base_resume',
            content: baseResume,
          })
        } else {
          // Delete and re-add (no update endpoint)
          await profileApi.deleteResume(profile.id, 'base_resume')
          await profileApi.addResume(profile.id, {
            name: 'base_resume',
            content: baseResume,
          })
        }
        const r = await profileApi.listResumes(profile.id)
        setResumes(r)
      }

      setError('')
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
      if (name === 'base_resume') setBaseResume('')
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

            {/* Base Resume */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Base Resume (initial version)
              </label>
              <textarea
                value={baseResume}
                onChange={(e) => setBaseResume(e.target.value)}
                rows={10}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
                placeholder="Paste your full resume text here...

Example:
John Doe
Data Analyst | 3 years experience

CONTACT
Email: john@example.com
Phone: +7 777 123 4567
Location: Almaty, Kazakhstan

SUMMARY
Data Analyst with 3 years of experience in Python, SQL, and BI tools...

EXPERIENCE
Data Analyst at Company X (2022-present)
- Built dashboards using Tableau and Power BI
- Automated reporting with Python (pandas, sqlalchemy)
- Analyzed data quality issues and proposed solutions

SKILLS
Python, SQL, PostgreSQL, Tableau, Power BI, pandas, numpy

EDUCATION
Bachelor in Computer Science, Kazakh-British Technical University"
              />
              <p className="text-xs text-gray-500 mt-1">
                This is your main resume. AI will adapt it for specific jobs.
              </p>
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
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900">
                        {r.name}
                        {r.name === 'base_resume' && (
                          <span className="ml-2 text-xs text-indigo-600">(main)</span>
                        )}
                      </p>
                      <p className="text-xs text-gray-500 truncate">
                        {r.content.slice(0, 100)}...
                      </p>
                    </div>
                    <button
                      onClick={() => handleDeleteResume(r.name)}
                      className="text-xs text-red-600 hover:text-red-800 ml-2 shrink-0"
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
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
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
        /* Create profile form */
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <h2 className="text-lg font-semibold">Create Your Profile</h2>
          <p className="text-sm text-gray-500">
            No profile found. Fill in your details below to get started.
          </p>

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

          {/* Base Resume */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Base Resume (initial version)
            </label>
            <textarea
              value={baseResume}
              onChange={(e) => setBaseResume(e.target.value)}
              rows={10}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
              placeholder="Paste your full resume text here...

Example:
John Doe
Data Analyst | 3 years experience

CONTACT
Email: john@example.com
Phone: +7 777 123 4567
Location: Almaty, Kazakhstan

SUMMARY
Data Analyst with 3 years of experience in Python, SQL, and BI tools...

EXPERIENCE
Data Analyst at Company X (2022-present)
- Built dashboards using Tableau and Power BI
- Automated reporting with Python (pandas, sqlalchemy)
- Analyzed data quality issues and proposed solutions

SKILLS
Python, SQL, PostgreSQL, Tableau, Power BI, pandas, numpy

EDUCATION
Bachelor in Computer Science, Kazakh-British Technical University"
            />
            <p className="text-xs text-gray-500 mt-1">
              This is your main resume. AI will adapt it for specific jobs.
            </p>
          </div>

          <button
            onClick={handleCreateProfile}
            disabled={creating}
            className="px-4 py-2 bg-indigo-600 text-white rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {creating ? 'Creating...' : 'Create Profile'}
          </button>
        </div>
      )}
    </div>
  )
}