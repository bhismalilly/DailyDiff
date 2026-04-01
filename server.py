import json
import os
import subprocess
from datetime import datetime, timedelta

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("standup-assistant")

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")


def last_working_day() -> str:
    """Return ISO date string for the last working day (skip weekends)."""
    today = datetime.now()
    weekday = today.weekday()  # 0=Mon ... 6=Sun
    if weekday == 0:  # Monday -> last Friday
        delta = 3
    elif weekday == 6:  # Sunday -> last Friday
        delta = 2
    else:
        delta = 1
    return (today - timedelta(days=delta)).strftime("%Y-%m-%d")


def get_github_username() -> str:
    """Return configured username or auto-detect via gh CLI."""
    if GITHUB_USERNAME:
        return GITHUB_USERNAME
    result = subprocess.run(
        ["C:\\Program Files\\GitHub CLI\\gh.exe", "api", "user", "--jq", ".login"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def run_gh(args: list[str]) -> list | dict:
    """Run a gh CLI command and return parsed JSON output."""
    result = subprocess.run(
        ["C:\\Program Files\\GitHub CLI\\gh.exe"] + args,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


@mcp.tool()
def get_standup_summary(
    project: str | None = None,
    since_date: str | None = None,
) -> dict:
    """Get a summary of GitHub commits and pull requests since the last working day for standup preparation.

    Args:
        project: Optional filter. Use "owner/repo" for a specific repo, or a
                 name prefix to match repo names (case-insensitive). If omitted,
                 all your activity is returned.
        since_date: Optional ISO date string (YYYY-MM-DD) to look back from.
                    Defaults to the last working day (skips weekends).
    """
    try:
        username = get_github_username()
    except Exception as e:
        return {"error": f"Could not determine GitHub username: {e}"}

    if not since_date:
        since_date = last_working_day()

    # --- Commits ---
    commit_args = [
        "search", "commits",
        f"--author={username}",
        f"--committer-date=>={since_date}",
        "--json", "repository,sha,commit,url",
        "--limit", "100",
    ]
    if project and "/" in project:
        commit_args += ["--repo", project]

    commits_by_repo: dict[str, list[dict]] = {}
    try:
        raw_commits = run_gh(commit_args)
        for c in raw_commits:
            repo_name = c["repository"]["fullName"]

            if project and "/" not in project:
                if not c["repository"]["name"].lower().startswith(project.lower()):
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
    pr_args = [
        "search", "prs",
        f"--author={username}",
        f"--created=>={since_date}",
        "--json", "repository,number,title,state,url,createdAt,labels",
        "--limit", "100",
    ]
    if project and "/" in project:
        pr_args += ["--repo", project]

    pull_requests: list[dict] = []
    try:
        raw_prs = run_gh(pr_args)
        for pr in raw_prs:
            repo_name = pr["repository"]["nameWithOwner"]

            if project and "/" not in project:
                if not pr["repository"]["name"].lower().startswith(project.lower()):
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
    }


if __name__ == "__main__":
    mcp.run()
