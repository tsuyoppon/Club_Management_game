"""Authentication utilities for the CLI."""
from typing import Dict

from .config import CliConfig


def build_headers(config: CliConfig) -> Dict[str, str]:
    # Only include auth header; do not leak extra data in verbose mode.
    return {"X-User-Email": config.user_email}
