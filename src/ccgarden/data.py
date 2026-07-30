from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class DayRing:
    day: str
    sessions: int
    lines_added: int
    lines_removed: int


@dataclass(frozen=True)
class RepoBranch:
    repo: str
    sessions: int
    lines_added: int
    lines_removed: int
    output_tokens: int
    input_tokens: int
    cost: float


@dataclass(frozen=True)
class GardenData:
    rings: list[DayRing]
    branches: list[RepoBranch]
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class RepoBranchDay:
    """A repo's cumulative totals as of one day -- a frame in the timeline."""

    day: str
    sessions: int
    lines_added: int
    lines_removed: int
    output_tokens: int
    input_tokens: int
    cost: float


@dataclass(frozen=True)
class GardenTimeline:
    """Day-by-day cumulative history, ready to be replayed as a growth."""

    days: list[str]
    daily_sessions: list[int]
    cumulative_sessions: list[int]
    branch_order: list[str]
    branch_days: dict[str, list[RepoBranchDay]]
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def load_garden_timeline(db_path: str) -> GardenTimeline:
    conn = sqlite3.connect(db_path)
    try:
        timeline = _load_timeline(conn)
    finally:
        conn.close()
    return timeline


def _load_cache_totals(conn: sqlite3.Connection) -> tuple[int, int]:
    """Garden-wide cache read/write token sums.

    Feeds the cache-efficiency flower count -- how many times a cache write
    has paid off, overall.
    """
    row = conn.execute(
        'SELECT COALESCE(SUM(cache_read_tokens), 0), '
        'COALESCE(SUM(cache_write_tokens), 0) FROM daily_totals'
    ).fetchone()
    return row[0], row[1]


def _load_timeline(conn: sqlite3.Connection) -> GardenTimeline:
    day_rows = conn.execute(
        'SELECT day, sessions FROM daily_totals ORDER BY day ASC'
    ).fetchall()
    days = [day for day, _ in day_rows]
    daily_sessions = [sessions for _, sessions in day_rows]
    day_index = {day: index for index, day in enumerate(days)}

    cumulative_sessions = []
    running_sessions = 0
    for sessions in daily_sessions:
        running_sessions += sessions
        cumulative_sessions.append(running_sessions)

    branch_order, branch_days = _load_branch_days(conn, days, day_index)
    cache_read_tokens, cache_write_tokens = _load_cache_totals(conn)

    return GardenTimeline(
        days=days,
        daily_sessions=daily_sessions,
        cumulative_sessions=cumulative_sessions,
        branch_order=branch_order,
        branch_days=branch_days,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )


def _load_branch_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
) -> tuple[list[str], dict[str, list[RepoBranchDay]]]:
    cursor = conn.execute(
        """
        SELECT day, repo, sessions, lines_added, lines_removed,
               output_tokens, input_tokens, cost
        FROM daily_repo_usage ORDER BY day ASC
        """
    )

    day_count = len(days)
    deltas: dict[str, list[tuple[int, int, int, int, int, float] | None]] = {}
    lines_added_totals: dict[str, int] = {}

    for row in cursor.fetchall():
        day, repo, sessions, lines_added, lines_removed = row[:5]
        output_tokens, input_tokens, cost = row[5:]
        index = day_index.get(day)
        if index is None:
            continue
        deltas.setdefault(repo, [None] * day_count)[index] = (
            sessions,
            lines_added,
            lines_removed,
            output_tokens,
            input_tokens,
            cost or 0.0,
        )
        lines_added_totals[repo] = (
            lines_added_totals.get(repo, 0) + lines_added
        )

    branch_order = sorted(
        deltas, key=lambda repo: lines_added_totals[repo], reverse=True
    )

    branch_days = {
        repo: _cumulative_branch_days(days, deltas[repo])
        for repo in branch_order
    }
    return branch_order, branch_days


def _cumulative_branch_days(
    days: list[str],
    deltas: list[tuple[int, int, int, int, int, float] | None],
) -> list[RepoBranchDay]:
    running_sessions = running_added = running_removed = 0
    running_output = running_input = 0
    running_cost = 0.0
    rows = []
    for day, delta in zip(days, deltas, strict=True):
        if delta is not None:
            sessions, lines_added, lines_removed, output, input_, cost = delta
            running_sessions += sessions
            running_added += lines_added
            running_removed += lines_removed
            running_output += output
            running_input += input_
            running_cost += cost
        rows.append(
            RepoBranchDay(
                day=day,
                sessions=running_sessions,
                lines_added=running_added,
                lines_removed=running_removed,
                output_tokens=running_output,
                input_tokens=running_input,
                cost=running_cost,
            )
        )
    return rows


def load_garden_data(db_path: str) -> GardenData:
    conn = sqlite3.connect(db_path)
    try:
        rings = _load_rings(conn)
        branches = _load_branches(conn)
        cache_read_tokens, cache_write_tokens = _load_cache_totals(conn)
    finally:
        conn.close()
    return GardenData(
        rings=rings,
        branches=branches,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )


def _load_rings(conn: sqlite3.Connection) -> list[DayRing]:
    cursor = conn.execute(
        'SELECT day, sessions, lines_added, lines_removed '
        'FROM daily_totals ORDER BY day ASC'
    )
    return [
        DayRing(
            day=day,
            sessions=sessions,
            lines_added=lines_added,
            lines_removed=lines_removed,
        )
        for day, sessions, lines_added, lines_removed in cursor.fetchall()
    ]


def _load_branches(conn: sqlite3.Connection) -> list[RepoBranch]:
    cursor = conn.execute(
        """
        SELECT repo,
               SUM(sessions),
               SUM(lines_added),
               SUM(lines_removed),
               SUM(output_tokens),
               SUM(input_tokens),
               SUM(cost)
        FROM daily_repo_usage
        GROUP BY repo
        ORDER BY SUM(lines_added) DESC
        """
    )
    return [
        RepoBranch(
            repo=row[0],
            sessions=row[1],
            lines_added=row[2],
            lines_removed=row[3],
            output_tokens=row[4],
            input_tokens=row[5],
            cost=row[6],
        )
        for row in cursor.fetchall()
    ]
