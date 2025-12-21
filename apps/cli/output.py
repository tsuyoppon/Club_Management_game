"""Simple output helpers (no extra deps)."""
from __future__ import annotations

import json
from typing import Any, Iterable, List, Mapping, Sequence


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False))


def _stringify(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


def print_table(rows: Sequence[Mapping[str, Any]], columns: List[str]) -> None:
    # Compute column widths
    headers = [col for col in columns]
    str_rows = [[_stringify(row.get(col, "")) for col in columns] for row in rows]
    widths = [max(len(h), *(len(r[idx]) for r in str_rows) if str_rows else [0]) for idx, h in enumerate(headers)]

    def fmt_row(row: Iterable[str]) -> str:
        return " | ".join(val.ljust(widths[idx]) for idx, val in enumerate(row))

    print(fmt_row(headers))
    print("-+-".join("-" * w for w in widths))
    for row in str_rows:
        print(fmt_row(row))

