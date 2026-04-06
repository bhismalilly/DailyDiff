import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools import get_standup_summary, get_commit_details

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
    """Get file-level diff details for a specific commit. Use this when the user
    asks for more detail about what changed in a particular commit.

    Args:
        repo: The repo in "owner/repo" format.
        sha: The commit SHA (full or short).
    """
    return get_commit_details(repo, sha)


if __name__ == "__main__":
    mcp.run()
