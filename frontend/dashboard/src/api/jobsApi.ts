import type { JobDetailResponse, JobsListResponse, JobsOverview } from "../jobs/types/jobs";

const API_BASE = "http://127.0.0.1:8000";

export type JobSearchParams = {
  keyword?: string;
  role?: string;
  source?: string;
  minScore?: string;
  season?: string;
  cohortYear?: string;
  postedWithinDays?: string;
  employmentType?: string;
  requireInternship?: boolean;
  includeRemote?: boolean;
  includeHybrid?: boolean;
  includeOnsite?: boolean;
  maxResults?: string;
  limit?: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
      throw new Error(`Jobs API request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Jobs backend is not reachable at 127.0.0.1:8000. Start or refresh Dexter, then try again.", {
        cause: error,
      });
    }
    throw error;
  }
}

export function getJobsOverview() {
  return request<JobsOverview>("/api/jobs/overview");
}

export function getJobs(params: JobSearchParams & { status?: string } = {}) {
  const search = new URLSearchParams();
  if (params.keyword) search.set("q", params.keyword);
  if (params.role) search.set("role", params.role);
  if (params.source) search.set("source", params.source);
  if (params.status) search.set("status", params.status);
  if (params.minScore) search.set("min_score", params.minScore);
  if (params.season && params.season !== "any") search.set("season", params.season);
  if (params.cohortYear) search.set("cohort_year", params.cohortYear);
  if (params.postedWithinDays) search.set("posted_within_days", params.postedWithinDays);
  if (params.employmentType) search.set("employment_type", params.employmentType);
  if (params.requireInternship !== undefined) search.set("require_internship", String(params.requireInternship));
  if (params.includeRemote !== undefined) search.set("include_remote", String(params.includeRemote));
  if (params.includeHybrid !== undefined) search.set("include_hybrid", String(params.includeHybrid));
  if (params.includeOnsite !== undefined) search.set("include_onsite", String(params.includeOnsite));
  if (params.limit) search.set("limit", params.limit);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return request<JobsListResponse>(`/api/jobs${suffix}`);
}

export function getJobDetail(jobId: number) {
  return request<JobDetailResponse>(`/api/jobs/${jobId}`);
}

export function runDemoDaily() {
  return request<Record<string, unknown>>("/api/jobs/run-daily?demo=true", { method: "POST" });
}

export function ingestDemoJobs() {
  return request<Record<string, unknown>>("/api/jobs/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: "all",
      demo: true,
      query: { keywords: "Software Engineer Intern 2027", demo: true, max_results: 100 },
    }),
  });
}

function searchKeywords(params: JobSearchParams = {}) {
  return [params.role, params.season !== "any" ? params.season : "", params.cohortYear, params.keyword]
    .filter(Boolean)
    .join(" ")
    .trim();
}

export function ingestLiveJobs(params: JobSearchParams = {}) {
  return request<Record<string, unknown>>("/api/jobs/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: params.source || "all",
      demo: false,
      dry_run: false,
      query: {
        keywords: searchKeywords(params) || "Software Engineer Intern",
        location: "",
        roles: params.role ? [params.role] : [],
        season: params.season === "any" ? "" : params.season || "",
        cohort_year: params.cohortYear ? Number(params.cohortYear) : null,
        posted_within_days: params.postedWithinDays ? Number(params.postedWithinDays) : null,
        employment_types: params.employmentType ? [params.employmentType] : [],
        require_internship: Boolean(params.requireInternship),
        include_remote: params.includeRemote ?? true,
        include_hybrid: params.includeHybrid ?? true,
        include_onsite: params.includeOnsite ?? true,
        demo: false,
        max_results: Number(params.maxResults || 25),
      },
    }),
  });
}

export async function runLiveSearch(params: JobSearchParams = {}) {
  const ingest = await ingestLiveJobs(params);
  const scoring = await scoreJobs();
  return { ingest, scoring };
}

export function scoreJobs() {
  return request<Record<string, unknown>>("/api/jobs/score", { method: "POST" });
}

export function openApplicationLinks(jobIds: number[], limit: number) {
  return request<{ ok: boolean; opened: number; failed: number; jobs: Array<{ id: number; title: string; company: string; apply_url: string }> }>("/api/jobs/open-applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_ids: jobIds, limit }),
  });
}

export function generatePacket(jobId: number) {
  return request<Record<string, unknown>>(`/api/jobs/${jobId}/packet`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: true }),
  });
}

export function approveJob(jobId: number) {
  return request<Record<string, unknown>>(`/api/jobs/${jobId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: "Approved from Jobs dashboard." }),
  });
}

export function skipJob(jobId: number) {
  return request<Record<string, unknown>>(`/api/jobs/${jobId}/skip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: "Skipped from Jobs dashboard." }),
  });
}

export function startDemoApplySession(jobId: number) {
  return request<Record<string, unknown>>(`/api/jobs/${jobId}/apply-session?demo=true`, { method: "POST" });
}

export function startApplySession(jobId: number) {
  return request<Record<string, unknown>>(`/api/jobs/${jobId}/apply-session`, { method: "POST" });
}
