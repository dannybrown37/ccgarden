from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from ccgarden.data import DayRing, GardenData, RepoBranch

if TYPE_CHECKING:
    from ccgarden.data import GardenTimeline, RepoBranchDay

VIEWBOX_WIDTH = 800
VIEWBOX_HEIGHT = 800
GROUND_Y = 750
TRUNK_HEIGHT = 300
TRUNK_TOP_Y = GROUND_Y - TRUNK_HEIGHT
TRUNK_CENTER_X = VIEWBOX_WIDTH / 2
TRUNK_BASE_HALF_WIDTH_MIN = 9.0
TRUNK_BASE_HALF_WIDTH_MAX = 30.0
TRUNK_TOP_TAPER = 0.72
BRANCH_ZONE_HEIGHT = 220
BRANCH_LENGTH_MIN = 30.0
BRANCH_LENGTH_MAX = 230.0
BRANCH_SPREAD_DEGREES = 55.0
BRANCH_TIP_WIDTH = 1.6
LEAVES_PER_SESSION = 5
LEAF_SATURATION_COUNT = 2000
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

TIMELINE_PER_DAY_SECONDS = 0.6
TIMELINE_MIN_DURATION_S = 5.0
TIMELINE_MAX_DURATION_S = 16.0
TIMELINE_MIN_DAYS_TO_ANIMATE = 2


def _trunk_half_width(total_sessions: int) -> float:
    return min(
        TRUNK_BASE_HALF_WIDTH_MIN + total_sessions * 0.8,
        TRUNK_BASE_HALF_WIDTH_MAX,
    )


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
        '<stop offset="0%" stop-color="#eaf6f0" />'
        '<stop offset="70%" stop-color="#eaf4ea" />'
        '<stop offset="100%" stop-color="#dcefe0" />'
        '</linearGradient>'
        '<linearGradient id="groundGradient" '
        'x1="0%" y1="0%" x2="0%" y2="100%">'
        '<stop offset="0%" stop-color="#74b25e" />'
        '<stop offset="100%" stop-color="#3f7a3f" />'
        '</linearGradient>'
        '<linearGradient id="trunkGradient" x1="0%" y1="0%" x2="100%" y2="0%">'
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
        stroke_width = min(0.75 + day_ring.sessions * 0.3, 3.5)
        d = f'M {cx - half_width},{y} Q {cx},{y - bow} {cx + half_width},{y}'
        elements.append(
            f'<path class="ring" d="{d}" fill="none" stroke="#3a2412" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" '
            f'opacity="0.22" />'
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


def _render_branch_shape(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
) -> str:
    dx = end_x - origin_x
    dy = end_y - origin_y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    mid_x = (origin_x + end_x) / 2 + px * bow
    mid_y = (origin_y + end_y) / 2 + py * bow
    avg_width = (base_width + tip_width) / 2

    base_left = (origin_x + px * base_width, origin_y + py * base_width)
    base_right = (origin_x - px * base_width, origin_y - py * base_width)
    tip_left = (end_x + px * tip_width, end_y + py * tip_width)
    tip_right = (end_x - px * tip_width, end_y - py * tip_width)
    ctrl_left = (mid_x + px * avg_width, mid_y + py * avg_width)
    ctrl_right = (mid_x - px * avg_width, mid_y - py * avg_width)

    return (
        f'M {base_left[0]},{base_left[1]} '
        f'Q {ctrl_left[0]},{ctrl_left[1]} {tip_left[0]},{tip_left[1]} '
        f'L {tip_right[0]},{tip_right[1]} '
        f'Q {ctrl_right[0]},{ctrl_right[1]} {base_right[0]},{base_right[1]} '
        f'Z'
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

        length = min(
            BRANCH_LENGTH_MIN + repo_branch.lines_added * 0.15,
            BRANCH_LENGTH_MAX,
        )
        end_x, end_y = _branch_endpoint(
            origin_x, origin_y, length, side, y_fraction
        )
        base_width = min(2.2 + repo_branch.sessions * 0.22, 7.0)
        curve_rng = random.Random(f'{repo_branch.repo}:curve')
        bow = length * 0.08 * side * (0.7 + 0.6 * curve_rng.random())

        shape_d = _render_branch_shape(
            origin_x,
            origin_y,
            end_x,
            end_y,
            base_width=base_width,
            tip_width=BRANCH_TIP_WIDTH,
            bow=bow,
        )
        elements.append(
            f'<path class="branch" data-repo="{repo_branch.repo}" '
            f'd="{shape_d}" fill="url(#trunkGradient)" '
            f'stroke="#3a2412" stroke-width="0.75" opacity="0.95" />'
        )
        elements.append(
            _render_leaves(repo_branch, origin_x, origin_y, end_x, end_y)
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


def _leaf_along_branch_offset(
    rng: random.Random,
) -> tuple[float, float, float]:
    """A leaf's fixed (t, perpendicular, along) placement, branch-relative.

    t is skewed toward the tip so foliage is densest out there, while still
    covering back into the branch.
    """
    t_raw = rng.random() ** 0.55
    t = (
        FOLIAGE_START_FRACTION
        + (FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION) * t_raw
    )
    perp_unit = rng.uniform(-1.0, 1.0)
    along_unit = rng.uniform(-0.3, 0.3)
    return t, perp_unit, along_unit


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

    dx, dy = end_x - origin_x, end_y - origin_y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    canopy_radius = _canopy_radius(leaf_count)
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    if has_canopy:
        for fraction in _foliage_blob_fractions(length):
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
        t, perp_unit, along_unit = _leaf_along_branch_offset(rng)
        radius_bound = (
            canopy_radius * (0.2 + 0.8 * _foliage_girth_fraction(t))
            if has_canopy
            else LEAF_SCATTER_RADIUS * 0.4
        )
        cx = origin_x + t * dx
        cy = origin_y + t * dy
        leaf_x = cx + (px * perp_unit + ux * along_unit) * radius_bound
        leaf_y = cy + (py * perp_unit + uy * along_unit) * radius_bound
        radius = max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5)
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


LEGEND_X = 20.0
LEGEND_Y = 20.0
LEGEND_WIDTH = 250.0
LEGEND_PADDING = 14.0
LEGEND_TITLE_HEIGHT = 20.0
LEGEND_ROW_HEIGHT = 32.0
LEGEND_ROWS = (
    ('Trunk', 'width grows with total sessions', 'trunk'),
    ('Rings', 'one per day worked; bolder = busier day', 'ring'),
    ('Branches', 'one per repo; longer = more lines added', 'branch'),
    ('Leaves', 'one per session; more = busier repo', 'leaf'),
)


def _render_legend_icon(icon: str, cx: float, cy: float) -> str:
    if icon == 'trunk':
        return (
            f'<rect x="{cx - 6:.1f}" y="{cy - 7:.1f}" width="12" height="14" '
            f'rx="3" fill="url(#trunkGradient)" stroke="#3a2412" '
            f'stroke-width="0.6" />'
        )
    if icon == 'ring':
        return (
            f'<path d="M{cx - 7:.1f},{cy + 3:.1f} Q{cx:.1f},{cy - 5:.1f} '
            f'{cx + 7:.1f},{cy + 3:.1f}" fill="none" stroke="#3a2412" '
            f'stroke-width="2.2" stroke-linecap="round" opacity="0.6" />'
        )
    if icon == 'branch':
        return (
            f'<path d="M{cx - 7:.1f},{cy + 7:.1f} Q{cx:.1f},{cy - 2:.1f} '
            f'{cx + 7:.1f},{cy - 7:.1f}" fill="none" '
            f'stroke="url(#trunkGradient)" stroke-width="3" '
            f'stroke-linecap="round" />'
        )
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f}) rotate(-15) scale(6)">'
        f'<path d="{LEAF_SHAPE_D}" fill="#5a9e5a" opacity="0.95" />'
        f'</g>'
    )


def _render_legend() -> str:
    """A small key panel explaining what each part of the tree represents.

    Without it, the trunk/rings/branches/leaves are just abstract shapes.
    """
    height = (
        LEGEND_PADDING * 2
        + LEGEND_TITLE_HEIGHT
        + LEGEND_ROW_HEIGHT * len(LEGEND_ROWS)
    )
    icon_cx = LEGEND_X + LEGEND_PADDING + 10
    text_x = LEGEND_X + LEGEND_PADDING + 26
    parts = [
        (
            f'<g class="legend">'
            f'<rect x="{LEGEND_X:.1f}" y="{LEGEND_Y:.1f}" '
            f'width="{LEGEND_WIDTH:.1f}" height="{height:.1f}" rx="10" '
            f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.88" />'
            f'<text x="{LEGEND_X + LEGEND_PADDING:.1f}" '
            f'y="{LEGEND_Y + LEGEND_PADDING + 12:.1f}" '
            f'font-family="Georgia, serif" font-size="13" font-weight="bold" '
            f'fill="#2f3b23">Key</text>'
        )
    ]
    for index, (label, desc, icon) in enumerate(LEGEND_ROWS):
        row_cy = (
            LEGEND_Y
            + LEGEND_PADDING
            + LEGEND_TITLE_HEIGHT
            + LEGEND_ROW_HEIGHT * index
            + LEGEND_ROW_HEIGHT / 2
        )
        parts.append(_render_legend_icon(icon, icon_cx, row_cy))
        parts.append(
            f'<text x="{text_x:.1f}" y="{row_cy - 3:.1f}" '
            f'font-family="Georgia, serif" font-size="10.5" '
            f'font-weight="bold" fill="#2f3b23">{label}</text>'
        )
        parts.append(
            f'<text x="{text_x:.1f}" y="{row_cy + 10:.1f}" '
            f'font-family="Georgia, serif" font-size="9.5" '
            f'fill="#4a4a3a">{desc}</text>'
        )
    parts.append('</g>')
    return ''.join(parts)


def render_svg(garden: GardenData) -> str:
    total_sessions = sum(day_ring.sessions for day_ring in garden.rings)
    base_half_width = _trunk_half_width(total_sessions)

    body = (
        _render_trunk(base_half_width)
        + _render_rings(garden.rings, base_half_width)
        + _render_branches_and_leaves(garden.branches, base_half_width)
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
        target_width = min(0.75 + sessions * 0.3, 3.5)
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
        elements.append(
            f'<path class="ring" d="{d}" fill="none" stroke="#3a2412" '
            f'stroke-width="{target_width:.3f}" stroke-linecap="round" '
            f'opacity="0.22">{animate}</path>'
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
        final_sessions = days[-1].sessions
        final_length = min(
            BRANCH_LENGTH_MIN + final_lines_added * 0.15, BRANCH_LENGTH_MAX
        )
        final_width = min(2.2 + final_sessions * 0.22, 7.0)

        d_values = []
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
            width_fraction = (
                min(day_stat.sessions / final_sessions, 1.0)
                if final_sessions
                else 1.0
            )
            length = (
                BRANCH_LENGTH_MIN
                + (final_length - BRANCH_LENGTH_MIN) * length_fraction
            )
            end_x, end_y = _branch_endpoint(
                origin_x, origin_y, length, side, y_fraction
            )
            base_width = 2.2 + (final_width - 2.2) * width_fraction
            bow = length * 0.08 * side * (0.7 + 0.6 * bow_factor)
            d_values.append(
                _render_branch_shape(
                    origin_x,
                    origin_y,
                    end_x,
                    end_y,
                    base_width=base_width,
                    tip_width=BRANCH_TIP_WIDTH,
                    bow=bow,
                )
            )
            day_vectors.append((end_x - origin_x, end_y - origin_y))

        animate = _animate_tag('d', d_values, key_times, duration)
        elements.append(
            f'<path class="branch" data-repo="{repo}" d="{d_values[-1]}" '
            f'fill="url(#trunkGradient)" stroke="#3a2412" '
            f'stroke-width="0.75" opacity="0.95">{animate}</path>'
        )

        elements.append(
            _render_timeline_leaves(
                repo,
                days,
                origin_x,
                origin_y,
                day_vectors,
                final_length=final_length,
                key_times=key_times,
                duration=duration,
            )
        )
    return ''.join(elements)


def _render_timeline_leaves(
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

    elements = []
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    day_canopy_radius = [
        _canopy_radius(day_stat.sessions * LEAVES_PER_SESSION)
        if day_stat.sessions * LEAVES_PER_SESSION >= CANOPY_MIN_LEAVES
        else 0.0
        for day_stat in days
    ]

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
        t, perp_unit, along_unit = _leaf_along_branch_offset(rng)
        radius = max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5)
        angle = rng.uniform(0, 360)
        color = rng.choice(LEAF_COLORS)
        girth = _foliage_girth_fraction(t)

        # Track the branch's position every day, not just on the day this
        # leaf appears -- otherwise the leaf fades in already sitting at its
        # (eventual) resting spot while the branch under it is still
        # visibly mid-growth, instead of riding the tip out with it.
        positions = []
        for day_index, (dx, dy) in enumerate(day_vectors):
            cx = origin_x + t * dx
            cy = origin_y + t * dy
            radius_bound = (
                day_canopy_radius[day_index] * (0.2 + 0.8 * girth)
                if has_canopy
                else LEAF_SCATTER_RADIUS * 0.4
            )
            positions.append(
                (
                    cx + (px * perp_unit + ux * along_unit) * radius_bound,
                    cy + (py * perp_unit + uy * along_unit) * radius_bound,
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
    return GardenData(rings=rings, branches=branches)


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
    base_half_width_by_day = [
        _trunk_half_width(sessions)
        for sessions in timeline.cumulative_sessions
    ]
    final_base_half_width = base_half_width_by_day[-1]

    body = (
        _render_timeline_trunk(base_half_width_by_day, key_times, duration)
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
