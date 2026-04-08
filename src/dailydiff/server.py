import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .tools import get_standup_summary, get_commit_details, get_raw_commit_diff, get_pr_diff

load_dotenv()

mcp = FastMCP("standup-assistant")


@mcp.tool()
def get_standup_summary_tool(
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
    return get_standup_summary(project, since_date)


@mcp.tool()
def get_commit_details_tool(
    repo: str,
    sha: str,
) -> dict:
    """Get detailed commit information including file-level diffs and line-by-line changes.
    Use this when the user asks what code changed or wants to see the actual diffs in a commit.

    If the response has diff_available=False or files have no patch content,
    you MUST automatically follow up with get_raw_commit_diff_tool using the same
    repo and sha — do not tell the user the diff is unavailable before trying that.

    Args:
        repo: The repo in "owner/repo" format.
        sha: The commit SHA (full or short).
    """
    return get_commit_details(repo, sha)


@mcp.tool()
def get_raw_commit_diff_tool(
    repo: str,
    sha: str,
) -> dict:
    """Fetch the raw unified diff for a commit using GitHub's diff media type.
    Use this when get_commit_details returns empty or when the commit message is
    vague and you need to see the actual code changes to describe what was done.

    Args:
        repo: The repo in "owner/repo" format.
        sha: The commit SHA (full or short).
    """
    return get_raw_commit_diff(repo, sha)


@mcp.tool()
def get_pr_diff_tool(
    repo: str,
    pr_number: int,
) -> dict:
    """Fetch the full unified diff for a pull request.
    Use this when the PR description is vague or missing and you need to understand
    what the PR actually changes in order to describe it accurately.

    Args:
        repo: The repo in "owner/repo" format.
        pr_number: The pull request number.
    """
    return get_pr_diff(repo, pr_number)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
