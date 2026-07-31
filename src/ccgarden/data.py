from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


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
    prompts: int = 0


@dataclass(frozen=True)
class ModelCloud:
    model: str
    output_tokens: int
    input_tokens: int


@dataclass(frozen=True)
class ToolBush:
    tool: str
    count: int


@dataclass(frozen=True)
class EffortBush:
    effort: str
    count: int


@dataclass(frozen=True)
class GardenData:
    rings: list[DayRing]
    branches: list[RepoBranch]
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    models: list[ModelCloud] = field(default_factory=list)
    tools: list[ToolBush] = field(default_factory=list)
    efforts: list[EffortBush] = field(default_factory=list)
    model_efforts: list[ModelCloud] = field(default_factory=list)


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
    prompts: int = 0


@dataclass(frozen=True)
class ModelUsageDay:
    """A model's cumulative token totals as of one day."""

    day: str
    output_tokens: int
    input_tokens: int


@dataclass(frozen=True)
class ToolUsageDay:
    """A tool's cumulative call count as of one day."""

    day: str
    count: int


@dataclass(frozen=True)
class EffortUsageDay:
    """An effort level's cumulative reply count as of one day."""

    day: str
    count: int


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
    cumulative_cache_read: list[int] = field(default_factory=list)
    cumulative_cache_write: list[int] = field(default_factory=list)
    model_order: list[str] = field(default_factory=list)
    model_days: dict[str, list[ModelUsageDay]] = field(default_factory=dict)
    model_effort_order: list[str] = field(default_factory=list)
    model_effort_days: dict[str, list[ModelUsageDay]] = field(
        default_factory=dict
    )
    tool_order: list[str] = field(default_factory=list)
    tool_days: dict[str, list[ToolUsageDay]] = field(default_factory=dict)
    effort_order: list[str] = field(default_factory=list)
    effort_days: dict[str, list[EffortUsageDay]] = field(default_factory=dict)


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
        'SELECT day, sessions, cache_read_tokens, cache_write_tokens '
        'FROM daily_totals ORDER BY day ASC'
    ).fetchall()
    days = [row[0] for row in day_rows]
    daily_sessions = [row[1] for row in day_rows]
    day_index = {day: index for index, day in enumerate(days)}

    cumulative_sessions = []
    cumulative_cache_read = []
    cumulative_cache_write = []
    running_sessions = running_cache_read = running_cache_write = 0
    for _, sessions, cache_read, cache_write in day_rows:
        running_sessions += sessions
        running_cache_read += cache_read
        running_cache_write += cache_write
        cumulative_sessions.append(running_sessions)
        cumulative_cache_read.append(running_cache_read)
        cumulative_cache_write.append(running_cache_write)

    branch_order, branch_days = _load_branch_days(conn, days, day_index)
    model_order, model_days = _load_model_days(conn, days, day_index)
    tool_order, tool_days = _load_tool_days(conn, days, day_index)
    effort_order, effort_days = _load_effort_days(conn, days, day_index)
    model_effort_order, model_effort_days = _load_model_effort_days(
        conn, days, day_index
    )
    cache_read_tokens, cache_write_tokens = _load_cache_totals(conn)

    return GardenTimeline(
        days=days,
        daily_sessions=daily_sessions,
        cumulative_sessions=cumulative_sessions,
        branch_order=branch_order,
        branch_days=branch_days,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        cumulative_cache_read=cumulative_cache_read,
        cumulative_cache_write=cumulative_cache_write,
        model_order=model_order,
        model_days=model_days,
        tool_order=tool_order,
        tool_days=tool_days,
        effort_order=effort_order,
        effort_days=effort_days,
        model_effort_order=model_effort_order,
        model_effort_days=model_effort_days,
    )


def _load_branch_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
) -> tuple[list[str], dict[str, list[RepoBranchDay]]]:
    cursor = conn.execute(
        """
        SELECT day, repo, sessions, lines_added, lines_removed,
               output_tokens, input_tokens, cost, prompts
        FROM daily_repo_usage ORDER BY day ASC
        """
    )

    day_count = len(days)
    deltas: dict[
        str, list[tuple[int, int, int, int, int, float, int] | None]
    ] = {}
    lines_added_totals: dict[str, int] = {}

    for row in cursor.fetchall():
        day, repo, sessions, lines_added, lines_removed = row[:5]
        output_tokens, input_tokens, cost, prompts = row[5:]
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
            prompts,
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
    deltas: list[tuple[int, int, int, int, int, float, int] | None],
) -> list[RepoBranchDay]:
    running_sessions = running_added = running_removed = 0
    running_output = running_input = 0
    running_cost = 0.0
    running_prompts = 0
    rows = []
    for day, delta in zip(days, deltas, strict=True):
        if delta is not None:
            (
                sessions,
                lines_added,
                lines_removed,
                output,
                input_,
                cost,
                prompts,
            ) = delta
            running_sessions += sessions
            running_added += lines_added
            running_removed += lines_removed
            running_output += output
            running_input += input_
            running_cost += cost
            running_prompts += prompts
        rows.append(
            RepoBranchDay(
                day=day,
                sessions=running_sessions,
                lines_added=running_added,
                lines_removed=running_removed,
                output_tokens=running_output,
                input_tokens=running_input,
                cost=running_cost,
                prompts=running_prompts,
            )
        )
    return rows


def _load_models(conn: sqlite3.Connection) -> list[ModelCloud]:
    cursor = conn.execute(
        """
        SELECT model, SUM(output_tokens), SUM(input_tokens)
        FROM daily_model_usage
        GROUP BY model
        HAVING SUM(output_tokens) + SUM(input_tokens) > 0
        ORDER BY SUM(output_tokens) + SUM(input_tokens) DESC
        """
    )
    return [
        ModelCloud(model=row[0], output_tokens=row[1], input_tokens=row[2])
        for row in cursor.fetchall()
    ]


def _load_model_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
) -> tuple[list[str], dict[str, list[ModelUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, model, output_tokens, input_tokens '
        'FROM daily_model_usage ORDER BY day ASC'
    )

    day_count = len(days)
    deltas: dict[str, list[tuple[int, int] | None]] = {}
    token_totals: dict[str, int] = {}

    for day, model, output_tokens, input_tokens in cursor.fetchall():
        index = day_index.get(day)
        if index is None:
            continue
        deltas.setdefault(model, [None] * day_count)[index] = (
            output_tokens,
            input_tokens,
        )
        token_totals[model] = (
            token_totals.get(model, 0) + output_tokens + input_tokens
        )

    # Models with no real token usage (e.g. a synthetic placeholder model
    # with all-zero rows) shouldn't get a cloud of their own.
    model_order = sorted(
        (model for model in deltas if token_totals[model] > 0),
        key=lambda model: token_totals[model],
        reverse=True,
    )

    model_days = {
        model: _cumulative_model_days(days, deltas[model])
        for model in model_order
    }
    return model_order, model_days


def _cumulative_model_days(
    days: list[str],
    deltas: list[tuple[int, int] | None],
) -> list[ModelUsageDay]:
    running_output = running_input = 0
    rows = []
    for day, delta in zip(days, deltas, strict=True):
        if delta is not None:
            output_tokens, input_tokens = delta
            running_output += output_tokens
            running_input += input_tokens
        rows.append(
            ModelUsageDay(
                day=day,
                output_tokens=running_output,
                input_tokens=running_input,
            )
        )
    return rows


def _load_tools(conn: sqlite3.Connection) -> list[ToolBush]:
    cursor = conn.execute(
        """
        SELECT tool, SUM(count)
        FROM daily_tool_usage
        GROUP BY tool
        HAVING SUM(count) > 0
        ORDER BY SUM(count) DESC
        """
    )
    return [ToolBush(tool=row[0], count=row[1]) for row in cursor.fetchall()]


def _load_tool_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
) -> tuple[list[str], dict[str, list[ToolUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, tool, count FROM daily_tool_usage ORDER BY day ASC'
    )

    day_count = len(days)
    deltas: dict[str, list[int | None]] = {}
    count_totals: dict[str, int] = {}

    for day, tool, count in cursor.fetchall():
        index = day_index.get(day)
        if index is None:
            continue
        deltas.setdefault(tool, [None] * day_count)[index] = count
        count_totals[tool] = count_totals.get(tool, 0) + count

    tool_order = sorted(
        (tool for tool in deltas if count_totals[tool] > 0),
        key=lambda tool: count_totals[tool],
        reverse=True,
    )

    tool_days = {
        tool: _cumulative_tool_days(days, deltas[tool]) for tool in tool_order
    }
    return tool_order, tool_days


def _cumulative_tool_days(
    days: list[str],
    deltas: list[int | None],
) -> list[ToolUsageDay]:
    running_count = 0
    rows = []
    for day, delta in zip(days, deltas, strict=True):
        if delta is not None:
            running_count += delta
        rows.append(ToolUsageDay(day=day, count=running_count))
    return rows


def _load_model_effort_clouds(conn: sqlite3.Connection) -> list[ModelCloud]:
    cursor = conn.execute(
        """
        SELECT model_effort, SUM(output_tokens), SUM(input_tokens)
        FROM daily_model_effort_usage
        GROUP BY model_effort
        HAVING SUM(output_tokens) + SUM(input_tokens) > 0
        ORDER BY SUM(output_tokens) + SUM(input_tokens) DESC
        """
    )
    return [
        ModelCloud(model=row[0], output_tokens=row[1], input_tokens=row[2])
        for row in cursor.fetchall()
    ]


def _load_model_effort_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
) -> tuple[list[str], dict[str, list[ModelUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, model_effort, output_tokens, input_tokens '
        'FROM daily_model_effort_usage ORDER BY day ASC'
    )

    day_count = len(days)
    deltas: dict[str, list[tuple[int, int] | None]] = {}
    token_totals: dict[str, int] = {}

    for day, label, output_tokens, input_tokens in cursor.fetchall():
        index = day_index.get(day)
        if index is None:
            continue
        deltas.setdefault(label, [None] * day_count)[index] = (
            output_tokens,
            input_tokens,
        )
        token_totals[label] = (
            token_totals.get(label, 0) + output_tokens + input_tokens
        )

    label_order = sorted(
        (label for label in deltas if token_totals[label] > 0),
        key=lambda label: token_totals[label],
        reverse=True,
    )

    label_days = {
        label: _cumulative_model_days(days, deltas[label])
        for label in label_order
    }
    return label_order, label_days


def _load_effort_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
) -> tuple[list[str], dict[str, list[EffortUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, effort, count FROM daily_effort_usage ORDER BY day ASC'
    )

    day_count = len(days)
    deltas: dict[str, list[int | None]] = {}
    count_totals: dict[str, int] = {}

    for day, effort, count in cursor.fetchall():
        index = day_index.get(day)
        if index is None:
            continue
        deltas.setdefault(effort, [None] * day_count)[index] = count
        count_totals[effort] = count_totals.get(effort, 0) + count

    effort_order = sorted(
        (effort for effort in deltas if count_totals[effort] > 0),
        key=lambda effort: count_totals[effort],
        reverse=True,
    )

    effort_days = {
        effort: _cumulative_effort_days(days, deltas[effort])
        for effort in effort_order
    }
    return effort_order, effort_days


def _cumulative_effort_days(
    days: list[str],
    deltas: list[int | None],
) -> list[EffortUsageDay]:
    running_count = 0
    rows = []
    for day, delta in zip(days, deltas, strict=True):
        if delta is not None:
            running_count += delta
        rows.append(EffortUsageDay(day=day, count=running_count))
    return rows


def _load_efforts(conn: sqlite3.Connection) -> list[EffortBush]:
    cursor = conn.execute(
        """
        SELECT effort, SUM(count)
        FROM daily_effort_usage
        GROUP BY effort
        HAVING SUM(count) > 0
        ORDER BY SUM(count) DESC
        """
    )
    return [
        EffortBush(effort=row[0], count=row[1]) for row in cursor.fetchall()
    ]


def load_garden_data(db_path: str) -> GardenData:
    conn = sqlite3.connect(db_path)
    try:
        rings = _load_rings(conn)
        branches = _load_branches(conn)
        models = _load_models(conn)
        tools = _load_tools(conn)
        efforts = _load_efforts(conn)
        model_efforts = _load_model_effort_clouds(conn)
        cache_read_tokens, cache_write_tokens = _load_cache_totals(conn)
    finally:
        conn.close()
    return GardenData(
        rings=rings,
        branches=branches,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        models=models,
        tools=tools,
        efforts=efforts,
        model_efforts=model_efforts,
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
               SUM(cost),
               SUM(prompts)
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
            prompts=row[7],
        )
        for row in cursor.fetchall()
    ]
