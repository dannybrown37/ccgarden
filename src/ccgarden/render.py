from __future__ import annotations

import datetime
import json
import math
import random
from typing import TYPE_CHECKING, NamedTuple

from ccgarden.data import (
    CartoonBird,
    DayRing,
    GardenData,
    ModelCloud,
    RepoBranch,
    ToolBush,
)

if TYPE_CHECKING:
    from ccgarden.data import GardenTimeline, RepoBranchDay, ToolUsageDay

VIEWBOX_WIDTH = 800
VIEWBOX_HEIGHT = 800
GROUND_Y = 728
# The legend gets its own band below the garden rather than sharing the thin
# strip of grass under GROUND_Y -- eight entries squeezed into 64px of height
# left each column too narrow, so the descriptions ran into their neighbours.
LEGEND_BAND_HEIGHT = 100.0
LEGEND_BAND_BOTTOM = VIEWBOX_HEIGHT + LEGEND_BAND_HEIGHT
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
# Lines added below which `_branch_length` grows quickly, and above which it
# compresses. Tune this rather than the min/max pair to rebalance the crown.
BRANCH_LENGTH_LOG_KNEE = 400.0
BRANCH_SPREAD_DEGREES = 55.0
# Strictly alternating branches at evenly interpolated angles read as a
# ladder rather than a tree, so each branch gets a seeded nudge to both its
# height on the trunk and its exit angle. Both are derived from the repo
# name, so the same db still renders the same garden.
BRANCH_ANGLE_JITTER_DEGREES = 8.0
# As a fraction of the gap between two neighbouring branch origins -- kept
# under half a gap so jitter can never reorder branches up the trunk.
BRANCH_Y_JITTER_FRACTION = 0.4
# A long branch carries more foliage, so it sags. Most of that sag lives in
# the belly of the branch (BRANCH_BOW_*, below) rather than the exit angle,
# which only tips this far towards horizontal at BRANCH_LENGTH_MAX -- a
# branch that leaves the trunk low and still lifts its tip is the vase
# shape real trees make as they grow back towards the light. Putting all the
# sag in the angle instead just flattened everything.
BRANCH_DROOP_DEGREES = 9.0
# Lateral belly of a branch as a fraction of its length, ramping from short
# (nearly straight) to BRANCH_LENGTH_MAX (a pronounced sag).
BRANCH_BOW_FRACTION_MIN = 0.07
BRANCH_BOW_FRACTION_MAX = 0.2
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
CLOUD_MARGIN = 24.0
CLOUD_Y_MIN = 40.0
# The tallest branch plus its canopy reaches into the top of the sky right
# above the trunk, so clouds are laid out in two bands either side of a
# keep-out column centered on the trunk rather than straight across the
# width. Half-width covers the trunk plus the reach of a near-vertical
# max-length branch's canopy, so even the biggest tree only clips the
# inside edge of a cloud instead of swallowing it whole.
CLOUD_TREE_KEEPOUT_HALF_WIDTH = 170.0
# How far down a cloud may drift, as a function of how far its slot sits
# from the trunk. Right beside the keep-out column the tree's outer
# branches are still climbing, so clouds stay high; out at the frame edges
# the sky is clear all the way down and small clouds can use it.
CLOUD_Y_MAX_NEAR_TREE = 150.0
CLOUD_Y_MAX_AT_EDGE = 330.0
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
# Each puff is scaled by a random size jitter, then `_blob_path` wobbles each
# of its vertices by up to a further shape jitter. A cloud therefore reaches
# well past its nominal radius -- roughly 1.4x -- which is what
# `_cloud_extent` turns into the margins that keep it inside the viewBox.
CLOUD_PUFF_SIZE_JITTER = (0.92, 1.08)
CLOUD_PUFF_SHAPE_JITTER = 0.16

# A cloud's reasoning-effort level darkens it toward a storm-cloud grey, so
# heavier-thinking model/effort combos read visually "heavier" in the sky.
# Unrecognized or absent effort falls back to 0.0 -- the original pale cloud.
CLOUD_EFFORT_DARKNESS = {
    'low': 0.15,
    'medium': 0.4,
    'high': 0.65,
    'xhigh': 0.85,
    'max': 1.0,
}
CLOUD_GRADIENT_STOPS = ('#ffffff', '#eef3f8', '#c7d5e4')
CLOUD_STORM_STOPS = ('#4d5566', '#333c4d', '#1c222e')

# The single sun, sized and positioned by the garden's all-in token total
# (every output/input/cache-read/cache-write token counted anywhere) --
# the one shape standing in for the whole garden's total "energy" rather
# than any one branch/model/tool's share of it. It rises from a low,
# barely-there position near the horizon at zero tokens up to its full
# height and brightness at the saturation point, echoing an actual
# sunrise into the dusk-blue sky gradient in `_render_defs`. Drawn first
# so clouds float in front of it, as they would in front of a real sun.
SUN_RADIUS_MIN = 26.0
SUN_RADIUS_MAX = 68.0
SUN_TOKENS_SATURATION = 200_000_000
SUN_X_START = 130.0
SUN_Y_START = 640.0
SUN_X_END = 660.0
SUN_Y_END = 95.0
SUN_RAY_COUNT = 12
# The halo is the sun's widest part -- wider than the rays -- so it sets how
# much clearance `_sun_position` has to keep from the top and sides.
SUN_HALO_RADIUS_FACTOR = 1.9
SUN_GRADIENT_STOPS = ('#fffbe6', '#ffd76a', '#ff9f45')
SUN_HALO_COLOR = '#fff3c4'
SUN_RAY_COLOR = '#ffdb8a'

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
BUSH_TOOL_COUNT_SATURATION = 3000
BUSH_GROWTH_EXPONENT = 0.65
BUSH_PUFFS = (
    (0.0, -0.55, 0.85),
    (-0.62, -0.3, 0.62),
    (0.62, -0.3, 0.62),
    (-0.25, -0.55, 0.5),
    (0.28, -0.55, 0.5),
)

# One sunflower per repo, standing as tall as that repo's prompt count.
# Prompts are the one thing *you* contribute rather than the tree, so they
# get a plant of their own instead of another dimension on the branches.
# Sunflowers are planted in the two flank bands either side of the tree --
# the widest stretch of empty ground in the frame, and far enough from the
# trunk that a tall stalk rises into open sky rather than into the canopy.
MAX_SUNFLOWERS = 8
SUNFLOWER_MARGIN = 20.0
SUNFLOWER_BAND_WIDTH = 150.0
SUNFLOWER_HEIGHT_MIN = 70.0
SUNFLOWER_HEIGHT_MAX = 200.0
SUNFLOWER_PROMPTS_SATURATION = 1500
SUNFLOWER_GROWTH_EXPONENT = 0.6
SUNFLOWER_PETAL_COUNT = 12
SUNFLOWER_PETAL_COLORS = ('#f5b731', '#f0a92a', '#ffc94d')
SUNFLOWER_STALK_COLOR = '#4f8f4f'

# One bird per cartoon adapter that saved tokens, sized by how many it
# saved. Cartoon is an optional external tool the garden plugs into, so
# unlike every other shape here the birds are simply absent -- along with
# their legend entry -- on a machine that doesn't have it. Tokens cartoon
# saves are tokens that never had to be sent, which is the one quantity in
# the garden that's about what *didn't* happen, so it gets the one shape
# that isn't rooted to the ground.
BIRD_MARGIN = 55.0
# Birds share the sky with the canopy, so like the clouds they skip the
# column of sky the tree grows into and spread across the two bands either
# side of it -- otherwise a small flock anchors near the middle of the
# frame and reads as hugging the tree.
BIRD_TREE_KEEPOUT_HALF_WIDTH = 150.0
# Deliberately lower than the clouds' band: the open mid-sky either side
# of the canopy is the emptiest part of the frame, and a bird is small
# enough to sit there without competing with anything.
BIRD_Y_MIN = 120.0
BIRD_Y_MAX = 430.0
MAX_BIRDS = 12
BIRD_SIZE_MIN = 6.0
BIRD_SIZE_MAX = 16.0
BIRD_TOKENS_SATURATION = 250_000
# The reference size the stroke width is scaled against.
BIRD_SIZE = 9.0
# Birds cluster into small skeins rather than scattering evenly: a handful
# of loose Vs reads as wildlife, an even spread reads as a dot grid.
BIRD_FLOCK_SIZE = 4
BIRD_FLOCK_SPACING_X = 15.0
BIRD_FLOCK_SPACING_Y = 8.0
# A dark silhouette is what a bird actually looks like, but the sky here is
# a dark dusk blue -- so they're drawn as a pale, near-white stroke, the
# only value that reads at this size against that gradient.
BIRD_COLOR = '#dce7f4'
EPSILON = 1e-6
BIRD_LEGEND_COLOR = '#3f4b5c'
BIRD_STROKE_WIDTH = 1.8
# In the timeline the flock drifts on its own slow loop, out from the tree
# and back. It is the one motion in the garden that isn't tied to the day
# frames -- cartoon reports a single snapshot, so there is no history to
# replay -- but birds in a still sky read as dead, and drifting invents no
# numbers, only movement.
BIRD_DRIFT_X = 26.0
BIRD_DRIFT_Y = 9.0
BIRD_DRIFT_SECONDS = 11.0

TOOLTIP_PAD = 8.0
TOOLTIP_FONT_SIZE = 13.0
TOOLTIP_HEIGHT = TOOLTIP_FONT_SIZE + TOOLTIP_PAD * 2

TIMELINE_PER_DAY_SECONDS = 0.6
TIMELINE_MIN_DURATION_S = 5.0
TIMELINE_MAX_DURATION_S = 16.0
TIMELINE_MIN_DAYS_TO_ANIMATE = 2

# Extra strip below the legend, holding the scrubber that appears once the
# initial timelapse finishes playing.
SCRUBBER_HEIGHT = 40.0
SCRUBBER_MARGIN = 4.0
SCRUBBER_TOTAL_HEIGHT = SCRUBBER_HEIGHT + SCRUBBER_MARGIN * 2
SCRUBBER_Y = LEGEND_BAND_BOTTOM + SCRUBBER_MARGIN
TIMELINE_VIEWBOX_HEIGHT = LEGEND_BAND_BOTTOM + SCRUBBER_TOTAL_HEIGHT


def _escape_xml(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _title(text: str) -> str:
    """A `<title>` child that browsers render as a native hover tooltip."""
    return f'<title>{_escape_xml(text)}</title>'


def _tt_attr(day_labels: list[str]) -> str:
    """A `data-tt` attribute: one tooltip string per day, JSON-encoded.

    A static `<title>` can't track which day the timeline animation is
    currently showing, so `_render_tap_tooltip` reads this instead for any
    element whose stats grow over the timeline -- picking the entry that
    matches the SMIL clock's current position rather than always the last.
    """
    encoded = _escape_xml(json.dumps(day_labels, ensure_ascii=False)).replace(
        "'", '&apos;'
    )
    return f"data-tt='{encoded}'"


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

    Lines added are distributed like most repo metrics: one or two repos
    carry an order of magnitude more than the rest. A linear mapping leaves
    every branch stubby, and a power curve (this used to be
    fraction ** 0.7) still hands the dominant repo most of the available
    length, which is what left the crown lopsided -- one branch at the cap
    and a fan of short ones under it.

    A log curve balances that: it climbs steeply below
    BRANCH_LENGTH_LOG_KNEE, so a modest repo still gets a branch with real
    presence, then compresses hard above it, so a 10x bigger repo reads as
    clearly bigger without running away with the frame. Relative ratios
    shrink -- that is the point. Absolute proportionality lives in the
    tooltip; the silhouette is for balance.
    """
    lines = min(lines_added, BRANCH_LINES_SATURATION)
    growth = math.log1p(lines / BRANCH_LENGTH_LOG_KNEE) / math.log1p(
        BRANCH_LINES_SATURATION / BRANCH_LENGTH_LOG_KNEE
    )
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
        f'{_cloud_gradient_defs()}'
        '<radialGradient id="sunGradient" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{SUN_GRADIENT_STOPS[0]}" />'
        f'<stop offset="55%" stop-color="{SUN_GRADIENT_STOPS[1]}" />'
        f'<stop offset="100%" stop-color="{SUN_GRADIENT_STOPS[2]}" />'
        '</radialGradient>'
        '<radialGradient id="sunHaloGradient" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{SUN_HALO_COLOR}" '
        'stop-opacity="0.55" />'
        f'<stop offset="100%" stop-color="{SUN_HALO_COLOR}" '
        'stop-opacity="0" />'
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


def _lerp_hex(start: str, end: str, fraction: float) -> str:
    """Blend two `#rrggbb` colors, `fraction` of the way from start to end."""
    start_rgb = (int(start[i : i + 2], 16) for i in (1, 3, 5))
    end_rgb = (int(end[i : i + 2], 16) for i in (1, 3, 5))
    channels = (
        round(s + (e - s) * fraction)
        for s, e in zip(start_rgb, end_rgb, strict=True)
    )
    return '#{:02x}{:02x}{:02x}'.format(*channels)


def _cloud_gradient_id(effort: str | None) -> str:
    """Gradient id for a cloud at this reasoning-effort level.

    Unrecognized or absent effort maps to the original pale `cloudGradient`.
    """
    if effort not in CLOUD_EFFORT_DARKNESS:
        return 'cloudGradient'
    return f'cloudGradient-{effort}'


def _cloud_gradient_defs() -> str:
    """One radial gradient per effort darkness level, plus the base cloud."""
    defs = []
    for gradient_id, darkness in (
        ('cloudGradient', 0.0),
        *(
            (f'cloudGradient-{effort}', darkness)
            for effort, darkness in CLOUD_EFFORT_DARKNESS.items()
        ),
    ):
        stops = tuple(
            _lerp_hex(pale, storm, darkness)
            for pale, storm in zip(
                CLOUD_GRADIENT_STOPS, CLOUD_STORM_STOPS, strict=True
            )
        )
        defs.append(
            f'<radialGradient id="{gradient_id}" cx="35%" cy="30%" r="75%">'
            f'<stop offset="0%" stop-color="{stops[0]}" />'
            f'<stop offset="60%" stop-color="{stops[1]}" />'
            f'<stop offset="100%" stop-color="{stops[2]}" />'
            '</radialGradient>'
        )
    return ''.join(defs)


def _effort_from_cloud_label(label: str) -> str | None:
    """Pull the effort out of a `model_effort_label` combo.

    E.g. `sonnet (high)` -> `high`; returns None for a bare model name.
    """
    if label.endswith(')') and '(' in label:
        return label.rsplit('(', 1)[1][:-1]
    return None


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
        jitter = rng.uniform(*CLOUD_PUFF_SIZE_JITTER)
        puff_radius = radius * r_frac * jitter
        d_values.append(
            _blob_path(
                dx_frac * radius,
                dy_frac * radius,
                puff_radius,
                random.Random(f'{seed}:{index}'),
                points=8,
                jitter=CLOUD_PUFF_SHAPE_JITTER,
            )
        )
    return d_values


def _cloud_extent() -> tuple[float, float, float]:
    """How far a radius-1 cloud reaches (left/right, up, down) from center.

    Derived from `CLOUD_PUFFS` and the two jitters rather than hardcoded, so
    retuning the puff layout can't silently reintroduce clouds that hang off
    the edge of the sky. Both jitters are taken at their worst case: a
    `_blob_path` curve stays inside the hull of its jittered vertices, so
    these are upper bounds on the drawn shape.
    """
    max_puff_scale = CLOUD_PUFF_SIZE_JITTER[1] * (1 + CLOUD_PUFF_SHAPE_JITTER)
    half_width = up = down = 0.0
    for dx_frac, dy_frac, r_frac in CLOUD_PUFFS:
        reach = r_frac * max_puff_scale
        half_width = max(half_width, abs(dx_frac) + reach)
        up = max(up, reach - dy_frac)
        down = max(down, reach + dy_frac)
    return half_width, up, down


def _clamp_cloud_position(
    x: float, y: float, radius: float
) -> tuple[float, float]:
    """Nudge a cloud's slot inward just enough to keep it fully in frame.

    Only clouds that would actually overflow move -- a small cloud clears
    every edge by a wide margin and keeps the scattered slot
    `_cloud_positions` gave it.
    """
    half_width, up, down = _cloud_extent()
    x = min(max(x, half_width * radius), VIEWBOX_WIDTH - half_width * radius)
    y = min(max(y, up * radius), VIEWBOX_HEIGHT - down * radius)
    return x, y


def _render_cloud(
    cx: float, cy: float, radius: float, seed: str, effort: str | None = None
) -> str:
    gradient_id = _cloud_gradient_id(effort)
    puffs = ''.join(
        f'<path d="{d}" fill="url(#{gradient_id})" opacity="0.88" />'
        for d in _cloud_puffs_d(radius, seed)
    )
    return f'<g transform="translate({cx:.1f},{cy:.1f})">{puffs}</g>'


def _cloud_bands() -> tuple[tuple[float, float], tuple[float, float]]:
    """The (start, end) x spans of the sky left and right of the tree."""
    left = (CLOUD_MARGIN, TRUNK_CENTER_X - CLOUD_TREE_KEEPOUT_HALF_WIDTH)
    right = (
        TRUNK_CENTER_X + CLOUD_TREE_KEEPOUT_HALF_WIDTH,
        VIEWBOX_WIDTH - CLOUD_MARGIN,
    )
    return left, right


def _cloud_slot_x(fraction: float) -> float:
    """The x for a slot `fraction` of the way through the usable sky.

    The two bands are treated as one continuous run so slots stay evenly
    spread overall, they just skip the column of sky the tree grows into.
    """
    (left_start, left_end), (right_start, right_end) = _cloud_bands()
    left_width = max(left_end - left_start, 0.0)
    right_width = max(right_end - right_start, 0.0)
    offset = fraction * (left_width + right_width)
    if offset <= left_width:
        return left_start + offset
    return right_start + (offset - left_width)


def _cloud_y_max(x: float) -> float:
    """How far down the sky a cloud at this x may drift.

    Ramps from `CLOUD_Y_MAX_NEAR_TREE` at the edge of the keep-out column
    out to `CLOUD_Y_MAX_AT_EDGE` at the frame's sides, following the way
    the tree's outer branches slope down away from the trunk.
    """
    distance = abs(x - TRUNK_CENTER_X)
    span = TRUNK_CENTER_X - CLOUD_MARGIN - CLOUD_TREE_KEEPOUT_HALF_WIDTH
    if span <= 0:
        return CLOUD_Y_MAX_NEAR_TREE
    fraction = min(
        max((distance - CLOUD_TREE_KEEPOUT_HALF_WIDTH) / span, 0.0), 1.0
    )
    return (
        CLOUD_Y_MAX_NEAR_TREE
        + (CLOUD_Y_MAX_AT_EDGE - CLOUD_Y_MAX_NEAR_TREE) * fraction
    )


def _cloud_positions(count: int) -> list[tuple[float, float]]:
    """Deterministic (x, y) sky slot for each of `count` clouds.

    Spread evenly across the two sky bands either side of the trunk's
    keep-out column (see `_cloud_slot_x`), with per-slot jitter so a full
    sky of models doesn't read as a mechanical grid, and a per-slot depth
    that opens up toward the frame edges (see `_cloud_y_max`). Shuffled
    before returning so slot order doesn't line up with the caller's
    (biggest-model-first) list order -- otherwise every render reads as a
    strict big-to-small gradient across the sky instead of a scattered
    distribution of sizes.
    """
    positions = []
    for index in range(count):
        rng = random.Random(f'ccgarden-cloud-slot:{index}')
        x = _cloud_slot_x((index + rng.uniform(0.25, 0.75)) / count)
        y_max = _cloud_y_max(x)
        y = CLOUD_Y_MIN + rng.uniform(0.0, y_max - CLOUD_Y_MIN)
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
        cx, cy = _clamp_cloud_position(x, y, radius)
        effort = _effort_from_cloud_label(model_cloud.model)
        title = _title(f'{model_cloud.model} — {total_tokens:,} tokens')
        elements.append(
            f'<g class="cloud">{title}'
            f'{_render_cloud(cx, cy, radius, model_cloud.model, effort)}</g>'
        )
    return ''.join(elements)


def _bird_size(tokens_saved: int) -> float:
    """A bird's wingspan for an adapter that saved this many tokens.

    Same sqrt-saturation shape as the other size formulas (see
    `_cloud_radius`, `_bush_radius`), so an adapter with modest savings is
    still a visible bird rather than a speck.
    """
    growth = math.sqrt(
        min(max(tokens_saved, 0), BIRD_TOKENS_SATURATION)
        / BIRD_TOKENS_SATURATION
    )
    return BIRD_SIZE_MIN + (BIRD_SIZE_MAX - BIRD_SIZE_MIN) * growth


def _bird_bands() -> tuple[tuple[float, float], tuple[float, float]]:
    """The (start, end) x spans of the sky left and right of the tree."""
    left = (BIRD_MARGIN, TRUNK_CENTER_X - BIRD_TREE_KEEPOUT_HALF_WIDTH)
    right = (
        TRUNK_CENTER_X + BIRD_TREE_KEEPOUT_HALF_WIDTH,
        VIEWBOX_WIDTH - BIRD_MARGIN,
    )
    return left, right


def _bird_slot_x(fraction: float) -> float:
    """The x for a slot `fraction` of the way through the usable sky.

    The two bands are treated as one continuous run so slots stay evenly
    spread overall, they just skip the column of sky the tree grows into.
    """
    (left_start, left_end), (right_start, right_end) = _bird_bands()
    left_width = max(left_end - left_start, 0.0)
    right_width = max(right_end - right_start, 0.0)
    offset = fraction * (left_width + right_width)
    if offset <= left_width:
        return left_start + offset
    return right_start + (offset - left_width)


def _bird_clamp_x(x: float) -> float:
    """Pull an x back into whichever sky band it is nearest."""
    (left_start, left_end), (right_start, right_end) = _bird_bands()
    if x <= left_end:
        return max(x, left_start)
    if x >= right_start:
        return min(x, right_end)
    # Inside the tree's column: fall out to the closer side of it.
    if x - left_end <= right_start - x:
        return left_end
    return right_start


def _bird_positions(count: int) -> list[tuple[float, float]]:
    """Deterministic (x, y) sky slot for each of `count` birds.

    Birds are dealt into skeins of up to `BIRD_FLOCK_SIZE`, each skein
    anchored at its own slot across the sky either side of the tree and
    laid out as a V trailing up and back from its leader.
    """
    if count <= 0:
        return []
    flock_count = math.ceil(count / BIRD_FLOCK_SIZE)
    positions = []
    for index in range(count):
        flock_index = index // BIRD_FLOCK_SIZE
        rank_in_flock = index % BIRD_FLOCK_SIZE
        anchor_rng = random.Random(f'ccgarden-bird-flock:{flock_index}')
        anchor_x = _bird_slot_x(
            (flock_index + anchor_rng.uniform(0.3, 0.7)) / flock_count
        )
        anchor_y = anchor_rng.uniform(BIRD_Y_MIN, BIRD_Y_MAX)

        # Alternate sides of the V, one step further back with each pair.
        side = -1.0 if rank_in_flock % 2 else 1.0
        rank = (rank_in_flock + 1) // 2
        rng = random.Random(f'ccgarden-bird:{index}')
        offset_x = side * rank * BIRD_FLOCK_SPACING_X * rng.uniform(0.8, 1.2)
        x = _bird_clamp_x(anchor_x + offset_x)
        y = min(
            anchor_y + rank * BIRD_FLOCK_SPACING_Y * rng.uniform(0.7, 1.3),
            BIRD_Y_MAX,
        )
        positions.append((x, y))
    return positions


def _bird_d(cx: float, cy: float, size: float) -> str:
    """A bird as the classic pair of wing strokes meeting at the body."""
    half = size / 2
    lift = size * 0.55
    return (
        f'M{cx - size:.1f},{cy:.1f} '
        f'Q{cx - half:.1f},{cy - lift:.1f} {cx:.1f},{cy:.1f} '
        f'Q{cx + half:.1f},{cy - lift:.1f} {cx + size:.1f},{cy:.1f}'
    )


def _render_bird(
    cx: float, cy: float, size: float, color: str = BIRD_COLOR
) -> str:
    return (
        f'<path d="{_bird_d(cx, cy, size)}" fill="none" '
        f'stroke="{color}" '
        f'stroke-width="{BIRD_STROKE_WIDTH * size / BIRD_SIZE:.2f}" '
        f'stroke-linecap="round" opacity="0.85" />'
    )


def _clear_of_sun(
    x: float, y: float, size: float, sun: tuple[float, float, float]
) -> tuple[float, float]:
    """Push a bird radially out of the sun's halo, if it landed inside it.

    A pale bird washes out completely against the halo, so the one thing
    a flock has to dodge is the sun -- clouds it may cross freely, which
    is what birds do anyway.
    """
    sun_x, sun_y, sun_radius = sun
    keepout = sun_radius * SUN_HALO_RADIUS_FACTOR + size * 2
    dx, dy = x - sun_x, y - sun_y
    distance = math.hypot(dx, dy)
    if distance >= keepout:
        return x, y
    if distance < EPSILON:
        # Dead center on the sun: no direction to push, so pick one.
        dx, dy, distance = 0.0, 1.0, 1.0
    scale = keepout / distance
    pushed_x = sun_x + dx * scale
    pushed_y = sun_y + dy * scale
    return (
        min(max(pushed_x, BIRD_MARGIN), VIEWBOX_WIDTH - BIRD_MARGIN),
        min(max(pushed_y, BIRD_Y_MIN), BIRD_Y_MAX),
    )


def _bird_slots(
    birds: list[CartoonBird], sun: tuple[float, float, float]
) -> list[tuple[float, float, float]]:
    """(x, y, size) for each bird, placed in the sky and clear of the sun."""
    sizes = [_bird_size(bird.tokens_saved) for bird in birds]
    return [
        (*_clear_of_sun(x, y, size, sun), size)
        for (x, y), size in zip(
            _bird_positions(len(birds)), sizes, strict=True
        )
    ]


def _bird_drift(
    index: int,
    x: float,
    y: float,
    size: float,
    sun: tuple[float, float, float],
) -> tuple[float, float]:
    """How far a bird drifts from its slot at the far end of its loop.

    Outward, away from the trunk, so the drift can never carry a bird into
    the canopy; the far end is put through the same band clamp and sun
    push-out as the slot itself, so both ends of the loop are legal
    positions and everything between them is too.
    """
    rng = random.Random(f'ccgarden-bird-drift:{index}')
    direction = 1.0 if x >= TRUNK_CENTER_X else -1.0
    far_x = _bird_clamp_x(x + direction * BIRD_DRIFT_X * rng.uniform(0.7, 1.3))
    far_y = min(
        max(y - BIRD_DRIFT_Y * rng.uniform(0.5, 1.3), BIRD_Y_MIN), BIRD_Y_MAX
    )
    far_x, far_y = _clear_of_sun(far_x, far_y, size, sun)
    return far_x - x, far_y - y


def _bird_drift_rule(index: int, dx: float, dy: float) -> str:
    """A slow there-and-back drift, looping for as long as the SVG is open.

    Deliberately not keyed to the timeline's day frames: it runs on its own
    clock so a paused or scrubbed replay still has a living sky.

    CSS rather than the `animateTransform` this used to be. SMIL transforms
    are never handed to the compositor, so a flock that drifts forever kept
    the whole document -- thousands of branch and leaf paths -- repainting on
    the main thread every frame, which visibly janked scrolling on any page
    embedding the garden. An equivalent CSS keyframe animation can be
    composited, and costs nothing once the layer is up.
    """
    rng = random.Random(f'ccgarden-bird-drift-time:{index}')
    duration = BIRD_DRIFT_SECONDS * rng.uniform(0.85, 1.15)
    return (
        f'@keyframes bird-drift-{index}{{'
        f'50%{{transform:translate({dx:.2f}px,{dy:.2f}px)}}}}'
        f'.bird-drift-{index}{{'
        f'animation:bird-drift-{index} {duration:.3f}s '
        f'ease-in-out infinite}}'
    )


def _bird_drift_style(rules: list[str]) -> str:
    """The flock's drift keyframes, plus the two rules they all share.

    `will-change` is what actually buys the compositor layer; without it a
    browser is free to keep animating the transform on the main thread and
    the SMIL problem comes straight back.
    """
    return (
        '<style>'
        + ''.join(rules)
        + '.bird-drift{will-change:transform}'
        + '@media (prefers-reduced-motion:reduce)'
        + '{.bird-drift{animation:none}}'
        + '</style>'
    )


def _bird_label(bird: CartoonBird, since: str) -> str:
    window = f' (last {since})' if since else ''
    return (
        f'{bird.adapter} — {bird.tokens_saved:,} tokens saved '
        f'over {bird.calls:,} calls{window}'
    )


def _render_birds(
    birds: list[CartoonBird],
    since: str,
    sun: tuple[float, float, float],
) -> str:
    """One bird per cartoon adapter -- nothing at all when cartoon is absent.

    Every caller passes whatever `load_cartoon_birds` came back with, so
    a machine without cartoon just renders a garden with an empty sky.
    """
    flock = birds[:MAX_BIRDS]
    if not flock:
        return ''
    slots = _bird_slots(flock, sun)
    elements = [
        f'<g class="bird">{_title(_bird_label(bird, since))}'
        f'{_render_bird(x, y, size)}</g>'
        for bird, (x, y, size) in zip(flock, slots, strict=True)
    ]
    return f'<g class="birds">{"".join(elements)}</g>'


def _sun_growth(total_tokens: int) -> float:
    """0..1 share of the way to `SUN_TOKENS_SATURATION`, sqrt-eased.

    Same sqrt-saturation shape as the other size formulas (see
    `_cloud_radius`, `_bush_radius`) -- there's only ever one sun, so
    unlike those per-category shapes there's no risk of it flattening
    several entries together, just the usual "small totals still read as
    something" floor.
    """
    return math.sqrt(
        min(total_tokens, SUN_TOKENS_SATURATION) / SUN_TOKENS_SATURATION
    )


def _sun_radius(total_tokens: int) -> float:
    growth = _sun_growth(total_tokens)
    return SUN_RADIUS_MIN + (SUN_RADIUS_MAX - SUN_RADIUS_MIN) * growth


def _sun_position(total_tokens: int) -> tuple[float, float]:
    """Where the sun sits.

    Rises from a low horizon point toward its zenith as the garden's
    total token count grows toward saturation, clamped so its halo never
    crosses the top or sides of the viewBox. The bottom is deliberately not
    clamped: at low token counts the sun sits half-buried below the horizon,
    which is the intended sunrise.
    """
    growth = _sun_growth(total_tokens)
    x = SUN_X_START + (SUN_X_END - SUN_X_START) * growth
    y = SUN_Y_START + (SUN_Y_END - SUN_Y_START) * growth
    halo_radius = _sun_radius(total_tokens) * SUN_HALO_RADIUS_FACTOR
    x = min(max(x, halo_radius), VIEWBOX_WIDTH - halo_radius)
    y = max(y, halo_radius)
    return x, y


def _sun_rays_d(radius: float) -> list[str]:
    """`d` values for each ray line radiating out from the sun's center."""
    inner = radius * 1.12
    outer = inner + radius * 0.55
    d_values = []
    for index in range(SUN_RAY_COUNT):
        angle = 2 * math.pi * index / SUN_RAY_COUNT
        x1 = inner * math.cos(angle)
        y1 = inner * math.sin(angle)
        x2 = outer * math.cos(angle)
        y2 = outer * math.sin(angle)
        d_values.append(f'M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}')
    return d_values


def _render_sun(cx: float, cy: float, radius: float) -> str:
    halo_radius = radius * SUN_HALO_RADIUS_FACTOR
    rays = ''.join(
        f'<path d="{d}" stroke="{SUN_RAY_COLOR}" '
        f'stroke-width="{max(radius * 0.12, 2.5):.2f}" '
        f'stroke-linecap="round" opacity="0.7" />'
        for d in _sun_rays_d(radius)
    )
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f})">'
        f'<circle r="{halo_radius:.2f}" fill="url(#sunHaloGradient)" />'
        f'{rays}'
        f'<circle r="{radius:.2f}" fill="url(#sunGradient)" />'
        f'</g>'
    )


def _bush_radius(tool_count: int) -> float:
    """A tool's bush radius, growing toward a cap without fully flattening.

    Tool call counts are far more top-heavy than day-level totals (one
    tool -- typically Bash -- often outnumbers the next-most-used tool by
    3x or more), so this uses a gentler, more-linear curve than the plain
    sqrt-saturation shape in `_cloud_radius`/`_canopy_radius`: a fractional
    exponent above 0.5 lets the heaviest hitters actually look heavier,
    while still giving a rarely-used tool a visible bush instead of
    vanishing.
    """
    growth = (
        min(tool_count, BUSH_TOOL_COUNT_SATURATION)
        / BUSH_TOOL_COUNT_SATURATION
    ) ** BUSH_GROWTH_EXPONENT
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


def _sunflower_height(prompts: int) -> float:
    """A repo's sunflower height, growing toward a cap without flattening.

    Same shape as `_bush_radius` and for the same reason: prompt counts
    are top-heavy across repos (one main project usually dwarfs the rest),
    so a fractional exponent above 0.5 keeps the busiest repo visibly the
    tallest while a barely-touched repo still gets a stalk you can see.
    """
    growth = (
        min(prompts, SUNFLOWER_PROMPTS_SATURATION)
        / SUNFLOWER_PROMPTS_SATURATION
    ) ** SUNFLOWER_GROWTH_EXPONENT
    return (
        SUNFLOWER_HEIGHT_MIN
        + (SUNFLOWER_HEIGHT_MAX - SUNFLOWER_HEIGHT_MIN) * growth
    )


def _sunflower_x_positions(count: int) -> list[float]:
    """Ground-line x slot for each of `count` sunflowers, alternating sides.

    Two bands, one per flank, filled alternately so the sunflowers stay
    balanced either side of the trunk however many repos there are --
    filling one band before starting the other would leave a lone
    left-hand thicket for anyone with five repos.
    """
    left_count = math.ceil(count / 2)
    right_count = count - left_count
    positions: list[float] = []
    for side_index, side_count in ((0, left_count), (1, right_count)):
        band_start = (
            SUNFLOWER_MARGIN
            if side_index == 0
            else VIEWBOX_WIDTH - SUNFLOWER_MARGIN - SUNFLOWER_BAND_WIDTH
        )
        for index in range(side_count):
            rng = random.Random(
                f'ccgarden-sunflower-slot:{side_index}:{index}'
            )
            positions.append(
                band_start
                + SUNFLOWER_BAND_WIDTH
                * ((index + rng.uniform(0.25, 0.75)) / side_count)
            )
    # Interleave the two bands back into the caller's (prompts-descending)
    # order, so the tallest sunflowers don't all end up on one side.
    interleaved: list[float] = []
    for index in range(count):
        side, slot = index % 2, index // 2
        interleaved.append(
            positions[slot] if side == 0 else positions[left_count + slot]
        )
    return interleaved


def _render_sunflower(
    cx: float, base_y: float, height: float, seed: str
) -> str:
    """One sunflower, rooted at (cx, base_y) and growing upward.

    Laid out relative to a (0, 0) ground-contact point like `_render_bush`,
    so a caller can scale the whole group to grow it up out of the soil
    instead of expanding it symmetrically about its middle.
    """
    rng = random.Random(seed)
    lean = rng.uniform(-0.16, 0.16) * height
    head_x = lean
    head_y = -height
    head_radius = height * 0.115
    stalk_width = max(2.0, height * 0.035)

    parts = [
        (
            f'<path d="M0,0 Q{lean * 0.3:.1f},{-height * 0.55:.1f} '
            f'{head_x:.1f},{head_y:.1f}" fill="none" '
            f'stroke="{SUNFLOWER_STALK_COLOR}" '
            f'stroke-width="{stalk_width:.2f}" stroke-linecap="round" />'
        )
    ]
    for leaf_index, frac in enumerate((0.36, 0.6)):
        side = 1 if leaf_index % 2 == 0 else -1
        leaf_x = lean * frac * 0.4 + side * height * 0.07
        leaf_y = -height * frac
        leaf_scale = height * 0.1
        parts.append(
            f'<g transform="translate({leaf_x:.1f},{leaf_y:.1f}) '
            f'rotate({side * 68}) scale({leaf_scale:.2f})">'
            f'<path d="{LEAF_SHAPE_D}" fill="{SUNFLOWER_STALK_COLOR}" '
            f'opacity="0.9" />'
            f'</g>'
        )

    angle_offset = rng.uniform(0, 360 / SUNFLOWER_PETAL_COUNT)
    for petal_index in range(SUNFLOWER_PETAL_COUNT):
        angle = angle_offset + petal_index * (360 / SUNFLOWER_PETAL_COUNT)
        color = SUNFLOWER_PETAL_COLORS[
            petal_index % len(SUNFLOWER_PETAL_COLORS)
        ]
        parts.append(
            f'<ellipse cx="{head_x:.1f}" cy="{head_y:.1f}" '
            f'rx="{head_radius * 0.95:.2f}" ry="{head_radius * 0.36:.2f}" '
            f'fill="{color}" opacity="0.94" '
            f'transform="rotate({angle:.1f} {head_x:.1f} {head_y:.1f})" />'
        )
    parts.append(
        f'<circle cx="{head_x:.1f}" cy="{head_y:.1f}" '
        f'r="{head_radius * 0.52:.2f}" fill="{FLOWER_CENTER_COLOR}" />'
    )
    return (
        f'<g transform="translate({cx:.1f},{base_y:.1f})">{"".join(parts)}</g>'
    )


def _sunflower_repos(branches: list[RepoBranch]) -> list[RepoBranch]:
    """The repos that get a sunflower, tallest (most prompts) first."""
    with_prompts = [branch for branch in branches if branch.prompts > 0]
    with_prompts.sort(key=lambda branch: branch.prompts, reverse=True)
    return with_prompts[:MAX_SUNFLOWERS]


def _render_sunflowers(branches: list[RepoBranch]) -> str:
    repos = _sunflower_repos(branches)
    if not repos:
        return ''
    xs = _sunflower_x_positions(len(repos))
    parts = []
    for x, branch in zip(xs, repos, strict=True):
        plant = _render_sunflower(
            x, GROUND_Y, _sunflower_height(branch.prompts), branch.repo
        )
        parts.append(
            '<g class="sunflower">'
            f'{_title(f"{branch.repo} — {branch.prompts:,} prompts")}'
            f'{plant}</g>'
        )
    return ''.join(parts)


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


class _BranchPlacement(NamedTuple):
    """Where a repo's branch leaves the trunk, and at what pitch.

    Shared by the static and timeline renderers so both trees put the same
    repo in the same place -- the timeline is the same tree, grown.
    """

    origin_x: float
    origin_y: float
    side: int
    spread_index: float
    angle_jitter: float


def _branch_placement(
    index: int, count: int, repo: str, base_half_width: float
) -> _BranchPlacement:
    side = -1 if index % 2 == 0 else 1
    rng = random.Random(f'{repo}:place')
    spacing = 1.0 / max(count, 2)
    # Branches arrive ordered by lines added, descending -- so index 0 is the
    # longest, and it belongs at the *bottom* of the zone. Reading the order
    # straight through put the longest branches at the top and the stubs at
    # the base, which is an upside-down cone: the tips traced two rays
    # diverging upwards and the whole tree read as a V. Longest-lowest gives
    # the broad-at-the-bottom silhouette a real crown has.
    y_fraction = (
        1.0
        - index / max(count - 1, 1)
        + rng.uniform(-BRANCH_Y_JITTER_FRACTION, BRANCH_Y_JITTER_FRACTION)
        * spacing
    )
    y_fraction = min(max(y_fraction, 0.0), 1.0)
    origin_y = TRUNK_TOP_Y + y_fraction * BRANCH_ZONE_HEIGHT
    origin_half_width = _half_width_at(origin_y, base_half_width)
    return _BranchPlacement(
        origin_x=TRUNK_CENTER_X + origin_half_width * side * 0.5,
        origin_y=origin_y,
        side=side,
        spread_index=y_fraction,
        angle_jitter=rng.uniform(
            -BRANCH_ANGLE_JITTER_DEGREES, BRANCH_ANGLE_JITTER_DEGREES
        ),
    )


def _branch_bow(length: float, side: int, bow_factor: float) -> float:
    """How far a branch's midpoint sags off the straight origin-tip line.

    Signed by `side` because the perpendicular that `_branch_shape_points`
    offsets along points downwards on the right flank and upwards on the
    left, so `* side` is what makes both flanks sag rather than one of them
    arching over.
    """
    load = min(length / BRANCH_LENGTH_MAX, 1.0)
    fraction = (
        BRANCH_BOW_FRACTION_MIN
        + (BRANCH_BOW_FRACTION_MAX - BRANCH_BOW_FRACTION_MIN) * load
    )
    return length * fraction * side * (0.7 + 0.6 * bow_factor)


def _branch_endpoint(
    origin_x: float,
    origin_y: float,
    length: float,
    side: int,
    spread_index: float,
    *,
    angle_jitter: float = 0.0,
) -> tuple[float, float]:
    # One side-relative spread term carries all three contributions, so a
    # bigger number always means "further from vertical" on either flank.
    droop = BRANCH_DROOP_DEGREES * min(length / BRANCH_LENGTH_MAX, 1.0)
    spread = (
        BRANCH_SPREAD_DEGREES * (0.4 + 0.6 * spread_index)
        + angle_jitter
        + droop
    )
    angle_deg = 90 - side * spread
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
        placement = _branch_placement(
            index, count, repo_branch.repo, base_half_width
        )
        origin_x, origin_y, side = (
            placement.origin_x,
            placement.origin_y,
            placement.side,
        )

        length = _branch_length(repo_branch.lines_added)
        end_x, end_y = _branch_endpoint(
            origin_x,
            origin_y,
            length,
            side,
            placement.spread_index,
            angle_jitter=placement.angle_jitter,
        )
        base_width = _branch_width(
            repo_branch.output_tokens + repo_branch.input_tokens
        )
        curve_rng = random.Random(f'{repo_branch.repo}:curve')
        bow = _branch_bow(length, side, curve_rng.random())
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
LEGEND_Y = VIEWBOX_HEIGHT + LEGEND_MARGIN
LEGEND_HEIGHT = LEGEND_BAND_HEIGHT - LEGEND_MARGIN * 2
LEGEND_X = 14.0
LEGEND_WIDTH = VIEWBOX_WIDTH - LEGEND_X * 2
LEGEND_PADDING = 10.0
LEGEND_COLUMNS = 5
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
        (
            'one per model + effort;',
            'bigger = more tokens;',
            'darker = more effort',
        ),
        'cloud',
    ),
    (
        'Bushes',
        ('one per tool used;', 'bigger = used more'),
        'bush',
    ),
    (
        'Sun',
        ('rises + grows w/', 'total all-in tokens'),
        'sun',
    ),
    (
        'Sunflowers',
        ('one per repo;', 'taller = more prompts'),
        'sunflower',
    ),
    (
        'Birds',
        ('one per cartoon adapter;', 'bigger = more tokens saved'),
        'bird',
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


def _legend_icon_sun(cx: float, cy: float) -> str:
    return _render_sun(cx, cy, 6.0)


def _legend_icon_sunflower(cx: float, cy: float) -> str:
    return _render_sunflower(cx, cy + 8.0, 16.0, 'legend-sunflower')


def _legend_icon_bird(cx: float, cy: float) -> str:
    # Dark, unlike the sky birds: the legend panel is a pale cream card.
    return _render_bird(cx, cy + 2.0, 6.0, BIRD_LEGEND_COLOR)


LEGEND_ICON_RENDERERS = {
    'trunk': _legend_icon_trunk,
    'ring': _legend_icon_ring,
    'branch': _legend_icon_branch,
    'leaf': _legend_icon_leaf,
    'flower': _legend_icon_flower,
    'cloud': _legend_icon_cloud,
    'bush': _legend_icon_bush,
    'sun': _legend_icon_sun,
    'sunflower': _legend_icon_sunflower,
    'bird': _legend_icon_bird,
}


def _render_legend_icon(icon: str, cx: float, cy: float) -> str:
    return LEGEND_ICON_RENDERERS[icon](cx, cy)


def _render_legend(*, with_birds: bool = False) -> str:
    """A key panel explaining what each part of the tree represents.

    Sits in its own band below the garden viewBox, so it can never overlap
    the tree, and laid out as a 5x2 grid -- every entry across one row
    left barely 90px per entry, which the two- and three-line descriptions
    overflowed into each other, and a third row would need a taller band
    than the two- and three-line descriptions leave room for.

    The birds entry is dropped unless cartoon actually produced birds:
    a key to a shape that isn't in the sky is just a puzzle.
    """
    rows = [row for row in LEGEND_ROWS if with_birds or row[2] != 'bird']
    column_width = LEGEND_WIDTH / LEGEND_COLUMNS
    row_count = math.ceil(len(rows) / LEGEND_COLUMNS)
    row_height = LEGEND_HEIGHT / row_count
    parts = [
        (
            f'<g class="legend">'
            f'<rect x="0" y="{VIEWBOX_HEIGHT:.1f}" '
            f'width="{VIEWBOX_WIDTH:.1f}" '
            f'height="{LEGEND_BAND_HEIGHT:.1f}" fill="#3f7a3f" />'
            f'<rect x="{LEGEND_X:.1f}" y="{LEGEND_Y:.1f}" '
            f'width="{LEGEND_WIDTH:.1f}" height="{LEGEND_HEIGHT:.1f}" rx="8" '
            f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.88" />'
        )
    ]
    for index, (label, desc_lines, icon) in enumerate(rows):
        col_x = LEGEND_X + column_width * (index % LEGEND_COLUMNS)
        row_cy = (
            LEGEND_Y + row_height * (index // LEGEND_COLUMNS) + row_height / 2
        )
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
    sun_x, sun_y = _sun_position(garden.total_tokens)
    sun_title = _title(f'Sun — {garden.total_tokens:,} tokens (all-in)')

    body = (
        f'<g class="sun">{sun_title}'
        f'{_render_sun(sun_x, sun_y, _sun_radius(garden.total_tokens))}</g>'
        + _render_clouds(garden.model_efforts)
        + _render_birds(
            garden.birds,
            garden.cartoon_since,
            (sun_x, sun_y, _sun_radius(garden.total_tokens)),
        )
        + f'<g class="trunk-group">{trunk_title}'
        f'{_render_trunk(base_half_width)}</g>'
        + _render_rings(garden.rings, base_half_width)
        + _render_branches_and_leaves(garden.branches, base_half_width)
        # Sunflowers go down before the bushes so their stalks are rooted
        # behind the shrubbery rather than standing in front of it.
        + _render_sunflowers(garden.branches)
        + _render_bushes(garden.tools)
        + _render_flowers_on_bushes(
            flower_count,
            bush_footprints,
            garden.cache_read_tokens,
            garden.cache_write_tokens,
        )
        + _render_legend(with_birds=bool(garden.birds))
        + _render_tap_tooltip(LEGEND_BAND_BOTTOM)
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {LEGEND_BAND_BOTTOM:.1f}" '
        f'width="{VIEWBOX_WIDTH}" height="{LEGEND_BAND_BOTTOM:.1f}">'
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
        # A day with no sessions grew no ring -- notably the synthetic
        # day 0 the timeline starts from.
        if sessions <= 0:
            continue
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
        placement = _branch_placement(
            index, count, repo, final_base_half_width
        )
        origin_x, origin_y, side = (
            placement.origin_x,
            placement.origin_y,
            placement.side,
        )
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
            # `length` is the day's grown length, so the droop baked into
            # `_branch_endpoint` deepens over the timelapse: a branch sags
            # as it puts on foliage.
            end_x, end_y = _branch_endpoint(
                origin_x,
                origin_y,
                length,
                side,
                placement.spread_index,
                angle_jitter=placement.angle_jitter,
            )
            base_width = (
                BRANCH_WIDTH_MIN
                + (final_width - BRANCH_WIDTH_MIN) * width_fraction
            )
            bow = _branch_bow(length, side, bow_factor)
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
        day_labels = _branch_day_labels(repo, days)
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
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
            f'<g class="repo-group" {tt}>'
            f'{title}{collar}{branch_path}{leaves}</g>'
        )
    return ''.join(elements)


def _branch_day_labels(repo: str, days: list[RepoBranchDay]) -> list[str]:
    """One tooltip line per day for a repo's branch."""
    labels = []
    for day_stat in days:
        day_tokens = day_stat.output_tokens + day_stat.input_tokens
        avg_turns = (
            day_stat.prompts / day_stat.sessions if day_stat.sessions else 0.0
        )
        labels.append(
            f'{repo} — {day_stat.sessions} sessions, '
            f'+{day_stat.lines_added:,}/-{day_stat.lines_removed:,} '
            f'lines, {day_tokens:,} tokens, ${day_stat.cost:,.2f}, '
            f'{avg_turns:.1f} turns/session'
        )
    return labels


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


def _sun_day_values(
    days_tokens: list[int], final_tokens: int
) -> list[tuple[float, float, float]]:
    """Per-day (x, y, radius), grown as a share of the sun's *final* state.

    Not the same absolute-tokens formula re-evaluated per day -- see the
    identical reasoning in `_render_timeline_branches_and_leaves`.
    """
    final_x, final_y = _sun_position(final_tokens)
    final_radius = _sun_radius(final_tokens)
    values = []
    for day_tokens in days_tokens:
        fraction = min(day_tokens / final_tokens, 1.0) if final_tokens else 1.0
        x = SUN_X_START + (final_x - SUN_X_START) * fraction
        y = SUN_Y_START + (final_y - SUN_Y_START) * fraction
        radius = SUN_RADIUS_MIN + (final_radius - SUN_RADIUS_MIN) * fraction
        values.append((x, y, radius))
    return values


def _render_timeline_sun(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    cumulative = timeline.cumulative_total_tokens
    final_tokens = cumulative[-1] if cumulative else 0
    day_tokens = cumulative or [final_tokens]
    day_values = _sun_day_values(day_tokens, final_tokens)
    final_x, final_y, final_radius = day_values[-1]

    translate_values = [f'{x:.2f},{y:.2f}' for x, y, _ in day_values]
    scale_values = [f'{r / final_radius:.4f}' for _, _, r in day_values]
    translate_animate = _animate_transform_tag(
        'translate', translate_values, key_times, duration
    )
    scale_animate = _animate_transform_tag(
        'scale', scale_values, key_times, duration
    )
    day_labels = [f'Sun — {tokens:,} tokens (all-in)' for tokens in day_tokens]
    title = _title(day_labels[-1])
    tt = _tt_attr(day_labels)
    sun_shape = _render_sun(0, 0, final_radius)
    return (
        f'<g class="sun" {tt} '
        f'transform="translate({final_x:.1f},{final_y:.1f})">'
        f'{title}{translate_animate}'
        f'<g transform="scale(1)">{scale_animate}{sun_shape}</g>'
        f'</g>'
    )


def _render_timeline_clouds(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.model_effort_order:
        return ''

    positions = _cloud_positions(len(timeline.model_effort_order))
    elements = []
    for (slot_x, slot_y), model in zip(
        positions, timeline.model_effort_order, strict=True
    ):
        days = timeline.model_effort_days[model]
        final_tokens = days[-1].output_tokens + days[-1].input_tokens
        final_radius = _cloud_radius(final_tokens)
        # Clamped against the *final* radius: the slot is fixed for the whole
        # animation while the cloud scales up into it, so fitting at full size
        # means it fits on every frame.
        cx, cy = _clamp_cloud_position(slot_x, slot_y, final_radius)

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
        gradient_id = _cloud_gradient_id(_effort_from_cloud_label(model))
        puffs = ''.join(
            f'<path d="{d}" fill="url(#{gradient_id})" opacity="0.88" />'
            for d in _cloud_puffs_d(final_radius, model)
        )
        day_labels = [
            f'{model} — {day_stat.output_tokens + day_stat.input_tokens:,} '
            f'tokens'
            for day_stat in days
        ]
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        elements.append(
            f'<g class="cloud" {tt} transform="translate({cx:.1f},{cy:.1f})">'
            f'{title}<g transform="scale(1)">{animate}{puffs}</g>'
            f'</g>'
        )
    return ''.join(elements)


def _render_timeline_birds(timeline: GardenTimeline) -> str:
    """The flock, at full size for the whole replay but drifting as it flies.

    Everything else in the timeline replays day by day, but cartoon only
    reports a single since-window snapshot -- there are no per-day frames
    to animate, and faking a growth curve for them would be inventing
    history the tool never recorded. So the birds never grow; they just
    drift on their own loop (see `_bird_drift`), with their window spelled
    out in the tooltip.
    """
    # Keyed to the *final* sun, which climbs during the replay: a flock
    # placed clear of where the sun ends up is clear of it throughout.
    final_tokens = (
        timeline.cumulative_total_tokens[-1]
        if timeline.cumulative_total_tokens
        else 0
    )
    sun_x, sun_y = _sun_position(final_tokens)
    sun = (sun_x, sun_y, _sun_radius(final_tokens))

    flock = timeline.birds[:MAX_BIRDS]
    if not flock:
        return ''
    slots = _bird_slots(flock, sun)
    elements = []
    rules = []
    for index, (bird, (x, y, size)) in enumerate(
        zip(flock, slots, strict=True)
    ):
        dx, dy = _bird_drift(index, x, y, size, sun)
        rules.append(_bird_drift_rule(index, dx, dy))
        elements.append(
            f'<g class="bird">'
            f'{_title(_bird_label(bird, timeline.cartoon_since))}'
            f'<g class="bird-drift bird-drift-{index}">'
            f'{_render_bird(x, y, size)}</g></g>'
        )
    style = _bird_drift_style(rules)
    return f'<g class="birds">{style}{"".join(elements)}</g>'


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
        day_labels = [
            f'{tool} — used {day_stat.count:,} times' for day_stat in days
        ]
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        elements.append(
            f'<g class="bush" {tt} '
            f'transform="translate({x:.1f},{GROUND_Y})">'
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

    day_labels = [
        f'Cache efficiency — {read:,} cache reads per {write:,} cache writes'
        for read, write in zip(
            timeline.cumulative_cache_read,
            timeline.cumulative_cache_write,
            strict=True,
        )
    ]
    title = _title(day_labels[-1])
    tt = _tt_attr(day_labels)
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
            f'{translate_animate}{opacity_animate}{flower}'
            f'</g>'
        )
    return f'<g class="flowers" {tt}>{title}{"".join(elements)}</g>'


def _render_timeline_sunflowers(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    """Sunflowers growing out of the soil as each repo's prompts accumulate.

    Scaled from the ground-contact point like `_render_timeline_bushes`,
    so a stalk rises out of the earth rather than inflating in place, and
    keyed to each day's share of the repo's *final* prompt count for the
    same reason as `_bush_day_radii`.
    """
    repos = _sunflower_repos(
        [
            RepoBranch(
                repo=repo,
                sessions=0,
                lines_added=0,
                lines_removed=0,
                output_tokens=0,
                input_tokens=0,
                cost=0.0,
                prompts=timeline.branch_days[repo][-1].prompts,
            )
            for repo in timeline.branch_order
        ]
    )
    if not repos:
        return ''

    xs = _sunflower_x_positions(len(repos))
    elements = []
    for x, branch in zip(xs, repos, strict=True):
        days = timeline.branch_days[branch.repo]
        final_height = _sunflower_height(branch.prompts)
        final_prompts = days[-1].prompts
        scale_values = []
        for day_stat in days:
            fraction = (
                min(day_stat.prompts / final_prompts, 1.0)
                if final_prompts
                else 1.0
            )
            day_height = (
                SUNFLOWER_HEIGHT_MIN
                + (final_height - SUNFLOWER_HEIGHT_MIN) * fraction
            )
            scale_values.append(f'{day_height / final_height:.4f}')
        animate = _animate_transform_tag(
            'scale', scale_values, key_times, duration
        )
        plant = _render_sunflower(0, 0, final_height, branch.repo)
        day_labels = [
            f'{branch.repo} — {day_stat.prompts:,} prompts'
            for day_stat in days
        ]
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        elements.append(
            f'<g class="sunflower" {tt} '
            f'transform="translate({x:.1f},{GROUND_Y})">'
            f'{title}<g transform="scale(1)">{animate}{plant}</g>'
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
            prompts=timeline.branch_days[repo][-1].prompts,
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
        total_tokens=(
            timeline.cumulative_total_tokens[-1]
            if timeline.cumulative_total_tokens
            else 0
        ),
    )


def _render_tap_tooltip(
    view_height: float,
    key_times: list[float] | None = None,
    duration: float = 0.0,
) -> str:
    """A tap-activated stand-in for `<title>`, which never fires on touch.

    Browsers only surface a native `<title>` on hover, so on a phone every
    shape in the garden is silent. This draws the same text as real SVG
    content instead, and it has to live inside this document rather than
    the host page because the site embeds the garden through `<object>`,
    which nothing in the page's own DOM can draw over.

    On the timeline, a shape's stats keep growing after it's drawn (a
    branch mid-animation is not yet at its final session count), so a
    static `<title>` set once to the final day is wrong for most of the
    replay. Elements that grow carry a `data-tt` attribute instead (see
    `_tt_attr`) -- one label per day -- and this reads the SMIL clock via
    `getCurrentTime()` to pick the label matching what's on screen right
    now, for both the tap gesture and (since native `<title>` can't do
    this at all) mouse hover.
    """
    key_times = key_times or [0.0]
    box = (
        f'<rect id="ccgarden-tooltip-box" x="0" y="0" width="10" '
        f'height="{TOOLTIP_HEIGHT:.1f}" rx="6" fill="#fbfbf3" '
        f'stroke="#3a2412" stroke-width="1" opacity="0.95" />'
    )
    text = (
        f'<text id="ccgarden-tooltip-text" x="{TOOLTIP_PAD:.1f}" '
        f'y="{TOOLTIP_PAD + TOOLTIP_FONT_SIZE * 0.8:.1f}" '
        f'font-family="Georgia, serif" '
        f'font-size="{TOOLTIP_FONT_SIZE:.1f}" fill="#2f3b23"></text>'
    )
    group = (
        f'<g id="ccgarden-tooltip" opacity="0" '
        f'style="pointer-events:none;">{box}{text}</g>'
    )
    script = (
        '<script><![CDATA[\n'
        '(function () {\n'
        '  var svg = document.documentElement;\n'
        '  var group = document.getElementById("ccgarden-tooltip");\n'
        '  var box = document.getElementById("ccgarden-tooltip-box");\n'
        '  var text = document.getElementById("ccgarden-tooltip-text");\n'
        f'  var pad = {TOOLTIP_PAD:.1f};\n'
        f'  var boxHeight = {TOOLTIP_HEIGHT:.1f};\n'
        f'  var viewWidth = {VIEWBOX_WIDTH:.1f};\n'
        f'  var viewHeight = {view_height:.1f};\n'
        f'  var keyTimes = [{",".join(f"{t:.4f}" for t in key_times)}];\n'
        f'  var duration = {duration:.4f};\n'
        '  function currentDayIndex() {\n'
        '    var t = svg.getCurrentTime();\n'
        '    if (duration <= 0 || t >= duration) {\n'
        '      return keyTimes.length - 1;\n'
        '    }\n'
        '    var frac = t / duration;\n'
        '    var idx = 0;\n'
        '    for (var i = 0; i < keyTimes.length; i++) {\n'
        '      if (keyTimes[i] <= frac + 1e-6) { idx = i; } else { break; }\n'
        '    }\n'
        '    return idx;\n'
        '  }\n'
        '  function findTooltip(node) {\n'
        '    while (node && node !== svg) {\n'
        '      if (node.id === "ccgarden-scrubber") { return null; }\n'
        '      var days = node.getAttribute\n'
        '        ? node.getAttribute("data-tt")\n'
        '        : null;\n'
        '      if (days) {\n'
        '        var list = JSON.parse(days);\n'
        '        var idx = Math.min(currentDayIndex(), list.length - 1);\n'
        '        return { label: list[idx], dynamic: true };\n'
        '      }\n'
        '      var kids = node.childNodes || [];\n'
        '      for (var i = 0; i < kids.length; i++) {\n'
        '        if (kids[i].nodeName === "title") {\n'
        '          return { label: kids[i].textContent, dynamic: false };\n'
        '        }\n'
        '      }\n'
        '      node = node.parentNode;\n'
        '    }\n'
        '    return null;\n'
        '  }\n'
        '  function toUserSpace(event) {\n'
        '    var ctm = svg.getScreenCTM();\n'
        '    if (!ctm) { return null; }\n'
        '    var point = svg.createSVGPoint();\n'
        '    point.x = event.clientX;\n'
        '    point.y = event.clientY;\n'
        '    return point.matrixTransform(ctm.inverse());\n'
        '  }\n'
        '  function hide() { group.setAttribute("opacity", "0"); }\n'
        '  function show(label, at) {\n'
        '    text.textContent = label;\n'
        '    var width = text.getComputedTextLength() + pad * 2;\n'
        '    box.setAttribute("width", width.toFixed(1));\n'
        '    var x = at.x - width / 2;\n'
        '    var y = at.y - boxHeight - 14;\n'
        '    if (x < 4) { x = 4; }\n'
        '    if (x + width > viewWidth - 4) {\n'
        '      x = viewWidth - 4 - width;\n'
        '    }\n'
        '    if (y < 4) { y = at.y + 18; }\n'
        '    if (y + boxHeight > viewHeight - 4) {\n'
        '      y = viewHeight - 4 - boxHeight;\n'
        '    }\n'
        '    group.setAttribute(\n'
        '      "transform",\n'
        '      "translate(" + x.toFixed(1) + "," + y.toFixed(1) + ")"\n'
        '    );\n'
        '    group.setAttribute("opacity", "1");\n'
        '  }\n'
        '  var dynamicNodes = svg.querySelectorAll("[data-tt]");\n'
        '  for (var d = 0; d < dynamicNodes.length; d++) {\n'
        '    var dKids = dynamicNodes[d].childNodes;\n'
        '    for (var k = dKids.length - 1; k >= 0; k--) {\n'
        '      if (dKids[k].nodeName === "title") {\n'
        '        dynamicNodes[d].removeChild(dKids[k]);\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '  svg.addEventListener("pointerdown", function (event) {\n'
        '    if (event.pointerType === "mouse") { return; }\n'
        '    var found = findTooltip(event.target);\n'
        '    var at = found ? toUserSpace(event) : null;\n'
        '    if (at) { show(found.label, at); } else { hide(); }\n'
        '  });\n'
        '  svg.addEventListener("pointermove", function (event) {\n'
        '    if (event.pointerType !== "mouse") { return; }\n'
        '    var found = findTooltip(event.target);\n'
        '    if (found && found.dynamic) {\n'
        '      show(found.label, toUserSpace(event));\n'
        '    } else {\n'
        '      hide();\n'
        '    }\n'
        '  });\n'
        '  // A touch pointer "leaves" the moment the finger lifts, which\n'
        '  // would undo the tap we just handled -- only a cursor exit.\n'
        '  svg.addEventListener("pointerleave", function (event) {\n'
        '    if (event.pointerType !== "mouse") { return; }\n'
        '    hide();\n'
        '  });\n'
        '})();\n'
        ']]></script>'
    )
    return group + script


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
        f'<rect x="0" y="{LEGEND_BAND_BOTTOM:.1f}" '
        f'width="{VIEWBOX_WIDTH:.1f}" '
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
    trunk_day_labels = [
        f'Trunk — {sessions} total sessions'
        for sessions in timeline.cumulative_sessions
    ]
    trunk_title = _title(trunk_day_labels[-1])
    trunk_tt = _tt_attr(trunk_day_labels)

    body = (
        _render_timeline_sun(timeline, key_times, duration)
        + _render_timeline_clouds(timeline, key_times, duration)
        + _render_timeline_birds(timeline)
        + f'<g class="trunk-group" {trunk_tt}>{trunk_title}'
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
        # Behind the bushes -- see the same ordering note in `render_svg`.
        + _render_timeline_sunflowers(timeline, key_times, duration)
        + _render_timeline_bushes(timeline, key_times, duration)
        + _render_timeline_flowers_on_bushes(timeline, key_times, duration)
        + _render_legend(with_birds=bool(timeline.birds))
        + _render_scrubber(timeline, key_times, duration)
        + _render_tap_tooltip(TIMELINE_VIEWBOX_HEIGHT, key_times, duration)
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
