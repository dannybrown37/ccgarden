import sqlite3
from pathlib import Path

import pytest

from ccgarden.data import (
    DayRing,
    ModelCloud,
    RepoBranch,
    ToolBush,
    load_garden_data,
    load_garden_timeline,
)

SCHEMA = """
CREATE TABLE daily_totals (
    day TEXT PRIMARY KEY,
    sessions INTEGER NOT NULL,
    prompts INTEGER NOT NULL,
    replies INTEGER NOT NULL,
    thinking_blocks INTEGER NOT NULL,
    subagent_runs INTEGER NOT NULL,
    lines_added INTEGER NOT NULL,
    lines_removed INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cost_total REAL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE daily_repo_usage (
    day TEXT NOT NULL,
    repo TEXT NOT NULL,
    sessions INTEGER NOT NULL,
    prompts INTEGER NOT NULL,
    replies INTEGER NOT NULL,
    lines_added INTEGER NOT NULL,
    lines_removed INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cost REAL,
    PRIMARY KEY (day, repo)
);

CREATE TABLE daily_model_usage (
    day TEXT NOT NULL,
    model TEXT NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cost REAL,
    PRIMARY KEY (day, model)
);

CREATE TABLE daily_tool_usage (
    day TEXT NOT NULL,
    tool TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (day, tool)
);
"""


def make_db(
    tmp_path: Path,
    totals_rows: list[tuple],
    repo_rows: list[tuple],
    model_rows: list[tuple] | None = None,
    tool_rows: list[tuple] | None = None,
) -> str:
    db_path = tmp_path / 'ccstats.db'
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.executemany(
        'INSERT INTO daily_totals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        totals_rows,
    )
    conn.executemany(
        'INSERT INTO daily_repo_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        repo_rows,
    )
    conn.executemany(
        'INSERT INTO daily_model_usage VALUES (?,?,?,?,?,?,?)',
        model_rows or [],
    )
    conn.executemany(
        'INSERT INTO daily_tool_usage VALUES (?,?,?)',
        tool_rows or [],
    )
    conn.commit()
    conn.close()
    return str(db_path)


def model_row(
    day: str,
    model: str,
    *,
    output_tokens: int = 0,
    input_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost: float = 0.0,
) -> tuple:
    return (
        day,
        model,
        output_tokens,
        input_tokens,
        cache_read_tokens,
        cache_write_tokens,
        cost,
    )


def tool_row(day: str, tool: str, *, count: int = 0) -> tuple:
    return (day, tool, count)


def totals_row(
    day: str,
    sessions: int,
    lines_added: int,
    lines_removed: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> tuple:
    return (
        day,
        sessions,
        0,
        0,
        0,
        0,
        lines_added,
        lines_removed,
        0,
        0,
        cache_read_tokens,
        cache_write_tokens,
        0.0,
        day,
    )


def repo_row(
    day: str,
    repo: str,
    *,
    sessions: int,
    lines_added: int,
    lines_removed: int,
    output_tokens: int = 0,
    input_tokens: int = 0,
    cost: float = 0.0,
) -> tuple:
    return (
        day,
        repo,
        sessions,
        0,
        0,
        lines_added,
        lines_removed,
        output_tokens,
        input_tokens,
        0,
        0,
        cost,
    )


def test_load_garden_data_from_empty_db_returns_empty_lists(
    tmp_path: Path,
) -> None:
    db_path = make_db(tmp_path, totals_rows=[], repo_rows=[])

    garden = load_garden_data(db_path)

    assert garden.rings == []
    assert garden.branches == []
    assert garden.cache_read_tokens == 0
    assert garden.cache_write_tokens == 0


def test_load_garden_data_sums_cache_tokens_across_days(
    tmp_path: Path,
) -> None:
    totals_rows = [
        totals_row(
            '2026-07-26',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            cache_read_tokens=300,
            cache_write_tokens=100,
        ),
        totals_row(
            '2026-07-27',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            cache_read_tokens=200,
            cache_write_tokens=50,
        ),
    ]
    db_path = make_db(tmp_path, totals_rows=totals_rows, repo_rows=[])

    garden = load_garden_data(db_path)

    assert garden.cache_read_tokens == 500
    assert garden.cache_write_tokens == 150


@pytest.mark.parametrize(
    'insert_order',
    [
        ['2026-07-26', '2026-07-27', '2026-07-28'],
        ['2026-07-28', '2026-07-26', '2026-07-27'],
    ],
)
def test_load_rings_returns_days_ordered_ascending(
    tmp_path: Path, insert_order: list[str]
) -> None:
    totals_rows = [
        totals_row(day, sessions=1, lines_added=10, lines_removed=1)
        for day in insert_order
    ]
    db_path = make_db(tmp_path, totals_rows=totals_rows, repo_rows=[])

    garden = load_garden_data(db_path)

    assert [ring.day for ring in garden.rings] == [
        '2026-07-26',
        '2026-07-27',
        '2026-07-28',
    ]
    assert garden.rings[0] == DayRing(
        day='2026-07-26', sessions=1, lines_added=10, lines_removed=1
    )


def test_load_branches_aggregates_same_repo_across_days(
    tmp_path: Path,
) -> None:
    repo_rows = [
        repo_row(
            '2026-07-26',
            'dotfiles',
            sessions=2,
            lines_added=100,
            lines_removed=10,
            output_tokens=500,
            input_tokens=50,
            cost=1.5,
        ),
        repo_row(
            '2026-07-27',
            'dotfiles',
            sessions=3,
            lines_added=200,
            lines_removed=20,
            output_tokens=700,
            input_tokens=70,
            cost=2.5,
        ),
    ]
    db_path = make_db(tmp_path, totals_rows=[], repo_rows=repo_rows)

    garden = load_garden_data(db_path)

    assert garden.branches == [
        RepoBranch(
            repo='dotfiles',
            sessions=5,
            lines_added=300,
            lines_removed=30,
            output_tokens=1200,
            input_tokens=120,
            cost=4.0,
        )
    ]


def test_load_branches_sorts_by_lines_added_descending(tmp_path: Path) -> None:
    repo_rows = [
        repo_row(
            '2026-07-26',
            'small-repo',
            sessions=1,
            lines_added=10,
            lines_removed=1,
        ),
        repo_row(
            '2026-07-26',
            'big-repo',
            sessions=1,
            lines_added=999,
            lines_removed=1,
        ),
        repo_row(
            '2026-07-26',
            'mid-repo',
            sessions=1,
            lines_added=500,
            lines_removed=1,
        ),
    ]
    db_path = make_db(tmp_path, totals_rows=[], repo_rows=repo_rows)

    garden = load_garden_data(db_path)

    assert [branch.repo for branch in garden.branches] == [
        'big-repo',
        'mid-repo',
        'small-repo',
    ]


def test_load_models_aggregates_same_model_across_days(
    tmp_path: Path,
) -> None:
    model_rows = [
        model_row(
            '2026-07-26', 'claude-sonnet-5', output_tokens=100, input_tokens=10
        ),
        model_row(
            '2026-07-27', 'claude-sonnet-5', output_tokens=200, input_tokens=20
        ),
    ]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], model_rows=model_rows
    )

    garden = load_garden_data(db_path)

    assert garden.models == [
        ModelCloud(model='claude-sonnet-5', output_tokens=300, input_tokens=30)
    ]


def test_load_models_sorts_by_total_tokens_descending(tmp_path: Path) -> None:
    model_rows = [
        model_row(
            '2026-07-26', 'claude-haiku-4-5', output_tokens=10, input_tokens=1
        ),
        model_row(
            '2026-07-26', 'claude-opus-5', output_tokens=1000, input_tokens=100
        ),
        model_row(
            '2026-07-26', 'claude-sonnet-5', output_tokens=100, input_tokens=10
        ),
    ]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], model_rows=model_rows
    )

    garden = load_garden_data(db_path)

    assert [model_cloud.model for model_cloud in garden.models] == [
        'claude-opus-5',
        'claude-sonnet-5',
        'claude-haiku-4-5',
    ]


def test_load_models_excludes_models_with_no_token_usage(
    tmp_path: Path,
) -> None:
    model_rows = [model_row('2026-07-26', '<synthetic>')]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], model_rows=model_rows
    )

    garden = load_garden_data(db_path)

    assert garden.models == []


def test_load_tools_aggregates_same_tool_across_days(tmp_path: Path) -> None:
    tool_rows = [
        tool_row('2026-07-26', 'Read', count=5),
        tool_row('2026-07-27', 'Read', count=7),
    ]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], tool_rows=tool_rows
    )

    garden = load_garden_data(db_path)

    assert garden.tools == [ToolBush(tool='Read', count=12)]


def test_load_tools_sorts_by_count_descending(tmp_path: Path) -> None:
    tool_rows = [
        tool_row('2026-07-26', 'Grep', count=2),
        tool_row('2026-07-26', 'Bash', count=50),
        tool_row('2026-07-26', 'Read', count=10),
    ]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], tool_rows=tool_rows
    )

    garden = load_garden_data(db_path)

    assert [tool_bush.tool for tool_bush in garden.tools] == [
        'Bash',
        'Read',
        'Grep',
    ]


def test_load_garden_timeline_tracks_cumulative_cache_tokens_per_day(
    tmp_path: Path,
) -> None:
    totals_rows = [
        totals_row(
            '2026-07-26',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            cache_read_tokens=300,
            cache_write_tokens=100,
        ),
        totals_row(
            '2026-07-27',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            cache_read_tokens=200,
            cache_write_tokens=50,
        ),
    ]
    db_path = make_db(tmp_path, totals_rows=totals_rows, repo_rows=[])

    timeline = load_garden_timeline(db_path)

    assert timeline.cumulative_cache_read == [300, 500]
    assert timeline.cumulative_cache_write == [100, 150]


def test_load_tools_excludes_tools_with_zero_count(tmp_path: Path) -> None:
    tool_rows = [tool_row('2026-07-26', 'Read', count=0)]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], tool_rows=tool_rows
    )

    garden = load_garden_data(db_path)

    assert garden.tools == []
