import axios from 'axios'
import type {
  Application,
  ApplicationStatistics,
  CandidateProfile,
  Job,
  MatchResult,
  ResumeVersion,
  StatusHistory,
} from '../types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// === Jobs ===
export const jobsApi = {
  list: (params?: Record<string, any>) => api.get<Job[]>('/jobs/', { params }).then((r) => r.data),
  get: (id: string) => api.get<Job>(`/jobs/${id}`).then((r) => r.data),
  analyze: (jobId: string, candidateProfileId?: string) =>
    api.post<MatchResult>(`/matching/jobs/${jobId}/analyze`, null, {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
  getMatch: (jobId: string, candidateProfileId?: string) =>
    api.get<MatchResult | null>(`/matching/jobs/${jobId}/match`, {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
}

// === Applications ===
export const applicationsApi = {
  list: (params?: Record<string, any>) =>
    api.get<Application[]>('/applications/', { params }).then((r) => r.data),
  get: (id: string) => api.get<Application>(`/applications/${id}`).then((r) => r.data),
  create: (data: { job_id: string; cover_letter?: string; notes?: string }) =>
    api.post<Application>('/applications/', data).then((r) => r.data),
  update: (id: string, data: Record<string, any>) =>
    api.patch<Application>(`/applications/${id}`, data).then((r) => r.data),
  history: (id: string) =>
    api.get<StatusHistory[]>(`/applications/${id}/history`).then((r) => r.data),
  statistics: (candidateProfileId?: string) =>
    api.get<ApplicationStatistics>('/applications/statistics', {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
}

// === Profile ===
export const profileApi = {
  getByUser: (userId: string) =>
    api.get<CandidateProfile>('/profile/', { params: { user_id: userId } }).then((r) => r.data),
  get: (id: string) => api.get<CandidateProfile>(`/profile/${id}`).then((r) => r.data),
  create: (data: any) => api.post<CandidateProfile>('/profile/', data).then((r) => r.data),
  update: (id: string, data: any) =>
    api.put<CandidateProfile>(`/profile/${id}`, data).then((r) => r.data),
  // Resume versions
  listResumes: (profileId: string) =>
    api.get<ResumeVersion[]>(`/profile/${profileId}/resumes`).then((r) => r.data),
  addResume: (profileId: string, data: { name: string; content: string }) =>
    api.post<ResumeVersion>(`/profile/${profileId}/resumes`, data).then((r) => r.data),
  deleteResume: (profileId: string, name: string) =>
    api.delete(`/profile/${profileId}/resumes/${name}`),
}

// === Matching ===
export const matchingApi = {
  adaptResume: (data: { job_id: string; resume_text: string }) =>
    api.post('/matching/resume/adapt', data).then((r) => r.data),
  matchResume: (data: { job_id: string; resume_text: string }) =>
    api.post('/matching/resume/match', data).then((r) => r.data),
  generateCoverLetter: (data: {
    job_id: string
    candidate_name: string
    style?: string
  }) =>
    api.post('/matching/cover-letter', data).then((r) => r.data),
}

export default api