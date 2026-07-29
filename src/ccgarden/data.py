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


def load_garden_data(db_path: str) -> GardenData:
    conn = sqlite3.connect(db_path)
    try:
        rings = _load_rings(conn)
        branches = _load_branches(conn)
    finally:
        conn.close()
    return GardenData(rings=rings, branches=branches)


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
