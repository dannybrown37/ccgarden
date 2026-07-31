from __future__ import annotations

import datetime
import math
import random
from typing import TYPE_CHECKING

from ccgarden.data import DayRing, GardenData, ModelCloud, RepoBranch, ToolBush

if TYPE_CHECKING:
    from ccgarden.data import GardenTimeline, RepoBranchDay, ToolUsageDay

VIEWBOX_WIDTH = 800
VIEWBOX_HEIGHT = 800
GROUND_Y = 728
TRUNK_HEIGHT = 300
TRUNK_TOP_Y = GROUND_Y - TRUNK_HEIGHT
TRUNK_CENTER_X = VIEWBOX_WIDTH / 2
TRUNK_BASE_HALF_WIDTH_MIN = 9.0
TRUNK_BASE_HALF_WIDTH_MAX = 30.0
TRUNK_SESSIONS_SATURATION = 400
TRUNK_TOP_TAPER = 0.72
BRANCH_ZONE_HEIGHT = 220
BRANCH_LENGTH_MIN = 30.0
BRANCH_LENGTH_MAX = 230.0
BRANCH_LINES_SATURATION = 6000
BRANCH_LENGTH_EXPONENT = 0.7
BRANCH_SPREAD_DEGREES = 55.0
BRANCH_TIP_WIDTH = 1.6
BRANCH_WIDTH_MIN = 2.2
BRANCH_WIDTH_MAX = 7.0
BRANCH_TOKENS_SATURATION = 2_500_000
LEAVES_PER_SESSION = 5
LEAF_SATURATION_COUNT = 2000
LEAF_TURNS_FLOOR = 0.0
LEAF_TURNS_CEILING = 6.9
LEAF_SIZE_MULTIPLIER_MIN = 0.75
LEAF_SIZE_MULTIPLIER_MAX = 1.5
CANOPY_MIN_LEAVES = 3
CANOPY_RADIUS_MIN = 20.0
CANOPY_RADIUS_MAX = 130.0
LEAF_SCATTER_RADIUS = 45.0
LEAF_RADIUS = 7.0
LEAF_COLORS = ('#3f7a3f', '#4f8f4f', '#5a9e5a', '#6bb26b', '#7dc47d')
LEAF_SHAPE_D = 'M0,-1 C0.55,-0.75 0.55,0.75 0,1 C-0.55,0.75 -0.55,-0.75 0,-1 Z'
LEAF_VEIN_D = 'M0,-0.85 L0,0.85'
# Greenery covers the outer FOLIAGE_START_FRACTION..FOLIAGE_TIP_OVERHANG span
# of each branch's length (as a fraction from origin to tip), so long
# branches get proportionally more covered length instead of a single leaf
# ball stuck at the very tip.
FOLIAGE_START_FRACTION = 0.4
FOLIAGE_TIP_OVERHANG = 1.08
FOLIAGE_BLOB_SPACING = 55.0
MAX_FOLIAGE_BLOBS = 6
RING_STROKE_WIDTH_MIN = 0.75
RING_STROKE_WIDTH_MAX = 3.5
RING_SESSIONS_SATURATION = 60

FLOWER_COLORS = ('#f4c95d', '#f27ab0', '#fdfdf6', '#c98bdb', '#f2896d')
FLOWER_CENTER_COLOR = '#5a3d1a'
FLOWER_RADIUS = 5.0

# One cloud per model used, sized by how many tokens that model produced.
CLOUD_MARGIN = 50.0
CLOUD_Y_MIN = 50.0
CLOUD_Y_MAX = 150.0
CLOUD_RADIUS_MIN = 16.0
CLOUD_RADIUS_MAX = 60.0
CLOUD_TOKENS_SATURATION = 6_000_000
CLOUD_PUFFS = (
    (0.0, -0.18, 1.0),
    (-0.55, 0.12, 0.68),
    (0.55, 0.12, 0.68),
    (-0.18, 0.3, 0.55),
    (0.22, 0.3, 0.5),
)

# One bush per tool used, sized by how many times that tool was called.
# Puffs are laid out relative to a (0, 0) ground-contact point (see
# `_render_bush`), unlike clouds which are centered on their own midpoint.
# Capped at MAX_BUSHES (mirroring claude_stats.TOP_TOOLS_SHOWN) since a
# repo can easily touch a dozen-plus distinct tools -- more than that many
# max-size bushes wouldn't fit the ground strip without wall-to-wall overlap.
MAX_BUSHES = 10
BUSH_MARGIN = 40.0
BUSH_RADIUS_MIN = 12.0
BUSH_RADIUS_MAX = 34.0
BUSH_TOOL_COUNT_SATURATION = 600
BUSH_PUFFS = (
    (0.0, -0.55, 0.85),
    (-0.62, -0.3, 0.62),
    (0.62, -0.3, 0.62),
    (-0.25, -0.55, 0.5),
    (0.28, -0.55, 0.5),
)

TIMELINE_PER_DAY_SECONDS = 0.6
TIMELINE_MIN_DURATION_S = 5.0
TIMELINE_MAX_DURATION_S = 16.0
TIMELINE_MIN_DAYS_TO_ANIMATE = 2

# Extra strip below the legend, holding the scrubber that appears once the
# initial timelapse finishes playing.
SCRUBBER_HEIGHT = 40.0
SCRUBBER_MARGIN = 4.0
SCRUBBER_TOTAL_HEIGHT = SCRUBBER_HEIGHT + SCRUBBER_MARGIN * 2
SCRUBBER_Y = VIEWBOX_HEIGHT + SCRUBBER_MARGIN
TIMELINE_VIEWBOX_HEIGHT = VIEWBOX_HEIGHT + SCRUBBER_TOTAL_HEIGHT


def _escape_xml(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _title(text: str) -> str:
    """A `<title>` child that browsers render as a native hover tooltip."""
    return f'<title>{_escape_xml(text)}</title>'


def _format_day(day: str) -> str:
    try:
        return datetime.date.fromisoformat(day).strftime('%b %-d, %Y')
    except ValueError:
        return day


def _trunk_half_width(total_sessions: int) -> float:
    """Base half-width of the trunk, growing with cumulative sessions.

    A plain linear formula saturates at its cap within the first ~26
    sessions, which made the trunk (and its day-by-day growth animation)
    jump straight to full width on day one for anyone with a normal daily
    session count, instead of visibly widening across days/months like the
    canopy already does (see `_canopy_radius`).
    """
    growth = math.sqrt(
        min(total_sessions, TRUNK_SESSIONS_SATURATION)
        / TRUNK_SESSIONS_SATURATION
    )
    return (
        TRUNK_BASE_HALF_WIDTH_MIN
        + (TRUNK_BASE_HALF_WIDTH_MAX - TRUNK_BASE_HALF_WIDTH_MIN) * growth
    )


def _trunk_half_widths_for_timeline(
    cumulative_sessions: list[int],
) -> list[float]:
    """Per-day trunk half-widths for the growth timelapse.

    Evaluating `_trunk_half_width` independently on each day's raw
    cumulative total (as `render_svg`'s static render does) makes the
    trunk start already partway up the saturation curve on day one --
    with a normal amount of prior history, there's almost no headroom left
    to visibly grow into over the remaining days. Branches sidestep this
    by interpolating as a fraction of *their own* final size instead of
    re-deriving an absolute value per day; do the same here so the trunk
    always starts near the minimum and grows into the real final width.
    """
    final_width = _trunk_half_width(cumulative_sessions[-1])
    final_total = cumulative_sessions[-1] or 1
    return [
        TRUNK_BASE_HALF_WIDTH_MIN
        + (final_width - TRUNK_BASE_HALF_WIDTH_MIN) * (sessions / final_total)
        for sessions in cumulative_sessions
    ]


def _ring_stroke_width(sessions: int) -> float:
    """A ring's boldness for a day with this many sessions.

    Same saturation problem as the trunk: a linear formula capped out by
    ~9 sessions/day, so any normal work day maxed out the stroke and every
    ring looked identically bold regardless of how busy the day actually
    was.
    """
    growth = math.sqrt(
        min(sessions, RING_SESSIONS_SATURATION) / RING_SESSIONS_SATURATION
    )
    return (
        RING_STROKE_WIDTH_MIN
        + (RING_STROKE_WIDTH_MAX - RING_STROKE_WIDTH_MIN) * growth
    )


def _branch_length(lines_added: int) -> float:
    """A branch's length for a repo with this many cumulative lines added.

    A pure linear mapping reads as proportional but leaves every branch
    looking stubby for realistic lines-added totals, since none of them
    get near BRANCH_LINES_SATURATION; a pure sqrt curve fixes the
    stubbiness but compresses the ratios between repos too much (a repo
    with 17x the lines of another only ends up ~2.7x longer). Raising
    the fraction to BRANCH_LENGTH_EXPONENT (between the two) is a happy
    medium: smaller totals still get boosted off the floor, but relative
    differences between repos stay much closer to their real ratio than
    sqrt allows.
    """
    fraction = (
        min(lines_added, BRANCH_LINES_SATURATION) / BRANCH_LINES_SATURATION
    )
    growth = fraction**BRANCH_LENGTH_EXPONENT
    return BRANCH_LENGTH_MIN + (BRANCH_LENGTH_MAX - BRANCH_LENGTH_MIN) * growth


def _branch_width(total_tokens: int) -> float:
    """A branch's thickness for a repo with this many cumulative tokens.

    Length already tracks lines added and leaf count already tracks
    sessions, so thickness is free to carry a third signal: how much
    Claude actually read and wrote on that repo (input + output tokens),
    which can diverge a lot from lines-added for repos with long research
    or review sessions that touch little code. Same sqrt-saturation shape
    as the other size formulas so small totals still get lifted off the
    floor instead of staying visually flat.
    """
    growth = math.sqrt(
        min(total_tokens, BRANCH_TOKENS_SATURATION) / BRANCH_TOKENS_SATURATION
    )
    return BRANCH_WIDTH_MIN + (BRANCH_WIDTH_MAX - BRANCH_WIDTH_MIN) * growth


def _half_width_at(y: float, base_half_width: float) -> float:
    trunk_fraction = (GROUND_Y - y) / TRUNK_HEIGHT
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    return (
        base_half_width - (base_half_width - top_half_width) * trunk_fraction
    )


def _render_defs() -> str:
    return (
        '<defs>'
        '<linearGradient id="skyGradient" x1="0%" y1="0%" x2="0%" y2="100%">'
        '<stop offset="0%" stop-color="#1c3d5a" />'
        '<stop offset="55%" stop-color="#2f5c82" />'
        '<stop offset="100%" stop-color="#4a7fa5" />'
        '</linearGradient>'
        '<linearGradient id="groundGradient" '
        'x1="0%" y1="0%" x2="0%" y2="100%">'
        '<stop offset="0%" stop-color="#74b25e" />'
        '<stop offset="100%" stop-color="#3f7a3f" />'
        '</linearGradient>'
        '<linearGradient id="trunkGradient" gradientUnits="userSpaceOnUse" '
        f'x1="{TRUNK_CENTER_X - TRUNK_BASE_HALF_WIDTH_MAX}" y1="0" '
        f'x2="{TRUNK_CENTER_X + TRUNK_BASE_HALF_WIDTH_MAX}" y2="0">'
        '<stop offset="0%" stop-color="#4a2e1a" />'
        '<stop offset="45%" stop-color="#7a4a26" />'
        '<stop offset="70%" stop-color="#6b4226" />'
        '<stop offset="100%" stop-color="#3a2412" />'
        '</linearGradient>'
        '<radialGradient id="canopyGradient" cx="35%" cy="30%" r="75%">'
        '<stop offset="0%" stop-color="#8fcf6f" />'
        '<stop offset="55%" stop-color="#5a9e5a" />'
        '<stop offset="100%" stop-color="#2f5f2f" />'
        '</radialGradient>'
        '<radialGradient id="cloudGradient" cx="35%" cy="30%" r="75%">'
        '<stop offset="0%" stop-color="#ffffff" />'
        '<stop offset="60%" stop-color="#eef3f8" />'
        '<stop offset="100%" stop-color="#c7d5e4" />'
        '</radialGradient>'
        '<radialGradient id="bushGradient" cx="35%" cy="25%" r="75%">'
        '<stop offset="0%" stop-color="#a9c95a" />'
        '<stop offset="55%" stop-color="#6f8f3a" />'
        '<stop offset="100%" stop-color="#3f5620" />'
        '</radialGradient>'
        '<filter id="softBlur" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="3" />'
        '</filter>'
        '</defs>'
    )


def _render_background() -> str:
    wave = 6
    mid_x = VIEWBOX_WIDTH * 0.5
    quarter_x = VIEWBOX_WIDTH * 0.25
    three_quarter_x = VIEWBOX_WIDTH * 0.75
    ground_edge = (
        f'M0,{GROUND_Y} '
        f'Q {quarter_x},{GROUND_Y - wave} {mid_x},{GROUND_Y} '
        f'Q {three_quarter_x},{GROUND_Y + wave} {VIEWBOX_WIDTH},{GROUND_Y}'
    )
    ground_fill = (
        f'{ground_edge} L {VIEWBOX_WIDTH},{VIEWBOX_HEIGHT} '
        f'L0,{VIEWBOX_HEIGHT} Z'
    )
    return (
        f'<rect x="0" y="0" width="{VIEWBOX_WIDTH}" height="{VIEWBOX_HEIGHT}" '
        f'fill="url(#skyGradient)" />'
        f'<path d="{ground_fill}" fill="url(#groundGradient)" />'
        f'<path d="{ground_edge}" fill="none" stroke="#2f5f2f" '
        f'stroke-width="2" opacity="0.5" />'
        f'{_render_grass()}'
    )


def _render_grass() -> str:
    rng = random.Random('ccgarden-grass')
    elements = []
    for _ in range(46):
        x = rng.uniform(4, VIEWBOX_WIDTH - 4)
        y = GROUND_Y + rng.uniform(4, VIEWBOX_HEIGHT - GROUND_Y - 8)
        height = rng.uniform(6, 13)
        lean = rng.uniform(-4, 4)
        elements.append(
            f'<path d="M{x},{y} Q{x + lean},{y - height * 0.6} '
            f'{x + lean * 1.6},{y - height}" fill="none" '
            f'stroke="#2f5f2f" stroke-width="1.4" stroke-linecap="round" '
            f'opacity="0.4" />'
        )
    return ''.join(elements)


def _cache_efficiency_flower_count(
    cache_read_tokens: int, cache_write_tokens: int
) -> int:
    """Nearest whole multiple of cache reads per write -- one flower per x.

    Cache efficiency (reads/write) is otherwise invisible anywhere in the
    tree, unlike every other tracked stat; a garden-wide flower count gives
    it a home without tying it to any single repo's branch or bush.
    """
    if cache_write_tokens <= 0:
        return 0
    return max(0, round(cache_read_tokens / cache_write_tokens))


def _render_flower(
    cx: float, cy: float, size: float, petal_color: str, rng: random.Random
) -> str:
    orbit = size * 0.55
    petal_radius = size * 0.42
    angle_offset = rng.uniform(0, 72)
    petals = []
    for i in range(5):
        angle = math.radians(angle_offset + i * 72)
        petal_x = cx + orbit * math.cos(angle)
        petal_y = cy + orbit * math.sin(angle)
        petals.append(
            f'<circle cx="{petal_x:.1f}" cy="{petal_y:.1f}" '
            f'r="{petal_radius:.2f}" fill="{petal_color}" opacity="0.92" />'
        )
    petals = ''.join(petals)
    center = (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{size * 0.28:.2f}" '
        f'fill="{FLOWER_CENTER_COLOR}" opacity="0.95" />'
    )
    return petals + center


def _render_flowers_on_bushes(
    count: int,
    bush_footprints: list[tuple[float, float]],
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> str:
    """`count` flowers scattered across the given bush footprints.

    Cache efficiency has no bush or branch of its own to live on, so its
    flowers ride along on the tool bushes instead -- round-robining
    through them so they spread across every bush rather than piling onto
    one. With no bushes there's nowhere to plant them, so nothing renders.
    """
    if count <= 0 or not bush_footprints:
        return ''
    title = _title(
        f'Cache efficiency — {cache_read_tokens:,} cache reads per '
        f'{cache_write_tokens:,} cache writes'
    )
    rng = random.Random('ccgarden-flowers')
    elements = []
    for index in range(count):
        bush_x, bush_radius = bush_footprints[index % len(bush_footprints)]
        angle = rng.uniform(0, 2 * math.pi)
        dist = bush_radius * rng.uniform(0.0, 0.7)
        x = bush_x + dist * math.cos(angle)
        y = GROUND_Y - bush_radius * 0.6 + dist * math.sin(angle) * 0.6
        size = FLOWER_RADIUS * rng.uniform(0.6, 0.9)
        color = rng.choice(FLOWER_COLORS)
        elements.append(
            f'<g class="flower">{title}'
            f'{_render_flower(x, y, size, color, rng)}</g>'
        )
    return ''.join(elements)


def _cloud_radius(total_tokens: int) -> float:
    """A model's cloud radius, growing quickly then leveling off.

    Same sqrt-saturation shape as the other size formulas (see
    `_canopy_radius`, `_branch_width`) so a lightly-used model's cloud is
    still visible off the floor instead of vanishing, while a heavily-used
    model doesn't need an unbounded amount of sky to read as "the big one".
    """
    growth = math.sqrt(
        min(total_tokens, CLOUD_TOKENS_SATURATION) / CLOUD_TOKENS_SATURATION
    )
    return CLOUD_RADIUS_MIN + (CLOUD_RADIUS_MAX - CLOUD_RADIUS_MIN) * growth


def _cloud_puffs_d(radius: float, seed: str) -> list[str]:
    """`d` values for each lumpy puff making up one cloud, at this radius."""
    rng = random.Random(seed)
    d_values = []
    for index, (dx_frac, dy_frac, r_frac) in enumerate(CLOUD_PUFFS):
        jitter = rng.uniform(0.92, 1.08)
        puff_radius = radius * r_frac * jitter
        d_values.append(
            _blob_path(
                dx_frac * radius,
                dy_frac * radius,
                puff_radius,
                random.Random(f'{seed}:{index}'),
                points=8,
                jitter=0.16,
            )
        )
    return d_values


def _render_cloud(cx: float, cy: float, radius: float, seed: str) -> str:
    puffs = ''.join(
        f'<path d="{d}" fill="url(#cloudGradient)" opacity="0.88" />'
        for d in _cloud_puffs_d(radius, seed)
    )
    return f'<g transform="translate({cx:.1f},{cy:.1f})">{puffs}</g>'


def _cloud_positions(count: int) -> list[tuple[float, float]]:
    """Deterministic (x, y) sky slot for each of `count` clouds.

    Spread evenly across the width like the flower floor, with per-slot
    jitter so a full sky of models doesn't read as a mechanical grid.
    Shuffled before returning so slot order doesn't line up with the
    caller's (biggest-model-first) list order -- otherwise every render
    reads as a strict big-to-small gradient across the sky instead of a
    scattered distribution of sizes.
    """
    usable_width = VIEWBOX_WIDTH - CLOUD_MARGIN * 2
    positions = []
    for index in range(count):
        rng = random.Random(f'ccgarden-cloud-slot:{index}')
        x = CLOUD_MARGIN + usable_width * (
            (index + rng.uniform(0.25, 0.75)) / count
        )
        y = CLOUD_Y_MIN + rng.uniform(0.0, CLOUD_Y_MAX - CLOUD_Y_MIN)
        positions.append((x, y))
    random.Random('ccgarden-cloud-order').shuffle(positions)
    return positions


def _render_clouds(models: list[ModelCloud]) -> str:
    if not models:
        return ''
    positions = _cloud_positions(len(models))
    elements = []
    for (x, y), model_cloud in zip(positions, models, strict=True):
        total_tokens = model_cloud.output_tokens + model_cloud.input_tokens
        radius = _cloud_radius(total_tokens)
        title = _title(f'{model_cloud.model} — {total_tokens:,} tokens')
        elements.append(
            f'<g class="cloud">{title}'
            f'{_render_cloud(x, y, radius, model_cloud.model)}</g>'
        )
    return ''.join(elements)


def _bush_radius(tool_count: int) -> float:
    """A tool's bush radius, growing quickly then leveling off.

    Same sqrt-saturation shape as the other size formulas (see
    `_cloud_radius`, `_canopy_radius`) so a rarely-used tool still gets a
    visible bush instead of vanishing.
    """
    growth = math.sqrt(
        min(tool_count, BUSH_TOOL_COUNT_SATURATION)
        / BUSH_TOOL_COUNT_SATURATION
    )
    return BUSH_RADIUS_MIN + (BUSH_RADIUS_MAX - BUSH_RADIUS_MIN) * growth


def _bush_puffs_d(radius: float, seed: str) -> list[str]:
    """`d` values for each lumpy puff making up one bush, at this radius.

    Puffs are laid out relative to (0, 0) sitting at the bush's ground
    contact point, with every puff's lower edge at or below that line --
    so a caller translating to (x, GROUND_Y) gets a shrub resting on the
    grass, and scaling the whole group grows it up out of that same root
    point instead of expanding symmetrically the way a floating cloud does.
    """
    rng = random.Random(seed)
    d_values = []
    for index, (dx_frac, dy_frac, r_frac) in enumerate(BUSH_PUFFS):
        jitter = rng.uniform(0.92, 1.08)
        puff_radius = radius * r_frac * jitter
        d_values.append(
            _blob_path(
                dx_frac * radius,
                dy_frac * radius,
                puff_radius,
                random.Random(f'{seed}:{index}'),
                points=9,
                jitter=0.22,
            )
        )
    return d_values


def _render_bush(cx: float, base_y: float, radius: float, seed: str) -> str:
    puffs = ''.join(
        f'<path d="{d}" fill="url(#bushGradient)" opacity="0.94" />'
        for d in _bush_puffs_d(radius, seed)
    )
    return f'<g transform="translate({cx:.1f},{base_y:.1f})">{puffs}</g>'


def _bush_x_positions(count: int) -> list[float]:
    """Deterministic ground-line x slot for each of `count` bushes.

    Spread evenly across the width like the flower floor and cloud slots,
    with per-slot jitter so a full row of tools doesn't read as a
    mechanical grid. Shuffled before returning for the same reason as
    `_cloud_positions` -- the caller's list is sorted biggest-tool-first,
    and zipping it straight against slots in order would always put the
    biggest bush leftmost and the smallest rightmost.
    """
    usable_width = VIEWBOX_WIDTH - BUSH_MARGIN * 2
    positions = []
    for index in range(count):
        rng = random.Random(f'ccgarden-bush-slot:{index}')
        x = BUSH_MARGIN + usable_width * (
            (index + rng.uniform(0.2, 0.8)) / count
        )
        positions.append(x)
    random.Random('ccgarden-bush-order').shuffle(positions)
    return positions


def _bush_footprints(tools: list[ToolBush]) -> list[tuple[float, float]]:
    """(x, radius) ground-line footprint for each bush that will be drawn.

    Shared with the flower placement in `render_svg`/`render_timeline_svg`
    so flowers only ever land inside a bush that's actually rendered.
    """
    tools = tools[:MAX_BUSHES]
    if not tools:
        return []
    xs = _bush_x_positions(len(tools))
    return [
        (x, _bush_radius(tool_bush.count))
        for x, tool_bush in zip(xs, tools, strict=True)
    ]


def _render_bushes(tools: list[ToolBush]) -> str:
    tools = tools[:MAX_BUSHES]
    footprints = _bush_footprints(tools)
    return ''.join(
        (
            '<g class="bush">'
            f'{_title(f"{tool_bush.tool} — used {tool_bush.count:,} times")}'
            f'{_render_bush(x, GROUND_Y, radius, tool_bush.tool)}</g>'
        )
        for (x, radius), tool_bush in zip(footprints, tools, strict=True)
    )


def _render_trunk(base_half_width: float) -> str:
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    cx = TRUNK_CENTER_X
    lean = base_half_width * 0.1
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    top_shoulder_y = TRUNK_TOP_Y + top_half_width * 0.5
    dome_y = TRUNK_TOP_Y - top_half_width * 0.35
    left_ctrl_x = cx - (base_half_width + top_half_width) / 2 - lean
    right_ctrl_x = cx + (base_half_width + top_half_width) / 2 + lean

    d = (
        f'M {cx - base_half_width},{GROUND_Y} '
        f'Q {left_ctrl_x},{mid_y} {cx - top_half_width},{top_shoulder_y} '
        f'Q {cx},{dome_y} {cx + top_half_width},{top_shoulder_y} '
        f'Q {right_ctrl_x},{mid_y} {cx + base_half_width},{GROUND_Y} '
        f'Z'
    )
    trunk = (
        f'<path class="trunk" d="{d}" fill="url(#trunkGradient)" '
        f'stroke="#3a2412" stroke-width="1.5" stroke-linejoin="round" />'
    )
    return trunk + _render_bark_texture(base_half_width, top_half_width)


def _render_bark_texture(base_half_width: float, top_half_width: float) -> str:
    rng = random.Random('ccgarden-bark')
    cx = TRUNK_CENTER_X
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    elements = []
    for x_offset in (-0.32, 0.4):
        top_x = cx + x_offset * top_half_width
        base_x = cx + x_offset * base_half_width
        jitter = rng.uniform(-2, 2)
        elements.append(
            f'<path d="M{base_x},{GROUND_Y - 8} '
            f'Q{(base_x + top_x) / 2 + jitter},{mid_y} '
            f'{top_x},{TRUNK_TOP_Y + 10}" '
            f'fill="none" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.22" />'
        )
    return ''.join(elements)


def _render_rings(rings: list[DayRing], base_half_width: float) -> str:
    if not rings:
        return ''
    elements = []
    count = len(rings)
    for index, day_ring in enumerate(rings):
        y = GROUND_Y - (index + 1) / (count + 1) * TRUNK_HEIGHT
        half_width = _half_width_at(y, base_half_width) * 0.85
        cx = TRUNK_CENTER_X
        bow = half_width * 0.1
        stroke_width = _ring_stroke_width(day_ring.sessions)
        d = f'M {cx - half_width},{y} Q {cx},{y - bow} {cx + half_width},{y}'
        title = _title(
            f'{_format_day(day_ring.day)} — {day_ring.sessions} sessions, '
            f'+{day_ring.lines_added:,}/-{day_ring.lines_removed:,} lines'
        )
        elements.append(
            f'<path class="ring" d="{d}" fill="none" stroke="#3a2412" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" '
            f'opacity="0.22">{title}</path>'
        )
    return ''.join(elements)


def _branch_endpoint(
    origin_x: float,
    origin_y: float,
    length: float,
    side: int,
    spread_index: float,
) -> tuple[float, float]:
    angle_deg = 90 - (
        BRANCH_SPREAD_DEGREES * side * (0.4 + 0.6 * spread_index)
    )
    angle_rad = math.radians(angle_deg)
    end_x = origin_x + length * (1 if side > 0 else -1) * abs(
        math.cos(angle_rad)
    )
    end_y = origin_y - length * math.sin(angle_rad)
    return end_x, end_y


def _branch_shape_points(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
    root_overlap: float = 0.0,
) -> dict[str, tuple[float, float]]:
    """The six control/corner points of a tapered branch quad.

    `root_overlap` pulls the base back past `origin` along the branch's
    own axis, burying it a little deeper in whatever it grows out of
    (the trunk) so there's no sliver of background visible at the seam.
    """
    dx = end_x - origin_x
    dy = end_y - origin_y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    root_x = origin_x - ux * root_overlap
    root_y = origin_y - uy * root_overlap

    mid_x = (origin_x + end_x) / 2 + px * bow
    mid_y = (origin_y + end_y) / 2 + py * bow
    avg_width = (base_width + tip_width) / 2

    return {
        'base_left': (root_x + px * base_width, root_y + py * base_width),
        'base_right': (root_x - px * base_width, root_y - py * base_width),
        'tip_left': (end_x + px * tip_width, end_y + py * tip_width),
        'tip_right': (end_x - px * tip_width, end_y - py * tip_width),
        'ctrl_left': (mid_x + px * avg_width, mid_y + py * avg_width),
        'ctrl_right': (mid_x - px * avg_width, mid_y - py * avg_width),
    }


def _render_branch_shape(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
    root_overlap: float = 0.0,
) -> str:
    p = _branch_shape_points(
        origin_x,
        origin_y,
        end_x,
        end_y,
        base_width=base_width,
        tip_width=tip_width,
        bow=bow,
        root_overlap=root_overlap,
    )
    return (
        f'M {p["base_left"][0]},{p["base_left"][1]} '
        f'Q {p["ctrl_left"][0]},{p["ctrl_left"][1]} '
        f'{p["tip_left"][0]},{p["tip_left"][1]} '
        f'L {p["tip_right"][0]},{p["tip_right"][1]} '
        f'Q {p["ctrl_right"][0]},{p["ctrl_right"][1]} '
        f'{p["base_right"][0]},{p["base_right"][1]} '
        f'Z'
    )


def _render_branch_outline(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
    root_overlap: float = 0.0,
) -> str:
    """The branch's outer edge only, open at the base.

    Used for stroking: closing the path across the base would draw a
    hard straight line right where the branch is meant to melt into the
    trunk, which is exactly the seam we're trying to hide.
    """
    p = _branch_shape_points(
        origin_x,
        origin_y,
        end_x,
        end_y,
        base_width=base_width,
        tip_width=tip_width,
        bow=bow,
        root_overlap=root_overlap,
    )
    return (
        f'M {p["base_left"][0]},{p["base_left"][1]} '
        f'Q {p["ctrl_left"][0]},{p["ctrl_left"][1]} '
        f'{p["tip_left"][0]},{p["tip_left"][1]} '
        f'L {p["tip_right"][0]},{p["tip_right"][1]} '
        f'Q {p["ctrl_right"][0]},{p["ctrl_right"][1]} '
        f'{p["base_right"][0]},{p["base_right"][1]}'
    )


def _render_branch_collar(
    origin_x: float, origin_y: float, base_width: float, seed: str
) -> str:
    """A soft, blurred bark knuckle where a branch meets the trunk.

    Real branch unions bulge outward and blend gradually into the trunk's
    bark rather than butting up against it at a hard edge. A blurred,
    irregular blob roughly the branch's own width -- drawn under the
    branch fill -- fakes that transition cheaply.
    """
    radius = max(base_width * 2.2, 6.0)
    rng = random.Random(f'{seed}:collar')
    blob_d = _blob_path(origin_x, origin_y, radius, rng, points=7, jitter=0.3)
    return (
        f'<path class="branch-collar" d="{blob_d}" '
        f'fill="url(#trunkGradient)" opacity="0.9" filter="url(#softBlur)" />'
    )


def _render_crown(base_half_width: float, top_half_width: float) -> str:
    rng = random.Random('ccgarden-crown')
    cx = TRUNK_CENTER_X
    cy = TRUNK_TOP_Y - top_half_width * 0.2
    radius = max(base_half_width * 1.15, 22.0)
    blob_d = _blob_path(cx, cy, radius, rng)
    return (
        f'<path class="canopy" d="{blob_d}" fill="url(#canopyGradient)" '
        f'opacity="0.9" />'
    )


def _render_branches_and_leaves(
    branches: list[RepoBranch], base_half_width: float
) -> str:
    if not branches:
        return ''
    elements = [
        _render_crown(base_half_width, base_half_width * TRUNK_TOP_TAPER)
    ]
    count = len(branches)
    for index, repo_branch in enumerate(branches):
        side = -1 if index % 2 == 0 else 1
        y_fraction = index / max(count - 1, 1)
        origin_y = TRUNK_TOP_Y + y_fraction * BRANCH_ZONE_HEIGHT
        origin_half_width = _half_width_at(origin_y, base_half_width)
        origin_x = TRUNK_CENTER_X + origin_half_width * side * 0.5

        length = _branch_length(repo_branch.lines_added)
        end_x, end_y = _branch_endpoint(
            origin_x, origin_y, length, side, y_fraction
        )
        base_width = _branch_width(
            repo_branch.output_tokens + repo_branch.input_tokens
        )
        curve_rng = random.Random(f'{repo_branch.repo}:curve')
        bow = length * 0.08 * side * (0.7 + 0.6 * curve_rng.random())
        root_overlap = base_width * 0.9

        shape_d = _render_branch_shape(
            origin_x,
            origin_y,
            end_x,
            end_y,
            base_width=base_width,
            tip_width=BRANCH_TIP_WIDTH,
            bow=bow,
            root_overlap=root_overlap,
        )
        outline_d = _render_branch_outline(
            origin_x,
            origin_y,
            end_x,
            end_y,
            base_width=base_width,
            tip_width=BRANCH_TIP_WIDTH,
            bow=bow,
            root_overlap=root_overlap,
        )
        total_tokens = repo_branch.output_tokens + repo_branch.input_tokens
        avg_turns = (
            repo_branch.prompts / repo_branch.sessions
            if repo_branch.sessions
            else 0.0
        )
        title = _title(
            f'{repo_branch.repo} — {repo_branch.sessions} sessions, '
            f'+{repo_branch.lines_added:,}/-{repo_branch.lines_removed:,} '
            f'lines, {total_tokens:,} tokens, ${repo_branch.cost:,.2f}, '
            f'{avg_turns:.1f} turns/session'
        )
        collar = _render_branch_collar(
            origin_x, origin_y, base_width, repo_branch.repo
        )
        branch_path = (
            f'<path class="branch" data-repo="{repo_branch.repo}" '
            f'd="{shape_d}" fill="url(#trunkGradient)" opacity="0.95" />'
            f'<path d="{outline_d}" fill="none" stroke="#3a2412" '
            f'stroke-width="0.75" stroke-linecap="round" opacity="0.95" />'
        )
        leaves = _render_leaves(repo_branch, origin_x, origin_y, end_x, end_y)
        elements.append(
            f'<g class="repo-group">{title}{collar}{branch_path}{leaves}</g>'
        )
    return ''.join(elements)


def _blob_path(
    center_x: float,
    center_y: float,
    radius: float,
    rng: random.Random,
    *,
    points: int = 9,
    jitter: float = 0.32,
) -> str:
    vertices = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        r = radius * (1 + rng.uniform(-jitter, jitter))
        vertices.append(
            (center_x + r * math.cos(angle), center_y + r * math.sin(angle))
        )
    start_mid = (
        (vertices[0][0] + vertices[-1][0]) / 2,
        (vertices[0][1] + vertices[-1][1]) / 2,
    )
    d = f'M {start_mid[0]},{start_mid[1]} '
    for i in range(points):
        p1 = vertices[i]
        p2 = vertices[(i + 1) % points]
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        d += f'Q {p1[0]},{p1[1]} {mid[0]},{mid[1]} '
    return d + 'Z'


def _canopy_radius(leaf_count: int) -> float:
    """Leaf-cluster radius, growing quickly at first then leveling off.

    A plain linear formula saturates at its cap almost immediately once a
    repo has more than ~45 sessions, which made a bursty repo's canopy
    (and every leaf scattered around it) jump to its final size on its
    first active day instead of visibly growing across days after.
    """
    saturation = min(leaf_count, LEAF_SATURATION_COUNT)
    growth = math.sqrt(saturation / LEAF_SATURATION_COUNT)
    return CANOPY_RADIUS_MIN + (CANOPY_RADIUS_MAX - CANOPY_RADIUS_MIN) * growth


def _leaf_size_multiplier(avg_turns_per_session: float) -> float:
    """Leaf-size scale for a repo with this many turns/session on average.

    Linear rather than the sqrt-saturation curve every other size formula
    here uses, because turns-per-session lives in a narrow, already
    human-scale range (roughly 1-15) instead of spanning the orders of
    magnitude that tokens or session counts do -- a saturating curve would
    flatten the real differences between repos into an almost-flat
    multiplier.
    """
    span = LEAF_TURNS_CEILING - LEAF_TURNS_FLOOR
    fraction = (avg_turns_per_session - LEAF_TURNS_FLOOR) / span
    fraction = max(0.0, min(1.0, fraction))
    return (
        LEAF_SIZE_MULTIPLIER_MIN
        + (LEAF_SIZE_MULTIPLIER_MAX - LEAF_SIZE_MULTIPLIER_MIN) * fraction
    )


def _foliage_girth_fraction(t: float) -> float:
    """0 at the start of the foliage zone, 1 by the tip.

    Leaves and blobs hug close to the branch where the greenery begins and
    billow out wider as they approach the tip.
    """
    span = FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION
    return max(0.0, min(1.0, (t - FOLIAGE_START_FRACTION) / span))


def _foliage_blob_fractions(length: float) -> list[float]:
    """Fractions-along-the-branch at which to anchor filler canopy blobs.

    More, evenly-spaced blobs for a longer branch so the greenery visibly
    bridges more of it instead of staying a single ball at the tip.
    """
    covered = length * (FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION)
    blob_count = max(
        1, min(MAX_FOLIAGE_BLOBS, round(covered / FOLIAGE_BLOB_SPACING) + 1)
    )
    if blob_count == 1:
        return [FOLIAGE_TIP_OVERHANG]
    span = FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION
    return [
        FOLIAGE_START_FRACTION + span * i / (blob_count - 1)
        for i in range(blob_count)
    ]


def _foliage_blob_relative_radii(length: float) -> list[tuple[float, float]]:
    """(fraction, radius-as-a-fraction-of-canopy_radius) per foliage blob.

    Mirrors the radius `_render_foliage_blob` actually draws at each
    fraction, so leaf placement can be weighted by real blob area instead
    of by raw along-branch position.
    """
    return [
        (
            fraction,
            0.35 + 0.65 * _foliage_girth_fraction(fraction),
        )
        for fraction in _foliage_blob_fractions(length)
    ]


def _leaf_placement(
    rng: random.Random,
    blob_relative_radii: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """A leaf's fixed (t, relative_radius, r_frac, angle) placement.

    Assigns the leaf to one of the branch's actual canopy blobs, weighted
    by that blob's area, then fixes a position inside its disk (radius
    fraction via sqrt for area-uniform density, angle over the full
    circle). Weighting by area -- rather than sampling t directly along
    the branch -- makes leaf density track how much green each blob
    actually covers, instead of piling up wherever the raw along-branch
    position happens to land. `relative_radius` and `r_frac` are kept
    separate (not pre-multiplied) so callers can rescale by a per-day
    canopy_radius during the growth timeline.
    """
    weights = [radius**2 for _, radius in blob_relative_radii]
    fraction, relative_radius = rng.choices(
        blob_relative_radii, weights=weights
    )[0]
    angle = rng.uniform(0.0, 2 * math.pi)
    r_frac = math.sqrt(rng.random())
    return fraction, relative_radius, r_frac, angle


def _leaf_offset(
    relative_radius: float,
    r_frac: float,
    angle: float,
    canopy_radius: float,
) -> tuple[float, float]:
    """A leaf's (perpendicular, along) pixel offset from its blob center."""
    radius = canopy_radius * relative_radius * r_frac
    return radius * math.cos(angle), radius * math.sin(angle)


def _render_foliage_blob(
    origin_x: float,
    origin_y: float,
    dx: float,
    dy: float,
    *,
    fraction: float,
    canopy_radius: float,
    seed: str,
) -> str:
    girth = _foliage_girth_fraction(fraction)
    blob_radius = canopy_radius * (0.35 + 0.65 * girth)
    cx = origin_x + fraction * dx
    cy = origin_y + fraction * dy
    shadow_d = _blob_path(
        cx + blob_radius * 0.18,
        cy + blob_radius * 0.22,
        blob_radius * 0.92,
        random.Random(f'{seed}:shadow'),
    )
    main_d = _blob_path(cx, cy, blob_radius, random.Random(f'{seed}:canopy'))
    return (
        f'<path class="canopy" d="{shadow_d}" fill="#2f5f2f" '
        f'opacity="0.3" filter="url(#softBlur)" />'
        f'<path class="canopy" d="{main_d}" fill="url(#canopyGradient)" '
        f'opacity="0.9" />'
    )


def _render_leaves(
    repo_branch: RepoBranch,
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
) -> str:
    leaf_count = repo_branch.sessions * LEAVES_PER_SESSION
    if leaf_count == 0:
        return ''
    rng = random.Random(repo_branch.repo)
    elements = []

    avg_turns = (
        repo_branch.prompts / repo_branch.sessions
        if repo_branch.sessions
        else 0.0
    )
    size_multiplier = _leaf_size_multiplier(avg_turns)

    dx, dy = end_x - origin_x, end_y - origin_y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    canopy_radius = _canopy_radius(leaf_count)
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    blob_relative_radii = (
        _foliage_blob_relative_radii(length) if has_canopy else []
    )
    if has_canopy:
        for fraction, _ in blob_relative_radii:
            elements.append(
                _render_foliage_blob(
                    origin_x,
                    origin_y,
                    dx,
                    dy,
                    fraction=fraction,
                    canopy_radius=canopy_radius,
                    seed=f'{repo_branch.repo}:{fraction:.3f}',
                )
            )

    for _ in range(leaf_count):
        if has_canopy:
            t, relative_radius, r_frac, blob_angle = _leaf_placement(
                rng, blob_relative_radii
            )
            perp_offset, along_offset = _leaf_offset(
                relative_radius, r_frac, blob_angle, canopy_radius
            )
        else:
            t = rng.uniform(FOLIAGE_START_FRACTION, FOLIAGE_TIP_OVERHANG)
            blob_angle = rng.uniform(0.0, 2 * math.pi)
            scatter_r = LEAF_SCATTER_RADIUS * 0.4 * math.sqrt(rng.random())
            perp_offset = scatter_r * math.cos(blob_angle)
            along_offset = scatter_r * math.sin(blob_angle)
        cx = origin_x + t * dx
        cy = origin_y + t * dy
        leaf_x = cx + px * perp_offset + ux * along_offset
        leaf_y = cy + py * perp_offset + uy * along_offset
        radius = (
            max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5) * size_multiplier
        )
        angle = rng.uniform(0, 360)
        color = rng.choice(LEAF_COLORS)
        elements.append(
            f'<g class="leaf" transform="translate({leaf_x:.1f},{leaf_y:.1f}) '
            f'rotate({angle:.1f}) scale({radius:.2f})">'
            f'<path d="{LEAF_SHAPE_D}" fill="{color}" opacity="0.92" />'
            f'<path d="{LEAF_VEIN_D}" stroke="#2f5f2f" stroke-width="0.12" '
            f'opacity="0.5" />'
            f'</g>'
        )
    return ''.join(elements)


LEGEND_MARGIN = 4.0
LEGEND_Y = GROUND_Y + LEGEND_MARGIN
LEGEND_HEIGHT = VIEWBOX_HEIGHT - GROUND_Y - LEGEND_MARGIN * 2
LEGEND_X = 14.0
LEGEND_WIDTH = VIEWBOX_WIDTH - LEGEND_X * 2
LEGEND_PADDING = 10.0
LEGEND_ROWS = (
    ('Trunk', ('width grows with', 'total sessions'), 'trunk'),
    ('Rings', ('one per day worked;', 'bolder = busier day'), 'ring'),
    (
        'Branches',
        ('one per repo', 'longer = more lines;', 'thicker = more tokens'),
        'branch',
    ),
    (
        'Leaves',
        ('one per session;', 'more = busier repo;', 'bigger = deeper turns'),
        'leaf',
    ),
    (
        'Flowers',
        ('one per whole ratio of', 'cache reads to writes'),
        'flower',
    ),
    (
        'Clouds',
        ('one per model used;', 'bigger = more tokens'),
        'cloud',
    ),
    (
        'Bushes',
        ('one per tool used;', 'bigger = used more'),
        'bush',
    ),
)


def _legend_icon_trunk(cx: float, cy: float) -> str:
    return (
        f'<rect x="{cx - 6:.1f}" y="{cy - 7:.1f}" width="12" height="14" '
        f'rx="3" fill="url(#trunkGradient)" stroke="#3a2412" '
        f'stroke-width="0.6" />'
    )


def _legend_icon_ring(cx: float, cy: float) -> str:
    return (
        f'<path d="M{cx - 7:.1f},{cy + 3:.1f} Q{cx:.1f},{cy - 5:.1f} '
        f'{cx + 7:.1f},{cy + 3:.1f}" fill="none" stroke="#3a2412" '
        f'stroke-width="2.2" stroke-linecap="round" opacity="0.6" />'
    )


def _legend_icon_branch(cx: float, cy: float) -> str:
    return (
        f'<path d="M{cx - 7:.1f},{cy + 7:.1f} Q{cx:.1f},{cy - 2:.1f} '
        f'{cx + 7:.1f},{cy - 7:.1f}" fill="none" '
        f'stroke="url(#trunkGradient)" stroke-width="3" '
        f'stroke-linecap="round" />'
    )


def _legend_icon_leaf(cx: float, cy: float) -> str:
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f}) rotate(-15) scale(6)">'
        f'<path d="{LEAF_SHAPE_D}" fill="#5a9e5a" opacity="0.95" />'
        f'</g>'
    )


def _legend_icon_flower(cx: float, cy: float) -> str:
    return _render_flower(
        cx, cy, 6.0, '#f27ab0', random.Random('legend-flower')
    )


def _legend_icon_cloud(cx: float, cy: float) -> str:
    return _render_cloud(cx, cy, 7.0, 'legend-cloud')


def _legend_icon_bush(cx: float, cy: float) -> str:
    return _render_bush(cx, cy + 5.0, 7.0, 'legend-bush')


LEGEND_ICON_RENDERERS = {
    'trunk': _legend_icon_trunk,
    'ring': _legend_icon_ring,
    'branch': _legend_icon_branch,
    'leaf': _legend_icon_leaf,
    'flower': _legend_icon_flower,
    'cloud': _legend_icon_cloud,
    'bush': _legend_icon_bush,
}


def _render_legend_icon(icon: str, cx: float, cy: float) -> str:
    return LEGEND_ICON_RENDERERS[icon](cx, cy)


def _render_legend() -> str:
    """A key strip explaining what each part of the tree represents.

    Runs the full width along the bottom, below the ground line -- every
    other part of the tree (trunk, rings, branches, leaves) sits above
    GROUND_Y, so a strip confined to the margin below it can never overlap
    them, unlike a panel placed somewhere over the canopy.
    """
    column_width = LEGEND_WIDTH / len(LEGEND_ROWS)
    row_cy = LEGEND_Y + LEGEND_HEIGHT / 2
    parts = [
        (
            f'<g class="legend">'
            f'<rect x="{LEGEND_X:.1f}" y="{LEGEND_Y:.1f}" '
            f'width="{LEGEND_WIDTH:.1f}" height="{LEGEND_HEIGHT:.1f}" rx="8" '
            f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.88" />'
        )
    ]
    for index, (label, desc_lines, icon) in enumerate(LEGEND_ROWS):
        col_x = LEGEND_X + column_width * index
        icon_cx = col_x + LEGEND_PADDING + 8
        text_x = col_x + LEGEND_PADDING + 20
        parts.append(_render_legend_icon(icon, icon_cx, row_cy - 2))
        parts.append(
            f'<text x="{text_x:.1f}" y="{row_cy - 9:.1f}" '
            f'font-family="Georgia, serif" font-size="10" '
            f'font-weight="bold" fill="#2f3b23">{label}</text>'
        )
        for line_index, desc_line in enumerate(desc_lines):
            line_y = row_cy + 2 + line_index * 9
            parts.append(
                f'<text x="{text_x:.1f}" y="{line_y:.1f}" '
                f'font-family="Georgia, serif" font-size="8.2" '
                f'fill="#4a4a3a">{desc_line}</text>'
            )
    parts.append('</g>')
    return ''.join(parts)


def render_svg(garden: GardenData) -> str:
    total_sessions = sum(day_ring.sessions for day_ring in garden.rings)
    base_half_width = _trunk_half_width(total_sessions)
    flower_count = _cache_efficiency_flower_count(
        garden.cache_read_tokens, garden.cache_write_tokens
    )

    bush_footprints = _bush_footprints(garden.tools)
    trunk_title = _title(f'Trunk — {total_sessions} total sessions')

    body = (
        _render_clouds(garden.model_efforts)
        + f'<g class="trunk-group">{trunk_title}'
        f'{_render_trunk(base_half_width)}</g>'
        + _render_rings(garden.rings, base_half_width)
        + _render_branches_and_leaves(garden.branches, base_half_width)
        + _render_bushes(garden.tools)
        + _render_flowers_on_bushes(
            flower_count,
            bush_footprints,
            garden.cache_read_tokens,
            garden.cache_write_tokens,
        )
        + _render_legend()
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {VIEWBOX_HEIGHT}" '
        f'width="{VIEWBOX_WIDTH}" height="{VIEWBOX_HEIGHT}">'
        f'{_render_defs()}'
        f'{_render_background()}'
        f'{body}'
        f'</svg>'
    )


# --- timeline (growth-over-time) rendering -----------------------------
#
# Renders the same tree, but with every shape's `d` (or opacity/stroke-
# width) driven by a native SMIL <animate> that replays real day-by-day
# cumulative history from the sqlite db: the trunk widens, branches
# lengthen, and canopy blobs swell exactly in step with the sessions that
# actually happened on each day, while rings and leaves step into view on
# the calendar day they were earned. The base (non-animated) attribute on
# every element is always the final, fully-grown value, so a viewer with
# no SMIL support just sees the finished tree instead of nothing.


def _timeline_duration(day_count: int) -> float:
    return min(
        max(day_count * TIMELINE_PER_DAY_SECONDS, TIMELINE_MIN_DURATION_S),
        TIMELINE_MAX_DURATION_S,
    )


def _key_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


def _animate_tag(
    attribute: str,
    values: list[str],
    key_times: list[float],
    duration: float,
) -> str:
    return (
        f'<animate attributeName="{attribute}" dur="{duration:.3f}s" '
        f'begin="0s" fill="freeze" calcMode="linear" '
        f'keyTimes="{";".join(f"{t:.4f}" for t in key_times)}" '
        f'values="{";".join(values)}" />'
    )


def _animate_transform_tag(
    transform_type: str,
    values: list[str],
    key_times: list[float],
    duration: float,
) -> str:
    return (
        f'<animateTransform attributeName="transform" '
        f'type="{transform_type}" dur="{duration:.3f}s" '
        f'begin="0s" fill="freeze" calcMode="linear" '
        f'keyTimes="{";".join(f"{t:.4f}" for t in key_times)}" '
        f'values="{";".join(values)}" />'
    )


def _trunk_path_d(base_half_width: float) -> str:
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    cx = TRUNK_CENTER_X
    lean = base_half_width * 0.1
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    top_shoulder_y = TRUNK_TOP_Y + top_half_width * 0.5
    dome_y = TRUNK_TOP_Y - top_half_width * 0.35
    left_ctrl_x = cx - (base_half_width + top_half_width) / 2 - lean
    right_ctrl_x = cx + (base_half_width + top_half_width) / 2 + lean
    return (
        f'M {cx - base_half_width:.2f},{GROUND_Y} '
        f'Q {left_ctrl_x:.2f},{mid_y:.2f} '
        f'{cx - top_half_width:.2f},{top_shoulder_y:.2f} '
        f'Q {cx:.2f},{dome_y:.2f} '
        f'{cx + top_half_width:.2f},{top_shoulder_y:.2f} '
        f'Q {right_ctrl_x:.2f},{mid_y:.2f} '
        f'{cx + base_half_width:.2f},{GROUND_Y} '
        f'Z'
    )


def _bark_stripe_d(
    base_half_width: float,
    top_half_width: float,
    x_offset: float,
    jitter: float,
) -> str:
    cx = TRUNK_CENTER_X
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    top_x = cx + x_offset * top_half_width
    base_x = cx + x_offset * base_half_width
    return (
        f'M{base_x:.2f},{GROUND_Y - 8} '
        f'Q{(base_x + top_x) / 2 + jitter:.2f},{mid_y:.2f} '
        f'{top_x:.2f},{TRUNK_TOP_Y + 10}'
    )


def _render_timeline_trunk(
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    d_values = [_trunk_path_d(width) for width in base_half_width_by_day]
    animate = _animate_tag('d', d_values, key_times, duration)
    trunk = (
        f'<path class="trunk" d="{d_values[-1]}" fill="url(#trunkGradient)" '
        f'stroke="#3a2412" stroke-width="1.5" stroke-linejoin="round">'
        f'{animate}</path>'
    )
    bark = _render_timeline_bark(base_half_width_by_day, key_times, duration)
    return trunk + bark


def _render_timeline_bark(
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    rng = random.Random('ccgarden-bark')
    elements = []
    for x_offset in (-0.32, 0.4):
        jitter = rng.uniform(-2, 2)
        d_values = [
            _bark_stripe_d(width, width * TRUNK_TOP_TAPER, x_offset, jitter)
            for width in base_half_width_by_day
        ]
        animate = _animate_tag('d', d_values, key_times, duration)
        elements.append(
            f'<path d="{d_values[-1]}" fill="none" stroke="#3a2412" '
            f'stroke-width="1" opacity="0.22">{animate}</path>'
        )
    return ''.join(elements)


def _render_timeline_rings(
    timeline: GardenTimeline,
    final_base_half_width: float,
    key_times: list[float],
    duration: float,
) -> str:
    day_count = len(timeline.days)
    if day_count == 0:
        return ''
    elements = []
    for index, sessions in enumerate(timeline.daily_sessions):
        y = GROUND_Y - (index + 1) / (day_count + 1) * TRUNK_HEIGHT
        half_width = _half_width_at(y, final_base_half_width) * 0.85
        cx = TRUNK_CENTER_X
        bow = half_width * 0.1
        target_width = _ring_stroke_width(sessions)
        d = (
            f'M {cx - half_width:.2f},{y:.2f} '
            f'Q {cx:.2f},{y - bow:.2f} {cx + half_width:.2f},{y:.2f}'
        )
        width_values = [
            f'{target_width:.3f}' if i >= index else '0'
            for i in range(day_count)
        ]
        animate = _animate_tag(
            'stroke-width', width_values, key_times, duration
        )
        title = _title(
            f'{_format_day(timeline.days[index])} — {sessions} sessions'
        )
        elements.append(
            f'<path class="ring" d="{d}" fill="none" stroke="#3a2412" '
            f'stroke-width="{target_width:.3f}" stroke-linecap="round" '
            f'opacity="0.22">{title}{animate}</path>'
        )
    return ''.join(elements)


def _render_timeline_crown(
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    cx = TRUNK_CENTER_X
    d_values = []
    for width in base_half_width_by_day:
        top_half_width = width * TRUNK_TOP_TAPER
        cy = TRUNK_TOP_Y - top_half_width * 0.2
        radius = max(width * 1.15, 22.0)
        d_values.append(
            _blob_path(cx, cy, radius, random.Random('ccgarden-crown'))
        )
    animate = _animate_tag('d', d_values, key_times, duration)
    return (
        f'<path class="canopy" d="{d_values[-1]}" fill="url(#canopyGradient)" '
        f'opacity="0.9">{animate}</path>'
    )


def _render_timeline_branches_and_leaves(
    timeline: GardenTimeline,
    final_base_half_width: float,
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.branch_order:
        return ''

    elements = [
        _render_timeline_crown(base_half_width_by_day, key_times, duration)
    ]
    count = len(timeline.branch_order)
    for index, repo in enumerate(timeline.branch_order):
        side = -1 if index % 2 == 0 else 1
        y_fraction = index / max(count - 1, 1)
        origin_y = TRUNK_TOP_Y + y_fraction * BRANCH_ZONE_HEIGHT
        origin_half_width = _half_width_at(origin_y, final_base_half_width)
        origin_x = TRUNK_CENTER_X + origin_half_width * side * 0.5
        bow_factor = random.Random(f'{repo}:curve').random()

        days = timeline.branch_days[repo]
        final_lines_added = days[-1].lines_added
        final_tokens = days[-1].output_tokens + days[-1].input_tokens
        final_length = _branch_length(final_lines_added)
        final_width = _branch_width(final_tokens)

        collar_rng_seed = f'{repo}:collar'
        d_values = []
        outline_d_values = []
        collar_d_values = []
        day_vectors: list[tuple[float, float]] = []
        for day_stat in days:
            if day_stat.sessions == 0:
                d_values.append(
                    _render_branch_shape(
                        origin_x,
                        origin_y,
                        origin_x,
                        origin_y,
                        base_width=0.0,
                        tip_width=0.0,
                        bow=0.0,
                    )
                )
                outline_d_values.append(
                    _render_branch_outline(
                        origin_x,
                        origin_y,
                        origin_x,
                        origin_y,
                        base_width=0.0,
                        tip_width=0.0,
                        bow=0.0,
                    )
                )
                collar_d_values.append(
                    _blob_path(
                        origin_x,
                        origin_y,
                        0.01,
                        random.Random(collar_rng_seed),
                        points=7,
                        jitter=0.3,
                    )
                )
                day_vectors.append((0.0, 0.0))
                continue
            # Grown as a share of the *final* length/width, not the same
            # absolute-lines_added formula re-evaluated per day -- that
            # formula saturates at BRANCH_LENGTH_MAX almost immediately
            # for a single big-diff day, which made the branch (and every
            # leaf anchored to its tip) jump straight to its final size on
            # day one instead of visibly growing across the days after.
            length_fraction = (
                min(day_stat.lines_added / final_lines_added, 1.0)
                if final_lines_added
                else 1.0
            )
            day_tokens = day_stat.output_tokens + day_stat.input_tokens
            width_fraction = (
                min(day_tokens / final_tokens, 1.0) if final_tokens else 1.0
            )
            length = (
                BRANCH_LENGTH_MIN
                + (final_length - BRANCH_LENGTH_MIN) * length_fraction
            )
            end_x, end_y = _branch_endpoint(
                origin_x, origin_y, length, side, y_fraction
            )
            base_width = (
                BRANCH_WIDTH_MIN
                + (final_width - BRANCH_WIDTH_MIN) * width_fraction
            )
            bow = length * 0.08 * side * (0.7 + 0.6 * bow_factor)
            root_overlap = base_width * 0.9
            d_values.append(
                _render_branch_shape(
                    origin_x,
                    origin_y,
                    end_x,
                    end_y,
                    base_width=base_width,
                    tip_width=BRANCH_TIP_WIDTH,
                    bow=bow,
                    root_overlap=root_overlap,
                )
            )
            outline_d_values.append(
                _render_branch_outline(
                    origin_x,
                    origin_y,
                    end_x,
                    end_y,
                    base_width=base_width,
                    tip_width=BRANCH_TIP_WIDTH,
                    bow=bow,
                    root_overlap=root_overlap,
                )
            )
            collar_d_values.append(
                _blob_path(
                    origin_x,
                    origin_y,
                    max(base_width * 2.2, 6.0),
                    random.Random(collar_rng_seed),
                    points=7,
                    jitter=0.3,
                )
            )
            day_vectors.append((end_x - origin_x, end_y - origin_y))

        animate = _animate_tag('d', d_values, key_times, duration)
        outline_animate = _animate_tag(
            'd', outline_d_values, key_times, duration
        )
        collar_animate = _animate_tag(
            'd', collar_d_values, key_times, duration
        )
        final_day = days[-1]
        final_day_tokens = final_day.output_tokens + final_day.input_tokens
        final_avg_turns = (
            final_day.prompts / final_day.sessions
            if final_day.sessions
            else 0.0
        )
        title = _title(
            f'{repo} — {final_day.sessions} sessions, '
            f'+{final_day.lines_added:,}/-{final_day.lines_removed:,} '
            f'lines, {final_day_tokens:,} tokens, ${final_day.cost:,.2f}, '
            f'{final_avg_turns:.1f} turns/session'
        )
        collar = (
            f'<path class="branch-collar" d="{collar_d_values[-1]}" '
            f'fill="url(#trunkGradient)" opacity="0.9" '
            f'filter="url(#softBlur)">{collar_animate}</path>'
        )
        branch_path = (
            f'<path class="branch" data-repo="{repo}" d="{d_values[-1]}" '
            f'fill="url(#trunkGradient)" opacity="0.95">{animate}</path>'
            f'<path d="{outline_d_values[-1]}" fill="none" '
            f'stroke="#3a2412" stroke-width="0.75" stroke-linecap="round" '
            f'opacity="0.95">{outline_animate}</path>'
        )
        leaves = _render_timeline_leaves(
            repo,
            days,
            origin_x,
            origin_y,
            day_vectors,
            final_length=final_length,
            key_times=key_times,
            duration=duration,
        )
        elements.append(
            f'<g class="repo-group">{title}{collar}{branch_path}{leaves}</g>'
        )
    return ''.join(elements)


def _render_timeline_leaves(  # noqa: PLR0915
    repo: str,
    days: list[RepoBranchDay],
    origin_x: float,
    origin_y: float,
    day_vectors: list[tuple[float, float]],
    *,
    final_length: float,
    key_times: list[float],
    duration: float,
) -> str:
    # A branch's direction is fixed once chosen (only its length grows day
    # to day), so the unit vectors from the *final* vector describe every
    # day's branch equally well.
    final_dx, final_dy = day_vectors[-1]
    final_length = math.hypot(final_dx, final_dy) or final_length or 1.0
    ux, uy = final_dx / final_length, final_dy / final_length
    px, py = -uy, ux

    day_count = len(days)
    leaf_count = days[-1].sessions * LEAVES_PER_SESSION
    if leaf_count == 0:
        return ''

    final_day = days[-1]
    avg_turns = (
        final_day.prompts / final_day.sessions if final_day.sessions else 0.0
    )
    size_multiplier = _leaf_size_multiplier(avg_turns)

    elements = []
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    day_canopy_radius = [
        _canopy_radius(day_stat.sessions * LEAVES_PER_SESSION)
        if day_stat.sessions * LEAVES_PER_SESSION >= CANOPY_MIN_LEAVES
        else 0.0
        for day_stat in days
    ]
    blob_relative_radii = (
        _foliage_blob_relative_radii(final_length) if has_canopy else []
    )

    if has_canopy:
        for fraction in _foliage_blob_fractions(final_length):
            girth = _foliage_girth_fraction(fraction)
            shadow_values = []
            main_values = []
            for day_index, (dx, dy) in enumerate(day_vectors):
                cx = origin_x + fraction * dx
                cy = origin_y + fraction * dy
                blob_radius = day_canopy_radius[day_index] * (
                    0.35 + 0.65 * girth
                )
                shadow_values.append(
                    _blob_path(
                        cx + blob_radius * 0.18,
                        cy + blob_radius * 0.22,
                        blob_radius * 0.92,
                        random.Random(f'{repo}:{fraction:.3f}:shadow'),
                    )
                )
                main_values.append(
                    _blob_path(
                        cx,
                        cy,
                        blob_radius,
                        random.Random(f'{repo}:{fraction:.3f}:canopy'),
                    )
                )
            shadow_animate = _animate_tag(
                'd', shadow_values, key_times, duration
            )
            main_animate = _animate_tag('d', main_values, key_times, duration)
            elements.append(
                f'<path class="canopy" d="{shadow_values[-1]}" '
                f'fill="#2f5f2f" opacity="0.3" '
                f'filter="url(#softBlur)">{shadow_animate}</path>'
            )
            elements.append(
                f'<path class="canopy" d="{main_values[-1]}" '
                f'fill="url(#canopyGradient)" opacity="0.9">'
                f'{main_animate}</path>'
            )

    rng = random.Random(f'{repo}:leaves')
    for leaf_index in range(leaf_count):
        if has_canopy:
            t, relative_radius, r_frac, blob_angle = _leaf_placement(
                rng, blob_relative_radii
            )
        else:
            t = rng.uniform(FOLIAGE_START_FRACTION, FOLIAGE_TIP_OVERHANG)
            blob_angle = rng.uniform(0.0, 2 * math.pi)
        radius = (
            max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5) * size_multiplier
        )
        angle = rng.uniform(0, 360)
        color = rng.choice(LEAF_COLORS)

        # Track the branch's position every day, not just on the day this
        # leaf appears -- otherwise the leaf fades in already sitting at its
        # (eventual) resting spot while the branch under it is still
        # visibly mid-growth, instead of riding the tip out with it.
        positions = []
        for day_index, (dx, dy) in enumerate(day_vectors):
            cx = origin_x + t * dx
            cy = origin_y + t * dy
            if has_canopy:
                perp_offset, along_offset = _leaf_offset(
                    relative_radius,
                    r_frac,
                    blob_angle,
                    day_canopy_radius[day_index],
                )
            else:
                scatter_r = LEAF_SCATTER_RADIUS * 0.4
                perp_offset = scatter_r * math.cos(blob_angle)
                along_offset = scatter_r * math.sin(blob_angle)
            positions.append(
                (
                    cx + px * perp_offset + ux * along_offset,
                    cy + py * perp_offset + uy * along_offset,
                )
            )

        final_x, final_y = positions[-1]
        translate_values = [f'{x:.1f},{y:.1f}' for x, y in positions]
        translate_animate = _animate_transform_tag(
            'translate', translate_values, key_times, duration
        )

        birth_index = next(
            (
                i
                for i, day_stat in enumerate(days)
                if day_stat.sessions * LEAVES_PER_SESSION > leaf_index
            ),
            day_count - 1,
        )
        opacity_values = [
            '1' if i >= birth_index else '0' for i in range(day_count)
        ]
        opacity_animate = _animate_tag(
            'opacity', opacity_values, key_times, duration
        )
        elements.append(
            f'<g class="leaf" '
            f'transform="translate({final_x:.1f},{final_y:.1f})">'
            f'{translate_animate}'
            f'<g transform="rotate({angle:.1f}) scale({radius:.2f})" '
            f'opacity="1">'
            f'<path d="{LEAF_SHAPE_D}" fill="{color}" opacity="0.92" />'
            f'<path d="{LEAF_VEIN_D}" stroke="#2f5f2f" stroke-width="0.12" '
            f'opacity="0.5" />'
            f'{opacity_animate}'
            f'</g>'
            f'</g>'
        )
    return ''.join(elements)


def _render_timeline_clouds(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.model_effort_order:
        return ''

    positions = _cloud_positions(len(timeline.model_effort_order))
    elements = []
    for (cx, cy), model in zip(
        positions, timeline.model_effort_order, strict=True
    ):
        days = timeline.model_effort_days[model]
        final_tokens = days[-1].output_tokens + days[-1].input_tokens
        final_radius = _cloud_radius(final_tokens)

        # Grown as a share of the model's *final* radius, not the same
        # absolute-tokens formula re-evaluated per day -- see the identical
        # reasoning in `_render_timeline_branches_and_leaves`.
        scale_values = []
        for day_stat in days:
            day_tokens = day_stat.output_tokens + day_stat.input_tokens
            fraction = (
                min(day_tokens / final_tokens, 1.0) if final_tokens else 1.0
            )
            day_radius = (
                CLOUD_RADIUS_MIN + (final_radius - CLOUD_RADIUS_MIN) * fraction
            )
            scale_values.append(f'{day_radius / final_radius:.4f}')

        animate = _animate_transform_tag(
            'scale', scale_values, key_times, duration
        )
        puffs = ''.join(
            f'<path d="{d}" fill="url(#cloudGradient)" opacity="0.88" />'
            for d in _cloud_puffs_d(final_radius, model)
        )
        title = _title(f'{model} — {final_tokens:,} tokens')
        elements.append(
            f'<g class="cloud" transform="translate({cx:.1f},{cy:.1f})">'
            f'{title}<g transform="scale(1)">{animate}{puffs}</g>'
            f'</g>'
        )
    return ''.join(elements)


def _bush_day_radii(
    days: list[ToolUsageDay], final_radius: float
) -> list[float]:
    """Per-day bush radius, grown as a share of the tool's *final* radius.

    Not the same absolute-count formula re-evaluated per day -- see the
    identical reasoning in `_render_timeline_branches_and_leaves`.
    """
    final_count = days[-1].count
    radii = []
    for day_stat in days:
        fraction = (
            min(day_stat.count / final_count, 1.0) if final_count else 1.0
        )
        radii.append(
            BUSH_RADIUS_MIN + (final_radius - BUSH_RADIUS_MIN) * fraction
        )
    return radii


def _render_timeline_bushes(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.tool_order:
        return ''

    tool_order = timeline.tool_order[:MAX_BUSHES]
    xs = _bush_x_positions(len(tool_order))
    elements = []
    for x, tool in zip(xs, tool_order, strict=True):
        days = timeline.tool_days[tool]
        final_radius = _bush_radius(days[-1].count)
        day_radii = _bush_day_radii(days, final_radius)

        scale_values = [f'{r / final_radius:.4f}' for r in day_radii]
        animate = _animate_transform_tag(
            'scale', scale_values, key_times, duration
        )
        puffs = ''.join(
            f'<path d="{d}" fill="url(#bushGradient)" opacity="0.94" />'
            for d in _bush_puffs_d(final_radius, tool)
        )
        title = _title(f'{tool} — used {days[-1].count:,} times')
        elements.append(
            f'<g class="bush" transform="translate({x:.1f},{GROUND_Y})">'
            f'{title}<g transform="scale(1)">{animate}{puffs}</g>'
            f'</g>'
        )
    return ''.join(elements)


def _render_timeline_flowers_on_bushes(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    """Flowers riding each bush's growth, fading in as cache efficiency grows.

    Mirrors `_render_timeline_leaves`: a flower's height above the ground
    tracks its bush's radius *on that day*, not the bush's eventual size,
    so it doesn't start already floating above a bush that hasn't grown
    that tall yet. It also fades in on the day the running cache-read/
    write ratio first reaches its index, the same birth_index approach
    leaves use for a count that grows over the timeline.
    """
    final_flower_count = _cache_efficiency_flower_count(
        timeline.cache_read_tokens, timeline.cache_write_tokens
    )
    tool_order = timeline.tool_order[:MAX_BUSHES]
    day_count = len(timeline.days)
    if (
        final_flower_count <= 0
        or not tool_order
        or len(timeline.cumulative_cache_read) != day_count
        or len(timeline.cumulative_cache_write) != day_count
    ):
        return ''

    xs = _bush_x_positions(len(tool_order))
    bush_day_radii = []
    for tool in tool_order:
        days = timeline.tool_days[tool]
        final_radius = _bush_radius(days[-1].count)
        bush_day_radii.append(_bush_day_radii(days, final_radius))

    day_flower_counts = [
        _cache_efficiency_flower_count(read, write)
        for read, write in zip(
            timeline.cumulative_cache_read,
            timeline.cumulative_cache_write,
            strict=True,
        )
    ]

    title = _title(
        f'Cache efficiency — {timeline.cache_read_tokens:,} cache reads per '
        f'{timeline.cache_write_tokens:,} cache writes'
    )
    rng = random.Random('ccgarden-flowers')
    elements = []
    for index in range(final_flower_count):
        bush_index = index % len(tool_order)
        bush_x = xs[bush_index]
        day_radii = bush_day_radii[bush_index]

        angle = rng.uniform(0, 2 * math.pi)
        dist_frac = rng.uniform(0.0, 0.7)
        size = FLOWER_RADIUS * rng.uniform(0.6, 0.9)
        color = rng.choice(FLOWER_COLORS)

        positions = [
            (
                bush_x + day_radius * dist_frac * math.cos(angle),
                GROUND_Y
                - day_radius * 0.6
                + day_radius * dist_frac * math.sin(angle) * 0.6,
            )
            for day_radius in day_radii
        ]

        final_x, final_y = positions[-1]
        translate_values = [f'{x:.1f},{y:.1f}' for x, y in positions]
        translate_animate = _animate_transform_tag(
            'translate', translate_values, key_times, duration
        )

        birth_index = next(
            (i for i, count in enumerate(day_flower_counts) if count > index),
            day_count - 1,
        )
        opacity_values = [
            '1' if i >= birth_index else '0' for i in range(day_count)
        ]
        opacity_animate = _animate_tag(
            'opacity', opacity_values, key_times, duration
        )
        flower = _render_flower(0, 0, size, color, rng)
        elements.append(
            f'<g class="flower" '
            f'transform="translate({final_x:.1f},{final_y:.1f})" '
            f'opacity="1">'
            f'{title}{translate_animate}{opacity_animate}{flower}'
            f'</g>'
        )
    return ''.join(elements)


def _timeline_final_garden(timeline: GardenTimeline) -> GardenData:
    """The tree's final state, for the fallback when there's <2 days."""
    rings = [
        DayRing(day=day, sessions=sessions, lines_added=0, lines_removed=0)
        for day, sessions in zip(
            timeline.days, timeline.daily_sessions, strict=True
        )
    ]
    branches = [
        RepoBranch(
            repo=repo,
            sessions=timeline.branch_days[repo][-1].sessions,
            lines_added=timeline.branch_days[repo][-1].lines_added,
            lines_removed=timeline.branch_days[repo][-1].lines_removed,
            output_tokens=timeline.branch_days[repo][-1].output_tokens,
            input_tokens=timeline.branch_days[repo][-1].input_tokens,
            cost=timeline.branch_days[repo][-1].cost,
        )
        for repo in timeline.branch_order
    ]
    model_efforts = [
        ModelCloud(
            model=label,
            output_tokens=timeline.model_effort_days[label][-1].output_tokens,
            input_tokens=timeline.model_effort_days[label][-1].input_tokens,
        )
        for label in timeline.model_effort_order
    ]
    tools = [
        ToolBush(tool=tool, count=timeline.tool_days[tool][-1].count)
        for tool in timeline.tool_order
    ]
    return GardenData(
        rings=rings,
        branches=branches,
        cache_read_tokens=timeline.cache_read_tokens,
        cache_write_tokens=timeline.cache_write_tokens,
        model_efforts=model_efforts,
        tools=tools,
    )


def _render_scrubber(
    timeline: GardenTimeline, key_times: list[float], duration: float
) -> str:
    """A ground-strip slider that seeks the timelapse's own SMIL clock.

    Every `<animate>`/`<animateTransform>` the timeline renders shares this
    same `key_times`/`duration` pair (see `render_timeline_svg`), so a single
    document-time value fully determines every element's frame -- scrubbing
    is just `svg.pauseAnimations()` once, then `svg.setCurrentTime(t)` per
    drag, with no separate day-state to keep in sync. Stays hidden and
    non-interactive until the initial playthrough finishes, per the request
    to add the scrubber *after* the animation rather than replacing it.
    """
    day_count = len(timeline.days)
    day_labels = [_format_day(day) for day in timeline.days]
    key_times_js = '[' + ','.join(f'{t:.4f}' for t in key_times) + ']'
    day_labels_js = (
        '[' + ','.join(f'"{_escape_xml(label)}"' for label in day_labels) + ']'
    )

    panel_x = LEGEND_X
    panel_width = LEGEND_WIDTH
    ground_fill = (
        f'<rect x="0" y="{VIEWBOX_HEIGHT:.1f}" width="{VIEWBOX_WIDTH:.1f}" '
        f'height="{SCRUBBER_TOTAL_HEIGHT:.1f}" fill="#3f7a3f" />'
    )
    panel = (
        f'<rect x="{panel_x:.1f}" y="{SCRUBBER_Y:.1f}" '
        f'width="{panel_width:.1f}" height="{SCRUBBER_HEIGHT:.1f}" rx="8" '
        f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" opacity="0.88" />'
    )
    foreign = (
        f'<foreignObject x="{panel_x + 14:.1f}" y="{SCRUBBER_Y + 5:.1f}" '
        f'width="{panel_width - 28:.1f}" height="{SCRUBBER_HEIGHT - 10:.1f}">'
        '<div xmlns="http://www.w3.org/1999/xhtml" '
        'style="font-family: Georgia, serif; color: #2f3b23; '
        'display: flex; align-items: center; gap: 10px; height: 100%;">'
        '<span style="font-size: 9px; opacity: 0.75; white-space: nowrap;">'
        'Time travel</span>'
        '<input id="ccgarden-scrubber-input" type="range" '
        f'min="0" max="{day_count - 1}" value="{day_count - 1}" step="1" '
        'style="flex: 1;" />'
        '<span id="ccgarden-scrubber-label" '
        'style="font-size: 11px; font-weight: bold; white-space: nowrap;">'
        f'{_escape_xml(day_labels[-1])}</span>'
        '</div>'
        '</foreignObject>'
    )
    group = (
        f'<g id="ccgarden-scrubber" '
        f'style="opacity:0;pointer-events:none;transition:opacity 0.6s ease;">'
        f'{panel}{foreign}</g>'
    )
    script = (
        '<script><![CDATA[\n'
        '(function () {\n'
        '  var svg = document.documentElement;\n'
        '  var group = document.getElementById("ccgarden-scrubber");\n'
        '  var input = document.getElementById("ccgarden-scrubber-input");\n'
        '  var label = document.getElementById("ccgarden-scrubber-label");\n'
        f'  var duration = {duration:.4f};\n'
        f'  var keyTimes = {key_times_js};\n'
        f'  var dayLabels = {day_labels_js};\n'
        '  var paused = false;\n'
        '  function reveal() {\n'
        '    group.style.opacity = "1";\n'
        '    group.style.pointerEvents = "auto";\n'
        '  }\n'
        '  function seek(dayIndex) {\n'
        '    if (!paused) { svg.pauseAnimations(); paused = true; }\n'
        '    svg.setCurrentTime(keyTimes[dayIndex] * duration);\n'
        '    label.textContent = dayLabels[dayIndex];\n'
        '  }\n'
        '  input.addEventListener("input", function () {\n'
        '    seek(parseInt(input.value, 10));\n'
        '  });\n'
        '  window.setTimeout(reveal, duration * 1000 + 150);\n'
        '})();\n'
        ']]></script>'
    )
    return ground_fill + group + script


def render_timeline_svg(timeline: GardenTimeline) -> str:
    """Render the tree with its real day-by-day history replayed as growth.

    Every shape's geometry is driven by a SMIL <animate> keyed to the
    actual cumulative stats on each day in `timeline.days`, so the tree
    grows exactly the way the underlying repos actually grew. Falls back
    to the plain (non-animated) render when there's fewer than two days
    of history to replay.
    """
    day_count = len(timeline.days)
    if day_count < TIMELINE_MIN_DAYS_TO_ANIMATE:
        return render_svg(_timeline_final_garden(timeline))

    duration = _timeline_duration(day_count)
    key_times = _key_times(day_count)
    base_half_width_by_day = _trunk_half_widths_for_timeline(
        timeline.cumulative_sessions
    )
    final_base_half_width = base_half_width_by_day[-1]
    trunk_title = _title(
        f'Trunk — {timeline.cumulative_sessions[-1]} total sessions'
    )

    body = (
        _render_timeline_clouds(timeline, key_times, duration)
        + f'<g class="trunk-group">{trunk_title}'
        + _render_timeline_trunk(base_half_width_by_day, key_times, duration)
        + '</g>'
        + _render_timeline_rings(
            timeline, final_base_half_width, key_times, duration
        )
        + _render_timeline_branches_and_leaves(
            timeline,
            final_base_half_width,
            base_half_width_by_day,
            key_times,
            duration,
        )
        + _render_timeline_bushes(timeline, key_times, duration)
        + _render_timeline_flowers_on_bushes(timeline, key_times, duration)
        + _render_legend()
        + _render_scrubber(timeline, key_times, duration)
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {TIMELINE_VIEWBOX_HEIGHT:.1f}" '
        f'width="{VIEWBOX_WIDTH}" height="{TIMELINE_VIEWBOX_HEIGHT:.1f}">'
        f'{_render_defs()}'
        f'{_render_background()}'
        f'{body}'
        f'</svg>'
    )
