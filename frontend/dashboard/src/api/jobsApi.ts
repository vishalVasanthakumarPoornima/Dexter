import type { JobDetailResponse, JobsListResponse, JobsOverview } from "../jobs/types/jobs";

const API_BASE = "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    throw new Error(`Jobs API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getJobsOverview() {
  return request<JobsOverview>("/api/jobs/overview");
}

export function getJobs(params: { q?: string; source?: string; status?: string; minScore?: string } = {}) {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.source) search.set("source", params.source);
  if (params.status) search.set("status", params.status);
  if (params.minScore) search.set("min_score", params.minScore);
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

export function scoreJobs() {
  return request<Record<string, unknown>>("/api/jobs/score", { method: "POST" });
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
