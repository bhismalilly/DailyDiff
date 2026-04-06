"""MCP tool definitions."""

from github_api import (
    get_github_username,
    last_working_day,
    get_repo_commits,
    get_repo_events,
    run_gh,
)
from formatters import get_response_format


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

    SUGGESTED SCRIPT: Generate a conversational 2-3 sentence standup summary that sounds natural.
    Use contractions, vary sentence structure, and lead with key accomplishments.
    Avoid template language like "Yesterday I... Today I... No blockers."
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


def get_commit_details(
    repo: str,
    sha: str,
) -> dict:
    """Get file-level diff details for a specific commit. Use this when the user
    asks for more detail about what changed in a particular commit.

    Args:
        repo: The repo in "owner/repo" format.
        sha: The commit SHA (full or short).
    """
    jq_filter = '{sha, message: .commit.message, author: .commit.author.name, date: .commit.author.date, html_url, stats, files: [.files[] | {filename, status, additions, deletions}]}'
    try:
        commit = run_gh([
            "api", f"/repos/{repo}/commits/{sha}",
            "--jq", jq_filter,
        ])
        return {
            "sha": commit["sha"][:8],
            "message": commit["message"],
            "author": commit["author"],
            "date": commit["date"],
            "url": commit["html_url"],
            "stats": commit.get("stats", {}),
            "files": commit.get("files", []),
        }
    except Exception as e:
        return {"error": f"Failed to fetch commit details: {e}"}
