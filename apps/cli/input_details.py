"""Formatting helpers for conditional decision-input targets."""
from __future__ import annotations

from typing import Any

import click


def print_available_input_details(data: Any) -> None:
    if not isinstance(data, dict):
        return
    details = data.get("available_input_details")
    if isinstance(details, list) and details:
        click.echo("Available inputs this turn:")
        for detail in details:
            if not isinstance(detail, dict):
                continue
            key = detail.get("key") or "-"
            label = detail.get("label") or key
            target = detail.get("target")
            if isinstance(target, dict):
                season_number = target.get("season_number")
                month_name = target.get("month_name") or "-"
                opponent_name = target.get("opponent_name") or "-"
                click.echo(
                    f"- {key}: {label} -> Season {season_number} {month_name} home vs {opponent_name}"
                )
            else:
                click.echo(f"- {key}: {label}")
        return

    available = data.get("available_inputs")
    if available:
        click.echo("Available inputs this turn:")
        for value in available:
            click.echo(f"- {value}")
