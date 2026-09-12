"""hirogari's command-line interface. See SPEC.md for the command list."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from hirogari.analysis import diff_in_diff, lift
from hirogari.output import emit
from hirogari.sources import github_releases, github_stars, github_traffic, npm, pypi
from hirogari.sources.base import SourceError
from hirogari.store import DEFAULT_DB_PATH, Event, MetricPoint, Store


def _attempt_metrics(
    store: Store, label: str, fetch: Callable[[], list[MetricPoint]]
) -> bool:
    try:
        points = fetch()
    except SourceError as exc:
        print(f"warning: {label} failed: {exc}", file=sys.stderr)
        return False
    n = store.upsert_metrics(points)
    print(f"{label}: {n} row(s)")
    return True


def _attempt_events(store: Store, label: str, fetch: Callable[[], list[Event]]) -> bool:
    try:
        events = fetch()
    except SourceError as exc:
        print(f"warning: {label} failed: {exc}", file=sys.stderr)
        return False
    n = store.upsert_events(events)
    print(f"{label}: {n} row(s)")
    return True


def cmd_collect(args: argparse.Namespace) -> int:
    project: str = args.project
    token = os.environ.get("GITHUB_TOKEN")
    store = Store(args.db)

    ok = True
    ok &= _attempt_events(
        store,
        f"{project}: github releases",
        partial(github_releases.collect_releases, project, token=token),
    )
    if token:
        ok &= _attempt_metrics(
            store,
            f"{project}: github stars",
            partial(github_stars.collect_stars, project, token=token),
        )
    else:
        # Verified live: as of July 2026 GitHub restricts stargazer
        # listings to repo admins/collaborators (see github_stars.py's
        # docstring) -- a token only helps here if it's yours to admin.
        # Skip proactively instead of always failing with the same error.
        print(
            f"{project}: github stars: skipped "
            "(GITHUB_TOKEN not set; only works if you admin the repo anyway)"
        )
    if args.pypi:
        ok &= _attempt_metrics(
            store, f"{project}: pypi downloads", partial(pypi.collect_downloads, project, args.pypi)
        )
    if args.npm:
        ok &= _attempt_metrics(
            store, f"{project}: npm downloads", partial(npm.collect_downloads, project, args.npm)
        )
    if token:
        ok &= _attempt_metrics(
            store,
            f"{project}: github traffic",
            partial(github_traffic.collect_traffic, project, token=token),
        )
    else:
        print(f"{project}: github traffic: skipped (GITHUB_TOKEN not set)")

    store.close()
    return 0 if ok else 1


def cmd_events(args: argparse.Namespace) -> int:
    project: str = args.project
    token = os.environ.get("GITHUB_TOKEN")
    store = Store(args.db)
    ok = _attempt_events(
        store,
        f"{project}: github releases",
        partial(github_releases.collect_releases, project, token=token),
    )
    store.close()
    return 0 if ok else 1


def cmd_event_add(args: argparse.Namespace) -> int:
    try:
        when = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"error: --date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
        return 1
    store = Store(args.db)
    store.upsert_event(Event(args.project, when, args.kind, args.label, args.url))
    store.close()
    print(f"added {args.kind} event {args.label!r} on {when.isoformat()} for {args.project}")
    return 0


def _control_pool(store: Store, project: str, metric: str) -> list[str]:
    """Every other project in the local db that has this exact metric —
    the default DiD control pool. No cadence/relevance filtering: an
    unusable control (insufficient data, its own event in-window) is
    excluded per-event by `diff_in_diff` itself, not here."""
    source, _, name = metric.partition(".")
    return [
        candidate
        for candidate in store.list_projects()
        if candidate != project
        and any(s == source and n == name for s, n, *_rest in store.list_metrics(candidate))
    ]


def cmd_lift(args: argparse.Namespace) -> int:
    store = Store(args.db)
    events = store.get_events(args.project)
    if not events:
        print(
            f"no events stored for {args.project} -- run `hirogari events {args.project}` first",
            file=sys.stderr,
        )
        return 1

    control_projects: list[str] = []
    if args.did:
        control_projects = _control_pool(store, args.project, args.metric)
        if not control_projects:
            print(
                f"warning: --did requested but no other project in the db has metric "
                f"{args.metric!r} -- every row's control fields will be empty",
                file=sys.stderr,
            )

    rows: list[dict[str, Any]] = []
    for event in events:
        if args.did:
            did_result = diff_in_diff(
                store,
                args.project,
                args.metric,
                event.date,
                control_projects,
                pre=args.pre,
                post=args.post,
                sustain_start=args.sustain_start,
                sustain_end=args.sustain_end,
            )
            row_data = did_result.to_dict()
        else:
            lift_result = lift(
                store,
                args.project,
                args.metric,
                event.date,
                pre=args.pre,
                post=args.post,
                sustain_start=args.sustain_start,
                sustain_end=args.sustain_end,
            )
            row_data = lift_result.to_dict()
        rows.append({"event_kind": event.kind, "event_label": event.label, **row_data})
    store.close()
    emit(rows, csv_path=args.csv, as_json=args.json)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = Store(args.db)
    events = store.get_events(args.project)
    metrics = store.list_metrics(args.project)
    if not events:
        print(f"no events stored for {args.project}", file=sys.stderr)
        return 1
    if not metrics:
        print(f"no metrics stored for {args.project}", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = []
    for source, name, *_rest in metrics:
        metric_id = f"{source}.{name}"
        for event in events:
            result = lift(store, args.project, metric_id, event.date)
            rows.append({"event_kind": event.kind, "event_label": event.label, **result.to_dict()})
    store.close()
    emit(rows, csv_path=args.csv, as_json=args.json)
    return 0


def cmd_study(args: argparse.Namespace) -> int:
    try:
        lines = Path(args.projects_file).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"error: could not read {args.projects_file}: {exc}", file=sys.stderr)
        return 1

    token = os.environ.get("GITHUB_TOKEN")
    store = Store(args.db)
    any_failure = False
    projects: list[str] = []

    # Phase 1: collect everything for every project first. --did needs
    # every OTHER project's data available as a potential control when
    # analyzing any one project's events, so analysis can't start until
    # the whole pool has been collected.
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        project = parts[0]
        pypi_package = parts[1] if len(parts) > 1 and parts[1] else None
        projects.append(project)

        print(f"== {project} ==")
        # functools.partial binds `project`/`pypi_package` immediately as
        # arguments rather than capturing the loop variable by reference,
        # so there's no late-binding hazard from defining these in a loop.
        ok = _attempt_events(
            store,
            f"{project}: github releases",
            partial(github_releases.collect_releases, project, token=token),
        )
        if token:
            ok &= _attempt_metrics(
                store,
                f"{project}: github stars",
                partial(github_stars.collect_stars, project, token=token),
            )
        else:
            print(f"{project}: github stars: skipped (GITHUB_TOKEN not set; GitHub requires auth)")
        if pypi_package:
            ok &= _attempt_metrics(
                store,
                f"{project}: pypi downloads",
                partial(pypi.collect_downloads, project, pypi_package),
            )
        if not ok:
            any_failure = True

    # Phase 2: analyze. Every project's own events, against every metric
    # it has, with every other studied project available as a --did
    # control candidate (diff_in_diff itself excludes any that turn out
    # confounded or insufficient for a given event's specific window).
    all_rows: list[dict[str, Any]] = []
    for project in projects:
        events = store.get_events(project, kind="release")
        metrics = store.list_metrics(project)
        for source, name, *_rest in metrics:
            metric_id = f"{source}.{name}"
            for event in events:
                if args.did:
                    control_projects = [p for p in projects if p != project]
                    did_result = diff_in_diff(
                        store, project, metric_id, event.date, control_projects
                    )
                    row_data = did_result.to_dict()
                else:
                    lift_result = lift(store, project, metric_id, event.date)
                    row_data = lift_result.to_dict()
                all_rows.append(
                    {
                        "project": project,
                        "event_kind": event.kind,
                        "event_label": event.label,
                        **row_data,
                    }
                )

    store.close()
    emit(all_rows, csv_path=args.csv, as_json=args.json)
    return 0 if not any_failure else 1


def cmd_list(args: argparse.Namespace) -> int:
    store = Store(args.db)
    projects = store.list_projects()
    if not projects:
        print("(empty database)")
        store.close()
        return 0
    for project in projects:
        print(project)
        for source, name, start, end, count in store.list_metrics(project):
            print(f"  {source}.{name}: {count} day(s), {start} to {end}")
        events = store.get_events(project)
        by_kind: dict[str, int] = {}
        for event in events:
            by_kind[event.kind] = by_kind.get(event.kind, 0) + 1
        kinds = ", ".join(f"{count} {kind}" for kind, count in sorted(by_kind.items()))
        print(f"  events: {len(events)}" + (f" ({kinds})" if kinds else ""))
    store.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    # --db lives ONLY on the top-level parser, not duplicated onto each
    # subparser via `parents=`. argparse's subparser dispatch parses each
    # subcommand into a *fresh* namespace and then copies every one of
    # its own actions' values (defaults included) back onto the outer
    # namespace -- so a shared `--db` action on both levels means the
    # subparser's default silently overwrites whatever `--db` the user
    # gave *before* the subcommand, unless they also repeat it after.
    # Keeping it top-level-only means `--db` must come before the
    # subcommand (`hirogari --db PATH lift ...`), which sidesteps the
    # footgun entirely instead of working around it.
    parser = argparse.ArgumentParser(
        prog="hirogari",
        description=(
            "Measure whether releases, docs changes, and posts moved OSS "
            "adoption, and whether it lasted."
        ),
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB_PATH, help=f"SQLite database path (default: {DEFAULT_DB_PATH})"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="fetch + store all available metrics for a project")
    p_collect.add_argument("project", help="owner/repo")
    p_collect.add_argument("--pypi", help="PyPI package name")
    p_collect.add_argument("--npm", help="npm package name")
    p_collect.set_defaults(func=cmd_collect)

    p_events = sub.add_parser("events", help="fetch GitHub releases as events")
    p_events.add_argument("project", help="owner/repo")
    p_events.set_defaults(func=cmd_events)

    p_event = sub.add_parser("event", help="manage events")
    event_sub = p_event.add_subparsers(dest="event_command", required=True)
    p_event_add = event_sub.add_parser("add", help="add a manual event")
    p_event_add.add_argument("project", help="owner/repo")
    p_event_add.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_event_add.add_argument("--label", required=True)
    p_event_add.add_argument("--kind", default="manual", help="release | post | docs | manual")
    p_event_add.add_argument("--url")
    p_event_add.set_defaults(func=cmd_event_add)

    p_lift = sub.add_parser("lift", help="compute lift for every stored event against one metric")
    p_lift.add_argument("project", help="owner/repo")
    p_lift.add_argument(
        "--metric", default="pypi.downloads", help="source.name, e.g. pypi.downloads"
    )
    p_lift.add_argument("--pre", type=int, default=14)
    p_lift.add_argument("--post", type=int, default=14)
    p_lift.add_argument("--sustain-start", type=int, default=15, dest="sustain_start")
    p_lift.add_argument("--sustain-end", type=int, default=42, dest="sustain_end")
    p_lift.add_argument(
        "--did",
        action="store_true",
        help=(
            "also net the lift against every other project in the db sharing this "
            "metric, as difference-in-differences controls (see SPEC.md)"
        ),
    )
    p_lift.add_argument("--csv", help="write results to this path instead of printing a table")
    p_lift.add_argument("--json", action="store_true", help="print results as JSON, not a table")
    p_lift.set_defaults(func=cmd_lift)

    p_report = sub.add_parser(
        "report", help="lift for every stored event against every stored metric"
    )
    p_report.add_argument("project", help="owner/repo")
    p_report.add_argument("--csv")
    p_report.add_argument("--json", action="store_true")
    p_report.set_defaults(func=cmd_report)

    p_study = sub.add_parser("study", help="collect + compute lift across many projects at once")
    p_study.add_argument("projects_file", help="newline-delimited 'owner/repo[,pypi_package]' file")
    p_study.add_argument(
        "--did",
        action="store_true",
        help="net each project's lift against every other project in this study as a control",
    )
    p_study.add_argument("--csv")
    p_study.add_argument("--json", action="store_true")
    p_study.set_defaults(func=cmd_study)

    p_list = sub.add_parser("list", help="show what's in the local db")
    p_list.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
