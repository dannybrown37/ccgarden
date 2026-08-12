from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from ccgarden.claude_stats import (
    DEFAULT_CARTOON_SINCE,
    parse_cartoon_stats,
    run_cartoon_stats,
)


@dataclass(frozen=True)
class DayRange:
    """An optional inclusive `day` filter shared by every loader query.

    Every table is day-keyed with ISO `day` strings, and no query has a
    WHERE clause of its own, so `clause()` can always be spliced in
    directly after the FROM and its `params` prepended to the query's.
    """

    since: str | None = None
    until: str | None = None

    def clause(self) -> str:
        conditions = []
        if self.since is not None:
            conditions.append('day >= ?')
        if self.until is not None:
            conditions.append('day <= ?')
        if not conditions:
            return ''
        return ' WHERE ' + ' AND '.join(conditions)

    @property
    def params(self) -> tuple[str, ...]:
        return tuple(
            bound for bound in (self.since, self.until) if bound is not None
        )


ALL_DAYS = DayRange()


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
class CartoonBird:
    """One cartoon adapter's token savings over the reporting window.

    Cartoon is an optional external tool, so this list is simply empty
    when it isn't installed -- see `load_cartoon_birds`.
    """

    adapter: str
    calls: int
    tokens_saved: int


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
    total_tokens: int = 0
    birds: list[CartoonBird] = field(default_factory=list)
    cartoon_since: str = ''
    # Prompts by local hour, and the share of them typed at night.
    hour_counts: dict[int, int] = field(default_factory=dict)
    nightness: float = 0.0
    # How alive the garden is *today* -- see `_daily_vitality`.
    vitality: float = 1.0


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
    cumulative_total_tokens: list[int] = field(default_factory=list)
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
    # Cartoon reports a single since-window snapshot rather than daily
    # history, so birds have no per-day frames to replay.
    birds: list[CartoonBird] = field(default_factory=list)
    cartoon_since: str = ''
    # One nightness per day -- the only per-day channel that isn't
    # cumulative, since the sky reflects that day alone.
    daily_nightness: list[float] = field(default_factory=list)
    hour_counts: dict[int, int] = field(default_factory=dict)
    # Also non-cumulative, and the only channel that can fall: how
    # recently you worked, which drives the season.
    daily_vitality: list[float] = field(default_factory=list)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Whether `table` is present in this db.

    `daily_hour_usage` arrived after the first released schema, so a db
    recorded by an older version simply has no hours in it. That's a
    garden with no opinion about the time of day, not an error -- the
    table appears again on the next `ccstats` run.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


NIGHT_HOURS = frozenset({21, 22, 23, 0, 1, 2, 3, 4, 5})


def _nightness(hour_counts: dict[int, int]) -> float:
    """Share of a day's prompts typed at night, 0.0-1.0.

    Drives how dark the sky is drawn. A day with no prompts at all has no
    opinion about the time of day, so it comes back 0.0 (broad daylight)
    rather than dividing by zero.
    """
    total = sum(hour_counts.values())
    if total <= 0:
        return 0.0
    night = sum(
        count for hour, count in hour_counts.items() if hour in NIGHT_HOURS
    )
    return night / total


def _load_hour_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
    days_range: DayRange = ALL_DAYS,
) -> tuple[list[float], dict[int, int]]:
    """Per-day nightness plus the garden-wide hour histogram.

    Nightness is deliberately *not* cumulative: unlike every other shape,
    the sky reflects how you were working on that day, not the sum of
    every day before it.
    """
    if not _table_exists(conn, 'daily_hour_usage'):
        return [0.0] * len(days), {}

    cursor = conn.execute(
        'SELECT day, hour, count '
        f'FROM daily_hour_usage{days_range.clause()} ORDER BY day ASC',
        days_range.params,
    )

    per_day: list[dict[int, int]] = [{} for _ in days]
    overall: dict[int, int] = {}
    for day, hour, count in cursor.fetchall():
        index = day_index.get(day)
        if index is None:
            continue
        per_day[index][hour] = per_day[index].get(hour, 0) + count
        overall[hour] = overall.get(hour, 0) + count

    return [_nightness(counts) for counts in per_day], overall


def load_cartoon_birds(
    since: str = DEFAULT_CARTOON_SINCE,
) -> list[CartoonBird]:
    """Per-adapter cartoon savings, biggest first -- empty if unavailable.

    Cartoon is an optional external binary the garden merely plugs into,
    so every way it can be absent or unhappy (not installed, non-zero
    exit, timeout, unparseable output) has to come back as "no birds"
    rather than an error: a garden without cartoon is just a garden with
    an empty sky. Adapters that saved nothing get no bird either -- a
    passthrough adapter is real, but it isn't a saving worth drawing.
    """
    try:
        output = run_cartoon_stats(since)
        stats = parse_cartoon_stats(output) if output is not None else None
    except (OSError, ValueError):
        return []
    if not stats:
        return []

    birds = [
        CartoonBird(
            adapter=adapter,
            calls=counts.get('calls', 0),
            tokens_saved=counts.get('saved', 0),
        )
        for adapter, counts in stats['by_adapter'].items()
        if counts.get('saved', 0) > 0
    ]
    birds.sort(key=lambda bird: bird.tokens_saved, reverse=True)
    return birds


def load_garden_timeline(
    db_path: str,
    cartoon_since: str = DEFAULT_CARTOON_SINCE,
    days: DayRange = ALL_DAYS,
) -> GardenTimeline:
    conn = sqlite3.connect(db_path)
    try:
        timeline = _load_timeline(conn, days)
    finally:
        conn.close()
    return replace(
        timeline,
        birds=load_cartoon_birds(cartoon_since),
        cartoon_since=cartoon_since,
    )


def _load_cache_totals(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> tuple[int, int]:
    """Garden-wide cache read/write token sums.

    Feeds the cache-efficiency flower count -- how many times a cache write
    has paid off, overall.
    """
    row = conn.execute(
        'SELECT COALESCE(SUM(cache_read_tokens), 0), '
        'COALESCE(SUM(cache_write_tokens), 0) '
        f'FROM daily_totals{days.clause()}',
        days.params,
    ).fetchone()
    return row[0], row[1]


def _load_total_tokens(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> int:
    """Garden-wide sum of every token counted anywhere.

    Includes output, input, cache read, and cache write. Feeds the
    sun -- the one shape that represents the whole garden's total
    "energy" rather than any single branch/model/tool's share of it.
    """
    row = conn.execute(
        'SELECT COALESCE(SUM(output_tokens), 0) '
        '+ COALESCE(SUM(input_tokens), 0) '
        '+ COALESCE(SUM(cache_read_tokens), 0) '
        '+ COALESCE(SUM(cache_write_tokens), 0) '
        f'FROM daily_totals{days.clause()}',
        days.params,
    ).fetchone()
    return row[0]


# A gap shorter than this is a weekend, not a dormancy, and shouldn't
# cost the garden its leaves.
DORMANCY_MIN_GAP_DAYS = 4
# Days of silence for the garden to lose half its vitality. Tuned so a
# fortnight away reads as autumn and a couple of months as bare winter.
DORMANCY_HALF_LIFE_DAYS = 12.0
# It takes two days to have a gap between them.
MIN_DAYS_WITH_A_GAP = 2
# Frames a single gap may spend. Every missed day gets one until the
# budget runs out, then the gap is sampled instead -- a year away can't
# buy a year of frames, since each one costs an entry in every animated
# attribute in the SVG. Past the budget it's the vitality decay, not the
# frame count, that says how long you were gone.
DORMANT_FRAMES_MAX = 6


def _dormant_days_in_gap(previous: date, current: date) -> list[date]:
    """Evenly spaced stand-in days for the silence between two workdays.

    One frame per missed day is right for a long weekend and absurd for
    a sabbatical, so short gaps get every day and longer ones are
    sampled across the whole span -- the dates still walk the calendar
    through the lapse, they just skip.
    """
    gap = (current - previous).days
    if gap < DORMANCY_MIN_GAP_DAYS:
        return []
    count = min(gap - 1, DORMANT_FRAMES_MAX)
    days = {
        previous + timedelta(days=round(index * gap / (count + 1)))
        for index in range(1, count + 1)
    }
    return sorted(days - {previous, current})


def _with_dormant_days(
    day_rows: list[tuple[str, int, int, int, int, int]],
) -> list[tuple[str, int, int, int, int, int]]:
    """Insert all-zero frames across every real gap.

    The db only holds days you actually worked, so without these a
    three-month break is just one frame boundary and the timelapse
    skips straight over it. Synthetic days give the animation somewhere
    to *be* dormant, and because they carry no rows in any other table,
    every cumulative shape simply holds its value there rather than
    growing -- which is exactly what a gap means. Frames are the
    timelapse's unit of time, so spending several on a gap is what gives
    the lapse (and its rain) weight proportional to how long it ran.
    """
    if len(day_rows) < MIN_DAYS_WITH_A_GAP:
        return day_rows

    expanded = [day_rows[0]]
    for row in day_rows[1:]:
        previous = date.fromisoformat(expanded[-1][0])
        current = date.fromisoformat(row[0])
        expanded.extend(
            (str(day), 0, 0, 0, 0, 0)
            for day in _dormant_days_in_gap(previous, current)
        )
        expanded.append(row)
    return expanded


def _daily_vitality(days: list[str], active: set[str]) -> list[float]:
    """How alive the garden is on each frame, 1.0 down to ~0.

    Decays with the number of calendar days since you last worked, so a
    lapse turns the leaves and the ground turn autumnal and a return
    brings them back. Unlike the cumulative channels this one can fall:
    that's the whole point of it.
    """
    vitality = []
    last_active: date | None = None
    for day in days:
        current = date.fromisoformat(day)
        if day in active:
            last_active = current
        gap = (current - last_active).days if last_active else 0
        vitality.append(0.5 ** (gap / DORMANCY_HALF_LIFE_DAYS))
    return vitality


def _with_seed_day(
    day_rows: list[tuple[str, int, int, int, int, int]],
) -> list[tuple[str, int, int, int, int, int]]:
    """Prepend an empty day so the timelapse grows out of bare ground.

    The first recorded day is already a full day's work, so replaying
    straight from it opens on a garden that has clearly been going for a
    while. One synthetic all-zero day before it gives the animation a
    day 0 to start from.
    """
    if not day_rows:
        return day_rows
    first_day = date.fromisoformat(day_rows[0][0])
    seed = (str(first_day - timedelta(days=1)), 0, 0, 0, 0, 0)
    return [seed, *day_rows]


def _load_timeline(
    conn: sqlite3.Connection, days_range: DayRange = ALL_DAYS
) -> GardenTimeline:
    day_rows = conn.execute(
        'SELECT day, sessions, cache_read_tokens, cache_write_tokens, '
        'output_tokens, input_tokens '
        f'FROM daily_totals{days_range.clause()} ORDER BY day ASC',
        days_range.params,
    ).fetchall()
    active_days = {row[0] for row in day_rows}
    day_rows = _with_seed_day(_with_dormant_days(day_rows))
    days = [row[0] for row in day_rows]
    daily_sessions = [row[1] for row in day_rows]
    day_index = {day: index for index, day in enumerate(days)}

    cumulative_sessions = []
    cumulative_cache_read = []
    cumulative_cache_write = []
    cumulative_total_tokens = []
    running_sessions = running_cache_read = running_cache_write = 0
    running_total_tokens = 0
    for (
        _,
        sessions,
        cache_read,
        cache_write,
        output_tokens,
        input_tokens,
    ) in day_rows:
        running_sessions += sessions
        running_cache_read += cache_read
        running_cache_write += cache_write
        running_total_tokens += (
            output_tokens + input_tokens + cache_read + cache_write
        )
        cumulative_sessions.append(running_sessions)
        cumulative_cache_read.append(running_cache_read)
        cumulative_cache_write.append(running_cache_write)
        cumulative_total_tokens.append(running_total_tokens)

    branch_order, branch_days = _load_branch_days(
        conn, days, day_index, days_range
    )
    model_order, model_days = _load_model_days(
        conn, days, day_index, days_range
    )
    tool_order, tool_days = _load_tool_days(conn, days, day_index, days_range)
    effort_order, effort_days = _load_effort_days(
        conn, days, day_index, days_range
    )
    model_effort_order, model_effort_days = _load_model_effort_days(
        conn, days, day_index, days_range
    )
    cache_read_tokens, cache_write_tokens = _load_cache_totals(
        conn, days_range
    )
    daily_nightness, hour_counts = _load_hour_days(
        conn, days, day_index, days_range
    )

    return GardenTimeline(
        daily_nightness=daily_nightness,
        hour_counts=hour_counts,
        daily_vitality=_daily_vitality(days, active_days),
        days=days,
        daily_sessions=daily_sessions,
        cumulative_sessions=cumulative_sessions,
        branch_order=branch_order,
        branch_days=branch_days,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        cumulative_cache_read=cumulative_cache_read,
        cumulative_cache_write=cumulative_cache_write,
        cumulative_total_tokens=cumulative_total_tokens,
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
    days_range: DayRange = ALL_DAYS,
) -> tuple[list[str], dict[str, list[RepoBranchDay]]]:
    cursor = conn.execute(
        'SELECT day, repo, sessions, lines_added, lines_removed, '
        'output_tokens, input_tokens, cost, prompts '
        f'FROM daily_repo_usage{days_range.clause()} ORDER BY day ASC',
        days_range.params,
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


def _load_models(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> list[ModelCloud]:
    cursor = conn.execute(
        f"""
        SELECT model, SUM(output_tokens), SUM(input_tokens)
        FROM daily_model_usage{days.clause()}
        GROUP BY model
        HAVING SUM(output_tokens) + SUM(input_tokens) > 0
        ORDER BY SUM(output_tokens) + SUM(input_tokens) DESC
        """,
        days.params,
    )
    return [
        ModelCloud(model=row[0], output_tokens=row[1], input_tokens=row[2])
        for row in cursor.fetchall()
    ]


def _load_model_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
    days_range: DayRange = ALL_DAYS,
) -> tuple[list[str], dict[str, list[ModelUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, model, output_tokens, input_tokens '
        f'FROM daily_model_usage{days_range.clause()} ORDER BY day ASC',
        days_range.params,
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


def _load_tools(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> list[ToolBush]:
    cursor = conn.execute(
        f"""
        SELECT tool, SUM(count)
        FROM daily_tool_usage{days.clause()}
        GROUP BY tool
        HAVING SUM(count) > 0
        ORDER BY SUM(count) DESC
        """,
        days.params,
    )
    return [ToolBush(tool=row[0], count=row[1]) for row in cursor.fetchall()]


def _load_tool_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
    days_range: DayRange = ALL_DAYS,
) -> tuple[list[str], dict[str, list[ToolUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, tool, count '
        f'FROM daily_tool_usage{days_range.clause()} ORDER BY day ASC',
        days_range.params,
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


def _load_model_effort_clouds(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> list[ModelCloud]:
    cursor = conn.execute(
        f"""
        SELECT model_effort, SUM(output_tokens), SUM(input_tokens)
        FROM daily_model_effort_usage{days.clause()}
        GROUP BY model_effort
        HAVING SUM(output_tokens) + SUM(input_tokens) > 0
        ORDER BY SUM(output_tokens) + SUM(input_tokens) DESC
        """,
        days.params,
    )
    return [
        ModelCloud(model=row[0], output_tokens=row[1], input_tokens=row[2])
        for row in cursor.fetchall()
    ]


def _load_model_effort_days(
    conn: sqlite3.Connection,
    days: list[str],
    day_index: dict[str, int],
    days_range: DayRange = ALL_DAYS,
) -> tuple[list[str], dict[str, list[ModelUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, model_effort, output_tokens, input_tokens '
        f'FROM daily_model_effort_usage{days_range.clause()} '
        'ORDER BY day ASC',
        days_range.params,
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
    days_range: DayRange = ALL_DAYS,
) -> tuple[list[str], dict[str, list[EffortUsageDay]]]:
    cursor = conn.execute(
        'SELECT day, effort, count '
        f'FROM daily_effort_usage{days_range.clause()} ORDER BY day ASC',
        days_range.params,
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


def _load_efforts(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> list[EffortBush]:
    cursor = conn.execute(
        f"""
        SELECT effort, SUM(count)
        FROM daily_effort_usage{days.clause()}
        GROUP BY effort
        HAVING SUM(count) > 0
        ORDER BY SUM(count) DESC
        """,
        days.params,
    )
    return [
        EffortBush(effort=row[0], count=row[1]) for row in cursor.fetchall()
    ]


def load_garden_data(
    db_path: str,
    cartoon_since: str = DEFAULT_CARTOON_SINCE,
    days: DayRange = ALL_DAYS,
) -> GardenData:
    conn = sqlite3.connect(db_path)
    try:
        rings = _load_rings(conn, days)
        branches = _load_branches(conn, days)
        models = _load_models(conn, days)
        tools = _load_tools(conn, days)
        efforts = _load_efforts(conn, days)
        model_efforts = _load_model_effort_clouds(conn, days)
        cache_read_tokens, cache_write_tokens = _load_cache_totals(conn, days)
        total_tokens = _load_total_tokens(conn, days)
        hour_counts = _load_hours(conn, days)
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
        total_tokens=total_tokens,
        birds=load_cartoon_birds(cartoon_since),
        cartoon_since=cartoon_since,
        hour_counts=hour_counts,
        nightness=_nightness(hour_counts),
        vitality=_vitality_today(rings),
    )


def _vitality_today(rings: list[DayRing]) -> float:
    """Today's vitality, from how long ago the last recorded day was.

    A still garden is rendered "as of now", so a garden last worked in
    the spring should be shown in the autumn it has actually reached --
    not frozen green on its final active day.
    """
    if not rings:
        return 1.0
    gap = (date.today() - date.fromisoformat(rings[-1].day)).days
    return 0.5 ** (max(gap, 0) / DORMANCY_HALF_LIFE_DAYS)


def _load_hours(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> dict[int, int]:
    if not _table_exists(conn, 'daily_hour_usage'):
        return {}
    cursor = conn.execute(
        f"""
        SELECT hour, SUM(count)
        FROM daily_hour_usage{days.clause()}
        GROUP BY hour
        HAVING SUM(count) > 0
        """,
        days.params,
    )
    return dict(cursor.fetchall())


def _load_rings(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> list[DayRing]:
    cursor = conn.execute(
        'SELECT day, sessions, lines_added, lines_removed '
        f'FROM daily_totals{days.clause()} ORDER BY day ASC',
        days.params,
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


def _load_branches(
    conn: sqlite3.Connection, days: DayRange = ALL_DAYS
) -> list[RepoBranch]:
    cursor = conn.execute(
        f"""
        SELECT repo,
               SUM(sessions),
               SUM(lines_added),
               SUM(lines_removed),
               SUM(output_tokens),
               SUM(input_tokens),
               SUM(cost),
               SUM(prompts)
        FROM daily_repo_usage{days.clause()}
        GROUP BY repo
        ORDER BY SUM(lines_added) DESC
        """,
        days.params,
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
