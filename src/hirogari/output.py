"""Text-table / CSV / JSON output helpers shared by the CLI."""

from __future__ import annotations

import csv
import json
import sys
from typing import Any, TextIO


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def print_table(
    headers: list[str], rows: list[dict[str, Any]], file: TextIO | None = None
) -> None:
    # `file` defaults to None (resolved to sys.stdout *here*, at call
    # time) rather than `= sys.stdout` as the parameter default: a
    # default value is evaluated once, at function-definition time, so it
    # would permanently bind whatever sys.stdout was when this module was
    # first imported -- silently ignoring any later stdout redirection
    # (pytest's capsys included).
    if file is None:
        file = sys.stdout
    if not rows:
        print("(no rows)", file=file)
        return
    str_rows = [[format_cell(row.get(h)) for h in headers] for row in rows]
    widths = [max(len(headers[i]), *(len(r[i]) for r in str_rows)) for i in range(len(headers))]

    def fmt(cols: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths, strict=True))

    print(fmt(headers), file=file)
    print(fmt(["-" * w for w in widths]), file=file)
    for r in str_rows:
        print(fmt(r), file=file)


def write_csv(path: str, headers: list[str], rows: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def print_json(rows: list[dict[str, Any]], file: TextIO | None = None) -> None:
    print(json.dumps(rows, indent=2), file=file if file is not None else sys.stdout)


def emit(rows: list[dict[str, Any]], *, csv_path: str | None, as_json: bool) -> None:
    """Shared "how should this command's results come out" logic: --json
    wins if both are passed, then --csv, then a readable table to stdout."""
    if not rows:
        print("(no results)")
        return
    headers = list(rows[0].keys())
    if as_json:
        print_json(rows)
    elif csv_path:
        write_csv(csv_path, headers, rows)
        print(f"wrote {len(rows)} row(s) to {csv_path}")
    else:
        print_table(headers, rows)
