export type JobScore = {
  overall_score: number;
  title_score: number;
  skills_score: number;
  seniority_score: number;
  location_score: number;
  visa_score: number;
  freshness_score: number;
  source_confidence_score: number;
  explanation: string;
  gaps: string[];
  match_reasons: string[];
  risk_flags: string[];
  recommendation: string;
  confidence: number;
};

export type ApplicationPacket = {
  id: number;
  job_id: number;
  resume_variant_path: string;
  cover_letter_path: string;
  short_answers_json: Record<string, unknown>;
  resume_diff_summary: string;
  recommendation: string;
  confidence: number;
  blockers: string[];
  approval?: Approval | null;
};

export type Approval = {
  id: number;
  application_packet_id: number;
  status: string;
  requested_at?: string | null;
  approved_at?: string | null;
  rejected_at?: string | null;
  notes?: string;
};

export type JobItem = {
  id: number;
  canonical_id?: string;
  title: string;
  company: string;
  location: string;
  remote_type: string;
  employment_type: string;
  internship_flag: boolean;
  salary_min?: number | null;
  salary_max?: number | null;
  currency?: string;
  source: string;
  source_url: string;
  apply_url: string;
  status: string;
  restricted: boolean;
  manual_required: boolean;
  discovered_at?: string | null;
  description?: string;
  requirements?: string[];
  responsibilities?: string[];
  benefits?: string[];
  score?: JobScore | null;
  packet?: ApplicationPacket | null;
};

export type JobSource = {
  id: number | string;
  name: string;
  type: string;
  enabled: boolean;
  health_status: string;
  last_run_at?: string | null;
  last_error?: string;
  requires_api_key?: boolean;
  restricted_mode?: boolean;
};

export type IngestionRun = {
  id: number;
  source: string;
  started_at?: string | null;
  finished_at?: string | null;
  status: string;
  jobs_found: number;
  jobs_new: number;
  jobs_updated: number;
  jobs_deduped: number;
  error?: string;
};

export type BrowserApplySession = {
  id: number;
  job_id: number;
  status: string;
  url: string;
  screenshot_dir: string;
  fields_detected: Array<Record<string, unknown>>;
  fields_filled: Array<Record<string, unknown>>;
  fields_blocked: Array<Record<string, unknown>>;
  requires_human: boolean;
  metadata?: Record<string, unknown>;
};

export type JobsOverview = {
  ok: boolean;
  metrics: {
    total_jobs: number;
    new_jobs_today: number;
    top_matches: number;
    ready_to_apply: number;
    needs_approval: number;
    blocked_manual: number;
    applications_submitted: number;
  };
  top_jobs: JobItem[];
  sources: JobSource[];
  recent_runs: IngestionRun[];
};

export type JobsListResponse = {
  ok: boolean;
  jobs: JobItem[];
  count: number;
};

export type JobDetailResponse = {
  ok: boolean;
  job: JobItem;
  browser_sessions: BrowserApplySession[];
};
