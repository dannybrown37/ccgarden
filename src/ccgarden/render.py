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
TRUNK_BASE_HALF_WIDTH_MIN = 8.0
TRUNK_BASE_HALF_WIDTH_MAX = 90.0
TRUNK_TOP_TAPER = 0.4
BRANCH_ZONE_HEIGHT = 220
BRANCH_LENGTH_MIN = 30.0
BRANCH_LENGTH_MAX = 260.0
BRANCH_SPREAD_DEGREES = 55.0
MAX_LEAVES_PER_BRANCH = 40
LEAF_SCATTER_RADIUS = 45.0
LEAF_RADIUS = 5.0


def _trunk_half_width(total_sessions: int) -> float:
    return min(
        TRUNK_BASE_HALF_WIDTH_MIN + total_sessions * 2.0,
        TRUNK_BASE_HALF_WIDTH_MAX,
    )


def _half_width_at(y: float, base_half_width: float) -> float:
    trunk_fraction = (GROUND_Y - y) / TRUNK_HEIGHT
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    return (
        base_half_width - (base_half_width - top_half_width) * trunk_fraction
    )


def _render_trunk(base_half_width: float) -> str:
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    cx = TRUNK_CENTER_X
    points = (
        f'{cx - base_half_width},{GROUND_Y} '
        f'{cx - top_half_width},{TRUNK_TOP_Y} '
        f'{cx + top_half_width},{TRUNK_TOP_Y} '
        f'{cx + base_half_width},{GROUND_Y}'
    )
    return (
        f'<polygon class="trunk" points="{points}" '
        f'fill="#6b4226" stroke="#4a2e1a" stroke-width="2" />'
    )


def _render_rings(rings: list[DayRing], base_half_width: float) -> str:
    if not rings:
        return ''
    elements = []
    count = len(rings)
    for index, day_ring in enumerate(rings):
        y = GROUND_Y - (index + 1) / (count + 1) * TRUNK_HEIGHT
        half_width = _half_width_at(y, base_half_width) * 0.9
        cx = TRUNK_CENTER_X
        stroke_width = min(1.0 + day_ring.sessions * 0.5, 6.0)
        elements.append(
            f'<line class="ring" x1="{cx - half_width}" y1="{y}" '
            f'x2="{cx + half_width}" y2="{y}" '
            f'stroke="#4a2e1a" stroke-width="{stroke_width}" '
            f'opacity="0.6" />'
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


def _render_branches_and_leaves(
    branches: list[RepoBranch], base_half_width: float
) -> str:
    if not branches:
        return ''
    elements = []
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
        stroke_width = min(2.0 + repo_branch.sessions * 0.3, 10.0)

        elements.append(
            f'<line class="branch" data-repo="{repo_branch.repo}" '
            f'x1="{origin_x}" y1="{origin_y}" x2="{end_x}" y2="{end_y}" '
            f'stroke="#4a2e1a" stroke-width="{stroke_width}" '
            f'stroke-linecap="round" />'
        )
        elements.append(_render_leaves(repo_branch, end_x, end_y))
    return ''.join(elements)


def _render_leaves(
    repo_branch: RepoBranch, center_x: float, center_y: float
) -> str:
    leaf_count = min(repo_branch.sessions, MAX_LEAVES_PER_BRANCH)
    if leaf_count == 0:
        return ''
    rng = random.Random(repo_branch.repo)
    elements = []
    for _ in range(leaf_count):
        offset_x = rng.uniform(-LEAF_SCATTER_RADIUS, LEAF_SCATTER_RADIUS)
        offset_y = rng.uniform(-LEAF_SCATTER_RADIUS, LEAF_SCATTER_RADIUS)
        elements.append(
            f'<circle class="leaf" cx="{center_x + offset_x}" '
            f'cy="{center_y + offset_y}" r="{LEAF_RADIUS}" '
            f'fill="#5a9e5a" opacity="0.85" />'
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
        f'<rect x="0" y="0" width="{VIEWBOX_WIDTH}" height="{VIEWBOX_HEIGHT}" '
        f'fill="#eaf4ea" />'
        f'<line x1="0" y1="{GROUND_Y}" x2="{VIEWBOX_WIDTH}" y2="{GROUND_Y}" '
        f'stroke="#3a5a3a" stroke-width="3" />'
        f'{body}'
        f'</svg>'
    )
