export interface Job {
  id: string
  source: string
  external_id: string
  title: string
  company: string
  description: string
  location: string | null
  salary_min: number | null
  salary_max: number | null
  currency: string | null
  employment_type: string | null
  work_format: string | null
  url: string | null
  published_at: string | null
  first_seen_at: string
  last_seen_at: string
}

export interface JobSource {
  id: string
  name: string
  type: string
  enabled: boolean
}

export interface SkillMatch {
  skill: string
  match_type: string
  confidence: number
}

export interface MatchResult {
  job_id: string
  candidate_profile_id: string
  score: number
  recommendation: string
  matched_skills: SkillMatch[]
  missing_skills: string[]
  strong_matches: string[]
  concerns: string[]
  reasoning_summary: string
  analyzed_at: string
}

export interface Application {
  id: string
  job_id: string
  candidate_profile_id: string
  status: string
  cover_letter: string | null
  adapted_resume: string | null
  applied_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface StatusHistory {
  id: string
  application_id: string
  from_status: string | null
  to_status: string
  comment: string | null
  changed_at: string
}

export interface ApplicationStatistics {
  total: number
  by_status: Record<string, number>
  interview_rate: number
  response_rate: number
}

export interface CandidateProfile {
  id: string
  user_id: string
  desired_positions: string[]
  skills: string[]
  technologies: Record<string, string[]>
  experience_years: number | null
  experience_level: string | null
  education: any[] | null
  languages: Record<string, string>
  location: string | null
  desired_salary_min: number | null
  desired_salary_max: number | null
  salary_currency: string
  employment_types: string[] | null
  work_formats: string[] | null
  relocation_possible: boolean
  business_trips_acceptable: boolean
  resume_versions: Record<string, string>
  additional_preferences: any | null
}

export interface ResumeVersion {
  name: string
  content: string
}