"""CLI-specific exceptions."""
from typing import Optional

class CliError(Exception):
    """Base CLI error."""

class ConfigError(CliError):
    """Configuration file or value issues."""

    def __init__(self, message: str):
        super().__init__(message)

class ApiError(CliError):
    """HTTP API error wrapper."""

    def __init__(self, status_code: int, message: str, body: Optional[str] = None):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}")

class ValidationError(CliError):
    """User input validation error."""

    def __init__(self, message: str):
        super().__init__(message)
