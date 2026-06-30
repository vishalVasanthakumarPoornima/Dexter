import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Download,
  ExternalLink,
  FileText,
  Filter,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  SkipForward,
} from "lucide-react";
import {
  approveJob,
  downloadTailoredResume,
  generatePacket,
  getJobDetail,
  getJobs,
  getJobsOverview,
  openApplicationLinks,
  runLiveSearch,
  scoreJobs,
  skipJob,
  startApplySession,
} from "../api/jobsApi";
import type { JobSearchParams } from "../api/jobsApi";
import type { BrowserApplySession, JobDetailResponse, JobItem, JobsOverview } from "../jobs/types/jobs";

type JobsPageProps = {
  onSendMessage: (message: string) => Promise<void> | void;
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

type SavePickerWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName?: string;
    types?: Array<{ description: string; accept: Record<string, string[]> }>;
  }) => Promise<{ createWritable: () => Promise<{ write: (blob: Blob) => Promise<void>; close: () => Promise<void> }> }>;
};

export default function JobsPage({ onSendMessage }: JobsPageProps) {
  const [overview, setOverview] = useState<JobsOverview | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [detail, setDetail] = useState<JobDetailResponse | null>(null);
  const [status, setStatus] = useState("Loading Jobs OS...");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [minScore, setMinScore] = useState("");
  const [role, setRole] = useState("Software Engineer Intern");
  const [customRole, setCustomRole] = useState("");
  const [season, setSeason] = useState("any");
  const [cohortYear, setCohortYear] = useState("2026");
  const [postedWithinDays, setPostedWithinDays] = useState("30");
  const [employmentType, setEmploymentType] = useState("internship");
  const [requireInternship, setRequireInternship] = useState(true);
  const [includeRemote, setIncludeRemote] = useState(true);
  const [includeHybrid, setIncludeHybrid] = useState(true);
  const [includeOnsite, setIncludeOnsite] = useState(true);
  const [maxResults, setMaxResults] = useState("25");
  const [bulkOpenLimit, setBulkOpenLimit] = useState("10");
  const [busy, setBusy] = useState(false);
  const [liveSearchStartedAt, setLiveSearchStartedAt] = useState<number | null>(null);
  const [liveSearchElapsed, setLiveSearchElapsed] = useState(0);

  const selectedJob = detail?.job ?? jobs.find((job) => job.id === selectedJobId) ?? jobs[0] ?? null;
  const sources = useMemo(() => overview?.sources ?? [], [overview?.sources]);
  const sourceOptions = useMemo(() => sources.map((item) => item.name).sort(), [sources]);
  const effectiveRole = role === "__custom__" ? customRole.trim() : role;
  const filteredMetrics = useMemo(() => {
    const topMatches = jobs.filter((job) => (job.score?.overall_score ?? 0) >= 70).length;
    const ready = jobs.filter((job) => job.score?.recommendation === "apply").length;
    const needsApproval = jobs.filter((job) => job.status === "packet_created" || job.packet?.approval?.status === "requested").length;
    const manual = jobs.filter((job) => job.manual_required || job.score?.recommendation === "manual_review").length;
    const submitted = jobs.filter((job) => job.status === "submitted").length;
    return {
      total: jobs.length,
      topMatches,
      ready,
      needsApproval,
      manual,
      submitted,
    };
  }, [jobs]);

  function searchParams(): JobSearchParams {
    return {
      keyword: query,
      role: effectiveRole,
      source,
      minScore,
      season,
      cohortYear,
      postedWithinDays,
      employmentType,
      requireInternship,
      includeRemote,
      includeHybrid,
      includeOnsite,
      maxResults,
      limit: "200",
    };
  }

  async function refresh() {
    const [overviewData, jobsData] = await Promise.all([
      getJobsOverview(),
      getJobs(searchParams()),
    ]);
    setOverview(overviewData);
    setJobs(jobsData.jobs ?? []);
    const visibleJobs = jobsData.jobs ?? [];
    const selectedStillVisible = selectedJobId ? visibleJobs.some((job) => job.id === selectedJobId) : false;
    const targetId = selectedStillVisible ? selectedJobId : visibleJobs[0]?.id;
    if (targetId) {
      setSelectedJobId(targetId);
      setDetail(await getJobDetail(targetId));
    } else {
      setSelectedJobId(null);
      setDetail(null);
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

  async function runLiveSearchWithProgress() {
    const targetRole = effectiveRole || "the selected role";
    setBusy(true);
    setLiveSearchElapsed(0);
    setLiveSearchStartedAt(Date.now());
    setStatus(`Live search running for ${targetRole}. Checking sources, filtering roles, then scoring matches.`);
    try {
      const result = await runLiveSearch(searchParams());
      setStatus(`Live search complete. Refreshing results... ${JSON.stringify(result).slice(0, 140)}`);
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Live job search failed.");
    } finally {
      setBusy(false);
      setLiveSearchStartedAt(null);
    }
  }

  async function refreshWithStatus(label = "Refresh jobs") {
    setBusy(true);
    setStatus(`${label}...`);
    try {
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : `${label} failed.`);
    } finally {
      setBusy(false);
    }
  }

  async function askDexterForStatus() {
    setBusy(true);
    setStatus("Asking Dexter to summarize Jobs OS status in the main chat...");
    try {
      await onSendMessage("Summarize my Jobs OS status: searches, top matches, approvals, generated packets, and manual blockers.");
      setStatus("Sent a Jobs OS status request to Dexter chat.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Ask Dexter failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveTailoredResume(jobId: number) {
    setBusy(true);
    setStatus("Generating Jake-template LaTeX resume export...");
    try {
      const exportFile = await downloadTailoredResume(jobId);
      const saveWindow = window as SavePickerWindow;
      const isPdf = exportFile.filename.toLowerCase().endsWith(".pdf");
      if (saveWindow.showSaveFilePicker) {
        const handle = await saveWindow.showSaveFilePicker({
          suggestedName: exportFile.filename,
          types: [
            {
              description: isPdf ? "PDF resume" : "LaTeX resume",
              accept: isPdf ? { "application/pdf": [".pdf"] } : { "application/x-tex": [".tex"] },
            },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(exportFile.blob);
        await writable.close();
      } else {
        const url = URL.createObjectURL(exportFile.blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = exportFile.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      }
      const compileText = exportFile.compiled
        ? `Compiled with ${exportFile.compiler || "LaTeX"}.`
        : "Downloaded .tex because no LaTeX compiler is installed locally.";
      setStatus(`Resume export ready: ${exportFile.filename}. ${compileText}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Resume export failed.");
    } finally {
      setBusy(false);
    }
  }

  async function selectJob(jobId: number) {
    setSelectedJobId(jobId);
    setDetail(await getJobDetail(jobId));
  }

  async function bulkOpenApplications() {
    const limit = Math.max(1, Math.min(Number(bulkOpenLimit) || 10, 50));
    const candidates = jobs.filter((job) => job.apply_url && job.status !== "skipped").slice(0, limit);
    setBusy(true);
    setStatus(`Opening ${candidates.length} application link(s)...`);
    try {
      const result = await openApplicationLinks(candidates.map((job) => job.id), limit);
      const failureText = result.failed ? ` ${result.failed} failed to open on this machine.` : "";
      setStatus(`Dexter opened ${result.opened}/${candidates.length} application link(s) from the current filtered results.${failureText}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Bulk open failed.");
    } finally {
      setBusy(false);
    }
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

  useEffect(() => {
    if (!liveSearchStartedAt) return undefined;
    const timer = window.setInterval(() => {
      setLiveSearchElapsed(Math.floor((Date.now() - liveSearchStartedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [liveSearchStartedAt]);

  return (
    <section className="center wide-page jobs-page">
      <section className="chat-card jobs-shell-card">
        <div className="card-header jobs-main-header">
          <div>
            <ShieldCheck size={18} />
            <strong>Jobs OS</strong>
          </div>
          <div className="header-actions">
            <button disabled={busy || (role === "__custom__" && !customRole.trim())} onClick={runLiveSearchWithProgress}>
              {liveSearchStartedAt ? <span className="jobs-button-spinner" aria-hidden="true" /> : <Search size={14} />} Live Search
            </button>
            <button disabled={busy} onClick={() => runAction("Score jobs", scoreJobs)}>
              <RefreshCw size={14} /> Score
            </button>
            <button disabled={busy || !jobs.length} onClick={bulkOpenApplications}>
              <ExternalLink size={14} /> Bulk Open
            </button>
            <button disabled={busy} onClick={askDexterForStatus} title="Send a Jobs OS status question to Dexter chat.">
              <FileText size={14} /> Ask Status
            </button>
          </div>
        </div>

        <p className="jobs-status">{status}</p>
        {liveSearchStartedAt && (
          <div className="jobs-live-progress" role="status" aria-live="polite">
            <span className="jobs-progress-ring" aria-hidden="true" />
            <div>
              <strong>Searching live job sources</strong>
              <p>
                Running for {liveSearchElapsed}s. Dexter is fetching postings, applying your role filters, deduping, and scoring matches.
              </p>
            </div>
          </div>
        )}

        <section className="jobs-search-panel">
          <div className="jobs-search-grid">
            <label>
              <span>Role</span>
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                <option>Software Engineer Intern</option>
                <option>Backend Engineer Intern</option>
                <option>AI Engineer Intern</option>
                <option>Security Engineer Intern</option>
                <option>Frontend Engineer Intern</option>
                <option>Full Stack Engineer Intern</option>
                <option>New Grad Software Engineer</option>
                <option value="__custom__">Other role...</option>
              </select>
            </label>
            {role === "__custom__" && (
              <label>
                <span>Custom Role</span>
                <input value={customRole} onChange={(event) => setCustomRole(event.target.value)} placeholder="e.g. Robotics Software Intern" />
              </label>
            )}
            <label>
              <span>Term</span>
              <select value={season} onChange={(event) => setSeason(event.target.value)}>
                <option value="any">Any</option>
                <option value="fall">Fall</option>
                <option value="spring">Spring</option>
                <option value="summer">Summer</option>
                <option value="winter">Winter</option>
              </select>
            </label>
            <label>
              <span>Year</span>
              <input value={cohortYear} onChange={(event) => setCohortYear(event.target.value.replace(/\D/g, "").slice(0, 4))} placeholder="2026" />
            </label>
            <label>
              <span>Posted</span>
              <select value={postedWithinDays} onChange={(event) => setPostedWithinDays(event.target.value)}>
                <option value="">Any date</option>
                <option value="1">Today</option>
                <option value="7">Last 7 days</option>
                <option value="14">Last 14 days</option>
                <option value="30">Last 30 days</option>
                <option value="60">Last 60 days</option>
              </select>
            </label>
            <label>
              <span>Type</span>
              <select value={employmentType} onChange={(event) => setEmploymentType(event.target.value)}>
                <option value="internship">Internship</option>
                <option value="new_grad">New Grad</option>
                <option value="full_time">Full Time</option>
                <option value="">Any</option>
              </select>
            </label>
            <label>
              <span>Source</span>
              <select value={source} onChange={(event) => setSource(event.target.value)}>
                <option value="">All sources</option>
                {sourceOptions.map((item) => (
                  <option value={item} key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Keywords</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="AI, security, backend" />
            </label>
            <label>
              <span>Min Score</span>
              <input value={minScore} onChange={(event) => setMinScore(event.target.value.replace(/[^\d.]/g, ""))} placeholder="55" />
            </label>
            <label>
              <span>Per Source</span>
              <input value={maxResults} onChange={(event) => setMaxResults(event.target.value.replace(/\D/g, "").slice(0, 3))} placeholder="25" />
            </label>
            <label>
              <span>Bulk Open</span>
              <input value={bulkOpenLimit} onChange={(event) => setBulkOpenLimit(event.target.value.replace(/\D/g, "").slice(0, 2))} placeholder="10" />
            </label>
          </div>
          <div className="jobs-toggle-row">
            <label><input type="checkbox" checked={requireInternship} onChange={(event) => setRequireInternship(event.target.checked)} /> Internships only</label>
            <label><input type="checkbox" checked={includeRemote} onChange={(event) => setIncludeRemote(event.target.checked)} /> Remote</label>
            <label><input type="checkbox" checked={includeHybrid} onChange={(event) => setIncludeHybrid(event.target.checked)} /> Hybrid</label>
            <label><input type="checkbox" checked={includeOnsite} onChange={(event) => setIncludeOnsite(event.target.checked)} /> Onsite</label>
            <button disabled={busy} onClick={() => refreshWithStatus("Apply filters")}>Apply Filters</button>
          </div>
        </section>

        <div className="jobs-metrics">
          <MetricTile label="Visible Jobs" value={filteredMetrics.total} />
          <MetricTile label="Top Matches" value={filteredMetrics.topMatches} />
          <MetricTile label="Ready" value={filteredMetrics.ready} />
          <MetricTile label="Needs Approval" value={filteredMetrics.needsApproval} />
          <MetricTile label="Manual" value={filteredMetrics.manual} />
          <MetricTile label="Submitted" value={filteredMetrics.submitted} />
        </div>

        <div className="jobs-grid">
          <section className="mini-panel jobs-feed-panel">
            <div className="panel-title-row">
              <h3>
                <Filter size={16} /> Job Feed
              </h3>
              <button disabled={busy} onClick={() => refreshWithStatus()}>Refresh</button>
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
              {!jobs.length && <p className="jobs-empty">No jobs loaded. Run Live Search to populate the feed.</p>}
            </div>
          </section>

          <JobDetailPanel
            job={selectedJob}
            sessions={detail?.browser_sessions ?? []}
            busy={busy}
            runAction={runAction}
            saveTailoredResume={saveTailoredResume}
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
  saveTailoredResume,
  refreshJob,
}: {
  job: JobItem | null;
  sessions: BrowserApplySession[];
  busy: boolean;
  runAction: (label: string, action: () => Promise<Record<string, unknown>>) => Promise<void>;
  saveTailoredResume: (jobId: number) => Promise<void>;
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
        <button disabled={busy} onClick={() => runAction("Approve and tailor resume", () => approveJob(job.id).then(async (result) => { await refreshJob(); return result; }))}>
          <Check size={14} /> Approve + Tailor
        </button>
        <button disabled={busy} onClick={() => saveTailoredResume(job.id)}>
          <Download size={14} /> Download Resume
        </button>
        <button disabled={busy} onClick={() => runAction("Skip job", () => skipJob(job.id))}>
          <SkipForward size={14} /> Skip
        </button>
        <button disabled={busy} onClick={() => runAction("Prepare form session", () => startApplySession(job.id).then(async (result) => { await refreshJob(); return result; }))}>
          <Play size={14} /> Prep Form
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
          <p>Resume export: use Download Resume to save a Jake-template LaTeX/PDF file outside the Dexter project.</p>
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
