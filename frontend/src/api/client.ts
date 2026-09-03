import axios from 'axios'
import type {
  Application,
  ApplicationPackage,
  ApplicationStatistics,
  CandidateProfile,
  DreamJobs,
  GapAnalysis,
  Job,
  JobSource,
  LearningRoadmap,
  ManualJobCreate,
  ManualJobImportResponse,
  MarketOverview,
  MatchResult,
  ResumeProfile,
  ResumeRecommendation,
  ResumeVersion,
  SkillGap,
  SoftMatchResponse,
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
  createManual: (data: ManualJobCreate) =>
    api.post<ManualJobImportResponse>('/jobs/manual', data).then((r) => r.data),
  analyze: (jobId: string, candidateProfileId?: string) =>
    api.post<MatchResult>(`/matching/jobs/${jobId}/analyze`, null, {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
  softMatch: (jobId: string, candidateProfileId?: string) =>
    api.post<SoftMatchResponse>(`/matching/match`, null, {
      params: { job_id: jobId, ...(candidateProfileId ? { candidate_profile_id: candidateProfileId } : {}) },
    }).then((r) => r.data),
  analyzeNew: (jobId: string, candidateProfileId?: string) =>
    api.post<MatchResult>(`/matching/analyze`, null, {
      params: { job_id: jobId, ...(candidateProfileId ? { candidate_profile_id: candidateProfileId } : {}) },
    }).then((r) => r.data),
  getMatch: (jobId: string, candidateProfileId?: string) =>
    api.get<MatchResult | null>(`/matching/jobs/${jobId}/match`, {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
}

// === Job Sources ===
export const sourcesApi = {
  list: (params?: Record<string, any>) =>
    api.get<JobSource[]>('/jobs/sources/', { params }).then((r) => r.data),
}

// === Applications ===
export const applicationsApi = {
  list: (params?: Record<string, any>) =>
    api.get<Application[]>('/applications/', { params }).then((r) => r.data),
  get: (id: string) => api.get<Application>(`/applications/${id}`).then((r) => r.data),
  getByJob: (jobId: string) =>
    api.get<Application | null>(`/applications/by-job/${jobId}`).then((r) => r.data),
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
  preparePackage: (id: string) =>
    api.post<ApplicationPackage>(`/applications/${id}/prepare-package`).then((r) => r.data),
  getPackage: (id: string) =>
    api.get<ApplicationPackage | null>(`/applications/${id}/package`).then((r) => r.data),
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
  overrideRecommendation: (jobId: string, recommendation: string) =>
    api.put<MatchResult>(`/matching/jobs/${jobId}/recommendation`, { recommendation }).then(
      (r) => r.data,
    ),
  clearRecommendationOverride: (jobId: string) =>
    api.delete<MatchResult>(`/matching/jobs/${jobId}/recommendation`).then((r) => r.data),
  gaps: (jobId: string) =>
    api.get<GapAnalysis>(`/matching/jobs/${jobId}/gaps`).then((r) => r.data),
  recommendResume: (jobId: string, candidateProfileId?: string) =>
    api
      .post<ResumeRecommendation>(`/matching/jobs/${jobId}/recommend-resume`, {
        params: candidateProfileId
          ? { candidate_profile_id: candidateProfileId }
          : {},
      })
      .then((r) => r.data),
}

// === Resume profiles (Phase 3: Master CV -> specialized profiles) ===
export const resumeProfilesApi = {
  list: (profileId: string) =>
    api
      .get<ResumeProfile[]>(`/profile/${profileId}/resume-profiles`)
      .then((r) => r.data),
  create: (profileId: string, data: Partial<ResumeProfile>) =>
    api
      .post<ResumeProfile>(`/profile/${profileId}/resume-profiles`, data)
      .then((r) => r.data),
  get: (resumeProfileId: string) =>
    api.get<ResumeProfile>(`/resume-profiles/${resumeProfileId}`).then((r) => r.data),
  update: (resumeProfileId: string, data: Partial<ResumeProfile>) =>
    api
      .put<ResumeProfile>(`/resume-profiles/${resumeProfileId}`, data)
      .then((r) => r.data),
  delete: (resumeProfileId: string) =>
    api.delete(`/resume-profiles/${resumeProfileId}`),
}

// === Analytics (career intelligence v2) ===
export const analyticsApi = {
  marketOverview: (candidateProfileId?: string) =>
    api.get<MarketOverview>('/analytics/market-overview', {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
  skillGap: (candidateProfileId?: string) =>
    api.get<SkillGap>('/analytics/skill-gap', {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
  learningRoadmap: (candidateProfileId?: string) =>
    api.get<LearningRoadmap>('/analytics/learning-roadmap', {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
  dreamJobs: (candidateProfileId?: string) =>
    api.get<DreamJobs>('/analytics/dream-jobs', {
      params: candidateProfileId ? { candidate_profile_id: candidateProfileId } : {},
    }).then((r) => r.data),
}

export default api