import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ExternalLink,
  FileText,
  Filter,
  Play,
  RefreshCw,
  ShieldCheck,
  SkipForward,
  Sparkles,
} from "lucide-react";
import {
  approveJob,
  generatePacket,
  getJobDetail,
  getJobs,
  getJobsOverview,
  ingestDemoJobs,
  runDemoDaily,
  scoreJobs,
  skipJob,
  startDemoApplySession,
} from "../api/jobsApi";
import type { BrowserApplySession, JobDetailResponse, JobItem, JobsOverview } from "../jobs/types/jobs";

type JobsPageProps = {
  onSendMessage: (message: string) => void;
};

function scoreLabel(job: JobItem) {
  return job.score ? `${job.score.overall_score.toFixed(1)}` : "--";
}

function classForRecommendation(value?: string) {
  if (value === "apply") return "apply";
  if (value === "skip") return "skip";
  if (value === "manual_review") return "manual";
  return "maybe";
}

export default function JobsPage({ onSendMessage }: JobsPageProps) {
  const [overview, setOverview] = useState<JobsOverview | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [detail, setDetail] = useState<JobDetailResponse | null>(null);
  const [status, setStatus] = useState("Loading Jobs OS...");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState("");
  const [busy, setBusy] = useState(false);

  const selectedJob = detail?.job ?? jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null;
  const sources = overview?.sources ?? [];
  const sourceOptions = useMemo(() => Array.from(new Set(jobs.map((job) => job.source))).sort(), [jobs]);

  async function refresh() {
    const [overviewData, jobsData] = await Promise.all([
      getJobsOverview(),
      getJobs({ q: query, source, minScore }),
    ]);
    setOverview(overviewData);
    setJobs(jobsData.jobs ?? []);
    const targetId = selectedJobId ?? jobsData.jobs?.[0]?.id;
    if (targetId) {
      setSelectedJobId(targetId);
      setDetail(await getJobDetail(targetId));
    }
    setStatus(`Loaded ${jobsData.count ?? 0} job(s).`);
  }

  async function runAction(label: string, action: () => Promise<Record<string, unknown>>) {
    setBusy(true);
    setStatus(`${label}...`);
    try {
      const result = await action();
      setStatus(`${label} complete. ${JSON.stringify(result).slice(0, 180)}`);
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : `${label} failed.`);
    } finally {
      setBusy(false);
    }
  }

  async function selectJob(jobId: number) {
    setSelectedJobId(jobId);
    setDetail(await getJobDetail(jobId));
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refresh().catch((error) => {
        setStatus(error instanceof Error ? error.message : "Could not load Jobs OS.");
      });
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="center wide-page jobs-page">
      <section className="chat-card jobs-shell-card">
        <div className="card-header jobs-main-header">
          <div>
            <ShieldCheck size={18} />
            <strong>Jobs OS</strong>
          </div>
          <div className="header-actions">
            <button disabled={busy} onClick={() => runAction("Run demo daily flow", runDemoDaily)}>
              <Play size={14} /> Demo
            </button>
            <button disabled={busy} onClick={() => runAction("Ingest demo jobs", ingestDemoJobs)}>
              <Sparkles size={14} /> Ingest
            </button>
            <button disabled={busy} onClick={() => runAction("Score jobs", scoreJobs)}>
              <RefreshCw size={14} /> Score
            </button>
            <button disabled={busy} onClick={() => onSendMessage("job application status")}>
              <FileText size={14} /> Ask Dexter
            </button>
          </div>
        </div>

        <p className="jobs-status">{status}</p>

        <div className="jobs-metrics">
          <MetricTile label="Total Jobs" value={overview?.metrics.total_jobs ?? 0} />
          <MetricTile label="Top Matches" value={overview?.metrics.top_matches ?? 0} />
          <MetricTile label="Ready" value={overview?.metrics.ready_to_apply ?? 0} />
          <MetricTile label="Needs Approval" value={overview?.metrics.needs_approval ?? 0} />
          <MetricTile label="Manual" value={overview?.metrics.blocked_manual ?? 0} />
          <MetricTile label="Submitted" value={overview?.metrics.applications_submitted ?? 0} />
        </div>

        <div className="jobs-grid">
          <section className="mini-panel jobs-feed-panel">
            <div className="panel-title-row">
              <h3>
                <Filter size={16} /> Job Feed
              </h3>
              <button disabled={busy} onClick={refresh}>Refresh</button>
            </div>

            <div className="jobs-filters">
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Keyword, company, skill" />
              <select value={source} onChange={(event) => setSource(event.target.value)}>
                <option value="">All sources</option>
                {sourceOptions.map((item) => (
                  <option value={item} key={item}>{item}</option>
                ))}
              </select>
              <input value={minScore} onChange={(event) => setMinScore(event.target.value)} placeholder="Min score" />
              <button onClick={refresh}>Apply</button>
            </div>

            <div className="jobs-table">
              {jobs.map((job) => (
                <button
                  className={`jobs-row ${selectedJob?.id === job.id ? "selected" : ""}`}
                  key={job.id}
                  onClick={() => selectJob(job.id)}
                >
                  <span className="jobs-score">{scoreLabel(job)}</span>
                  <span>
                    <strong>{job.title}</strong>
                    <small>{job.company} · {job.location || "Unknown"} · {job.source}</small>
                  </span>
                  <b className={`job-rec ${classForRecommendation(job.score?.recommendation)}`}>
                    {job.score?.recommendation ?? job.status}
                  </b>
                </button>
              ))}
              {!jobs.length && <p className="jobs-empty">No jobs loaded. Run Demo to populate the vertical slice.</p>}
            </div>
          </section>

          <JobDetailPanel
            job={selectedJob}
            sessions={detail?.browser_sessions ?? []}
            busy={busy}
            runAction={runAction}
            refreshJob={() => selectedJobId ? selectJob(selectedJobId) : Promise.resolve()}
          />
        </div>

        <div className="jobs-lower-grid">
          <section className="mini-panel">
            <h3>Source Health</h3>
            <div className="jobs-source-list">
              {sources.map((item) => (
                <div className="jobs-source-row" key={item.name}>
                  <span>{item.name}</span>
                  <b className={item.health_status === "ok" ? "on" : item.health_status === "auth_required" ? "manual" : "off"}>
                    {item.health_status}
                  </b>
                  <small>{item.restricted_mode ? "manual-only" : item.requires_api_key ? "credentials" : "ready"}</small>
                </div>
              ))}
            </div>
          </section>

          <section className="mini-panel">
            <h3>Run History</h3>
            <div className="jobs-run-list">
              {(overview?.recent_runs ?? []).map((run) => (
                <div className="jobs-run-row" key={run.id}>
                  <span>{run.source}</span>
                  <b>{run.status}</b>
                  <small>{run.jobs_new} new / {run.jobs_found} found</small>
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>
    </section>
  );
}

function MetricTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="jobs-metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function JobDetailPanel({
  job,
  sessions,
  busy,
  runAction,
  refreshJob,
}: {
  job: JobItem | null;
  sessions: BrowserApplySession[];
  busy: boolean;
  runAction: (label: string, action: () => Promise<Record<string, unknown>>) => Promise<void>;
  refreshJob: () => Promise<void>;
}) {
  if (!job) {
    return (
      <section className="mini-panel jobs-detail-panel">
        <h3>Job Detail</h3>
        <p className="jobs-empty">Select a job to inspect score, packet, and approval state.</p>
      </section>
    );
  }

  return (
    <section className="mini-panel jobs-detail-panel">
      <div className="jobs-detail-header">
        <div>
          <h3>{job.title}</h3>
          <p>{job.company} · {job.location || "Unknown location"}</p>
        </div>
        <span className="jobs-score large">{scoreLabel(job)}</span>
      </div>

      <div className="jobs-actions">
        <button disabled={busy} onClick={() => runAction("Generate packet", () => generatePacket(job.id).then(async (result) => { await refreshJob(); return result; }))}>
          <FileText size={14} /> Packet
        </button>
        <button disabled={busy} onClick={() => runAction("Approve job", () => approveJob(job.id))}>
          <Check size={14} /> Approve
        </button>
        <button disabled={busy} onClick={() => runAction("Skip job", () => skipJob(job.id))}>
          <SkipForward size={14} /> Skip
        </button>
        <button disabled={busy} onClick={() => runAction("Start fake apply session", () => startDemoApplySession(job.id).then(async (result) => { await refreshJob(); return result; }))}>
          <Play size={14} /> Fake Form
        </button>
        {job.apply_url && (
          <a className="jobs-link-button" href={job.apply_url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> Open
          </a>
        )}
      </div>

      <div className="jobs-detail-section">
        <h4>Recommendation</h4>
        <p>
          <b className={`job-rec ${classForRecommendation(job.score?.recommendation)}`}>{job.score?.recommendation ?? "unscored"}</b>
          {job.manual_required && <b className="job-rec manual">manual required</b>}
          {job.restricted && <b className="job-rec skip">restricted</b>}
        </p>
        <p>{job.score?.explanation ?? "Run scoring to calculate fit."}</p>
      </div>

      <div className="jobs-detail-columns">
        <div>
          <h4>Match Reasons</h4>
          <ul>{(job.score?.match_reasons ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div>
          <h4>Gaps</h4>
          <ul>{(job.score?.gaps ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      </div>

      {job.packet && (
        <div className="jobs-detail-section">
          <h4>Application Packet</h4>
          <p>{job.packet.resume_diff_summary}</p>
          <code>{job.packet.resume_variant_path}</code>
          <code>{job.packet.cover_letter_path}</code>
          <p>Approval: {job.packet.approval?.status ?? "requested"}</p>
        </div>
      )}

      <div className="jobs-detail-section">
        <h4>Description</h4>
        <p>{job.description || "No description available."}</p>
      </div>

      <div className="jobs-detail-section">
        <h4>Browser Sessions</h4>
        {sessions.map((session) => (
          <div className="jobs-session-row" key={session.id}>
            <span>{session.status}</span>
            <small>{session.fields_filled.length} filled / {session.fields_blocked.length} blocked</small>
            <code>{session.screenshot_dir}</code>
          </div>
        ))}
        {!sessions.length && <p>No apply session yet.</p>}
      </div>
    </section>
  );
}
