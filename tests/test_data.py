import sqlite3
from pathlib import Path

import pytest

from ccgarden.data import (
    ALL_DAYS,
    CartoonBird,
    DayRange,
    DayRing,
    EffortBush,
    ModelCloud,
    RepoBranch,
    ToolBush,
    load_cartoon_birds,
    load_garden_data,
    load_garden_timeline,
    _daily_vitality,
    _nightness,
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

CREATE TABLE daily_effort_usage (
    day TEXT NOT NULL,
    effort TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (day, effort)
);

CREATE TABLE daily_model_effort_usage (
    day TEXT NOT NULL,
    model_effort TEXT NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    PRIMARY KEY (day, model_effort)
);

CREATE TABLE IF NOT EXISTS daily_hour_usage (
    day TEXT NOT NULL,
    hour INTEGER NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (day, hour)
);
"""


def make_db(
    tmp_path: Path,
    totals_rows: list[tuple],
    repo_rows: list[tuple],
    *,
    model_rows: list[tuple] | None = None,
    tool_rows: list[tuple] | None = None,
    effort_rows: list[tuple] | None = None,
    model_effort_rows: list[tuple] | None = None,
    hour_rows: list[tuple] | None = None,
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
    conn.executemany(
        'INSERT INTO daily_hour_usage VALUES (?,?,?)',
        hour_rows or [],
    )
    conn.executemany(
        'INSERT INTO daily_effort_usage VALUES (?,?,?)',
        effort_rows or [],
    )
    conn.executemany(
        'INSERT INTO daily_model_effort_usage VALUES (?,?,?,?,?,?)',
        model_effort_rows or [],
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


def model_effort_row(
    day: str,
    model_effort: str,
    *,
    output_tokens: int = 0,
    input_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> tuple:
    return (
        day,
        model_effort,
        output_tokens,
        input_tokens,
        cache_read_tokens,
        cache_write_tokens,
    )


def effort_row(day: str, effort: str, *, count: int = 0) -> tuple:
    return (day, effort, count)


def totals_row(
    day: str,
    sessions: int,
    lines_added: int,
    lines_removed: int,
    *,
    output_tokens: int = 0,
    input_tokens: int = 0,
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
        output_tokens,
        input_tokens,
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


def test_load_garden_data_sums_total_tokens_across_days(
    tmp_path: Path,
) -> None:
    totals_rows = [
        totals_row(
            '2026-07-26',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            output_tokens=40,
            input_tokens=10,
            cache_read_tokens=300,
            cache_write_tokens=100,
        ),
        totals_row(
            '2026-07-27',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            output_tokens=20,
            input_tokens=5,
            cache_read_tokens=200,
            cache_write_tokens=50,
        ),
    ]
    db_path = make_db(tmp_path, totals_rows=totals_rows, repo_rows=[])

    garden = load_garden_data(db_path)

    assert garden.total_tokens == 725


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


def test_load_garden_timeline_starts_from_an_empty_seed_day(
    tmp_path: Path,
) -> None:
    totals_rows = [
        totals_row('2026-07-26', sessions=3, lines_added=10, lines_removed=1),
    ]
    repo_rows = [
        repo_row(
            '2026-07-26', 'alpha', sessions=3, lines_added=10, lines_removed=1
        )
    ]
    db_path = make_db(tmp_path, totals_rows=totals_rows, repo_rows=repo_rows)

    timeline = load_garden_timeline(db_path)

    assert timeline.days == ['2026-07-25', '2026-07-26']
    assert timeline.daily_sessions == [0, 3]
    assert timeline.cumulative_sessions == [0, 3]
    first_frame = timeline.branch_days['alpha'][0]
    assert first_frame.day == '2026-07-25'
    assert first_frame.sessions == 0
    assert first_frame.lines_added == 0


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

    assert timeline.cumulative_cache_read == [0, 300, 500]
    assert timeline.cumulative_cache_write == [0, 100, 150]


def test_load_garden_timeline_tracks_cumulative_total_tokens_per_day(
    tmp_path: Path,
) -> None:
    totals_rows = [
        totals_row(
            '2026-07-26',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            output_tokens=40,
            input_tokens=10,
            cache_read_tokens=300,
            cache_write_tokens=100,
        ),
        totals_row(
            '2026-07-27',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            output_tokens=20,
            input_tokens=5,
            cache_read_tokens=200,
            cache_write_tokens=50,
        ),
    ]
    db_path = make_db(tmp_path, totals_rows=totals_rows, repo_rows=[])

    timeline = load_garden_timeline(db_path)

    assert timeline.cumulative_total_tokens == [0, 450, 725]


def test_load_tools_excludes_tools_with_zero_count(tmp_path: Path) -> None:
    tool_rows = [tool_row('2026-07-26', 'Read', count=0)]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], tool_rows=tool_rows
    )

    garden = load_garden_data(db_path)

    assert garden.tools == []


def test_load_efforts_aggregates_same_effort_across_days(
    tmp_path: Path,
) -> None:
    effort_rows = [
        effort_row('2026-07-26', 'high', count=5),
        effort_row('2026-07-27', 'high', count=7),
    ]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], effort_rows=effort_rows
    )

    garden = load_garden_data(db_path)

    assert garden.efforts == [EffortBush(effort='high', count=12)]


def test_load_efforts_sorts_by_count_descending(tmp_path: Path) -> None:
    effort_rows = [
        effort_row('2026-07-26', 'low', count=2),
        effort_row('2026-07-26', 'high', count=50),
        effort_row('2026-07-26', 'medium', count=10),
    ]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], effort_rows=effort_rows
    )

    garden = load_garden_data(db_path)

    assert [effort_bush.effort for effort_bush in garden.efforts] == [
        'high',
        'medium',
        'low',
    ]


def test_load_efforts_excludes_efforts_with_zero_count(
    tmp_path: Path,
) -> None:
    effort_rows = [effort_row('2026-07-26', 'high', count=0)]
    db_path = make_db(
        tmp_path, totals_rows=[], repo_rows=[], effort_rows=effort_rows
    )

    garden = load_garden_data(db_path)

    assert garden.efforts == []


def test_load_model_efforts_aggregates_same_pairing_across_days(
    tmp_path: Path,
) -> None:
    model_effort_rows = [
        model_effort_row(
            '2026-07-26', 'claude-sonnet-5 (high)', output_tokens=200
        ),
        model_effort_row(
            '2026-07-27', 'claude-sonnet-5 (high)', output_tokens=100
        ),
    ]
    db_path = make_db(
        tmp_path,
        totals_rows=[],
        repo_rows=[],
        model_effort_rows=model_effort_rows,
    )

    garden = load_garden_data(db_path)

    assert garden.model_efforts == [
        ModelCloud(
            model='claude-sonnet-5 (high)', output_tokens=300, input_tokens=0
        )
    ]


def test_load_model_efforts_sorts_by_total_tokens_descending(
    tmp_path: Path,
) -> None:
    model_effort_rows = [
        model_effort_row(
            '2026-07-26', 'claude-haiku (medium)', output_tokens=10
        ),
        model_effort_row(
            '2026-07-26', 'claude-opus-5 (high)', output_tokens=500
        ),
        model_effort_row(
            '2026-07-26', 'claude-sonnet-5 (low)', output_tokens=100
        ),
    ]
    db_path = make_db(
        tmp_path,
        totals_rows=[],
        repo_rows=[],
        model_effort_rows=model_effort_rows,
    )

    garden = load_garden_data(db_path)

    assert [cloud.model for cloud in garden.model_efforts] == [
        'claude-opus-5 (high)',
        'claude-sonnet-5 (low)',
        'claude-haiku (medium)',
    ]


def test_load_model_efforts_excludes_pairings_with_no_token_usage(
    tmp_path: Path,
) -> None:
    model_effort_rows = [model_effort_row('2026-07-26', 'claude-opus-5')]
    db_path = make_db(
        tmp_path,
        totals_rows=[],
        repo_rows=[],
        model_effort_rows=model_effort_rows,
    )

    garden = load_garden_data(db_path)

    assert garden.model_efforts == []


CARTOON_OUTPUT = """calls: 40
tokens_saved: 7000
by_adapter:
  pytest:
    calls: 30
    saved: 6000
  passthrough:
    calls: 10
    saved: 0
"""


def test_load_cartoon_birds_reads_per_adapter_savings_biggest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'ccgarden.data.run_cartoon_stats', lambda _since: CARTOON_OUTPUT
    )

    birds = load_cartoon_birds('7d')

    # passthrough saved nothing, so it earns no bird.
    assert birds == [
        CartoonBird(adapter='pytest', calls=30, tokens_saved=6000)
    ]


def test_load_cartoon_birds_is_empty_when_cartoon_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_cartoon_stats already returns None for a missing binary, a
    # non-zero exit, or a timeout -- all of which must read as "no birds".
    monkeypatch.setattr('ccgarden.data.run_cartoon_stats', lambda _since: None)

    assert load_cartoon_birds('7d') == []


def test_load_cartoon_birds_is_empty_when_output_is_unparseable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'ccgarden.data.run_cartoon_stats',
        lambda _since: 'calls: not-a-number\n',
    )

    assert load_cartoon_birds('7d') == []


def test_load_cartoon_birds_is_empty_when_cartoon_blows_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(since: str) -> str:
        raise OSError(since)

    monkeypatch.setattr('ccgarden.data.run_cartoon_stats', boom)

    assert load_cartoon_birds('7d') == []


def test_load_garden_data_without_cartoon_still_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr('ccgarden.data.run_cartoon_stats', lambda _since: None)
    db_path = make_db(tmp_path, totals_rows=[], repo_rows=[])

    garden = load_garden_data(db_path)

    assert garden.birds == []


def test_nightness_is_the_share_of_prompts_typed_at_night() -> None:
    # 3 of 12 prompts fall in NIGHT_HOURS (23:00 and 02:00).
    assert _nightness({9: 6, 14: 3, 23: 2, 2: 1}) == pytest.approx(0.25)


def test_nightness_of_a_day_with_no_prompts_is_zero() -> None:
    assert _nightness({}) == 0.0


def test_load_garden_data_aggregates_hours_across_days(
    tmp_path: Path,
) -> None:
    db_path = make_db(
        tmp_path,
        totals_rows=[totals_row('2026-01-01', 1, 0, 0)],
        repo_rows=[],
        hour_rows=[
            ('2026-01-01', 9, 4),
            ('2026-01-01', 23, 1),
            ('2026-01-02', 9, 2),
            ('2026-01-02', 2, 3),
        ],
    )

    garden = load_garden_data(db_path, cartoon_since='')

    assert garden.hour_counts == {9: 6, 23: 1, 2: 3}
    assert garden.nightness == pytest.approx(0.4)


def test_timeline_nightness_is_per_day_not_cumulative(tmp_path: Path) -> None:
    db_path = make_db(
        tmp_path,
        totals_rows=[
            totals_row('2026-01-01', 1, 0, 0),
            totals_row('2026-01-02', 1, 0, 0),
        ],
        repo_rows=[],
        hour_rows=[
            # An all-night first day followed by an all-day second one.
            ('2026-01-01', 2, 5),
            ('2026-01-02', 14, 5),
        ],
    )

    timeline = load_garden_timeline(db_path, cartoon_since='')

    # The seed day leads, then the real days -- and day two drops back to
    # full daylight rather than inheriting day one's night.
    assert timeline.daily_nightness == [0.0, 1.0, 0.0]


def test_hours_are_absent_when_the_table_predates_the_feature(
    tmp_path: Path,
) -> None:
    db_path = make_db(
        tmp_path,
        totals_rows=[totals_row('2026-01-01', 1, 0, 0)],
        repo_rows=[],
    )
    sqlite3.connect(db_path).execute('DROP TABLE daily_hour_usage')

    garden = load_garden_data(db_path, cartoon_since='')
    timeline = load_garden_timeline(db_path, cartoon_since='')

    assert garden.hour_counts == {}
    assert garden.nightness == 0.0
    assert timeline.daily_nightness == [0.0, 0.0]


def test_day_range_limits_what_the_garden_loads(tmp_path: Path) -> None:
    db_path = make_db(
        tmp_path,
        totals_rows=[
            totals_row('2026-01-01', 1, 10, 0),
            totals_row('2026-02-01', 1, 20, 0),
            totals_row('2026-03-01', 1, 40, 0),
        ],
        repo_rows=[],
    )

    garden = load_garden_data(
        db_path,
        cartoon_since='',
        days=DayRange(since='2026-02-01', until='2026-02-28'),
    )

    assert [ring.day for ring in garden.rings] == ['2026-02-01']


def test_an_open_ended_day_range_bounds_only_one_side(
    tmp_path: Path,
) -> None:
    db_path = make_db(
        tmp_path,
        totals_rows=[
            totals_row('2026-01-01', 1, 10, 0),
            totals_row('2026-02-01', 1, 20, 0),
            totals_row('2026-03-01', 1, 40, 0),
        ],
        repo_rows=[],
    )

    garden = load_garden_data(
        db_path, cartoon_since='', days=DayRange(since='2026-02-01')
    )

    assert [ring.day for ring in garden.rings] == ['2026-02-01', '2026-03-01']


def test_the_default_day_range_selects_everything() -> None:
    assert ALL_DAYS.clause() == ''
    assert ALL_DAYS.params == ()


def test_a_long_gap_gets_a_dormant_frame_of_its_own(tmp_path: Path) -> None:
    """Without one, a months-long lapse is a single frame boundary."""
    db_path = make_db(
        tmp_path,
        totals_rows=[
            totals_row('2026-01-01', 1, 0, 0),
            totals_row('2026-03-02', 1, 0, 0),
        ],
        repo_rows=[],
    )

    timeline = load_garden_timeline(db_path, cartoon_since='')

    assert timeline.days == [
        '2025-12-31',  # seed
        '2026-01-01',
        '2026-01-31',  # dormant midpoint
        '2026-03-02',
    ]
    dormant = timeline.daily_vitality[2]
    assert dormant < 0.2
    # The garden comes back to life when you do.
    assert timeline.daily_vitality[-1] == pytest.approx(1.0)


def test_a_weekend_is_not_a_dormancy(tmp_path: Path) -> None:
    db_path = make_db(
        tmp_path,
        totals_rows=[
            totals_row('2026-01-02', 1, 0, 0),  # Friday
            totals_row('2026-01-05', 1, 0, 0),  # Monday
        ],
        repo_rows=[],
    )

    timeline = load_garden_timeline(db_path, cartoon_since='')

    assert timeline.days == ['2026-01-01', '2026-01-02', '2026-01-05']
    assert all(value == 1.0 for value in timeline.daily_vitality)


def test_a_dormant_frame_holds_growth_rather_than_reversing_it(
    tmp_path: Path,
) -> None:
    """Cumulative shapes must not shrink during a gap -- only pause."""
    db_path = make_db(
        tmp_path,
        totals_rows=[
            totals_row('2026-01-01', 3, 0, 0),
            totals_row('2026-03-02', 2, 0, 0),
        ],
        repo_rows=[],
    )

    timeline = load_garden_timeline(db_path, cartoon_since='')

    assert timeline.cumulative_sessions == [0, 3, 3, 5]


def test_vitality_decays_with_days_since_the_last_active_day() -> None:
    days = ['2026-01-01', '2026-01-13', '2026-01-25']

    vitality = _daily_vitality(days, active={'2026-01-01'})

    # One half-life, then two.
    assert vitality[0] == pytest.approx(1.0)
    assert vitality[1] == pytest.approx(0.5, abs=0.01)
    assert vitality[2] == pytest.approx(0.25, abs=0.01)
