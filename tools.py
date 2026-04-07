"""MCP tool definitions."""

from github_api import (
    get_github_username,
    last_working_day,
    get_repo_commits,
    get_repo_events,
    run_gh,
    run_gh_raw,
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
    """Get detailed commit information including file-level diffs and line-by-line changes.
    Use this when the user asks for more detail about what changed in a particular commit.

    Args:
        repo: The repo in "owner/repo" format.
        sha: The commit SHA (full or short).
    """
    try:
        # Fetch raw JSON without --jq to avoid empty output when jq filter
        # fails on unexpected API response shapes (e.g. private org repos)
        raw = run_gh(["api", f"/repos/{repo}/commits/{sha}"])
        files = [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                # patch is absent for binary files or diffs exceeding GitHub's size limit
                "patch": f.get("patch"),
            }
            for f in raw.get("files", [])
        ]
        has_patches = any(f["patch"] for f in files)
        return {
            "sha": raw["sha"][:8],
            "message": raw["commit"]["message"],
            "author": raw["commit"]["author"]["name"],
            "date": raw["commit"]["author"]["date"],
            "url": raw["html_url"],
            "stats": raw.get("stats", {}),
            "files": files,
            "diff_available": has_patches,
            "diff_note": None if has_patches else "Patch content unavailable — files may be binary, too large, or access may be restricted. File-level stats are still shown above.",
        }
    except Exception as e:
        return {"error": f"Failed to fetch commit details: {e}"}


def get_raw_commit_diff(
    repo: str,
    sha: str,
) -> dict:
    """Fetch the raw unified diff for a commit using GitHub's diff media type.
    This is a different code path from the JSON API and works even when the
    JSON endpoint returns empty — useful for org/private repos and when commit
    messages are not descriptive enough to understand what changed.

    Args:
        repo: The repo in "owner/repo" format.
        sha: The commit SHA (full or short).
    """
    try:
        diff_text = run_gh_raw([
            "api", f"/repos/{repo}/commits/{sha}",
            "-H", "Accept: application/vnd.github.diff",
        ])
        return {
            "sha": sha,
            "repo": repo,
            "diff": diff_text,
        }
    except Exception as e:
        return {"error": f"Failed to fetch raw diff: {e}"}


def get_pr_diff(
    repo: str,
    pr_number: int,
) -> dict:
    """Fetch the full unified diff for a pull request.
    Use this to understand what a PR actually changes when the PR description
    is missing, vague, or commit messages are not descriptive.

    Args:
        repo: The repo in "owner/repo" format.
        pr_number: The pull request number.
    """
    try:
        diff_text = run_gh_raw([
            "api", f"/repos/{repo}/pulls/{pr_number}",
            "-H", "Accept: application/vnd.github.diff",
        ])
        return {
            "repo": repo,
            "pr_number": pr_number,
            "diff": diff_text,
        }
    except Exception as e:
        return {"error": f"Failed to fetch PR diff: {e}"}
