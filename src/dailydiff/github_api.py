"""GitHub API interactions via gh CLI."""

import json
import os
import subprocess
from datetime import datetime, timedelta

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")


def last_working_day() -> str:
    """Return ISO date string for the last working day (skip weekends)."""
    today = datetime.now()
    weekday = today.weekday()
    if weekday == 0:
        delta = 3
    elif weekday == 6:
        delta = 2
    else:
        delta = 1
    return (today - timedelta(days=delta)).strftime("%Y-%m-%d")


def get_github_username() -> str:
    """Return configured username or auto-detect via gh CLI."""
    if GITHUB_USERNAME:
        return GITHUB_USERNAME
    result = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return result.stdout.strip()


def run_gh(args: list[str]) -> list | dict:
    """Run a gh CLI command and return parsed JSON output."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    # Some org repos cause gh to exit with code 1 due to SSO warnings in stderr
    # even when the response body is valid — check output first before failing
    if not result.stdout or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "Empty response from gh CLI")
    return json.loads(result.stdout)


def run_gh_raw(args: list[str]) -> str:
    """Run a gh CLI command and return raw text output (for diffs, patches, etc.)."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    # Same as run_gh — prioritise output over exit code for org repos
    if not result.stdout or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "Empty response from gh CLI")
    return result.stdout


def get_active_branches(repo: str, username: str, since_date: str) -> list[str]:
    """Find branches the user pushed to since since_date.

    Uses the user's own event feed (/users/{username}/events) which works for
    private org repos and requires only 1-2 paginated calls instead of probing
    each branch individually.
    """
    branches: set[str] = set()

    for page in range(1, 11):  # GitHub caps at 10 pages
        try:
            events = run_gh([
                "api",
                f"/users/{username}/events?per_page=100&page={page}",
            ])
        except Exception:
            break

        if not events:
            break

        for event in events:
            if event["created_at"][:10] < since_date:
                continue
            if event.get("repo", {}).get("name", "") != repo:
                continue
            if event["type"] == "PushEvent":
                ref = event["payload"]["ref"]
                if ref.startswith("refs/heads/"):
                    ref = ref[len("refs/heads/"):]
                branches.add(ref)
            elif event["type"] == "CreateEvent" and event["payload"]["ref_type"] == "branch":
                branches.add(event["payload"]["ref"])

        # Stop paging once all events on this page predate since_date
        if events[-1]["created_at"][:10] < since_date:
            break

    return list(branches)


def get_repo_commits(repo: str, username: str, since_date: str) -> list[dict]:
    """Fetch commits from a specific repo across all active branches."""
    branches = get_active_branches(repo, username, since_date)

    # Always include the default branch
    if not any(b in ("main", "master") for b in branches):
        branches.append("main")

    seen_shas: set[str] = set()
    commits: list[dict] = []

    for branch in branches:
        try:
            raw = run_gh([
                "api",
                f"/repos/{repo}/commits?author={username}&since={since_date}T00:00:00Z&sha={branch}&per_page=100",
            ])
        except Exception:
            continue

        for c in raw:
            sha = c["sha"][:8]
            if sha in seen_shas:
                continue
            seen_shas.add(sha)
            commits.append({
                "sha": sha,
                "message": c["commit"]["message"].split("\n")[0],
                "date": c["commit"]["author"]["date"],
                "url": c["html_url"],
                "branch": branch,
            })

    return commits


def get_repo_events(repo: str, username: str, since_date: str) -> list[dict]:
    """Get branch creation and push events for the user from the events API."""
    try:
        events = run_gh([
            "api",
            f"/repos/{repo}/events?per_page=100",
        ])
    except Exception:
        return []

    activity: list[dict] = []
    for event in events:
        if event["actor"]["login"] != username:
            continue
        if event["created_at"][:10] < since_date:
            continue

        if event["type"] == "CreateEvent" and event["payload"]["ref_type"] == "branch":
            activity.append({
                "type": "branch_created",
                "branch": event["payload"]["ref"],
                "date": event["created_at"],
            })
        elif event["type"] == "PushEvent":
            ref = event["payload"]["ref"]
            if ref.startswith("refs/heads/"):
                ref = ref[len("refs/heads/"):]
            activity.append({
                "type": "push",
                "branch": ref,
                "date": event["created_at"],
                "commits": len(event["payload"].get("commits", [])),
            })

    return activity
