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
MAX_LEAVES_PER_BRANCH = 500
CANOPY_MIN_LEAVES = 3
CANOPY_RADIUS_MIN = 20.0
CANOPY_RADIUS_MAX = 130.0
LEAF_SCATTER_RADIUS = 45.0
LEAF_RADIUS = 7.0
LEAF_COLORS = ('#3f7a3f', '#4f8f4f', '#5a9e5a', '#6bb26b', '#7dc47d')
LEAF_SHAPE_D = 'M0,-1 C0.55,-0.75 0.55,0.75 0,1 C-0.55,0.75 -0.55,-0.75 0,-1 Z'
LEAF_VEIN_D = 'M0,-0.85 L0,0.85'

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
        leaf_anchor_x = end_x + (end_x - origin_x) * 0.08
        leaf_anchor_y = end_y + (end_y - origin_y) * 0.08
        elements.append(
            _render_leaves(repo_branch, leaf_anchor_x, leaf_anchor_y)
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
    saturation = min(leaf_count, MAX_LEAVES_PER_BRANCH)
    growth = math.sqrt(saturation / MAX_LEAVES_PER_BRANCH)
    return CANOPY_RADIUS_MIN + (CANOPY_RADIUS_MAX - CANOPY_RADIUS_MIN) * growth


def _render_leaves(
    repo_branch: RepoBranch, center_x: float, center_y: float
) -> str:
    leaf_count = min(repo_branch.sessions, MAX_LEAVES_PER_BRANCH)
    if leaf_count == 0:
        return ''
    rng = random.Random(repo_branch.repo)
    elements = []

    canopy_radius = _canopy_radius(leaf_count)
    if leaf_count >= CANOPY_MIN_LEAVES:
        shadow_d = _blob_path(
            center_x + canopy_radius * 0.18,
            center_y + canopy_radius * 0.22,
            canopy_radius * 0.92,
            rng,
        )
        elements.append(
            f'<path class="canopy" d="{shadow_d}" fill="#2f5f2f" '
            f'opacity="0.35" filter="url(#softBlur)" />'
        )
        blob_d = _blob_path(center_x, center_y, canopy_radius, rng)
        elements.append(
            f'<path class="canopy" d="{blob_d}" fill="url(#canopyGradient)" '
            f'opacity="0.92" />'
        )
        scatter_radius = canopy_radius * 0.75
    else:
        scatter_radius = LEAF_SCATTER_RADIUS * 0.4

    for _ in range(leaf_count):
        offset_x = rng.uniform(-scatter_radius, scatter_radius)
        offset_y = rng.uniform(-scatter_radius, scatter_radius)
        radius = max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5)
        angle = rng.uniform(0, 360)
        color = rng.choice(LEAF_COLORS)
        leaf_x = center_x + offset_x
        leaf_y = center_y + offset_y
        elements.append(
            f'<g class="leaf" transform="translate({leaf_x:.1f},{leaf_y:.1f}) '
            f'rotate({angle:.1f}) scale({radius:.2f})">'
            f'<path d="{LEAF_SHAPE_D}" fill="{color}" opacity="0.92" />'
            f'<path d="{LEAF_VEIN_D}" stroke="#2f5f2f" stroke-width="0.12" '
            f'opacity="0.5" />'
            f'</g>'
        )
    return ''.join(elements)


def render_svg(garden: GardenData) -> str:
    total_sessions = sum(day_ring.sessions for day_ring in garden.rings)
    base_half_width = _trunk_half_width(total_sessions)

    body = (
        _render_trunk(base_half_width)
        + _render_rings(garden.rings, base_half_width)
        + _render_branches_and_leaves(garden.branches, base_half_width)
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
        anchor_by_day: list[tuple[float, float]] = []
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
                anchor_by_day.append((origin_x, origin_y))
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
            anchor_by_day.append(
                (
                    end_x + (end_x - origin_x) * 0.08,
                    end_y + (end_y - origin_y) * 0.08,
                )
            )

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
                anchor_by_day,
                key_times=key_times,
                duration=duration,
            )
        )
    return ''.join(elements)


def _render_timeline_leaves(
    repo: str,
    days: list[RepoBranchDay],
    anchor_by_day: list[tuple[float, float]],
    *,
    key_times: list[float],
    duration: float,
) -> str:
    day_count = len(days)
    leaf_count = min(days[-1].sessions, MAX_LEAVES_PER_BRANCH)
    if leaf_count == 0:
        return ''

    elements = []
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    # Scatter radius per day -- grown in step with the canopy/leaf count so
    # a leaf born early (while the branch is still short) lands close to
    # that day's small cluster instead of being flung out to where the
    # *final* canopy will eventually reach.
    scatter_radius_by_day = []
    if has_canopy:
        shadow_values = []
        main_values = []
        for day_stat, (center_x, center_y) in zip(
            days, anchor_by_day, strict=True
        ):
            day_leaf_count = min(day_stat.sessions, MAX_LEAVES_PER_BRANCH)
            radius = (
                _canopy_radius(day_leaf_count)
                if day_leaf_count >= CANOPY_MIN_LEAVES
                else 0.0
            )
            scatter_radius_by_day.append(radius * 0.75)
            shadow_values.append(
                _blob_path(
                    center_x + radius * 0.18,
                    center_y + radius * 0.22,
                    radius * 0.92,
                    random.Random(f'{repo}:shadow'),
                )
            )
            main_values.append(
                _blob_path(
                    center_x, center_y, radius, random.Random(f'{repo}:canopy')
                )
            )
        shadow_animate = _animate_tag('d', shadow_values, key_times, duration)
        main_animate = _animate_tag('d', main_values, key_times, duration)
        elements.append(
            f'<path class="canopy" d="{shadow_values[-1]}" fill="#2f5f2f" '
            f'opacity="0.35" filter="url(#softBlur)">{shadow_animate}</path>'
        )
        elements.append(
            f'<path class="canopy" d="{main_values[-1]}" '
            f'fill="url(#canopyGradient)" opacity="0.92">{main_animate}</path>'
        )
    else:
        final_scatter = LEAF_SCATTER_RADIUS * 0.4
        for day_stat in days:
            day_leaf_count = min(day_stat.sessions, MAX_LEAVES_PER_BRANCH)
            fraction = day_leaf_count / leaf_count if leaf_count else 0.0
            scatter_radius_by_day.append(final_scatter * fraction)

    rng = random.Random(f'{repo}:leaves')
    for leaf_index in range(leaf_count):
        offset_unit_x = rng.uniform(-1.0, 1.0)
        offset_unit_y = rng.uniform(-1.0, 1.0)
        radius = max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5)
        angle = rng.uniform(0, 360)
        color = rng.choice(LEAF_COLORS)

        # Track the branch's anchor point every day, not just on the day
        # this leaf appears -- otherwise the leaf fades in already sitting
        # at its (eventual) resting spot while the branch under it is
        # still visibly mid-growth, instead of riding the tip out with it.
        positions = [
            (
                anchor_x + offset_unit_x * scatter,
                anchor_y + offset_unit_y * scatter,
            )
            for (anchor_x, anchor_y), scatter in zip(
                anchor_by_day, scatter_radius_by_day, strict=True
            )
        ]
        final_x, final_y = positions[-1]
        translate_values = [f'{x:.1f},{y:.1f}' for x, y in positions]
        translate_animate = _animate_transform_tag(
            'translate', translate_values, key_times, duration
        )

        birth_index = next(
            (
                i
                for i, day_stat in enumerate(days)
                if day_stat.sessions > leaf_index
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
