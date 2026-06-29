from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import requests

from backend.utils.logger import log_action


RUNS_DIR = Path("logs/job_agent_runs")
CORE_SOURCES = ("linkedin", "dice", "glassdoor")
SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "linkedin": {
        "label": "LinkedIn Jobs",
        "kind": "job_board",
        "signup_url": "https://www.linkedin.com/signup",
    },
    "dice": {
        "label": "Dice",
        "kind": "job_board",
        "signup_url": "https://www.dice.com/register",
    },
    "glassdoor": {
        "label": "Glassdoor",
        "kind": "job_board",
        "signup_url": "https://www.glassdoor.com/profile/joinNow_input.htm",
    },
    "github_search": {
        "label": "GitHub internship repositories",
        "kind": "github",
        "signup_url": "https://github.com/signup",
    },
    "github_simplify": {
        "label": "SimplifyJobs GitHub lists",
        "kind": "github",
        "signup_url": "https://github.com/signup",
    },
    "github_pittcsc": {
        "label": "Pitt CSC GitHub internship lists",
        "kind": "github",
        "signup_url": "https://github.com/signup",
    },
    "intern_list": {
        "label": "Intern List",
        "kind": "internship_list",
        "signup_url": "https://www.intern-list.com/",
    },
    "simplify": {
        "label": "Simplify",
        "kind": "job_board",
        "signup_url": "https://simplify.jobs/auth/signup",
    },
    "levels_fyi": {
        "label": "Levels.fyi Internships",
        "kind": "job_board",
        "signup_url": "https://www.levels.fyi/internships/",
    },
    "wellfound": {
        "label": "Wellfound",
        "kind": "startup_board",
        "signup_url": "https://wellfound.com/signup",
    },
    "yc_jobs": {
        "label": "Y Combinator Jobs",
        "kind": "startup_board",
        "signup_url": "https://www.ycombinator.com/jobs",
    },
    "greenhouse": {
        "label": "Greenhouse company boards",
        "kind": "ats_search",
        "signup_url": "",
    },
    "lever": {
        "label": "Lever company boards",
        "kind": "ats_search",
        "signup_url": "",
    },
    "builtin": {
        "label": "Built In",
        "kind": "job_board",
        "signup_url": "https://builtin.com/join",
    },
    "indeed": {
        "label": "Indeed",
        "kind": "job_board",
        "signup_url": "https://secure.indeed.com/account/register",
    },
    "ziprecruiter": {
        "label": "ZipRecruiter",
        "kind": "job_board",
        "signup_url": "https://www.ziprecruiter.com/register",
    },
    "handshake": {
        "label": "Handshake",
        "kind": "student_board",
        "signup_url": "https://joinhandshake.com/",
    },
    "ripplematch": {
        "label": "RippleMatch",
        "kind": "student_board",
        "signup_url": "https://ripplematch.com/",
    },
    "wayup": {
        "label": "WayUp",
        "kind": "student_board",
        "signup_url": "https://www.wayup.com/",
    },
}
DEFAULT_SOURCES = tuple(SOURCE_REGISTRY)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,!?:;")


def _infer_target_year(query: str) -> str:
    match = re.search(r"\b(20\d{2})\b", query)
    return match.group(1) if match else ""


def _infer_role(query: str, explicit_role: str = "") -> str:
    if explicit_role.strip():
        return _clean(explicit_role)

    lower = query.lower()
    is_internship = any(token in lower for token in ("internship", "internships", "intern "))
    is_new_grad = "new grad" in lower or "new-grad" in lower

    aliases = {
        "swe": "Software Engineer",
        "software engineer": "Software Engineer",
        "software developer": "Software Developer",
        "frontend": "Frontend Engineer",
        "front end": "Frontend Engineer",
        "backend": "Backend Engineer",
        "back end": "Backend Engineer",
        "full stack": "Full Stack Engineer",
        "data engineer": "Data Engineer",
        "ml engineer": "Machine Learning Engineer",
        "ai engineer": "AI Engineer",
        "cybersecurity": "Cybersecurity Analyst",
        "security analyst": "Security Analyst",
    }

    for token, role_name in aliases.items():
        if token in lower:
            if is_internship and "intern" not in role_name.lower():
                return f"{role_name} Intern"
            if is_new_grad and "new grad" not in role_name.lower():
                return f"New Grad {role_name}"
            return role_name

    match = re.search(
        r"(?:apply(?:\s+to|\s+for)?|find|search(?:\s+for)?)\s+(?:the\s+latest\s+)?(.+?)\s+(?:jobs?|internships?|roles?|positions?)",
        query,
        re.I,
    )
    if match:
        return _clean(match.group(1))

    if is_internship:
        return "Software Engineer Intern"

    if is_new_grad:
        return "New Grad Software Engineer"

    return "Software Engineer"


def _infer_location(query: str, explicit_location: str = "") -> str:
    if explicit_location.strip():
        return _clean(explicit_location)

    lower = query.lower()
    if "remote" in lower:
        return "Remote"

    match = re.search(r"\b(?:in|near|around)\s+([A-Za-z][A-Za-z\s,.-]{2,})", query)
    if match:
        location = re.split(
            r"\b(?:on|from|using|with|and\s+apply|that|where)\b",
            match.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        return _clean(location)

    return ""


def _all_sources_requested(query: str, source_scope: str = "") -> bool:
    lower = query.lower()
    return source_scope.lower() == "all" or any(
        phrase in lower
        for phrase in (
            "all portals",
            "all platforms",
            "all sources",
            "more portals",
            "different sources",
            "not restricted",
            "not just",
        )
    )


def _normalize_sites(
    sites: str | list[str] | tuple[str, ...] | None,
    query: str,
    source_scope: str = "",
) -> list[str]:
    requested: list[str] = []

    if isinstance(sites, str):
        requested.extend(part.strip().lower() for part in sites.split(","))
    elif sites:
        requested.extend(str(part).strip().lower() for part in sites)

    lower = query.lower()
    aliases = {
        "github": "github_search",
        "simplifyjobs": "github_simplify",
        "simplify jobs": "github_simplify",
        "pitt": "github_pittcsc",
        "pittcsc": "github_pittcsc",
        "intern-list": "intern_list",
        "intern list": "intern_list",
        "levels": "levels_fyi",
        "levels.fyi": "levels_fyi",
        "yc": "yc_jobs",
        "y combinator": "yc_jobs",
        "zip recruiter": "ziprecruiter",
    }
    for source in DEFAULT_SOURCES:
        if source in lower and source not in requested:
            requested.append(source)
    for token, source in aliases.items():
        if token in lower and source not in requested:
            requested.append(source)

    if _all_sources_requested(query, source_scope):
        requested = list(DEFAULT_SOURCES)
    elif not any(site in SOURCE_REGISTRY for site in requested):
        requested = list(DEFAULT_SOURCES)

    return [site for site in DEFAULT_SOURCES if site in requested]


def _search_keywords(role: str, query: str, target_year: str) -> str:
    lower = query.lower()
    terms = [role]

    if target_year:
        terms.insert(0, target_year)

    if any(token in lower for token in ("intern", "internship", "internships")) and "intern" not in role.lower():
        terms.append("internship")

    if "new grad" in lower and "new grad" not in role.lower():
        terms.append("new grad")

    return _clean(" ".join(dict.fromkeys(term for term in terms if term)))


def _google_site_search(domain: str, keywords: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"site:{domain} {keywords}")


def _github_search_url(query: str) -> str:
    return "https://github.com/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "type": "repositories",
            "s": "updated",
            "o": "desc",
        }
    )


def _job_search_urls(role: str, location: str, sites: list[str], query: str, target_year: str) -> list[dict[str, str]]:
    keywords = _search_keywords(role, query, target_year)
    keywords_q = urllib.parse.quote_plus(keywords)
    location_q = urllib.parse.quote_plus(location)
    simplify_repo = f"https://github.com/SimplifyJobs/Summer{target_year}-Internships" if target_year else ""
    pitt_repo = f"https://github.com/pittcsc/Summer{target_year}-Internships" if target_year else ""
    urls = {
        "linkedin": (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={keywords_q}&sortBy=DD&f_TPR=r86400"
            + (f"&location={location_q}" if location else "")
        ),
        "dice": (
            "https://www.dice.com/jobs"
            f"?q={keywords_q}&radius=30&radiusUnit=mi&page=1&pageSize=20&filters.postedDate=ONE"
            + (f"&location={location_q}" if location else "")
        ),
        "glassdoor": (
            "https://www.glassdoor.com/Job/jobs.htm"
            f"?sc.keyword={keywords_q}"
            + (f"&locKeyword={location_q}" if location else "")
        ),
        "github_search": (
            _github_search_url(keywords + " internships repositories")
        ),
        "github_simplify": simplify_repo or _github_search_url("org:SimplifyJobs internships"),
        "github_pittcsc": pitt_repo or _github_search_url("org:pittcsc internships"),
        "intern_list": _google_site_search("intern-list.com", keywords),
        "simplify": f"https://simplify.jobs/jobs?query={keywords_q}",
        "levels_fyi": "https://www.levels.fyi/internships/",
        "wellfound": f"https://wellfound.com/jobs?q={keywords_q}",
        "yc_jobs": f"https://www.ycombinator.com/jobs?query={keywords_q}",
        "greenhouse": _google_site_search("boards.greenhouse.io", keywords),
        "lever": _google_site_search("jobs.lever.co", keywords),
        "builtin": f"https://builtin.com/jobs?search={keywords_q}",
        "indeed": f"https://www.indeed.com/jobs?q={keywords_q}" + (f"&l={location_q}" if location else ""),
        "ziprecruiter": f"https://www.ziprecruiter.com/jobs-search?search={keywords_q}",
        "handshake": f"https://app.joinhandshake.com/stu/postings?query={keywords_q}",
        "ripplematch": "https://ripplematch.com/jobs",
        "wayup": f"https://www.wayup.com/s/jobs/?keywords={keywords_q}",
    }
    return [
        {
            "site": site,
            "label": SOURCE_REGISTRY[site]["label"],
            "kind": SOURCE_REGISTRY[site]["kind"],
            "url": urls[site],
            "fallback_url": (
                _github_search_url(f"org:SimplifyJobs {target_year} internships")
                if site == "github_simplify" and target_year
                else _github_search_url(f"org:pittcsc {target_year} internships")
                if site == "github_pittcsc" and target_year
                else ""
            ),
        }
        for site in sites
    ]


def _signup_urls(sites: list[str], email: str) -> list[dict[str, str]]:
    urls: list[dict[str, str]] = []
    for site in sites:
        signup_url = SOURCE_REGISTRY[site].get("signup_url") or ""
        if not signup_url:
            continue
        if email and site in {"handshake"}:
            signup_url += "?email=" + urllib.parse.quote_plus(email)
        urls.append(
            {
                "site": site,
                "label": SOURCE_REGISTRY[site]["label"],
                "kind": SOURCE_REGISTRY[site]["kind"],
                "url": signup_url,
            }
        )
    return urls


def _check_url(item: dict[str, str], timeout: float = 7.0) -> dict[str, Any]:
    url = item["url"]
    status = {
        "site": item["site"],
        "label": item.get("label", item["site"]),
        "url": url,
        "final_url": url,
        "status_code": None,
        "ok_to_open": True,
        "not_found": False,
        "login_required": False,
        "used_fallback": False,
        "error": "",
    }

    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Dexter/1.0"
                )
            },
        )
        text_sample = response.text[:6000].lower()
        status.update(
            {
                "final_url": response.url,
                "status_code": response.status_code,
                "not_found": response.status_code == 404
                or "404 not found" in text_sample
                or "page not found" in text_sample
                or "this is not the web page you are looking for" in text_sample,
                "login_required": response.status_code in {401, 403}
                or "sign in" in text_sample
                or "log in" in text_sample,
            }
        )
    except Exception as e:
        status.update({"error": str(e), "ok_to_open": True})
        return status

    if status["not_found"] and item.get("fallback_url"):
        fallback_item = {**item, "url": item["fallback_url"], "fallback_url": ""}
        fallback_status = _check_url(fallback_item, timeout=timeout)
        fallback_status["used_fallback"] = True
        fallback_status["original_url"] = url
        item["url"] = item["fallback_url"]
        return fallback_status

    status["ok_to_open"] = not status["not_found"]
    return status


def _check_urls(urls: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [_check_url(item) for item in urls]


def _summary_html(run_id: str, title: str, urls: list[dict[str, str]], statuses: list[dict[str, Any]]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    status_by_site = {item["site"]: item for item in statuses}
    rows = []

    for item in urls:
        status = status_by_site.get(item["site"], {})
        badge = "OK"
        if status.get("not_found"):
            badge = "404"
        elif status.get("login_required"):
            badge = "LOGIN"
        elif status.get("error"):
            badge = "CHECK"
        elif status.get("used_fallback"):
            badge = "FALLBACK"

        rows.append(
            "<tr>"
            f"<td>{escape(item.get('label', item['site']))}</td>"
            f"<td>{escape(item.get('kind', 'source'))}</td>"
            f"<td>{escape(str(status.get('status_code') or ''))}</td>"
            f"<td>{escape(badge)}</td>"
            f"<td><a href=\"{escape(item['url'])}\">{escape(item['url'])}</a></td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ background: #05070d; color: #e5f8ff; font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 28px; }}
    h1 {{ color: #22e7ff; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid rgba(148, 163, 184, .2); padding: 10px; text-align: left; vertical-align: top; }}
    th {{ color: #67e8f9; }}
    a {{ color: #7dd3fc; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p>Dexter checked these sources before opening tabs. 404 pages are skipped or replaced by fallback searches when available.</p>
  <table>
    <thead><tr><th>Source</th><th>Type</th><th>Status</th><th>Result</th><th>URL</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>"""
    path = RUNS_DIR / f"{run_id}_brave_group.html"
    path.write_text(html, encoding="utf-8")
    return path


def _open_urls(urls: list[dict[str, str]], browser: str, group_title: str = "", run_id: str = "", statuses: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    openable_urls = [
        item
        for item in urls
        if not statuses
        or next((status for status in statuses if status.get("site") == item["site"]), {}).get("ok_to_open", True)
    ]

    if browser == "Brave Browser" and openable_urls:
        summary_url = ""
        if run_id and statuses:
            summary_path = _summary_html(run_id, group_title or "Dexter Job Sources", urls, statuses)
            summary_url = summary_path.resolve().as_uri()

        all_urls = [summary_url, *(item["url"] for item in openable_urls)] if summary_url else [item["url"] for item in openable_urls]
        try:
            from backend.tools.browser_agent import browser_agent

            for index, url in enumerate(all_urls):
                if index > 0:
                    browser_agent(action="new_tab", timeout_seconds=10)
                browser_agent(action="open_url", url=url, wait_seconds=0.2, timeout_seconds=12)
            for item in openable_urls:
                results.append({"site": item["site"], "ok": True, "mode": "dexter_controlled_browser"})
            return results
        except Exception as e:
            results.append({"site": "browser_agent", "ok": False, "error": str(e)})

        apple_lines = [
            'tell application "Brave Browser"',
            "activate",
            "set jobWindow to make new window",
        ]

        if all_urls:
            apple_lines.append(f'set URL of active tab of jobWindow to "{all_urls[0]}"')
            for url in all_urls[1:]:
                apple_lines.append(f'make new tab at end of tabs of jobWindow with properties {{URL:"{url}"}}')

        apple_lines.append("end tell")

        try:
            subprocess.run(
                ["osascript", "-e", "\n".join(apple_lines)],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            for item in openable_urls:
                results.append({"site": item["site"], "ok": True, "mode": "dedicated_brave_window"})
            return results
        except Exception as e:
            results.append({"site": "brave_group", "ok": False, "error": str(e)})

    for item in openable_urls:
        command = ["open"]
        if browser:
            command.extend(["-a", browser])
        command.append(item["url"])

        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=12)
            results.append({"site": item["site"], "ok": True})
        except Exception as e:
            results.append({"site": item["site"], "ok": False, "error": str(e)})

    return results


def _write_run(run: dict[str, Any]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run['id']}.json"
    path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    return path


def _latest_run() -> dict[str, Any] | None:
    if not RUNS_DIR.exists():
        return None

    runs = sorted(RUNS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not runs:
        return None

    return json.loads(runs[0].read_text(encoding="utf-8"))


def job_application_agent(
    action: str = "start",
    query: str = "",
    role: str = "",
    location: str = "",
    sites: str | list[str] | None = None,
    source_scope: str = "",
    email: str = "",
    browser: str = "Brave Browser",
    max_applications: int = 10,
    auto_apply: bool = False,
    open_browser: bool = True,
    save_password_to_brave: bool = False,
    match_resume: bool = True,
    check_pages: bool = True,
    brave_group: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    """Prepare and track browser-based job application runs.

    This tool intentionally does not final-submit applications. It opens/searches
    the right places and records the run so Dexter can continue after Vishal
    reviews listings and login state in the browser.
    """
    clean_action = _clean(action).lower().replace("-", "_") or "start"

    if clean_action in {"status", "latest"}:
        try:
            from backend.jobs.service import overview

            jobs_overview = overview()
            metrics = jobs_overview.get("metrics", {})
            return {
                "ok": True,
                "tool": "job_application_agent",
                "output": (
                    "Dexter Jobs OS status: "
                    f"{metrics.get('total_jobs', 0)} jobs, "
                    f"{metrics.get('ready_to_apply', 0)} ready to apply, "
                    f"{metrics.get('needs_approval', 0)} approval item(s), "
                    f"{metrics.get('blocked_manual', 0)} manual/restricted item(s)."
                ),
                "jobs_overview": jobs_overview,
                "run": _latest_run(),
            }
        except Exception:
            pass
        run = _latest_run()
        if not run:
            return {"ok": True, "tool": "job_application_agent", "output": "No job runs yet.", "run": None}
        output = (
            f"Latest job run: {run['role']}"
            + (f" in {run['location']}" if run.get("location") else "")
            + f" across {', '.join(run['sites'])}. Status: {run['status']}."
        )
        return {"ok": True, "tool": "job_application_agent", "output": output, "run": run}

    role_name = _infer_role(query, role)
    location_name = _infer_location(query, location)
    target_year = _infer_target_year(query)
    site_names = _normalize_sites(sites, query, source_scope)
    is_signup = clean_action in {"signup", "sign_up", "register", "create_accounts", "create_account"}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if not is_signup and os.getenv("DEXTER_JOBS_OS_LEGACY_LINKS", "false").lower() not in {"1", "true", "yes"}:
        try:
            from backend.jobs.schemas import JobQuery
            from backend.jobs.service import generate_packets, ingest_jobs, latest_report, score_jobs

            demo_mode = os.getenv("DEXTER_JOBS_DEMO_MODE", "false").lower() in {"1", "true", "yes"}
            ingest = ingest_jobs(
                source="all",
                query=JobQuery(
                    keywords=query or role_name,
                    location=location_name,
                    max_results=max(1, min(int(max_applications or 10), 100)),
                    demo=demo_mode,
                ),
                demo=demo_mode,
            )
            scoring = score_jobs()
            packets = generate_packets(limit=max(1, min(int(max_applications or 10), 50)))
            report = latest_report()
            output = (
                f"Dexter Jobs OS ingested {ingest.get('jobs_found', 0)} posting(s), "
                f"created {ingest.get('jobs_new', 0)} new job(s), scored {scoring.get('jobs_scored', 0)}, "
                f"and generated {packets.get('packets_generated', 0)} application packet(s). "
                "Final submission remains disabled and every application requires approval."
            )
            return {
                "ok": True,
                "tool": "job_application_agent",
                "mode": "jobs_os",
                "output": output,
                "ingest": ingest,
                "scoring": scoring,
                "packets": packets,
                "report": report,
            }
        except Exception as e:
            return {"ok": False, "tool": "job_application_agent", "mode": "jobs_os", "error": str(e)}

    urls = _signup_urls(site_names, email) if is_signup else _job_search_urls(
        role_name,
        location_name,
        site_names,
        query,
        target_year,
    )
    checked = _check_urls(urls) if check_pages else []
    opened = (
        _open_urls(
            urls,
            browser,
            group_title=(
                "Dexter Signup Sources"
                if is_signup
                else f"Dexter {role_name} {target_year}".strip()
            ),
            run_id=run_id,
            statuses=checked,
        )
        if open_browser and (brave_group or browser != "Brave Browser")
        else _open_urls(urls, browser, statuses=checked)
        if open_browser
        else []
    )
    opened_modes = {str(item.get("mode") or "") for item in opened if item.get("ok")}
    used_controlled_browser = "dexter_controlled_browser" in opened_modes

    run = {
        "id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "signup_pending" if is_signup else "ready_for_review",
        "action": clean_action,
        "query": query,
        "role": role_name,
        "location": location_name,
        "target_year": target_year,
        "sites": site_names,
        "sources": [
            {
                "site": site,
                "label": SOURCE_REGISTRY[site]["label"],
                "kind": SOURCE_REGISTRY[site]["kind"],
            }
            for site in site_names
        ],
        "max_applications": max(1, min(int(max_applications or 10), 50)),
        "auto_apply_requested": bool(auto_apply),
        "account_email": email,
        "save_password_to_brave_requested": bool(save_password_to_brave),
        "match_resume": bool(match_resume),
        "browser": browser,
        "searches": urls,
        "checked": checked,
        "opened": opened,
        "notes": notes,
        "guardrails": {
            "uses_existing_browser_sessions": True,
            "stores_credentials": False,
            "final_submit_requires_user_review": True,
            "account_creation_requires_user_completion": True,
            "password_save_is_browser_prompt": True,
            "native_brave_tab_group_api_available": False,
            "uses_dedicated_brave_window": bool(
                brave_group and browser == "Brave Browser" and not used_controlled_browser
            ),
            "uses_dexter_controlled_browser": used_controlled_browser,
            "handles_captcha_or_mfa": "manual",
        },
        "next_steps": (
            [
                "Use the opened signup pages to create accounts with your Gmail.",
                "Let Brave save passwords from its own password-save prompt after you create each account.",
                "Complete any email confirmation, CAPTCHA, or MFA manually.",
                "Tell Dexter to continue after the accounts are logged in.",
            ]
            if is_signup
            else [
                "Upload your resume/documents if you want skill matching.",
                "Confirm each source is logged in where needed.",
                "Review the opened listings and tell Dexter which ones are okay to apply to.",
                "Dexter can draft/fill applications, but final submission stays behind a review checkpoint.",
            ]
        ),
    }

    path = _write_run(run)
    log_action("job_application_run_started", {**run, "run_file": str(path)})

    opened_ok = [item["site"] for item in opened if item.get("ok")]
    opened_failed = [item for item in opened if not item.get("ok")]
    not_found = [item["site"] for item in checked if item.get("not_found")]
    fallbacks = [item["site"] for item in checked if item.get("used_fallback")]

    source_labels = [SOURCE_REGISTRY[site]["label"] for site in site_names]
    if is_signup:
        output = (
            f"Prepared signup/login workflow for {len(urls)} sources"
            + (f" using {email}" if email else "")
            + ". "
        )
    else:
        output = (
            f"Started a job run for {role_name}"
            + (f" {target_year}" if target_year else "")
            + (f" in {location_name}" if location_name else "")
            + f" across {len(site_names)} sources. "
        )

    if opened_ok:
        if used_controlled_browser:
            output += f"Opened {len(opened_ok)} source tab(s) in Dexter's controlled Brave session. "
        elif browser == "Brave Browser" and brave_group:
            output += f"Opened a dedicated Brave window with {len(opened_ok)} source tabs. "
        else:
            output += f"Opened in {browser}: {', '.join(opened_ok)}. "
    elif open_browser:
        output += "I created the run, but the browser tabs did not open successfully. "
    else:
        output += (
            "Prepared the signup URLs without opening the browser. "
            if is_signup
            else "Prepared the search URLs without opening the browser. "
        )

    if is_signup:
        output += (
            "I did not create accounts, enter passwords, confirm email, or save credentials. "
            "Brave can save passwords only when you accept its password-save prompt after signup."
        )
    else:
        output += (
            "Sources include: "
            + ", ".join(source_labels[:8])
            + ("..." if len(source_labels) > 8 else "")
            + ". I will use existing logged-in browser sessions and will not store passwords. "
            "Upload your resume for skill matching; final-submit stays behind your review."
        )

    if not_found:
        output += f" Skipped 404/not-found sources: {', '.join(not_found)}."
    if fallbacks:
        output += f" Used fallback searches for: {', '.join(fallbacks)}."

    return {
        "ok": True,
        "tool": "job_application_agent",
        "output": output,
        "run": run,
        "run_file": str(path),
        "searches": urls,
        "checked": checked,
        "opened": opened,
        "open_errors": opened_failed,
    }
