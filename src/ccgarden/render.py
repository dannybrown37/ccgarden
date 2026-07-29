from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccgarden.data import DayRing, GardenData, RepoBranch

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
MAX_LEAVES_PER_BRANCH = 40
CANOPY_MIN_LEAVES = 3
LEAF_SCATTER_RADIUS = 45.0
LEAF_RADIUS = 7.0
LEAF_COLORS = ('#3f7a3f', '#4f8f4f', '#5a9e5a', '#6bb26b', '#7dc47d')
LEAF_SHAPE_D = 'M0,-1 C0.55,-0.75 0.55,0.75 0,1 C-0.55,0.75 -0.55,-0.75 0,-1 Z'
LEAF_VEIN_D = 'M0,-0.85 L0,0.85'


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


def _render_leaves(
    repo_branch: RepoBranch, center_x: float, center_y: float
) -> str:
    leaf_count = min(repo_branch.sessions, MAX_LEAVES_PER_BRANCH)
    if leaf_count == 0:
        return ''
    rng = random.Random(repo_branch.repo)
    elements = []

    canopy_radius = min(20 + leaf_count * 2.4, 78.0)
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
