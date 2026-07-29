#!/usr/bin/env python3
"""Aggregate Claude Code session logs into usage statistics.

Reads the JSONL transcripts under ~/.claude/projects and reports totals on
demand -- every run re-reads the logs, so the numbers only cover transcripts
still present on this machine. Each run also upserts today's rollup into the
sqlite history db (see --db-path), so daily totals survive log rotation;
--record backfills a --since/--until range instead of printing a report.

Work is attributed to a repo by the launch directory recorded in each
transcript, so sessions spread across worktrees and subdirectories roll up
into the repo they belong to. See resolve_repo_roots for the ladder.
"""

import argparse
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from collections.abc import Iterable, Iterator

DEFAULT_LOG_ROOT = Path.home() / '.claude' / 'projects'
DEFAULT_DB_PATH = Path.home() / '.claude' / 'ccstats.db'
SUBAGENT_DIR = 'subagents'
TURN_DURATION_SUBTYPE = 'turn_duration'
P50 = 0.5
P95 = 0.95
MILLISECONDS_PER_SECOND = 1000
FALLBACK_TERMINAL_SIZE = (80, 24)
COLUMN_GAP = 4
DEFAULT_PRICING_PATH = Path(__file__).resolve().parent / 'model_pricing.json'
PRICING_STALE_AFTER_DAYS = 60
TOKENS_PER_MILLION = 1_000_000
CARTOON_BINARY = 'cartoon'
CARTOON_STATS_TIMEOUT_S = 5
DEFAULT_CARTOON_SINCE = '7d'

RESET = '\x1b[0m'
BOLD = '\x1b[1m'
DIM = '\x1b[2m'
CYAN = '\x1b[36m'

SPARK_CHARS = '▁▂▃▄▅▆▇█'
BAR_FILLED = '█'
BAR_EMPTY = '░'
MAX_SPARK_POINTS = 60
BAR_WIDTH = 12
REPO_BAR_WIDTH = 14
MIN_BOX_WIDTH = 46
MAX_BOX_WIDTH = 74
TOP_TOOLS_SHOWN = 10
MIN_SPARK_DAYS = 2


@dataclass
class ModelUsage:
    """Per-model token totals -- needed because prices differ by model."""

    output_tokens: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class ModelPrice:
    """Dollars per million tokens for one model, from model_pricing.json."""

    input_per_million: float
    output_per_million: float
    expires: date | None = None
    note: str | None = None


@dataclass(frozen=True)
class PricingTable:
    as_of: date
    cache_write_multiplier: float
    cache_read_multiplier: float
    models: dict[str, ModelPrice]


@dataclass
class CostBreakdown:
    """Estimated spend for a UsageStats snapshot, priced via a PricingTable."""

    total: float
    by_category: dict[str, float]
    by_model: dict[str, float]
    unpriced_models: set[str]
    expired_models: set[str]
    pricing_as_of: date
    pricing_stale: bool


@dataclass(frozen=True)
class RepoReport:
    """One repo's slice of a run, already priced."""

    label: str
    stats: 'UsageStats'
    cost: CostBreakdown | None


@dataclass
class UsageStats:
    """Totals across every transcript that matched the requested window."""

    session_ids: set[str] = field(default_factory=set)
    prompts: int = 0
    replies: int = 0
    output_tokens: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    thinking_blocks: int = 0
    subagent_runs: int = 0
    longest_prompt_chars: int = 0
    models: Counter = field(default_factory=Counter)
    tools: Counter = field(default_factory=Counter)
    model_usage: dict[str, ModelUsage] = field(default_factory=dict)
    output_tokens_by_day: dict[date, int] = field(default_factory=dict)
    wall_durations_ms: list[int] = field(default_factory=list)
    model_durations_ms: list[float] = field(default_factory=list)
    model_durations_ms_by_model: dict[str, list[float]] = field(
        default_factory=dict,
    )
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @property
    def sessions(self) -> int:
        return len(self.session_ids)

    @property
    def cache_hit_ratio(self) -> float | None:
        """Share of input tokens served from cache rather than sent fresh."""
        denominator = self.cache_read_tokens + self.input_tokens
        if denominator == 0:
            return None
        return self.cache_read_tokens / denominator

    @property
    def cache_efficiency(self) -> float | None:
        """Cache reads per cache write -- how many times a write paid off."""
        if self.cache_write_tokens == 0:
            return None
        return self.cache_read_tokens / self.cache_write_tokens


@dataclass
class TurnTracker:
    """Per-turn timing, rebuilt from the gaps between records.

    A turn's `turn_duration` record names no model, so the turn is credited
    to whichever model produced the most replies inside it -- a turn that
    delegates to a subagent still belongs to the model driving it.

    Model time counts only the gaps that end at a reply. A gap ending at a
    tool result is where tool execution and any wait for the human's approval
    live, so excluding those yields generation time alone rather than trying
    to subtract an approval wait that is never logged.
    """

    models: Counter = field(default_factory=Counter)
    previous_stamp: datetime | None = None
    model_ms: float = 0.0

    def begin_turn(self, stamp: datetime | None) -> None:
        self.models.clear()
        self.model_ms = 0.0
        self.previous_stamp = stamp

    def note_record(
        self,
        stamp: datetime | None,
        *,
        from_model: bool,
    ) -> None:
        if stamp is None:
            return
        if from_model and self.previous_stamp is not None:
            gap = (stamp - self.previous_stamp).total_seconds()
            self.model_ms += max(gap, 0.0) * MILLISECONDS_PER_SECOND
        self.previous_stamp = stamp

    def note_reply(self, model: str | None, stamp: datetime | None) -> None:
        if model:
            self.models[model] += 1
        self.note_record(stamp, from_model=True)

    def close_turn(self) -> tuple[str | None, float]:
        dominant = self.models.most_common(1)
        model_ms = self.model_ms
        self.begin_turn(None)
        return (dominant[0][0] if dominant else None), model_ms


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile, or None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(fraction * len(ordered))
    return float(ordered[max(rank - 1, 0)])


def find_logs(roots: list[Path]) -> list[Path]:
    """Every transcript under the given roots, newest last."""
    logs: list[Path] = []
    for root in roots:
        if root.is_file():
            logs.append(root)
        elif root.is_dir():
            logs.extend(sorted(root.rglob('*.jsonl')))
    return logs


def iter_records(path: Path) -> Iterator[dict]:
    """Yield parsed records, skipping lines left truncated by a crash."""
    with path.open(encoding='utf-8', errors='replace') as handle:
        for raw in handle:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return None


def is_prompt(record: dict) -> bool:
    """True for text the human typed, not a tool result or injected note."""
    if record.get('type') != 'user':
        return False
    if record.get('toolUseResult') is not None or record.get('isMeta'):
        return False

    content = record.get('message', {}).get('content')
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            block.get('type') == 'text'
            for block in content
            if isinstance(block, dict)
        )
    return False


def prompt_text(record: dict) -> str:
    content = record.get('message', {}).get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(
            block.get('text', '')
            for block in content
            if isinstance(block, dict)
        )
    return ''


def count_patch_lines(patch: object) -> tuple[int, int]:
    """Added and removed line counts from an Edit/Write structuredPatch."""
    added = removed = 0
    if not isinstance(patch, list):
        return added, removed

    for hunk in patch:
        if not isinstance(hunk, dict):
            continue
        for line in hunk.get('lines', []):
            if not isinstance(line, str):
                continue
            if line.startswith('+'):
                added += 1
            elif line.startswith('-'):
                removed += 1
    return added, removed


def in_window(
    stamp: datetime | None,
    since: date | None,
    until: date | None,
) -> bool:
    if stamp is None:
        return since is None and until is None
    day = stamp.date()
    if since and day < since:
        return False
    return not (until and day > until)


def tally_assistant(stats: UsageStats, record: dict, day: date | None) -> None:
    message = record.get('message', {})
    stats.replies += 1

    model = message.get('model')

    usage = message.get('usage') or {}
    output = usage.get('output_tokens', 0) or 0
    input_ = usage.get('input_tokens', 0) or 0
    cache_read = usage.get('cache_read_input_tokens', 0) or 0
    cache_write = usage.get('cache_creation_input_tokens', 0) or 0

    stats.output_tokens += output
    stats.input_tokens += input_
    stats.cache_read_tokens += cache_read
    stats.cache_write_tokens += cache_write

    if model:
        stats.models[model] += 1
        model_usage = stats.model_usage.setdefault(model, ModelUsage())
        model_usage.output_tokens += output
        model_usage.input_tokens += input_
        model_usage.cache_read_tokens += cache_read
        model_usage.cache_write_tokens += cache_write

    if day is not None and output:
        stats.output_tokens_by_day[day] = (
            stats.output_tokens_by_day.get(day, 0) + output
        )

    for block in message.get('content', []):
        if not isinstance(block, dict):
            continue
        kind = block.get('type')
        if kind == 'thinking':
            stats.thinking_blocks += 1
        elif kind == 'tool_use':
            stats.tools[block.get('name', 'unknown')] += 1


def track_span(stats: UsageStats, stamp: datetime) -> None:
    if stats.first_seen is None or stamp < stats.first_seen:
        stats.first_seen = stamp
    if stats.last_seen is None or stamp > stats.last_seen:
        stats.last_seen = stamp


def is_turn_boundary(record: dict) -> bool:
    return (
        record.get('type') == 'system'
        and record.get('subtype') == TURN_DURATION_SUBTYPE
    )


def tally_turn_duration(
    stats: UsageStats,
    record: dict,
    turn: TurnTracker,
) -> None:
    duration = record.get('durationMs')
    model, model_ms = turn.close_turn()

    if isinstance(duration, int):
        stats.wall_durations_ms.append(duration)
    if model_ms <= 0:
        return

    stats.model_durations_ms.append(model_ms)
    if model:
        stats.model_durations_ms_by_model.setdefault(model, []).append(
            model_ms,
        )


def tally_record(
    stats: UsageStats,
    record: dict,
    stamp: datetime | None,
    turn: TurnTracker,
) -> None:
    day = stamp.date() if stamp else None

    if record.get('type') == 'assistant':
        tally_assistant(stats, record, day)
        turn.note_reply(record.get('message', {}).get('model'), stamp)
    elif is_turn_boundary(record):
        tally_turn_duration(stats, record, turn)
    elif is_prompt(record):
        stats.prompts += 1
        stats.longest_prompt_chars = max(
            stats.longest_prompt_chars,
            len(prompt_text(record)),
        )
        turn.begin_turn(stamp)
    elif record.get('type') == 'user':
        turn.note_record(stamp, from_model=False)

    result = record.get('toolUseResult')
    if isinstance(result, dict):
        added, removed = count_patch_lines(result.get('structuredPatch'))
        stats.lines_added += added
        stats.lines_removed += removed


def collect_stats_from_logs(
    logs: Iterable[Path],
    since: date | None = None,
    until: date | None = None,
) -> UsageStats:
    """Total up the interesting bits of the given transcripts."""
    stats = UsageStats()

    for path in logs:
        is_subagent = path.parent.name == SUBAGENT_DIR
        counted_subagent = False
        turn = TurnTracker()

        for record in iter_records(path):
            stamp = parse_timestamp(record.get('timestamp'))
            if not in_window(stamp, since, until):
                continue

            if stamp:
                track_span(stats, stamp)

            session = record.get('sessionId') or record.get('session_id')
            if session:
                stats.session_ids.add(session)

            if is_subagent and not counted_subagent:
                stats.subagent_runs += 1
                counted_subagent = True

            tally_record(stats, record, stamp, turn)

    return stats


def collect_stats(
    roots: list[Path],
    since: date | None = None,
    until: date | None = None,
) -> UsageStats:
    """Walk every transcript under roots and total up the interesting bits."""
    return collect_stats_from_logs(find_logs(roots), since, until)


UNKNOWN_REPO = '(unknown)'
WORKTREES_SUFFIX = '-worktrees'
GITDIR_PREFIX = 'gitdir:'


def peek_cwd(path: Path) -> str | None:
    """The directory Claude launched in, per the first record naming one."""
    for record in iter_records(path):
        cwd = record.get('cwd')
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def worktree_main_root(git_file: Path) -> Path | None:
    """Follow a linked worktree's `.git` pointer file to its main repo."""
    try:
        text = git_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None

    for line in text.splitlines():
        if not line.startswith(GITDIR_PREFIX):
            continue
        gitdir = Path(line[len(GITDIR_PREFIX) :].strip())
        if not gitdir.is_absolute():
            gitdir = git_file.parent / gitdir
        for parent in gitdir.parents:
            if parent.name == '.git':
                return parent.parent
    return None


def git_root_on_disk(start: Path) -> Path | None:
    """Nearest repo ancestor of `start`, with worktrees mapped to their repo.

    Returns None for a path that no longer exists: its surviving ancestors
    say nothing about which repo the session was actually working in.
    """
    if not start.is_dir():
        return None

    for candidate in (start, *start.parents):
        git_path = candidate / '.git'
        if git_path.is_dir():
            return candidate
        if git_path.is_file():
            return worktree_main_root(git_path) or candidate
    return None


def worktree_sibling_root(cwd: Path) -> Path | None:
    """Repo root implied by `gwt`'s `<repo>-worktrees/<branch>` layout.

    Path-only, so it still attributes worktrees that have since been removed
    -- which most of them have.
    """
    for candidate in (cwd, *cwd.parents):
        name = candidate.name
        if name.endswith(WORKTREES_SUFFIX) and name != WORKTREES_SUFFIX:
            return candidate.parent / name[: -len(WORKTREES_SUFFIX)]
    return None


def enclosing_root(cwd: Path, roots: set[Path]) -> Path | None:
    """The deepest already-known repo root that contains `cwd`."""
    matches = [root for root in roots if root == cwd or root in cwd.parents]
    if not matches:
        return None
    return max(matches, key=lambda root: len(root.parts))


def resolve_repo_roots(cwds: Iterable[str]) -> dict[str, Path]:
    """Map each launch directory to the repo root it belongs to.

    Layered because most historical cwds have been deleted: an on-disk `.git`
    wins, then the `-worktrees/` naming convention, then containment inside a
    root some other cwd already resolved to.
    """
    distinct = sorted({cwd for cwd in cwds if cwd})
    resolved: dict[str, Path] = {}
    unresolved: list[str] = []

    for cwd in distinct:
        path = Path(cwd)
        root = git_root_on_disk(path) or worktree_sibling_root(path)
        if root is None:
            unresolved.append(cwd)
        else:
            resolved[cwd] = root

    known = set(resolved.values())
    for cwd in unresolved:
        path = Path(cwd)
        resolved[cwd] = enclosing_root(path, known) or path

    return resolved


def label_repo_roots(roots: Iterable[Path]) -> dict[Path, str]:
    """Basenames, widened to full paths only where two repos share a name."""
    distinct = set(roots)
    name_counts = Counter(root.name for root in distinct)
    return {
        root: (root.name if name_counts[root.name] == 1 else str(root))
        for root in distinct
    }


def group_logs_by_repo(logs: Iterable[Path]) -> dict[str, list[Path]]:
    """Bucket transcripts by the repo their launch directory resolves to."""
    cwd_by_log = {path: peek_cwd(path) for path in logs}
    root_by_cwd = resolve_repo_roots(cwd_by_log.values())
    labels = label_repo_roots(root_by_cwd.values())

    grouped: dict[str, list[Path]] = {}
    for path, cwd in cwd_by_log.items():
        root = root_by_cwd.get(cwd) if cwd else None
        label = UNKNOWN_REPO if root is None else labels[root]
        grouped.setdefault(label, []).append(path)
    return grouped


def merge_model_usage(merged: UsageStats, part: UsageStats) -> None:
    for model, usage in part.model_usage.items():
        target = merged.model_usage.setdefault(model, ModelUsage())
        target.output_tokens += usage.output_tokens
        target.input_tokens += usage.input_tokens
        target.cache_read_tokens += usage.cache_read_tokens
        target.cache_write_tokens += usage.cache_write_tokens


def merge_durations(merged: UsageStats, part: UsageStats) -> None:
    merged.wall_durations_ms.extend(part.wall_durations_ms)
    merged.model_durations_ms.extend(part.model_durations_ms)
    for model, durations in part.model_durations_ms_by_model.items():
        merged.model_durations_ms_by_model.setdefault(model, []).extend(
            durations,
        )


def merge_span(merged: UsageStats, part: UsageStats) -> None:
    for stamp in (part.first_seen, part.last_seen):
        if stamp is not None:
            track_span(merged, stamp)


def merge_counts(merged: UsageStats, part: UsageStats) -> None:
    merged.session_ids |= part.session_ids
    merged.prompts += part.prompts
    merged.replies += part.replies
    merged.output_tokens += part.output_tokens
    merged.input_tokens += part.input_tokens
    merged.cache_read_tokens += part.cache_read_tokens
    merged.cache_write_tokens += part.cache_write_tokens
    merged.lines_added += part.lines_added
    merged.lines_removed += part.lines_removed
    merged.thinking_blocks += part.thinking_blocks
    merged.subagent_runs += part.subagent_runs
    merged.longest_prompt_chars = max(
        merged.longest_prompt_chars,
        part.longest_prompt_chars,
    )
    merged.models.update(part.models)
    merged.tools.update(part.tools)
    for day, tokens in part.output_tokens_by_day.items():
        merged.output_tokens_by_day[day] = (
            merged.output_tokens_by_day.get(day, 0) + tokens
        )


def merge_stats(parts: Iterable[UsageStats]) -> UsageStats:
    """Combine per-repo snapshots into the headline totals."""
    merged = UsageStats()
    for part in parts:
        merge_counts(merged, part)
        merge_model_usage(merged, part)
        merge_durations(merged, part)
        merge_span(merged, part)
    return merged


def collect_grouped_stats(
    grouped: dict[str, list[Path]],
    since: date | None = None,
    until: date | None = None,
) -> dict[str, UsageStats]:
    """Per-repo snapshots for pre-grouped logs, ordered by output tokens."""
    by_repo = {
        label: collect_stats_from_logs(paths, since, until)
        for label, paths in grouped.items()
    }
    return dict(
        sorted(
            by_repo.items(),
            key=lambda item: item[1].output_tokens,
            reverse=True,
        ),
    )


def collect_stats_by_repo(
    roots: list[Path],
    since: date | None = None,
    until: date | None = None,
) -> dict[str, UsageStats]:
    """Per-repo snapshots, keyed by repo label and ordered by output tokens."""
    return collect_grouped_stats(
        group_logs_by_repo(find_logs(roots)),
        since,
        until,
    )


def load_pricing(path: Path) -> PricingTable:
    """Load scripts/model_pricing.json (or an override path)."""
    data = json.loads(path.read_text())
    models = {
        name: ModelPrice(
            input_per_million=entry['input'],
            output_per_million=entry['output'],
            expires=(
                date.fromisoformat(entry['expires'])
                if entry.get('expires')
                else None
            ),
            note=entry.get('note'),
        )
        for name, entry in data['models'].items()
    }
    return PricingTable(
        as_of=date.fromisoformat(data['as_of']),
        cache_write_multiplier=data['cache_write_multiplier'],
        cache_read_multiplier=data['cache_read_multiplier'],
        models=models,
    )


def find_model_price(model: str, pricing: PricingTable) -> ModelPrice | None:
    """Longest-prefix match, so dated model IDs (…-20251001) still resolve."""
    matches = [name for name in pricing.models if model.startswith(name)]
    if not matches:
        return None
    return pricing.models[max(matches, key=len)]


def compute_cost(
    stats: UsageStats,
    pricing: PricingTable,
    *,
    today: date | None = None,
) -> CostBreakdown:
    """Estimate spend per token category and per model.

    Cache write/read costs use the pricing table's flat multipliers rather
    than a per-request TTL, since the JSONL logs don't record which TTL a
    given cache write used.
    """
    today = today or date.today()
    by_category = {
        'output': 0.0,
        'input': 0.0,
        'cache_read': 0.0,
        'cache_write': 0.0,
    }
    by_model: dict[str, float] = {}
    unpriced_models: set[str] = set()
    expired_models: set[str] = set()

    for model, usage in stats.model_usage.items():
        price = find_model_price(model, pricing)
        if price is None:
            unpriced_models.add(model)
            continue
        if price.expires is not None and today > price.expires:
            expired_models.add(model)

        output_cost = (
            usage.output_tokens / TOKENS_PER_MILLION * price.output_per_million
        )
        input_cost = (
            usage.input_tokens / TOKENS_PER_MILLION * price.input_per_million
        )
        cache_read_cost = (
            usage.cache_read_tokens
            / TOKENS_PER_MILLION
            * price.input_per_million
            * pricing.cache_read_multiplier
        )
        cache_write_cost = (
            usage.cache_write_tokens
            / TOKENS_PER_MILLION
            * price.input_per_million
            * pricing.cache_write_multiplier
        )

        by_category['output'] += output_cost
        by_category['input'] += input_cost
        by_category['cache_read'] += cache_read_cost
        by_category['cache_write'] += cache_write_cost
        by_model[model] = (
            output_cost + input_cost + cache_read_cost + cache_write_cost
        )

    stale = (today - pricing.as_of).days > PRICING_STALE_AFTER_DAYS or bool(
        expired_models,
    )

    return CostBreakdown(
        total=sum(by_category.values()),
        by_category=by_category,
        by_model=by_model,
        unpriced_models=unpriced_models,
        expired_models=expired_models,
        pricing_as_of=pricing.as_of,
        pricing_stale=stale,
    )


DAILY_STATS_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_totals (
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

CREATE TABLE IF NOT EXISTS daily_model_usage (
    day TEXT NOT NULL,
    model TEXT NOT NULL,
    output_tokens INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    cost REAL,
    PRIMARY KEY (day, model)
);

CREATE TABLE IF NOT EXISTS daily_repo_usage (
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
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DAILY_STATS_SCHEMA)


def record_day(
    conn: sqlite3.Connection,
    day: date,
    stats: UsageStats,
    cost: CostBreakdown | None,
) -> bool:
    """Upsert one day's totals and per-model rows; False if the day is idle.

    Per-model rows are deleted and reinserted rather than replaced in place,
    so a model dropped from the day's usage doesn't leave a stale row behind.
    """
    if not stats.session_ids:
        return False

    day_key = day.isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO daily_totals (
            day, sessions, prompts, replies, thinking_blocks,
            subagent_runs, lines_added, lines_removed, output_tokens,
            input_tokens, cache_read_tokens, cache_write_tokens,
            cost_total, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day_key,
            stats.sessions,
            stats.prompts,
            stats.replies,
            stats.thinking_blocks,
            stats.subagent_runs,
            stats.lines_added,
            stats.lines_removed,
            stats.output_tokens,
            stats.input_tokens,
            stats.cache_read_tokens,
            stats.cache_write_tokens,
            cost.total if cost else None,
            datetime.now().isoformat(),
        ),
    )

    conn.execute('DELETE FROM daily_model_usage WHERE day = ?', (day_key,))
    for model, usage in stats.model_usage.items():
        model_cost = cost.by_model.get(model) if cost else None
        conn.execute(
            """
            INSERT INTO daily_model_usage (
                day, model, output_tokens, input_tokens,
                cache_read_tokens, cache_write_tokens, cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day_key,
                model,
                usage.output_tokens,
                usage.input_tokens,
                usage.cache_read_tokens,
                usage.cache_write_tokens,
                model_cost,
            ),
        )

    return True


def record_repo_day(
    conn: sqlite3.Connection,
    day: date,
    by_repo: dict[str, UsageStats],
    pricing: PricingTable | None,
) -> None:
    """Replace one day's per-repo rows, skipping repos idle that day.

    Rows are deleted and reinserted rather than upserted, so a repo that
    stops appearing on a day doesn't leave a stale row behind.
    """
    day_key = day.isoformat()
    conn.execute('DELETE FROM daily_repo_usage WHERE day = ?', (day_key,))

    for repo, stats in by_repo.items():
        if not stats.session_ids:
            continue
        cost = compute_cost(stats, pricing) if pricing else None
        conn.execute(
            """
            INSERT INTO daily_repo_usage (
                day, repo, sessions, prompts, replies, lines_added,
                lines_removed, output_tokens, input_tokens,
                cache_read_tokens, cache_write_tokens, cost
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day_key,
                repo,
                stats.sessions,
                stats.prompts,
                stats.replies,
                stats.lines_added,
                stats.lines_removed,
                stats.output_tokens,
                stats.input_tokens,
                stats.cache_read_tokens,
                stats.cache_write_tokens,
                cost.total if cost else None,
            ),
        )


def iter_days(since: date, until: date) -> Iterator[date]:
    day = since
    while day <= until:
        yield day
        day += timedelta(days=1)


def record_range(
    conn: sqlite3.Connection,
    roots: list[Path],
    since: date,
    until: date,
    pricing: PricingTable | None,
) -> int:
    """Record each day in [since, until] and return how many had activity.

    Logs are grouped by repo once up front rather than per day, so a long
    backfill doesn't re-sniff every transcript's launch directory.
    """
    grouped = group_logs_by_repo(find_logs(roots))
    written = 0
    for day in iter_days(since, until):
        by_repo = collect_grouped_stats(grouped, since=day, until=day)
        stats = merge_stats(by_repo.values())
        cost = compute_cost(stats, pricing) if pricing else None
        if record_day(conn, day, stats, cost):
            record_repo_day(conn, day, by_repo, pricing)
            written += 1
    return written


def humanize(value: int) -> str:
    scales = ((1_000_000_000, 'B'), (1_000_000, 'M'), (1_000, 'K'))
    for limit, suffix in scales:
        if value >= limit:
            return f'{value / limit:.1f}{suffix}'
    return str(value)


def supports_color() -> bool:
    """Whether the terminal we're writing to can render ANSI colors."""
    return sys.stdout.isatty() and not os.environ.get('NO_COLOR')


def colorize(text: str, *codes: str, color: bool) -> str:
    if not color:
        return text
    return f'{"".join(codes)}{text}{RESET}'


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + '…'


def daily_series(by_day: dict[date, int]) -> list[int]:
    """Output tokens per calendar day, zero-filled so gaps read as gaps."""
    if not by_day:
        return []
    span = iter_days(min(by_day), max(by_day))
    return [by_day.get(day, 0) for day in span]


def bucket_series(values: list[int], max_points: int) -> list[int]:
    """Downsample by summing adjacent days so a long span still fits."""
    if max_points <= 0 or len(values) <= max_points:
        return values
    size = math.ceil(len(values) / max_points)
    return [sum(values[at : at + size]) for at in range(0, len(values), size)]


def sparkline(values: list[int]) -> str:
    peak = max(values, default=0)
    if not values:
        return ''
    if peak <= 0:
        return SPARK_CHARS[0] * len(values)
    top = len(SPARK_CHARS) - 1
    return ''.join(SPARK_CHARS[round(value / peak * top)] for value in values)


def bar(share: float, width: int = BAR_WIDTH) -> str:
    filled = min(round(max(share, 0.0) * width), width)
    return BAR_FILLED * filled + BAR_EMPTY * (width - filled)


def box_lines(title: str, body: str, width: int) -> list[str]:
    """A titled box around one line of body text, indented like a section."""
    heading = f'─ {title} '
    inner = max(len(heading) + 1, len(body) + 2, MIN_BOX_WIDTH)
    inner = min(max(inner, width - 6), MAX_BOX_WIDTH)
    inner = max(inner, len(heading) + 1, len(body) + 2)
    return [
        f'  ╭{heading}{"─" * (inner - len(heading))}╮',
        f'  │ {body.ljust(inner - 2)} │',
        f'  ╰{"─" * inner}╯',
    ]


def merge_side_by_side(
    left: list[str],
    right: list[str],
    width: int,
) -> list[str]:
    """Lay two report blocks side by side if they both fit in width.

    Falls back to stacking them (left block, blank line, right block)
    when the terminal is too narrow for both columns.
    """
    if not left or not right:
        return left + right

    left_width = max(len(line) for line in left)
    right_width = max(len(line) for line in right)
    if left_width + COLUMN_GAP + right_width > width:
        return [*left, '', *right]

    row_count = max(len(left), len(right))
    padded_left = [line.ljust(left_width) for line in left]
    padded_left += [' ' * left_width] * (row_count - len(padded_left))
    padded_right = right + [''] * (row_count - len(right))
    gap = ' ' * COLUMN_GAP
    return [
        f'{lft}{gap}{rgt}'
        for lft, rgt in zip(padded_left, padded_right, strict=True)
    ]


def report_span(stats: UsageStats) -> str:
    if not (stats.first_seen and stats.last_seen):
        return 'no transcripts found'
    return (
        f'{stats.first_seen:%Y-%m-%d} → {stats.last_seen:%Y-%m-%d}'
        f'   ·   {len(stats.output_tokens_by_day)} active days'
    )


SPARK_LABEL = 'daily output tokens'


def sparkline_lines(stats: UsageStats, *, color: bool) -> list[str]:
    """A one-line shape of output tokens per day, with a dated axis."""
    series = daily_series(stats.output_tokens_by_day)
    if len(series) < MIN_SPARK_DAYS:
        return []

    spark = sparkline(bucket_series(series, MAX_SPARK_POINTS))
    first, last = (
        min(stats.output_tokens_by_day),
        max(
            stats.output_tokens_by_day,
        ),
    )
    peak = humanize(max(series))
    axis_width = max(len(spark) - len(str(last)), len(str(first)) + 1)
    axis = f'{first!s:<{axis_width}}{last}'

    return [
        f'  {SPARK_LABEL}   peak {peak}/day',
        f'    {colorize(spark, CYAN, color=color)}',
        f'    {colorize(axis, DIM, color=color)}',
    ]


def totals_and_tokens_lines(
    stats: UsageStats,
) -> tuple[list[str], list[str]]:
    totals = (
        ('sessions', stats.sessions),
        ('prompts', stats.prompts),
        ('replies', stats.replies),
        ('thinking blocks', stats.thinking_blocks),
        ('subagent runs', stats.subagent_runs),
        ('lines added', stats.lines_added),
        ('lines removed', stats.lines_removed),
    )
    totals_lines = [f'  {label:<22} {value:>12,}' for label, value in totals]

    tokens = (
        ('tokens out', stats.output_tokens),
        ('tokens in', stats.input_tokens),
        ('cache read', stats.cache_read_tokens),
        ('cache written', stats.cache_write_tokens),
    )
    tokens_lines = [
        f'  {label:<22} {humanize(value):>12}' for label, value in tokens
    ]

    return totals_lines, tokens_lines


REPO_LABEL_WIDTH = 16


def build_repo_reports(
    by_repo: dict[str, UsageStats],
    pricing: PricingTable | None,
) -> list[RepoReport]:
    """Priced per-repo slices, busiest first, with idle repos dropped."""
    return [
        RepoReport(
            label=label,
            stats=stats,
            cost=compute_cost(stats, pricing) if pricing else None,
        )
        for label, stats in by_repo.items()
        if stats.session_ids
    ]


def repo_row(repo: RepoReport, share: float, *, color: bool) -> str:
    stats = repo.stats
    spend = f'$ {repo.cost.total:>8.2f}' if repo.cost else ' ' * 10
    churn = f'+{stats.lines_added:,}/-{stats.lines_removed:,}'
    return (
        f'    {truncate(repo.label, REPO_LABEL_WIDTH):<{REPO_LABEL_WIDTH}}'
        f' {colorize(bar(share, REPO_BAR_WIDTH), CYAN, color=color)}'
        f'  {spend}'
        f' {humanize(stats.output_tokens):>8}'
        f' {churn:>16}'
        f' {stats.sessions:>5,}'
    )


def repo_lines(repos: list[RepoReport], *, color: bool) -> list[str]:
    if not repos:
        return []

    weights = [
        repo.cost.total if repo.cost else float(repo.stats.output_tokens)
        for repo in repos
    ]
    total = sum(weights) or 1.0

    header = (
        f'    {"":<{REPO_LABEL_WIDTH}} {"":<{REPO_BAR_WIDTH}}'
        f'  {"spend":>10} {"tokens":>8} {"lines":>16} {"sess":>5}'
    )
    lines = ['  by repo', header]
    lines.extend(
        repo_row(repo, weight / total, color=color)
        for repo, weight in zip(repos, weights, strict=True)
    )
    return lines


CACHE_ROW_WIDTH = 20
CACHE_VALUE_WIDTH = 10


def cache_efficiency_lines(
    stats: UsageStats,
    *,
    explain: bool,
) -> list[str]:
    rows = []
    if stats.cache_hit_ratio is not None:
        rows.append(('cache hit ratio', f'{stats.cache_hit_ratio:.1%}'))
    if stats.cache_efficiency is not None:
        rows.append(('cache efficiency', f'{stats.cache_efficiency:.1f}x'))
    if not rows:
        return []

    lines = ['  caching']
    lines.extend(
        f'    {label:<{CACHE_ROW_WIDTH}} {value:>{CACHE_VALUE_WIDTH}}'
        for label, value in rows
    )
    if explain:
        lines.append(
            '    hit ratio = cache_read / (cache_read + input);'
            ' efficiency = cache_read / cache_write (>=2x healthy @ 5m TTL)',
        )
    return lines


TURN_LABEL_WIDTH = 30
TURN_STAT_WIDTH = 8


def turn_duration_row(label: str, durations: list[float]) -> str:
    p50 = percentile(durations, P50) or 0.0
    p95 = percentile(durations, P95) or 0.0
    return (
        f'    {label:<{TURN_LABEL_WIDTH}}'
        f' {p50 / MILLISECONDS_PER_SECOND:>{TURN_STAT_WIDTH}.1f}s'
        f' {p95 / MILLISECONDS_PER_SECOND:>{TURN_STAT_WIDTH}.1f}s'
        f' {len(durations):>7,}'
    )


def turn_duration_lines(stats: UsageStats, *, explain: bool) -> list[str]:
    if not (stats.model_durations_ms or stats.wall_durations_ms):
        return []

    header = (
        f'    {"":<{TURN_LABEL_WIDTH}}'
        f' {"p50":>{TURN_STAT_WIDTH + 1}}'
        f' {"p95":>{TURN_STAT_WIDTH + 1}}'
        f' {"turns":>7}'
    )
    lines = ['  turn duration', header]
    lines.append(turn_duration_row('model time', stats.model_durations_ms))
    lines.append(turn_duration_row('wall clock', stats.wall_durations_ms))

    by_model = sorted(
        stats.model_durations_ms_by_model.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    lines.extend(
        turn_duration_row(model, durations) for model, durations in by_model
    )
    if explain:
        lines.append(
            '    model time = gaps ending at a reply, so tool runs and '
            'approval waits are excluded; per-model rows are model time',
        )
    return lines


COST_CATEGORY_LABELS = (
    ('output', 'output'),
    ('input', 'input (uncached)'),
    ('cache_read', 'cache read'),
    ('cache_write', 'cache write'),
)
COST_ROW_WIDTH = 20
COST_PERCENT_WIDTH = 6
COST_AMOUNT_WIDTH = 9


def cost_row(label: str, share: float | None, amount: float) -> str:
    meter = ' ' * BAR_WIDTH if share is None else bar(share)
    percent = '' if share is None else f'{share:.1%}'
    return (
        f'    {label:<{COST_ROW_WIDTH}} {meter}'
        f' {percent:>{COST_PERCENT_WIDTH}}'
        f'  $ {amount:>{COST_AMOUNT_WIDTH}.2f}'
    )


def cost_lines(cost: CostBreakdown) -> list[str]:
    lines = ['  estimated spend', cost_row('total', None, cost.total)]

    for key, label in COST_CATEGORY_LABELS:
        amount = cost.by_category[key]
        share = amount / cost.total if cost.total else 0.0
        lines.append(cost_row(label, share, amount))

    if cost.unpriced_models:
        names = ', '.join(sorted(cost.unpriced_models))
        lines.append(f'    (excluded, no pricing on file: {names})')

    if cost.pricing_stale:
        expired = ''
        if cost.expired_models:
            names = ', '.join(sorted(cost.expired_models))
            expired = f'expired pricing for {names}; '
        lines.append(
            f'    pricing dated {cost.pricing_as_of} looks stale -- {expired}'
            'ask Claude to refresh scripts/model_pricing.json',
        )

    return lines


def cartoon_available() -> bool:
    return shutil.which(CARTOON_BINARY) is not None


def run_cartoon_stats(since: str) -> str | None:
    """Raw `cartoon stats --since <since>` output, or None if unusable.

    Cartoon tracks its own token savings in its own state, so this shells
    out to it rather than re-deriving anything from the transcripts.
    """
    if not cartoon_available():
        return None
    try:
        result = subprocess.run(  # noqa: S603
            [CARTOON_BINARY, 'stats', '--since', since],
            capture_output=True,
            text=True,
            timeout=CARTOON_STATS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def parse_cartoon_stats(output: str) -> dict:
    """Parse `cartoon stats`'s calls/tokens_saved/by_adapter text output."""
    calls = 0
    tokens_saved = 0
    by_adapter: dict[str, dict[str, int]] = {}
    current_adapter: str | None = None

    for line in output.splitlines():
        if not line.strip():
            continue
        if line.startswith('calls:'):
            calls = int(line.split(':', 1)[1].strip())
        elif line.startswith('tokens_saved:'):
            tokens_saved = int(line.split(':', 1)[1].strip())
        elif line.startswith('by_adapter:'):
            current_adapter = None
        elif line.startswith('    ') and current_adapter is not None:
            key, _, value = line.strip().partition(':')
            by_adapter[current_adapter][key.strip()] = int(value.strip())
        elif line.startswith('  '):
            current_adapter = line.strip().rstrip(':')
            by_adapter[current_adapter] = {}

    return {
        'calls': calls,
        'tokens_saved': tokens_saved,
        'by_adapter': by_adapter,
    }


CARTOON_ROW_WIDTH = 20


def cartoon_lines(stats: dict | None, since: str) -> list[str]:
    if not stats or not stats['calls']:
        return []

    tokens_saved = humanize(stats['tokens_saved'])
    lines = [
        f'  cartoon (--since {since})',
        f'    {"calls":<{CARTOON_ROW_WIDTH}} {stats["calls"]:>10,}',
        f'    {"tokens saved":<{CARTOON_ROW_WIDTH}} {tokens_saved:>10}',
    ]

    by_savings = sorted(
        stats['by_adapter'].items(),
        key=lambda item: item[1].get('saved', 0),
        reverse=True,
    )
    for adapter, counts in by_savings:
        lines.append(
            f'    {adapter:<{CARTOON_ROW_WIDTH}}'
            f' {counts.get("calls", 0):>4,} calls'
            f'  {humanize(counts.get("saved", 0)):>8} saved',
        )

    return lines


MIX_LABEL_WIDTH = 24


def mix_row(label: str, count: int, total: int, peak: int) -> str:
    """A ranked row: label, bar, share of total, count.

    The bar is scaled to the top item rather than the total, or every row
    below the leader collapses to an empty bar. The percentage still reads
    as a share of the total.

    Never colorized -- these blocks get laid out side by side, and ANSI
    codes would inflate the width calculation that alignment depends on.
    """
    return (
        f'    {truncate(label, MIX_LABEL_WIDTH):<{MIX_LABEL_WIDTH}}'
        f' {bar(count / peak if peak else 0.0)}'
        f' {count / total if total else 0.0:>5.1%} {count:>7,}'
    )


def ranked_lines(heading: str, counts: Counter, limit: int) -> list[str]:
    if not counts:
        return []
    ranked = counts.most_common(limit)
    total = sum(counts.values())
    peak = ranked[0][1]
    return [
        heading,
        *(mix_row(label, count, total, peak) for label, count in ranked),
    ]


def model_and_tool_lines(stats: UsageStats) -> tuple[list[str], list[str]]:
    return (
        ranked_lines('  model mix', stats.models, len(stats.models)),
        ranked_lines('  top tools', stats.tools, TOP_TOOLS_SHOWN),
    )


def append_section(
    lines: list[str],
    section: list[str],
    *,
    color: bool,
) -> None:
    """Add a blank line then the section, with its heading emphasized."""
    if not section:
        return
    section[0] = colorize(section[0], BOLD, color=color)
    lines.append('')
    lines.extend(section)


def format_report(
    stats: UsageStats,
    *,
    width: int | None = None,
    color: bool | None = None,
    cost: CostBreakdown | None = None,
    repos: list[RepoReport] | None = None,
    explain: bool = False,
    cartoon: dict | None = None,
    cartoon_since: str = DEFAULT_CARTOON_SINCE,
) -> str:
    if width is None:
        width = shutil.get_terminal_size(FALLBACK_TERMINAL_SIZE).columns
    if color is None:
        color = supports_color()

    lines: list[str] = ['']
    lines.extend(
        colorize(line, BOLD, CYAN, color=color)
        for line in box_lines('Claude Code usage', report_span(stats), width)
    )

    totals_lines, tokens_lines = totals_and_tokens_lines(stats)
    lines.append('')
    lines.extend(merge_side_by_side(totals_lines, tokens_lines, width))

    append_section(lines, sparkline_lines(stats, color=color), color=color)
    append_section(lines, repo_lines(repos or [], color=color), color=color)
    append_section(
        lines,
        cache_efficiency_lines(stats, explain=explain),
        color=color,
    )
    append_section(
        lines,
        turn_duration_lines(stats, explain=explain),
        color=color,
    )
    if cost is not None:
        append_section(lines, cost_lines(cost), color=color)

    append_section(
        lines,
        cartoon_lines(cartoon, cartoon_since),
        color=color,
    )

    model_lines, tool_lines = model_and_tool_lines(stats)
    if model_lines or tool_lines:
        merged = merge_side_by_side(model_lines, tool_lines, width)
        append_section(lines, merged, color=color)

    if stats.longest_prompt_chars:
        lines.append('')
        lines.append(
            f'  longest prompt: {stats.longest_prompt_chars:,} chars',
        )

    if not explain:
        lines.append('')
        lines.append(
            colorize('  (--explain for metric definitions)', DIM, color=color),
        )

    lines.append('')
    return '\n'.join(line.rstrip() for line in lines)


def cost_as_dict(cost: CostBreakdown | None) -> dict | None:
    if cost is None:
        return None
    return {
        'total': cost.total,
        'by_category': cost.by_category,
        'by_model': cost.by_model,
        'unpriced_models': sorted(cost.unpriced_models),
        'expired_models': sorted(cost.expired_models),
        'pricing_as_of': cost.pricing_as_of.isoformat(),
        'pricing_stale': cost.pricing_stale,
    }


def duration_as_dict(durations: list[float]) -> dict:
    return {
        'turns': len(durations),
        'p50': percentile(durations, P50),
        'p95': percentile(durations, P95),
    }


def turn_duration_as_dict(stats: UsageStats) -> dict:
    by_model = stats.model_durations_ms_by_model.items()
    return {
        'model_time': duration_as_dict(stats.model_durations_ms),
        'wall_clock': duration_as_dict(
            [float(ms) for ms in stats.wall_durations_ms],
        ),
        'by_model': {
            model: duration_as_dict(durations) for model, durations in by_model
        },
    }


def repo_as_dict(repo: RepoReport) -> dict:
    stats = repo.stats
    return {
        'repo': repo.label,
        'sessions': stats.sessions,
        'prompts': stats.prompts,
        'replies': stats.replies,
        'lines_added': stats.lines_added,
        'lines_removed': stats.lines_removed,
        'tokens': {
            'output': stats.output_tokens,
            'input': stats.input_tokens,
            'cache_read': stats.cache_read_tokens,
            'cache_write': stats.cache_write_tokens,
        },
        'cost': cost_as_dict(repo.cost),
        'models': dict(stats.models.most_common()),
        'tools': dict(stats.tools.most_common()),
    }


def stats_as_dict(
    stats: UsageStats,
    cost: CostBreakdown | None = None,
    repos: list[RepoReport] | None = None,
    cartoon: dict | None = None,
) -> dict:
    first, last = stats.first_seen, stats.last_seen
    return {
        'span': {
            'first': first.isoformat() if first else None,
            'last': last.isoformat() if last else None,
        },
        'sessions': stats.sessions,
        'prompts': stats.prompts,
        'replies': stats.replies,
        'thinking_blocks': stats.thinking_blocks,
        'subagent_runs': stats.subagent_runs,
        'lines_added': stats.lines_added,
        'lines_removed': stats.lines_removed,
        'tokens': {
            'output': stats.output_tokens,
            'input': stats.input_tokens,
            'cache_read': stats.cache_read_tokens,
            'cache_write': stats.cache_write_tokens,
        },
        'cache_hit_ratio': stats.cache_hit_ratio,
        'cache_efficiency': stats.cache_efficiency,
        'turn_duration_ms': turn_duration_as_dict(stats),
        'cost': cost_as_dict(cost),
        'cartoon': cartoon,
        'repos': [repo_as_dict(repo) for repo in repos or []],
        'models': dict(stats.models.most_common()),
        'tools': dict(stats.tools.most_common()),
        'longest_prompt_chars': stats.longest_prompt_chars,
        'output_tokens_by_day': {
            day.isoformat(): value
            for day, value in sorted(stats.output_tokens_by_day.items())
        },
    }


def parse_day(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        msg = f'expected YYYY-MM-DD, got {raw!r}'
        raise argparse.ArgumentTypeError(msg) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Summarize local Claude Code session logs.',
    )
    parser.add_argument(
        'log_root',
        nargs='*',
        type=Path,
        default=[DEFAULT_LOG_ROOT],
        help=f'transcript roots (default: {DEFAULT_LOG_ROOT})',
    )
    parser.add_argument('--since', type=parse_day, help='earliest day')
    parser.add_argument('--until', type=parse_day, help='latest day')
    parser.add_argument(
        '--json',
        action='store_true',
        help='emit machine-readable JSON instead of a report',
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='disable ANSI colors in the report',
    )
    parser.add_argument(
        '--explain',
        action='store_true',
        help='include the footnotes defining each metric',
    )
    parser.add_argument(
        '--pricing-path',
        type=Path,
        default=DEFAULT_PRICING_PATH,
        help=f'model pricing file (default: {DEFAULT_PRICING_PATH})',
    )
    parser.add_argument(
        '--record',
        action='store_true',
        help=(
            'backfill --since/--until into --db-path instead of printing '
            "a report; every normal run already records today's snapshot"
        ),
    )
    parser.add_argument(
        '--db-path',
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f'sqlite history db (default: {DEFAULT_DB_PATH})',
    )
    parser.add_argument(
        '--cartoon-since',
        default=DEFAULT_CARTOON_SINCE,
        help=(
            'window for `cartoon stats`, e.g. 7d|24h|30m '
            f'(default: {DEFAULT_CARTOON_SINCE}); skipped if cartoon is '
            'not installed'
        ),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    roots = args.log_root or [DEFAULT_LOG_ROOT]

    missing = [root for root in roots if not root.exists()]
    if missing:
        paths = ', '.join(str(root) for root in missing)
        print(f'No such log root: {paths}', file=sys.stderr)
        sys.exit(1)

    pricing = None
    if args.pricing_path.exists():
        pricing = load_pricing(args.pricing_path)
    else:
        print(
            f'No pricing file at {args.pricing_path} -- '
            'spend estimates disabled',
            file=sys.stderr,
        )

    if args.record:
        today = date.today()
        since = args.since or today
        until = args.until or today
        conn = sqlite3.connect(args.db_path)
        try:
            ensure_schema(conn)
            written = record_range(conn, roots, since, until, pricing)
            conn.commit()
        finally:
            conn.close()
        print(f'recorded {written} day(s) to {args.db_path}')
        return

    by_repo = collect_stats_by_repo(roots, since=args.since, until=args.until)
    stats = merge_stats(by_repo.values())
    repos = build_repo_reports(by_repo, pricing)
    cost = compute_cost(stats, pricing) if pricing else None

    cartoon_raw = run_cartoon_stats(args.cartoon_since)
    cartoon = (
        parse_cartoon_stats(cartoon_raw) if cartoon_raw is not None else None
    )

    today = date.today()
    conn = sqlite3.connect(args.db_path)
    try:
        ensure_schema(conn)
        record_range(conn, roots, today, today, pricing)
        conn.commit()
    finally:
        conn.close()

    if args.json:
        print(
            json.dumps(
                stats_as_dict(stats, cost, repos, cartoon),
                indent=2,
            ),
        )
    else:
        color = False if args.no_color else None
        print(
            format_report(
                stats,
                color=color,
                cost=cost,
                repos=repos,
                explain=args.explain,
                cartoon=cartoon,
                cartoon_since=args.cartoon_since,
            ),
        )


if __name__ == '__main__':
    main()
