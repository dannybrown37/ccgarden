"""Tests for ccgarden.claude_stats."""

import json
import shutil
import sqlite3
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from ccgarden.claude_stats import (
    BAR_WIDTH,
    MAX_SPARK_POINTS,
    UNKNOWN_REPO,
    CostBreakdown,
    RepoReport,
    ModelPrice,
    ModelUsage,
    PricingTable,
    UsageStats,
    bar,
    box_lines,
    bucket_series,
    build_repo_reports,
    cartoon_lines,
    collect_stats,
    collect_stats_by_repo,
    compute_cost,
    daily_series,
    ensure_schema,
    find_model_price,
    format_report,
    git_root_on_disk,
    iter_days,
    label_repo_roots,
    load_pricing,
    merge_stats,
    parse_cartoon_stats,
    peek_cwd,
    percentile,
    record_day,
    record_range,
    record_repo_day,
    resolve_repo_roots,
    run_cartoon_stats,
    sparkline,
    stats_as_dict,
    supports_color,
    truncate,
    worktree_sibling_root,
)

STAMP = '2026-07-26T09:00:00.000Z'
REPLY_OUTPUT_TOKENS = 10
REPLY_CACHE_READ_TOKENS = 100
LONG_PROMPT_CHARS = 500
EXPECTED_GENUINE_PROMPTS = 2
EXPECTED_ADDED_LINES = 2
EXPECTED_REMOVED_LINES = 1
EXPECTED_BASH_USES = 2
NARROW_WIDTH = 60
WIDE_WIDTH = 200
EXPECTED_CACHE_HIT_RATIO = 200 / 700
EXPECTED_CACHE_EFFICIENCY = 2.0
OPUS_MODEL_OUTPUT_TOKENS = 10
OPUS_MODEL_INPUT_TOKENS = 5
OPUS_MODEL_CACHE_READ_TOKENS = 100
OPUS_MODEL_CACHE_WRITE_TOKENS = 20
HAIKU_MODEL_OUTPUT_TOKENS = 3
HAIKU_MODEL_INPUT_TOKENS = 1


def _assistant(**overrides: object) -> dict:
    record = {
        'type': 'assistant',
        'sessionId': 's1',
        'timestamp': STAMP,
        'message': {
            'model': 'claude-opus-5',
            'content': [{'type': 'text', 'text': 'hi'}],
            'usage': {
                'output_tokens': 10,
                'cache_read_input_tokens': 100,
                'input_tokens': 1,
            },
        },
    }
    record.update(overrides)
    return record


def _prompt(text: str = 'do a thing', **overrides: object) -> dict:
    record = {
        'type': 'user',
        'sessionId': 's1',
        'timestamp': STAMP,
        'message': {'role': 'user', 'content': text},
    }
    record.update(overrides)
    return record


def _write_log(tmp_path: Path, records: list[dict], name: str = 'a') -> Path:
    path = tmp_path / f'{name}.jsonl'
    path.write_text(
        ''.join(json.dumps(record) + '\n' for record in records),
    )
    return path


def test_counts_only_genuine_prompts(tmp_path: Path) -> None:
    """Tool results and meta records outnumber prompts ~6:1 in real logs."""
    _write_log(
        tmp_path,
        [
            _prompt('real one'),
            _prompt('tool output', toolUseResult={'stdout': 'x'}),
            _prompt('injected context', isMeta=True),
            _prompt(
                'with blocks',
                message={
                    'role': 'user',
                    'content': [{'type': 'text', 'text': 'blocks'}],
                },
            ),
        ],
    )

    stats = collect_stats([tmp_path])

    assert stats.prompts == EXPECTED_GENUINE_PROMPTS


def test_sums_token_usage_and_counts_replies(tmp_path: Path) -> None:
    replies = [_assistant(), _assistant()]
    _write_log(tmp_path, replies)

    stats = collect_stats([tmp_path])

    assert stats.replies == len(replies)
    assert stats.output_tokens == len(replies) * REPLY_OUTPUT_TOKENS
    assert stats.cache_read_tokens == len(replies) * REPLY_CACHE_READ_TOKENS


def test_counts_lines_added_and_removed_from_patches(tmp_path: Path) -> None:
    patch = [
        {'lines': ['+added one', '-removed one', ' context', '+added two']},
    ]
    _write_log(
        tmp_path,
        [_prompt('edit', toolUseResult={'structuredPatch': patch})],
    )

    stats = collect_stats([tmp_path])

    assert stats.lines_added == EXPECTED_ADDED_LINES
    assert stats.lines_removed == EXPECTED_REMOVED_LINES


def test_tallies_models_tools_and_thinking_blocks(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [
            _assistant(
                message={
                    'model': 'claude-opus-5',
                    'usage': {},
                    'content': [
                        {'type': 'thinking', 'thinking': '...'},
                        {'type': 'tool_use', 'name': 'Bash'},
                    ],
                },
            ),
            _assistant(
                message={
                    'model': 'claude-haiku-4-5-20251001',
                    'usage': {},
                    'content': [{'type': 'tool_use', 'name': 'Bash'}],
                },
            ),
        ],
    )

    stats = collect_stats([tmp_path])

    assert stats.thinking_blocks == 1
    assert stats.tools['Bash'] == EXPECTED_BASH_USES
    assert stats.models['claude-opus-5'] == 1
    assert stats.models['claude-haiku-4-5-20251001'] == 1


def test_groups_output_tokens_by_day(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [
            _assistant(timestamp='2026-07-25T23:00:00.000Z'),
            _assistant(timestamp='2026-07-26T01:00:00.000Z'),
            _assistant(timestamp='2026-07-26T02:00:00.000Z'),
        ],
    )

    stats = collect_stats([tmp_path])

    assert stats.output_tokens_by_day == {
        date(2026, 7, 25): REPLY_OUTPUT_TOKENS,
        date(2026, 7, 26): 2 * REPLY_OUTPUT_TOKENS,
    }


@pytest.mark.parametrize(
    ('since', 'until', 'expected_replies'),
    [
        (None, None, 3),
        (date(2026, 7, 26), None, 2),
        (None, date(2026, 7, 25), 1),
        (date(2026, 7, 26), date(2026, 7, 26), 2),
    ],
)
def test_date_filters_bound_the_window(
    tmp_path: Path,
    since: date | None,
    until: date | None,
    expected_replies: int,
) -> None:
    _write_log(
        tmp_path,
        [
            _assistant(timestamp='2026-07-25T12:00:00.000Z'),
            _assistant(timestamp='2026-07-26T12:00:00.000Z'),
            _assistant(timestamp='2026-07-26T13:00:00.000Z'),
        ],
    )

    stats = collect_stats([tmp_path], since=since, until=until)

    assert stats.replies == expected_replies


def test_counts_distinct_sessions_and_subagent_runs(tmp_path: Path) -> None:
    _write_log(tmp_path, [_assistant(sessionId='s1')], name='one')
    _write_log(tmp_path, [_assistant(sessionId='s2')], name='two')
    subagents = tmp_path / 'subagents'
    subagents.mkdir()
    _write_log(subagents, [_assistant(sessionId='s3')], name='agent')

    stats = collect_stats([tmp_path])

    assert stats.sessions == len({'s1', 's2', 's3'})
    assert stats.subagent_runs == 1


def test_skips_malformed_lines_without_failing(tmp_path: Path) -> None:
    path = tmp_path / 'a.jsonl'
    path.write_text(
        '\n'.join(
            [
                'not json at all',
                json.dumps(_assistant()),
                '{"truncated": ',
                '',
            ],
        ),
    )

    stats = collect_stats([tmp_path])

    assert stats.replies == 1


def test_tracks_longest_prompt(tmp_path: Path) -> None:
    _write_log(tmp_path, [_prompt('short'), _prompt('x' * LONG_PROMPT_CHARS)])

    stats = collect_stats([tmp_path])

    assert stats.longest_prompt_chars == LONG_PROMPT_CHARS


def _stats_with_full_report_data() -> UsageStats:
    return UsageStats(
        session_ids={'s1'},
        prompts=5,
        replies=5,
        output_tokens=1000,
        input_tokens=500,
        cache_read_tokens=200,
        cache_write_tokens=100,
        lines_added=10,
        lines_removed=3,
        thinking_blocks=2,
        subagent_runs=1,
        longest_prompt_chars=42,
        models=Counter(
            {'claude-opus-5': 3, 'claude-haiku-4-5-20251001': 2},
        ),
        tools=Counter({'Bash': 4, 'Read': 2}),
        first_seen=datetime.fromisoformat(STAMP.replace('Z', '+00:00')),
        last_seen=datetime.fromisoformat(STAMP.replace('Z', '+00:00')),
    )


def _lines_mentioning_both(
    report: str,
    left_needle: str,
    right_needle: str,
) -> list[str]:
    return [
        line
        for line in report.split('\n')
        if left_needle in line and right_needle in line
    ]


def test_format_report_stacks_totals_and_tokens_when_narrow() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=NARROW_WIDTH,
        color=False,
    )

    assert not _lines_mentioning_both(report, 'sessions', 'tokens out')


def test_format_report_columns_totals_and_tokens_when_wide() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert _lines_mentioning_both(report, 'sessions', 'tokens out')


def test_format_report_stacks_models_and_tools_when_narrow() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=NARROW_WIDTH,
        color=False,
    )

    assert not _lines_mentioning_both(report, 'model mix', 'top tools')


def test_format_report_columns_models_and_tools_when_wide() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert _lines_mentioning_both(report, 'model mix', 'top tools')


def test_format_report_includes_ansi_codes_when_color_enabled() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=True,
    )

    assert '\x1b[' in report


def test_format_report_omits_ansi_codes_when_color_disabled() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert '\x1b[' not in report


@pytest.mark.parametrize(
    ('is_a_tty', 'no_color_env', 'expected'),
    [
        (True, None, True),
        (False, None, False),
        (True, '1', False),
    ],
)
def test_supports_color_reflects_tty_and_no_color_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_a_tty: bool,
    no_color_env: str | None,
    expected: bool,
) -> None:
    monkeypatch.setattr('sys.stdout.isatty', lambda: is_a_tty)
    if no_color_env is None:
        monkeypatch.delenv('NO_COLOR', raising=False)
    else:
        monkeypatch.setenv('NO_COLOR', no_color_env)

    assert supports_color() is expected


def test_cache_hit_ratio_computes_share_of_input_served_from_cache() -> None:
    stats = _stats_with_full_report_data()

    assert stats.cache_hit_ratio == pytest.approx(EXPECTED_CACHE_HIT_RATIO)


def test_cache_hit_ratio_is_none_without_reads_or_input() -> None:
    stats = UsageStats()

    assert stats.cache_hit_ratio is None


def test_cache_efficiency_computes_reads_per_write() -> None:
    stats = _stats_with_full_report_data()

    assert stats.cache_efficiency == pytest.approx(EXPECTED_CACHE_EFFICIENCY)


def test_cache_efficiency_is_none_without_cache_writes() -> None:
    stats = UsageStats(cache_read_tokens=100)

    assert stats.cache_efficiency is None


def test_format_report_includes_cache_efficiency_when_present() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'cache hit ratio' in report
    assert 'cache efficiency' in report


def test_format_report_omits_cache_efficiency_without_activity() -> None:
    stats = UsageStats(
        session_ids={'s1'},
        prompts=1,
        replies=1,
        output_tokens=10,
        first_seen=datetime.fromisoformat(STAMP.replace('Z', '+00:00')),
        last_seen=datetime.fromisoformat(STAMP.replace('Z', '+00:00')),
    )

    report = format_report(stats, width=WIDE_WIDTH, color=False)

    assert 'cache hit ratio' not in report
    assert 'cache efficiency' not in report


def test_stats_as_dict_includes_cache_efficiency_metrics() -> None:
    data = stats_as_dict(_stats_with_full_report_data())

    assert data['cache_hit_ratio'] == pytest.approx(EXPECTED_CACHE_HIT_RATIO)
    assert data['cache_efficiency'] == pytest.approx(EXPECTED_CACHE_EFFICIENCY)


def test_stats_as_dict_cache_metrics_are_none_without_data() -> None:
    data = stats_as_dict(UsageStats())

    assert data['cache_hit_ratio'] is None
    assert data['cache_efficiency'] is None


def test_tracks_per_model_token_usage(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [
            _assistant(
                message={
                    'model': 'claude-opus-5',
                    'content': [],
                    'usage': {
                        'output_tokens': 10,
                        'input_tokens': 5,
                        'cache_read_input_tokens': 100,
                        'cache_creation_input_tokens': 20,
                    },
                },
            ),
            _assistant(
                message={
                    'model': 'claude-haiku-4-5-20251001',
                    'content': [],
                    'usage': {'output_tokens': 3, 'input_tokens': 1},
                },
            ),
        ],
    )

    stats = collect_stats([tmp_path])

    opus_usage = stats.model_usage['claude-opus-5']
    assert opus_usage.output_tokens == OPUS_MODEL_OUTPUT_TOKENS
    assert opus_usage.input_tokens == OPUS_MODEL_INPUT_TOKENS
    assert opus_usage.cache_read_tokens == OPUS_MODEL_CACHE_READ_TOKENS
    assert opus_usage.cache_write_tokens == OPUS_MODEL_CACHE_WRITE_TOKENS

    haiku_usage = stats.model_usage['claude-haiku-4-5-20251001']
    assert haiku_usage.output_tokens == HAIKU_MODEL_OUTPUT_TOKENS
    assert haiku_usage.input_tokens == HAIKU_MODEL_INPUT_TOKENS


def _write_pricing(tmp_path: Path, **overrides: object) -> Path:
    data: dict = {
        'as_of': '2026-07-01',
        'cache_write_multiplier': 1.25,
        'cache_read_multiplier': 0.1,
        'models': {
            'claude-opus-5': {'input': 5.0, 'output': 25.0},
            'claude-haiku-4-5': {'input': 1.0, 'output': 5.0},
        },
    }
    data.update(overrides)
    path = tmp_path / 'pricing.json'
    path.write_text(json.dumps(data))
    return path


def test_load_pricing_parses_models_and_multipliers(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path))

    assert pricing.as_of == date(2026, 7, 1)
    assert pricing.cache_write_multiplier == pytest.approx(1.25)
    assert pricing.cache_read_multiplier == pytest.approx(0.1)
    assert pricing.models['claude-opus-5'].output_per_million == pytest.approx(
        25.0,
    )


def test_load_pricing_parses_optional_expiry(tmp_path: Path) -> None:
    path = _write_pricing(
        tmp_path,
        models={
            'claude-sonnet-5': {
                'input': 2.0,
                'output': 10.0,
                'expires': '2026-08-31',
            },
        },
    )

    pricing = load_pricing(path)

    assert pricing.models['claude-sonnet-5'].expires == date(2026, 8, 31)


def test_find_model_price_matches_dated_suffix_via_prefix(
    tmp_path: Path,
) -> None:
    pricing = load_pricing(_write_pricing(tmp_path))

    price = find_model_price('claude-haiku-4-5-20251001', pricing)

    assert price is not None
    assert price.output_per_million == pytest.approx(5.0)


def test_find_model_price_is_none_for_unknown_model(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path))

    assert find_model_price('<synthetic>', pricing) is None


def _pricing_table(**overrides: object) -> PricingTable:
    defaults: dict = {
        'as_of': date(2026, 7, 1),
        'cache_write_multiplier': 1.25,
        'cache_read_multiplier': 0.1,
        'models': {
            'claude-opus-5': ModelPrice(
                input_per_million=5.0,
                output_per_million=25.0,
            ),
        },
    }
    defaults.update(overrides)
    return PricingTable(**defaults)


def test_compute_cost_prices_each_token_category() -> None:
    stats = UsageStats(
        model_usage={
            'claude-opus-5': ModelUsage(
                output_tokens=1_000_000,
                input_tokens=1_000_000,
                cache_read_tokens=1_000_000,
                cache_write_tokens=1_000_000,
            ),
        },
    )

    cost = compute_cost(stats, _pricing_table(), today=date(2026, 7, 1))

    assert cost.by_category['output'] == pytest.approx(25.0)
    assert cost.by_category['input'] == pytest.approx(5.0)
    assert cost.by_category['cache_read'] == pytest.approx(0.5)
    assert cost.by_category['cache_write'] == pytest.approx(6.25)
    assert cost.total == pytest.approx(25.0 + 5.0 + 0.5 + 6.25)
    assert cost.by_model['claude-opus-5'] == pytest.approx(cost.total)


def test_compute_cost_flags_unpriced_models() -> None:
    stats = UsageStats(
        model_usage={'<synthetic>': ModelUsage(output_tokens=10)},
    )

    cost = compute_cost(stats, _pricing_table(), today=date(2026, 7, 1))

    assert cost.unpriced_models == {'<synthetic>'}
    assert cost.total == 0


@pytest.mark.parametrize(
    ('as_of', 'today', 'expected_stale'),
    [
        (date(2026, 1, 1), date(2026, 7, 1), True),
        (date(2026, 6, 1), date(2026, 7, 1), False),
    ],
)
def test_compute_cost_flags_staleness_by_age(
    *,
    as_of: date,
    today: date,
    expected_stale: bool,
) -> None:
    cost = compute_cost(
        UsageStats(),
        _pricing_table(as_of=as_of),
        today=today,
    )

    assert cost.pricing_stale is expected_stale


def test_compute_cost_flags_staleness_from_expired_model_price() -> None:
    stats = UsageStats(
        model_usage={
            'claude-sonnet-5': ModelUsage(output_tokens=1_000_000),
        },
    )
    pricing = _pricing_table(
        as_of=date(2026, 7, 1),
        models={
            'claude-sonnet-5': ModelPrice(
                input_per_million=2.0,
                output_per_million=10.0,
                expires=date(2026, 8, 31),
            ),
        },
    )

    cost = compute_cost(stats, pricing, today=date(2026, 9, 1))

    assert cost.expired_models == {'claude-sonnet-5'}
    assert cost.pricing_stale is True


def _sample_cost(**overrides: object) -> CostBreakdown:
    defaults: dict = {
        'total': 12.34,
        'by_category': {
            'output': 10.0,
            'input': 1.0,
            'cache_read': 0.5,
            'cache_write': 0.84,
        },
        'by_model': {'claude-opus-5': 12.34},
        'unpriced_models': set(),
        'expired_models': set(),
        'pricing_as_of': date(2026, 7, 1),
        'pricing_stale': False,
    }
    defaults.update(overrides)
    return CostBreakdown(**defaults)


def test_format_report_includes_estimated_spend_when_cost_given() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
        cost=_sample_cost(),
    )

    assert 'estimated spend' in report
    assert '12.34' in report


def test_format_report_omits_spend_section_without_cost() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'estimated spend' not in report


def test_format_report_flags_stale_pricing() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
        cost=_sample_cost(pricing_stale=True),
    )

    assert 'stale' in report


def test_stats_as_dict_includes_cost_when_given() -> None:
    data = stats_as_dict(
        _stats_with_full_report_data(),
        _sample_cost(unpriced_models={'<synthetic>'}),
    )

    assert data['cost']['total'] == pytest.approx(12.34)
    assert data['cost']['unpriced_models'] == ['<synthetic>']
    assert data['cost']['pricing_as_of'] == '2026-07-01'


def test_stats_as_dict_cost_is_none_without_cost_arg() -> None:
    data = stats_as_dict(_stats_with_full_report_data())

    assert data['cost'] is None


def _turn_duration(duration_ms: int, **overrides: object) -> dict:
    record = {
        'type': 'system',
        'subtype': 'turn_duration',
        'sessionId': 's1',
        'timestamp': STAMP,
        'durationMs': duration_ms,
    }
    record.update(overrides)
    return record


def _at(offset_seconds: float) -> str:
    """Timestamp `offset_seconds` after STAMP, for turn-timing tests."""
    base = datetime.fromisoformat(STAMP.replace('Z', '+00:00'))
    moment = base + timedelta(seconds=offset_seconds)
    return moment.isoformat().replace('+00:00', 'Z')


def _tool_result(**overrides: object) -> dict:
    record = {
        'type': 'user',
        'sessionId': 's1',
        'timestamp': STAMP,
        'toolUseResult': {'stdout': 'x'},
        'message': {'role': 'user', 'content': 'tool output'},
    }
    record.update(overrides)
    return record


SAMPLE_DURATIONS_MS = [1000, 2000, 3000]
EXPECTED_P50_MS = 2000
EXPECTED_P95_MS = 3000
OPUS_TURN_MS = 5000
HAIKU_TURN_MS = 500
FIRST_REPLY_SECONDS = 3
TOOL_GAP_SECONDS = 7
SECOND_REPLY_SECONDS = 2
EXPECTED_MODEL_MS = (FIRST_REPLY_SECONDS + SECOND_REPLY_SECONDS) * 1000
IDLE_SECONDS = 900


@pytest.mark.parametrize(
    ('values', 'fraction', 'expected'),
    [
        ([10, 20, 30], 0.5, 20),
        ([10, 20, 30], 0.95, 30),
        ([30, 10, 20], 0.5, 20),
        ([42], 0.5, 42),
        ([42], 0.95, 42),
        ([10, 20], 0.5, 10),
    ],
)
def test_percentile_uses_nearest_rank(
    values: list[int],
    fraction: float,
    expected: float,
) -> None:
    assert percentile(values, fraction) == pytest.approx(expected)


def test_collects_wall_durations_from_system_records(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        [_turn_duration(ms) for ms in SAMPLE_DURATIONS_MS],
    )

    stats = collect_stats([tmp_path])

    assert sorted(stats.wall_durations_ms) == SAMPLE_DURATIONS_MS


def test_model_time_counts_only_gaps_ending_at_a_reply(
    tmp_path: Path,
) -> None:
    """Gaps ending at a tool result hold tool runs and approval waits."""
    tool_moment = FIRST_REPLY_SECONDS + TOOL_GAP_SECONDS
    _write_log(
        tmp_path,
        [
            _prompt(timestamp=_at(0)),
            _assistant(timestamp=_at(FIRST_REPLY_SECONDS)),
            _tool_result(timestamp=_at(tool_moment)),
            _assistant(timestamp=_at(tool_moment + SECOND_REPLY_SECONDS)),
            _turn_duration(
                OPUS_TURN_MS,
                timestamp=_at(tool_moment + SECOND_REPLY_SECONDS),
            ),
        ],
    )

    stats = collect_stats([tmp_path])

    assert stats.model_durations_ms == [pytest.approx(EXPECTED_MODEL_MS)]


def test_model_time_excludes_idle_time_between_turns(
    tmp_path: Path,
) -> None:
    """A turn starts at your prompt, not when the previous turn ended."""
    _write_log(
        tmp_path,
        [
            _prompt(timestamp=_at(0)),
            _assistant(timestamp=_at(FIRST_REPLY_SECONDS)),
            _turn_duration(OPUS_TURN_MS, timestamp=_at(FIRST_REPLY_SECONDS)),
            _prompt(timestamp=_at(IDLE_SECONDS)),
            _assistant(
                timestamp=_at(IDLE_SECONDS + SECOND_REPLY_SECONDS),
            ),
            _turn_duration(
                HAIKU_TURN_MS,
                timestamp=_at(IDLE_SECONDS + SECOND_REPLY_SECONDS),
            ),
        ],
    )

    stats = collect_stats([tmp_path])

    assert stats.model_durations_ms == [
        pytest.approx(FIRST_REPLY_SECONDS * 1000),
        pytest.approx(SECOND_REPLY_SECONDS * 1000),
    ]


def test_attributes_model_time_to_the_turns_dominant_model(
    tmp_path: Path,
) -> None:
    """A turn that delegates to a subagent still belongs to the driver."""
    haiku = 'claude-haiku-4-5-20251001'
    haiku_message = {'model': haiku, 'content': [], 'usage': {}}
    _write_log(
        tmp_path,
        [
            _prompt(timestamp=_at(0)),
            _assistant(timestamp=_at(1)),
            _assistant(timestamp=_at(2)),
            _assistant(timestamp=_at(3), message=haiku_message),
            _turn_duration(OPUS_TURN_MS, timestamp=_at(3)),
            _prompt(timestamp=_at(4)),
            _assistant(timestamp=_at(5), message=haiku_message),
            _turn_duration(HAIKU_TURN_MS, timestamp=_at(5)),
        ],
    )

    stats = collect_stats([tmp_path])

    assert stats.model_durations_ms_by_model == {
        'claude-opus-5': [pytest.approx(3000)],
        haiku: [pytest.approx(1000)],
    }


def test_turn_without_preceding_reply_is_unattributed(
    tmp_path: Path,
) -> None:
    _write_log(tmp_path, [_turn_duration(OPUS_TURN_MS)])

    stats = collect_stats([tmp_path])

    assert stats.wall_durations_ms == [OPUS_TURN_MS]
    assert stats.model_durations_ms == []
    assert stats.model_durations_ms_by_model == {}


def test_turn_state_does_not_leak_across_transcripts(tmp_path: Path) -> None:
    """Each file is its own turn stream; a dangling reply must not carry."""
    haiku = 'claude-haiku-4-5-20251001'
    _write_log(tmp_path, [_prompt(timestamp=_at(0)), _assistant()], name='one')
    _write_log(
        tmp_path,
        [
            _prompt(timestamp=_at(0)),
            _assistant(
                timestamp=_at(1),
                message={'model': haiku, 'content': [], 'usage': {}},
            ),
            _turn_duration(HAIKU_TURN_MS, timestamp=_at(1)),
        ],
        name='two',
    )

    stats = collect_stats([tmp_path])

    assert stats.model_durations_ms_by_model == {haiku: [pytest.approx(1000)]}


def _stats_with_turn_durations() -> UsageStats:
    stats = _stats_with_full_report_data()
    stats.wall_durations_ms = list(SAMPLE_DURATIONS_MS)
    stats.model_durations_ms = [float(ms) for ms in SAMPLE_DURATIONS_MS]
    stats.model_durations_ms_by_model = {
        'claude-opus-5': [float(ms) for ms in SAMPLE_DURATIONS_MS],
    }
    return stats


def test_format_report_includes_turn_duration_when_present() -> None:
    report = format_report(
        _stats_with_turn_durations(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'turn duration' in report
    assert 'model time' in report
    assert 'wall clock' in report
    assert 'claude-opus-5' in report


def test_format_report_omits_turn_duration_without_turns() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'turn duration' not in report


def test_stats_as_dict_includes_turn_duration_metrics() -> None:
    data = stats_as_dict(_stats_with_turn_durations())

    model_time = data['turn_duration_ms']['model_time']
    assert model_time['turns'] == len(SAMPLE_DURATIONS_MS)
    assert model_time['p50'] == pytest.approx(EXPECTED_P50_MS)
    assert model_time['p95'] == pytest.approx(EXPECTED_P95_MS)
    assert data['turn_duration_ms']['wall_clock']['p50'] == pytest.approx(
        EXPECTED_P50_MS,
    )
    by_model = data['turn_duration_ms']['by_model']['claude-opus-5']
    assert by_model['p50'] == pytest.approx(EXPECTED_P50_MS)


def test_stats_as_dict_turn_duration_is_empty_without_turns() -> None:
    data = stats_as_dict(UsageStats())

    assert data['turn_duration_ms']['model_time']['turns'] == 0
    assert data['turn_duration_ms']['model_time']['p50'] is None
    assert data['turn_duration_ms']['by_model'] == {}


DAY = date(2026, 7, 26)
DAY_REPLIES = 3
DAY_OUTPUT_TOKENS = 100
UPDATED_DAY_REPLIES = 9
SAMPLE_COST_TOTAL = 1.23
EXPECTED_ACTIVE_DAYS = 2


def _day_stats(**overrides: object) -> UsageStats:
    stats = UsageStats(
        session_ids={'s1'},
        prompts=2,
        replies=DAY_REPLIES,
        output_tokens=DAY_OUTPUT_TOKENS,
        input_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
        thinking_blocks=1,
        subagent_runs=0,
        lines_added=4,
        lines_removed=1,
    )
    stats.model_usage['claude-opus-5'] = ModelUsage(
        output_tokens=DAY_OUTPUT_TOKENS,
        input_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
    )
    for key, value in overrides.items():
        setattr(stats, key, value)
    return stats


def _day_cost() -> CostBreakdown:
    return CostBreakdown(
        total=SAMPLE_COST_TOTAL,
        by_category={},
        by_model={'claude-opus-5': SAMPLE_COST_TOTAL},
        unpriced_models=set(),
        expired_models=set(),
        pricing_as_of=date(2026, 1, 1),
        pricing_stale=False,
    )


def test_ensure_schema_creates_tables() -> None:
    conn = sqlite3.connect(':memory:')

    ensure_schema(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }
    assert {
        'daily_totals',
        'daily_model_usage',
        'daily_repo_usage',
    } <= tables


def test_record_day_writes_totals_row() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    written = record_day(conn, DAY, _day_stats(), cost=None)

    row = conn.execute(
        'SELECT sessions, replies, output_tokens FROM daily_totals'
        ' WHERE day = ?',
        (DAY.isoformat(),),
    ).fetchone()
    assert written is True
    assert row == (1, DAY_REPLIES, DAY_OUTPUT_TOKENS)


def test_record_day_writes_per_model_row() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_day(conn, DAY, _day_stats(), cost=None)

    row = conn.execute(
        'SELECT output_tokens FROM daily_model_usage'
        ' WHERE day = ? AND model = ?',
        (DAY.isoformat(), 'claude-opus-5'),
    ).fetchone()
    assert row == (DAY_OUTPUT_TOKENS,)


def test_record_day_skips_day_without_sessions() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    written = record_day(conn, DAY, UsageStats(), cost=None)

    assert written is False
    assert conn.execute(
        'SELECT COUNT(*) FROM daily_totals',
    ).fetchone() == (0,)


def test_record_day_upserts_replacing_previous_totals() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)
    record_day(conn, DAY, _day_stats(), cost=None)

    record_day(conn, DAY, _day_stats(replies=UPDATED_DAY_REPLIES), cost=None)

    row = conn.execute(
        'SELECT COUNT(*), MAX(replies) FROM daily_totals WHERE day = ?',
        (DAY.isoformat(),),
    ).fetchone()
    assert row == (1, UPDATED_DAY_REPLIES)


def test_record_day_removes_stale_model_rows_on_replace() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)
    first = _day_stats()
    first.model_usage['claude-haiku-4-5-20251001'] = ModelUsage(
        output_tokens=3,
    )
    record_day(conn, DAY, first, cost=None)

    record_day(conn, DAY, _day_stats(), cost=None)

    models = {
        row[0]
        for row in conn.execute(
            'SELECT model FROM daily_model_usage WHERE day = ?',
            (DAY.isoformat(),),
        )
    }
    assert models == {'claude-opus-5'}


def test_record_day_stores_cost_when_given() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_day(conn, DAY, _day_stats(), _day_cost())

    total_row = conn.execute(
        'SELECT cost_total FROM daily_totals WHERE day = ?',
        (DAY.isoformat(),),
    ).fetchone()
    model_row = conn.execute(
        'SELECT cost FROM daily_model_usage WHERE day = ? AND model = ?',
        (DAY.isoformat(), 'claude-opus-5'),
    ).fetchone()
    assert total_row[0] == pytest.approx(SAMPLE_COST_TOTAL)
    assert model_row[0] == pytest.approx(SAMPLE_COST_TOTAL)


def test_record_day_leaves_cost_null_without_pricing() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_day(conn, DAY, _day_stats(), cost=None)

    row = conn.execute(
        'SELECT cost_total FROM daily_totals WHERE day = ?',
        (DAY.isoformat(),),
    ).fetchone()
    assert row == (None,)


def test_iter_days_yields_inclusive_range() -> None:
    days = list(iter_days(date(2026, 7, 24), date(2026, 7, 26)))

    assert days == [
        date(2026, 7, 24),
        date(2026, 7, 25),
        date(2026, 7, 26),
    ]


def test_iter_days_yields_single_day_when_since_equals_until() -> None:
    days = list(iter_days(DAY, DAY))

    assert days == [DAY]


def test_record_range_records_each_active_day_and_skips_empty(
    tmp_path: Path,
) -> None:
    _write_log(
        tmp_path,
        [
            _assistant(timestamp='2026-07-25T12:00:00.000Z'),
            _assistant(timestamp='2026-07-27T12:00:00.000Z'),
        ],
    )
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    written = record_range(
        conn,
        [tmp_path],
        date(2026, 7, 25),
        date(2026, 7, 27),
        pricing=None,
    )

    recorded_days = {
        row[0] for row in conn.execute('SELECT day FROM daily_totals')
    }
    assert written == EXPECTED_ACTIVE_DAYS
    assert recorded_days == {'2026-07-25', '2026-07-27'}


def _make_repo(root: Path) -> Path:
    (root / '.git').mkdir(parents=True)
    return root


def _make_linked_worktree(repo: Path, worktree: Path, name: str) -> Path:
    (repo / '.git' / 'worktrees' / name).mkdir(parents=True)
    worktree.mkdir(parents=True)
    (worktree / '.git').write_text(
        f'gitdir: {repo / ".git" / "worktrees" / name}\n',
    )
    return worktree


def test_peek_cwd_returns_the_first_recorded_launch_directory(
    tmp_path: Path,
) -> None:
    path = _write_log(
        tmp_path,
        [
            {'type': 'system', 'subtype': 'other'},
            _prompt(cwd='/home/danny/projects/dotfiles'),
            _assistant(cwd='/home/danny/projects/dotfiles/scripts'),
        ],
    )

    assert peek_cwd(path) == '/home/danny/projects/dotfiles'


def test_peek_cwd_is_none_when_no_record_names_one(tmp_path: Path) -> None:
    path = _write_log(tmp_path, [_prompt(), _assistant()])

    assert peek_cwd(path) is None


def test_git_root_on_disk_finds_the_nearest_repo_ancestor(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path / 'repo')
    nested = repo / 'src' / 'deep'
    nested.mkdir(parents=True)

    assert git_root_on_disk(nested) == repo


def test_git_root_on_disk_maps_a_linked_worktree_to_its_main_repo(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path / 'repo')
    worktree = _make_linked_worktree(repo, tmp_path / 'wt', 'feature')

    assert git_root_on_disk(worktree) == repo


def test_git_root_on_disk_ignores_ancestors_of_a_vanished_path(
    tmp_path: Path,
) -> None:
    """A deleted cwd's surviving ancestors say nothing about the session."""
    repo = _make_repo(tmp_path / 'repo')

    assert git_root_on_disk(repo / 'gone' / 'deeper') is None


@pytest.mark.parametrize(
    ('cwd', 'expected'),
    [
        ('/p/dotfiles-worktrees/gtd-wt', '/p/dotfiles'),
        ('/p/dotfiles-worktrees/gtd-wt/gtd', '/p/dotfiles'),
        ('/p/dotfiles', None),
        ('/p/-worktrees/wt', None),
    ],
)
def test_worktree_sibling_root_follows_the_gwt_layout(
    cwd: str,
    expected: str | None,
) -> None:
    """`gwt` puts worktrees in a `<repo>-worktrees/` sibling directory."""
    result = worktree_sibling_root(Path(cwd))

    assert result == (Path(expected) if expected else None)


def test_resolve_repo_roots_prefers_an_on_disk_git_root(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path / 'repo')
    nested = repo / 'scripts'
    nested.mkdir()

    resolved = resolve_repo_roots([str(nested)])

    assert resolved == {str(nested): repo}


def test_resolve_repo_roots_rolls_a_vanished_worktree_into_its_repo() -> None:
    cwd = '/p/dotfiles-worktrees/gtd-wt'

    resolved = resolve_repo_roots([cwd])

    assert resolved == {cwd: Path('/p/dotfiles')}


def test_resolve_repo_roots_rolls_a_vanished_subdir_under_a_known_root(
    tmp_path: Path,
) -> None:
    """Half of the historical cwds are gone, so containment is the fallback."""
    repo = _make_repo(tmp_path / 'repo')
    vanished = repo / 'project_manager'

    resolved = resolve_repo_roots([str(repo), str(vanished)])

    assert resolved[str(vanished)] == repo


def test_resolve_repo_roots_keeps_an_unattributable_path_as_its_own_root(
    tmp_path: Path,
) -> None:
    stray = tmp_path / 'nowhere' / 'deep'

    resolved = resolve_repo_roots([str(stray)])

    assert resolved == {str(stray): stray}


def test_label_repo_roots_uses_basenames_when_unambiguous() -> None:
    labels = label_repo_roots([Path('/p/dotfiles'), Path('/p/gtd')])

    assert labels == {
        Path('/p/dotfiles'): 'dotfiles',
        Path('/p/gtd'): 'gtd',
    }


def test_label_repo_roots_falls_back_to_full_paths_on_a_name_clash() -> None:
    labels = label_repo_roots([Path('/a/gtd'), Path('/b/gtd')])

    assert labels == {Path('/a/gtd'): '/a/gtd', Path('/b/gtd'): '/b/gtd'}


def test_merge_stats_matches_collecting_the_same_logs_at_once(
    tmp_path: Path,
) -> None:
    """Per-repo totals are merged into the headline, so they must agree."""
    _write_log(
        tmp_path,
        [_prompt(), _assistant(), _turn_duration(1000)],
        name='one',
    )
    _write_log(
        tmp_path,
        [
            _prompt(sessionId='s2'),
            _assistant(sessionId='s2', message={'model': 'claude-haiku-4-5'}),
        ],
        name='two',
    )
    logs = sorted(tmp_path.glob('*.jsonl'))

    merged = merge_stats(
        [collect_stats([log]) for log in logs],
    )
    at_once = collect_stats([tmp_path])

    assert stats_as_dict(merged) == stats_as_dict(at_once)


def test_merge_stats_of_nothing_is_an_empty_snapshot() -> None:
    merged = merge_stats([])

    assert merged.sessions == 0
    assert merged.first_seen is None


def test_collect_stats_by_repo_splits_logs_by_their_launch_directory(
    tmp_path: Path,
) -> None:
    logs = tmp_path / 'logs'
    logs.mkdir()
    dotfiles = _make_repo(tmp_path / 'dotfiles')
    gtd = _make_repo(tmp_path / 'gtd')
    _write_log(logs, [_prompt(cwd=str(dotfiles)), _assistant()], name='one')
    _write_log(logs, [_prompt(cwd=str(gtd))], name='two')

    by_repo = collect_stats_by_repo([logs])

    assert set(by_repo) == {'dotfiles', 'gtd'}
    assert by_repo['dotfiles'].replies == 1
    assert by_repo['gtd'].prompts == 1


def test_collect_stats_by_repo_buckets_logs_without_a_cwd(
    tmp_path: Path,
) -> None:
    _write_log(tmp_path, [_prompt(), _assistant()])

    by_repo = collect_stats_by_repo([tmp_path])

    assert set(by_repo) == {UNKNOWN_REPO}


GTD_DAY_OUTPUT_TOKENS = 40
EXPECTED_REPO_ROWS = 2


def test_record_repo_day_writes_one_row_per_active_repo() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_repo_day(
        conn,
        DAY,
        {
            'dotfiles': _day_stats(),
            'gtd': _day_stats(output_tokens=GTD_DAY_OUTPUT_TOKENS),
        },
        pricing=None,
    )

    rows = dict(
        conn.execute('SELECT repo, output_tokens FROM daily_repo_usage'),
    )
    assert rows == {
        'dotfiles': DAY_OUTPUT_TOKENS,
        'gtd': GTD_DAY_OUTPUT_TOKENS,
    }


def test_record_repo_day_skips_repos_idle_that_day() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_repo_day(
        conn,
        DAY,
        {'dotfiles': _day_stats(), 'gtd': UsageStats()},
        pricing=None,
    )

    repos = {
        row[0] for row in conn.execute('SELECT repo FROM daily_repo_usage')
    }
    assert repos == {'dotfiles'}


def test_record_repo_day_removes_stale_repo_rows_on_replace() -> None:
    """A repo dropping out of a day must not leave yesterday's row behind."""
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)
    record_repo_day(conn, DAY, {'gone': _day_stats()}, pricing=None)

    record_repo_day(conn, DAY, {'dotfiles': _day_stats()}, pricing=None)

    repos = {
        row[0] for row in conn.execute('SELECT repo FROM daily_repo_usage')
    }
    assert repos == {'dotfiles'}


def test_record_repo_day_prices_each_repo_separately(tmp_path: Path) -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)
    pricing = load_pricing(_write_pricing(tmp_path))

    record_repo_day(
        conn,
        DAY,
        {
            'dotfiles': _day_stats(),
            'gtd': _day_stats(model_usage={}),
        },
        pricing=pricing,
    )

    costs = dict(conn.execute('SELECT repo, cost FROM daily_repo_usage'))
    assert costs['dotfiles'] > 0
    assert costs['gtd'] == 0


def test_record_repo_day_leaves_cost_null_without_pricing() -> None:
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_repo_day(conn, DAY, {'dotfiles': _day_stats()}, pricing=None)

    costs = [
        row[0] for row in conn.execute('SELECT cost FROM daily_repo_usage')
    ]
    assert costs == [None]


def test_record_range_attributes_each_day_to_its_repo(tmp_path: Path) -> None:
    logs = tmp_path / 'logs'
    logs.mkdir()
    dotfiles = _make_repo(tmp_path / 'dotfiles')
    gtd = _make_repo(tmp_path / 'gtd')
    _write_log(logs, [_prompt(cwd=str(dotfiles)), _assistant()], name='one')
    _write_log(logs, [_prompt(cwd=str(gtd)), _assistant()], name='two')
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_range(conn, [logs], DAY, DAY, pricing=None)

    rows = dict(
        conn.execute('SELECT repo, output_tokens FROM daily_repo_usage'),
    )
    assert rows == {
        'dotfiles': REPLY_OUTPUT_TOKENS,
        'gtd': REPLY_OUTPUT_TOKENS,
    }


def test_record_range_repo_rows_sum_to_the_daily_total(tmp_path: Path) -> None:
    logs = tmp_path / 'logs'
    logs.mkdir()
    dotfiles = _make_repo(tmp_path / 'dotfiles')
    gtd = _make_repo(tmp_path / 'gtd')
    _write_log(logs, [_prompt(cwd=str(dotfiles)), _assistant()], name='one')
    _write_log(logs, [_prompt(cwd=str(gtd)), _assistant()], name='two')
    conn = sqlite3.connect(':memory:')
    ensure_schema(conn)

    record_range(conn, [logs], DAY, DAY, pricing=None)

    repo_total = conn.execute(
        'SELECT SUM(output_tokens) FROM daily_repo_usage WHERE day = ?',
        (DAY.isoformat(),),
    ).fetchone()[0]
    day_total = conn.execute(
        'SELECT output_tokens FROM daily_totals WHERE day = ?',
        (DAY.isoformat(),),
    ).fetchone()[0]
    assert repo_total == day_total


BAR_TEST_WIDTH = 10
HALF_BAR = 5
SPARK_LOWEST = '▁'
SPARK_HIGHEST = '█'
BOX_TEST_WIDTH = 60
EXPECTED_BOX_LINES = 3
GAP_DAY_SERIES = [10, 0, 5]
BUCKET_MAX_POINTS = 2


@pytest.mark.parametrize(
    ('share', 'expected'),
    [
        (0.0, '░' * BAR_TEST_WIDTH),
        (1.0, '█' * BAR_TEST_WIDTH),
        (0.5, '█' * HALF_BAR + '░' * HALF_BAR),
        (-1.0, '░' * BAR_TEST_WIDTH),
        (2.0, '█' * BAR_TEST_WIDTH),
    ],
)
def test_bar_renders_a_clamped_proportional_meter(
    share: float,
    expected: str,
) -> None:
    assert bar(share, BAR_TEST_WIDTH) == expected


def test_sparkline_is_empty_without_values() -> None:
    assert sparkline([]) == ''


def test_sparkline_flattens_an_all_zero_series() -> None:
    """A peak of zero must not divide by zero."""
    assert sparkline([0, 0, 0]) == SPARK_LOWEST * 3


def test_sparkline_scales_the_peak_to_the_tallest_glyph() -> None:
    spark = sparkline([1, 50, 100])

    assert len(spark) == len(GAP_DAY_SERIES)
    assert spark[-1] == SPARK_HIGHEST
    assert spark[0] == SPARK_LOWEST


def test_daily_series_zero_fills_days_with_no_activity() -> None:
    by_day = {date(2026, 7, 1): 10, date(2026, 7, 3): 5}

    assert daily_series(by_day) == GAP_DAY_SERIES


def test_daily_series_is_empty_without_any_days() -> None:
    assert daily_series({}) == []


def test_bucket_series_keeps_a_short_series_intact() -> None:
    assert bucket_series(GAP_DAY_SERIES, MAX_SPARK_POINTS) == GAP_DAY_SERIES


def test_bucket_series_sums_adjacent_days_to_fit_the_budget() -> None:
    buckets = bucket_series([1, 2, 3, 4], BUCKET_MAX_POINTS)

    assert buckets == [3, 7]
    assert sum(buckets) == sum([1, 2, 3, 4])


def test_box_lines_are_the_same_width() -> None:
    lines = box_lines('Title', 'body text', BOX_TEST_WIDTH)

    assert len(lines) == EXPECTED_BOX_LINES
    assert len({len(line) for line in lines}) == 1


def test_box_lines_never_clip_a_body_wider_than_the_terminal() -> None:
    body = 'x' * 90

    lines = box_lines('T', body, NARROW_WIDTH)

    assert body in lines[1]


@pytest.mark.parametrize(
    ('text', 'expected'),
    [('short', 'short'), ('exactly-ten', 'exactly-…')],
)
def test_truncate_ellipsizes_only_when_over_width(
    text: str,
    expected: str,
) -> None:
    assert truncate(text, len('exactly-ten') - 2) == expected


def test_build_repo_reports_drops_repos_with_no_sessions() -> None:
    reports = build_repo_reports(
        {'dotfiles': _day_stats(), 'idle': UsageStats()},
        pricing=None,
    )

    assert [report.label for report in reports] == ['dotfiles']


def test_build_repo_reports_prices_each_repo(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path))

    reports = build_repo_reports({'dotfiles': _day_stats()}, pricing)

    assert reports[0].cost is not None
    assert reports[0].cost.total > 0


def _repo_reports() -> list[RepoReport]:
    return [
        RepoReport(label='dotfiles', stats=_day_stats(), cost=None),
        RepoReport(
            label='gtd',
            stats=_day_stats(output_tokens=GTD_DAY_OUTPUT_TOKENS),
            cost=None,
        ),
    ]


def test_format_report_lists_each_repo_when_given() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
        repos=_repo_reports(),
    )

    assert 'by repo' in report
    assert 'dotfiles' in report
    assert 'gtd' in report


def test_format_report_omits_the_repo_section_without_repos() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'by repo' not in report


def test_format_report_hides_metric_footnotes_by_default() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'hit ratio = cache_read' not in report
    assert '--explain' in report


def test_format_report_shows_metric_footnotes_when_explaining() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
        explain=True,
    )

    assert 'hit ratio = cache_read' in report


def test_format_report_draws_a_sparkline_over_multiple_days() -> None:
    stats = _stats_with_full_report_data()
    stats.output_tokens_by_day = {
        date(2026, 7, 1): 10,
        date(2026, 7, 3): 5,
    }

    report = format_report(stats, width=WIDE_WIDTH, color=False)

    assert 'daily output tokens' in report
    assert SPARK_HIGHEST in report


def test_format_report_omits_the_sparkline_for_a_single_day() -> None:
    stats = _stats_with_full_report_data()
    stats.output_tokens_by_day = {date(2026, 7, 1): 10}

    report = format_report(stats, width=WIDE_WIDTH, color=False)

    assert 'daily output tokens' not in report


def test_format_report_leaves_no_trailing_whitespace() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
        repos=_repo_reports(),
    )

    assert not [line for line in report.split('\n') if line != line.rstrip()]


def test_format_report_scales_ranked_bars_to_the_leader() -> None:
    """Share-of-total bars would flatten every row under the top one."""
    stats = UsageStats(
        session_ids={'s1'},
        tools=Counter({'Bash': 100, 'Read': 50}),
        first_seen=datetime.fromisoformat(STAMP.replace('Z', '+00:00')),
        last_seen=datetime.fromisoformat(STAMP.replace('Z', '+00:00')),
    )

    report = format_report(stats, width=WIDE_WIDTH, color=False)
    read_row = next(line for line in report.split('\n') if 'Read' in line)

    assert '█' * BAR_WIDTH in report
    assert read_row.count('█') == BAR_WIDTH // 2


def test_stats_as_dict_includes_per_repo_slices() -> None:
    data = stats_as_dict(
        _stats_with_full_report_data(),
        None,
        _repo_reports(),
    )

    assert [entry['repo'] for entry in data['repos']] == ['dotfiles', 'gtd']
    assert data['repos'][0]['tokens']['output'] == DAY_OUTPUT_TOKENS


def test_stats_as_dict_has_an_empty_repo_list_without_repos() -> None:
    data = stats_as_dict(_stats_with_full_report_data())

    assert data['repos'] == []


# ── cartoon integration ──────────────────────────────────────────────────


CARTOON_STATS_OUTPUT = (
    'calls: 2\n'
    'tokens_saved: 166\n'
    'by_adapter:\n'
    '  pytest:\n'
    '    calls: 1\n'
    '    saved: 166\n'
    '  passthrough:\n'
    '    calls: 1\n'
    '    saved: 0\n'
)
CARTOON_STATS_PARSED = {
    'calls': 2,
    'tokens_saved': 166,
    'by_adapter': {
        'pytest': {'calls': 1, 'saved': 166},
        'passthrough': {'calls': 1, 'saved': 0},
    },
}
CARTOON_SINCE = '7d'


def test_parse_cartoon_stats_reads_totals_and_per_adapter_breakdown() -> None:
    assert parse_cartoon_stats(CARTOON_STATS_OUTPUT) == CARTOON_STATS_PARSED


def test_parse_cartoon_stats_handles_empty_by_adapter() -> None:
    output = 'calls: 0\ntokens_saved: 0\nby_adapter: {}\n'

    assert parse_cartoon_stats(output) == {
        'calls': 0,
        'tokens_saved': 0,
        'by_adapter': {},
    }


def test_run_cartoon_stats_returns_none_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _name: None)

    assert run_cartoon_stats(CARTOON_SINCE) is None


def test_run_cartoon_stats_returns_none_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _name: '/usr/bin/cartoon')
    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *args, **_kwargs: subprocess.CompletedProcess(
            args,
            1,
            stdout='',
            stderr='boom',
        ),
    )

    assert run_cartoon_stats(CARTOON_SINCE) is None


@pytest.mark.parametrize('error', [OSError, subprocess.TimeoutExpired])
def test_run_cartoon_stats_returns_none_when_subprocess_fails(
    monkeypatch: pytest.MonkeyPatch,
    error: type[Exception],
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _name: '/usr/bin/cartoon')

    def raise_error(*_args: object, **_kwargs: object) -> None:
        if error is subprocess.TimeoutExpired:
            raise error(cmd='cartoon', timeout=5)
        message = 'boom'
        raise error(message)

    monkeypatch.setattr(subprocess, 'run', raise_error)

    assert run_cartoon_stats(CARTOON_SINCE) is None


def test_run_cartoon_stats_returns_stdout_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _name: '/usr/bin/cartoon')
    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *args, **_kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout=CARTOON_STATS_OUTPUT,
            stderr='',
        ),
    )

    assert run_cartoon_stats(CARTOON_SINCE) == CARTOON_STATS_OUTPUT


def test_cartoon_lines_is_empty_without_any_calls() -> None:
    empty = {'calls': 0, 'tokens_saved': 0, 'by_adapter': {}}

    assert cartoon_lines(empty, CARTOON_SINCE) == []


def test_cartoon_lines_is_empty_when_stats_unavailable() -> None:
    assert cartoon_lines(None, CARTOON_SINCE) == []


def test_cartoon_lines_lists_calls_and_savings_per_adapter() -> None:
    lines = cartoon_lines(CARTOON_STATS_PARSED, CARTOON_SINCE)
    text = '\n'.join(lines)

    assert CARTOON_SINCE in lines[0]
    assert 'pytest' in text
    assert 'passthrough' in text
    assert '166' in text


def test_format_report_includes_cartoon_section_when_given() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
        cartoon=CARTOON_STATS_PARSED,
        cartoon_since=CARTOON_SINCE,
    )

    assert 'cartoon' in report
    assert 'pytest' in report


def test_format_report_omits_cartoon_section_without_stats() -> None:
    report = format_report(
        _stats_with_full_report_data(),
        width=WIDE_WIDTH,
        color=False,
    )

    assert 'pytest' not in report


def test_stats_as_dict_includes_cartoon_stats_when_given() -> None:
    data = stats_as_dict(
        _stats_with_full_report_data(),
        cartoon=CARTOON_STATS_PARSED,
    )

    assert data['cartoon'] == CARTOON_STATS_PARSED


def test_stats_as_dict_has_no_cartoon_stats_without_them() -> None:
    data = stats_as_dict(_stats_with_full_report_data())

    assert data['cartoon'] is None
