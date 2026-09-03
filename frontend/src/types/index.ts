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
  user_override_recommendation?: string | null
  matched_skills: SkillMatch[]
  missing_skills: string[]
  strong_matches: string[]
  concerns: string[]
  reasoning_summary: string
  stretch_analysis?: StretchAnalysis | null
  analyzed_at: string
}

// === Career intelligence v2 ===

export type MatchCategory =
  | 'DREAM_JOB'
  | 'STRETCH'
  | 'SOLID_MATCH'
  | 'MARKET_RESEARCH'
  | 'LEARNING_OPPORTUNITY'
  | 'IGNORE'

export const CATEGORY_LABELS_RU: Record<string, string> = {
  DREAM_JOB: '🔥 Работа мечты',
  STRETCH: '🚀 Растущая роль',
  SOLID_MATCH: '✅ Уверенное совпадение',
  MARKET_RESEARCH: '📊 Изучение рынка',
  LEARNING_OPPORTUNITY: '🎓 Чему учиться',
  IGNORE: '💤 Пропустить',
}

export const MATCH_CATEGORIES: MatchCategory[] = [
  'DREAM_JOB',
  'STRETCH',
  'SOLID_MATCH',
  'MARKET_RESEARCH',
  'LEARNING_OPPORTUNITY',
  'IGNORE',
]

export interface StretchAnalysis {
  is_stretch: boolean
  reasons: string[]
  blockers: string[]
  missing_key_skills: string[]
  required_experience_years: number | null
}

export interface GapItem {
  skill: string
  gap_type: string
  priority: string
}

export interface GapAnalysis {
  job_id: string
  candidate_profile_id: string
  score: number
  recommendation: string
  effective_recommendation: string
  gaps: GapItem[]
  stretch_analysis: StretchAnalysis | null
  summary: string
}

export interface PackageDiff {
  added_lines: number
  removed_lines: number
  unified_diff: string
}

export interface ApplicationPackage {
  application_id: string
  adapted_resume: string
  cover_letter: string
  diff: PackageDiff
  keyword_coverage: Record<string, number>
  improvement_score: number
  validation: Record<string, { is_valid: boolean; issues: string[] }>
  generated_at: string
  ai_model: string | null
}

export interface MarketOverview {
  candidate_profile_id: string
  total_analyzed: number
  by_category: Record<string, number>
  top_companies: { company: string; count: number }[]
  demanded_skills: { skill: string; count: number }[]
  salary: {
    avg_min: number | null
    avg_max: number | null
    vacancies_with_salary: number
  }
}

export interface SkillGapItem {
  skill: string
  in_jobs: number
  priority: string
}

export interface SkillGap {
  candidate_profile_id: string
  analyzed_vacancies: number
  gaps: SkillGapItem[]
}

export interface RoadmapStep {
  position: number
  skill: string
  in_jobs: number
  priority: string
  rationale: string
}

export interface LearningRoadmap {
  candidate_profile_id: string
  steps: RoadmapStep[]
  total: number
}

export interface DreamJobItem {
  job_id: string
  match_id: string
  title: string
  company: string
  url: string
  score: number
  category: string
  is_override: boolean
  salary: Record<string, any>
}

export interface DreamJobs {
  candidate_profile_id: string
  total: number
  jobs: DreamJobItem[]
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