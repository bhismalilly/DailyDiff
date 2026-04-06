import json
import os
import subprocess
from datetime import datetime, timedelta

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("standup-assistant")

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")


def get_response_format() -> str:
    """Read the response format instructions from RESPONSE_FORMAT.md."""
    format_path = os.path.join(os.path.dirname(__file__), "RESPONSE_FORMAT.md")
    try:
        with open(format_path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


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
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def run_gh(args: list[str]) -> list | dict:
    """Run a gh CLI command and return parsed JSON output."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


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


@mcp.tool()
def get_standup_summary(
    project: str | None = None,
    since_date: str | None = None,
) -> dict:
    """Get a summary of GitHub commits, pull requests, and branch activity since the last working day for standup preparation.

    Args:
        project: Optional filter. Use "owner/repo" for a specific repo, or a
                 name prefix to match repo names (case-insensitive). If omitted,
                 all your activity is returned.
        since_date: Optional ISO date string (YYYY-MM-DD) to look back from.
                    Defaults to the last working day (skips weekends).

    RESPONSE FORMAT: Follow the formatting rules in the included `response_format` field.
    """
    try:
        username = get_github_username()
    except Exception as e:
        return {"error": f"Could not determine GitHub username: {e}"}

    if not since_date:
        since_date = last_working_day()

    # --- Commits ---
    commits_by_repo: dict[str, list[dict]] = {}
    try:
        if project and "/" in project:
            repo_commits = get_repo_commits(project, username, since_date)
            if repo_commits:
                commits_by_repo[project] = repo_commits
        else:
            commit_args = [
                "search", "commits",
                f"--author={username}",
                f"--committer-date=>={since_date}",
                "--json", "repository,sha,commit,url",
                "--limit", "100",
            ]
            raw_commits = run_gh(commit_args)
            for c in raw_commits:
                repo_name = c["repository"]["fullName"]
                if project and not c["repository"]["name"].lower().startswith(project.lower()):
                    continue
                if repo_name not in commits_by_repo:
                    commits_by_repo[repo_name] = []
                commits_by_repo[repo_name].append({
                    "sha": c["sha"][:8],
                    "message": c["commit"]["message"].split("\n")[0],
                    "date": c["commit"]["author"]["date"],
                    "url": c["url"],
                })
    except Exception as e:
        return {"error": f"Failed to search commits: {e}"}

    # --- Pull Requests ---
    pull_requests: list[dict] = []
    try:
        if project and "/" in project:
            raw_prs = run_gh([
                "pr", "list",
                "--repo", project,
                "--search", f"author:{username} updated:>={since_date}",
                "--state", "all",
                "--json", "number,title,state,url,createdAt,labels",
                "--limit", "100",
            ])
            for pr in raw_prs:
                pull_requests.append({
                    "repo": project,
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"].lower(),
                    "url": pr["url"],
                    "created_at": pr["createdAt"],
                    "labels": [label["name"] for label in pr.get("labels", [])],
                })
        else:
            pr_args = [
                "search", "prs",
                f"--author={username}",
                f"--updated=>={since_date}",
                "--json", "repository,number,title,state,url,createdAt,labels",
                "--limit", "100",
            ]
            raw_prs = run_gh(pr_args)
            for pr in raw_prs:
                repo_name = pr["repository"]["nameWithOwner"]
                if project and not pr["repository"]["name"].lower().startswith(project.lower()):
                    continue
                pull_requests.append({
                    "repo": repo_name,
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "url": pr["url"],
                    "created_at": pr["createdAt"],
                    "labels": [label["name"] for label in pr.get("labels", [])],
                })
    except Exception as e:
        return {"error": f"Failed to search pull requests: {e}"}

    # --- Branch / Push Activity (specific repo only) ---
    branch_activity: list[dict] = []
    if project and "/" in project:
        branch_activity = get_repo_events(project, username, since_date)

    total_commits = sum(len(c) for c in commits_by_repo.values())
    changes = [{"repo": repo, "commits": commits} for repo, commits in commits_by_repo.items()]

    return {
        "since": since_date,
        "project_filter": project,
        "author": username,
        "total_commits": total_commits,
        "repos_with_changes": len(commits_by_repo),
        "changes": changes,
        "pull_requests": pull_requests,
        "branch_activity": branch_activity,
        "response_format": get_response_format(),
    }


if __name__ == "__main__":
    mcp.run()
