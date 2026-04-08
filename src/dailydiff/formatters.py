"""Response formatting and template loading."""

import os


def get_response_format() -> str:
    """Read the response format instructions from RESPONSE_FORMAT.md."""
    format_path = os.path.join(os.path.dirname(__file__), "RESPONSE_FORMAT.md")
    try:
        with open(format_path) as f:
            return f.read()
    except FileNotFoundError:
        return ""
