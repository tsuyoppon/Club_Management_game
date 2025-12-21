"""Input parsing helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .errors import ValidationError

MONTH_START = 8  # August -> month_index 1


def parse_month_to_index(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        dt = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValidationError("Month must be in YYYY-MM format") from exc
    month = dt.month
    # Map 8->1, 9->2, ..., 7->12
    return ((month - MONTH_START) % 12) + 1


def ensure_month_bounds(month_index: Optional[int], label: str) -> Optional[int]:
    if month_index is None:
        return None
    if month_index < 1 or month_index > 12:
        raise ValidationError(f"{label} must be between 1 and 12 (got {month_index})")
    return month_index

