"""Top-down garden plot renderer for ccgarden.

Renders a bird's-eye view of a kitchen garden where repos are raised
beds, model-effort combos are plant species, tools live in a shed,
and skills bloom as border flowers.  Driven by the same GardenData
that feeds the tree renderer, emitting SVG via string concatenation.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, NamedTuple

from ccgarden.render_utils import (
    _blend_hex,
    _escape_xml,
    _rain_opacity,
    _saturated_nightness,
    _title,
)

if TYPE_CHECKING:
    from ccgarden.data import (
        GardenData,
        RepoBranch,
        SkillFruit,
        ToolBush,
    )

# ── Viewbox and layout constants ───────────────────────────────

PLOT_VIEWBOX_WIDTH = 800
PLOT_VIEWBOX_HEIGHT = 800

FENCE_X = 60
FENCE_Y = 80
FENCE_W = 680
FENCE_H = 580

BED_ZONE_PAD = 12
BED_ZONE_X = FENCE_X + BED_ZONE_PAD
BED_ZONE_Y = FENCE_Y + BED_ZONE_PAD
BED_ZONE_W = FENCE_W - 2 * BED_ZONE_PAD
BED_ZONE_H = FENCE_H - 2 * BED_ZONE_PAD
BED_GUTTER = 8
BED_MIN_DIM = 40

LEGEND_BAND_Y = 740
LEGEND_BAND_HEIGHT = 130

# ── Color palette ──────────────────────────────────────────────

SOIL_COLOR = '#5c4033'
SOIL_DORMANT = '#7a6b5a'
FENCE_COLOR = '#8b6f47'
FENCE_POST_COLOR = '#5a3d1a'
PATH_COLOR = '#9e8a6d'
STONE_COLOR = '#c4a87a'
GRASS_COLOR = '#5a8f4a'
GRASS_DORMANT = '#8a7a5a'

SHED_BODY = '#7a4230'
SHED_ROOF = '#5a6670'
SUNDIAL_STONE = '#d4c9a8'
SUNDIAL_GNOMON = '#3a3a3a'
BARREL_WOOD = '#8b6914'
BARREL_BAND = '#4a4a4a'
BARREL_WATER = '#4a90c4'

PLANT_COLORS = {
    'haiku': '#7dba6d',
    'sonnet': '#4a8f4a',
    'opus': '#2d6b3d',
    'unknown': '#6a9a5a',
}
PLANT_DORMANT = '#b8a88a'
WEED_COLOR = '#8a7a55'
WEED_VITALITY_THRESHOLD = 0.75
WEED_MAX = 8

FLOWER_COLORS = ('#f4c95d', '#f27ab0', '#fdfdf6', '#c98bdb', '#f2896d')
FLOWER_CENTER = '#5a3d1a'

NIGHT_VEIL_COLOR = '#0a1628'

# ── Plant grid constants ───────────────────────────────────────

PLANT_SPACING_X = 16
PLANT_SPACING_Y = 18
PLANT_ROW_OFFSET = 8
PLANT_JITTER = 2.0
BED_AREA_SESSION_BONUS = 50
BED_FILL_FRACTION = 0.7

# ── Effort → plant scale ──────────────────────────────────────

EFFORT_SCALE = {
    'low': 0.7,
    'medium': 1.0,
    'high': 1.2,
    'xhigh': 1.3,
    'max': 1.4,
}
EFFORT_DARKNESS = {
    'low': -0.15,
    'medium': 0.0,
    'high': 0.15,
    'xhigh': 0.25,
    'max': 0.35,
}

# ── Token saturation for barrel ────────────────────────────────

BARREL_TOKEN_SATURATION = 5_000_000

OPACITY_EPSILON = 0.01


# ── Data types ─────────────────────────────────────────────────


class BedRect(NamedTuple):
    repo: str
    x: float
    y: float
    w: float
    h: float
    branch: RepoBranch


class PlantSpec(NamedTuple):
    model_family: str
    effort: str | None
    count: int


# ── Squarified treemap ─────────────────────────────────────────


def _bed_area_metric(branch: RepoBranch) -> float:
    return float(branch.lines_added + branch.sessions * BED_AREA_SESSION_BONUS)


def _worst_aspect(row_areas: list[float], side_length: float) -> float:
    if not row_areas or side_length <= 0:
        return math.inf
    total = sum(row_areas)
    worst = 0.0
    for area in row_areas:
        if total <= 0:
            return math.inf
        w = area / total * side_length
        h = total / side_length
        if w <= 0 or h <= 0:
            return math.inf
        ratio = max(w / h, h / w)
        worst = max(worst, ratio)
    return worst


def _squarify(
    values: list[float],
    rect: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    """Squarified treemap: values → non-overlapping rects."""
    if not values:
        return []

    total_value = sum(values)
    if total_value <= 0:
        return [(rect[0], rect[1], 0, 0)] * len(values)

    x, y, w, h = rect
    total_area = w * h

    indexed = sorted(
        [(v / total_value * total_area, i) for i, v in enumerate(values)],
        reverse=True,
    )

    results: list[tuple[float, float, float, float] | None] = [None] * len(
        values
    )

    while indexed:
        short_side = min(w, h)
        row = [indexed[0]]
        indexed = indexed[1:]

        while indexed:
            candidate = [*row, indexed[0]]
            if _worst_aspect(
                [a for a, _ in candidate], short_side
            ) <= _worst_aspect([a for a, _ in row], short_side):
                row = candidate
                indexed = indexed[1:]
            else:
                break

        row_total = sum(a for a, _ in row)

        if w >= h:
            row_width = row_total / h if h > 0 else w
            cy = y
            for area, idx in row:
                rh = area / row_width if row_width > 0 else h
                results[idx] = (x, cy, row_width, rh)
                cy += rh
            x += row_width
            w -= row_width
        else:
            row_height = row_total / w if w > 0 else h
            cx = x
            for area, idx in row:
                rw = area / row_height if row_height > 0 else w
                results[idx] = (cx, y, rw, row_height)
                cx += rw
            y += row_height
            h -= row_height

    return [r for r in results if r is not None]


def _layout_beds(branches: list[RepoBranch]) -> list[BedRect]:
    if not branches:
        return []

    metrics = [_bed_area_metric(b) for b in branches]
    rects = _squarify(
        metrics, (BED_ZONE_X, BED_ZONE_Y, BED_ZONE_W, BED_ZONE_H)
    )

    beds = []
    half = BED_GUTTER / 2
    for branch, (x, y, w, h) in zip(branches, rects, strict=True):
        bx = x + half
        by = y + half
        bw = max(w - BED_GUTTER, BED_MIN_DIM)
        bh = max(h - BED_GUTTER, BED_MIN_DIM)
        beds.append(BedRect(branch.repo, bx, by, bw, bh, branch))
    return beds


# ── Model family detection ─────────────────────────────────────


def _model_family(label: str) -> str:
    lower = label.lower()
    for family in ('haiku', 'sonnet', 'opus'):
        if family in lower:
            return family
    return 'unknown'


def _effort_from_label(label: str) -> str | None:
    """Extract effort level from a 'model (effort)' label."""
    if '(' in label and ')' in label:
        after = label.split('(', maxsplit=1)[1]
        return after.split(')', maxsplit=1)[0].strip()
    return None


def _plant_specs(branch: RepoBranch) -> list[PlantSpec]:
    specs = []
    for label, count in branch.model_effort_counts.items():
        if count <= 0:
            continue
        specs.append(
            PlantSpec(
                model_family=_model_family(label),
                effort=_effort_from_label(label),
                count=count,
            )
        )
    return sorted(specs, key=lambda s: s.count, reverse=True)


# ── Plant shapes (SVG symbols) ─────────────────────────────────


def _render_plant_defs() -> str:
    """<defs> block with <symbol> for each plant family."""
    haiku = (
        '<symbol id="plant-haiku" viewBox="-8 -8 16 16">'
        '<circle cx="0" cy="0" r="1.5" fill="#3a5a2a"/>'
        '<ellipse cx="0" cy="-4" rx="2" ry="3.5"'
        ' fill="currentColor" opacity="0.85"/>'
        '<ellipse cx="3.5" cy="2" rx="2" ry="3.5"'
        ' transform="rotate(120,0,0)"'
        ' fill="currentColor" opacity="0.80"/>'
        '<ellipse cx="-3.5" cy="2" rx="2" ry="3.5"'
        ' transform="rotate(-120,0,0)"'
        ' fill="currentColor" opacity="0.80"/>'
        '</symbol>'
    )
    sonnet = (
        '<symbol id="plant-sonnet" viewBox="-8 -8 16 16">'
        '<circle cx="0" cy="0" r="2" fill="#3a5a2a"/>'
    )
    for i in range(6):
        angle = i * 60
        sonnet += (
            f'<ellipse cx="0" cy="-4.5" rx="2.2" ry="3.8"'
            f' transform="rotate({angle},0,0)"'
            f' fill="currentColor" opacity="0.82"/>'
        )
    sonnet += '</symbol>'

    opus = (
        '<symbol id="plant-opus" viewBox="-8 -8 16 16">'
        '<circle cx="0" cy="0" r="2.5" fill="#1a4a2a"/>'
    )
    for i in range(8):
        angle = i * 45
        opus += (
            f'<ellipse cx="0" cy="-4" rx="2.5" ry="4"'
            f' transform="rotate({angle},0,0)"'
            f' fill="currentColor" opacity="0.78"/>'
        )
    for i in range(4):
        angle = i * 90 + 22.5
        opus += (
            f'<ellipse cx="0" cy="-2.8" rx="1.8" ry="2.8"'
            f' transform="rotate({angle},0,0)"'
            f' fill="currentColor" opacity="0.65"/>'
        )
    opus += '</symbol>'

    unknown = (
        '<symbol id="plant-unknown" viewBox="-8 -8 16 16">'
        '<circle cx="0" cy="0" r="1.5" fill="#3a5a2a"/>'
        '<ellipse cx="0" cy="-3.5" rx="1.8" ry="3"'
        ' fill="currentColor" opacity="0.8"/>'
        '<ellipse cx="3" cy="1.5" rx="1.8" ry="3"'
        ' transform="rotate(90,0,0)"'
        ' fill="currentColor" opacity="0.75"/>'
        '</symbol>'
    )

    weed = (
        '<symbol id="plant-weed" viewBox="-8 -8 16 16">'
        '<line x1="0" y1="3" x2="0" y2="-5"'
        f' stroke="{WEED_COLOR}" stroke-width="1"/>'
        '<line x1="0" y1="-1" x2="-3" y2="-4"'
        f' stroke="{WEED_COLOR}" stroke-width="0.8"/>'
        '<line x1="0" y1="-3" x2="2.5" y2="-6"'
        f' stroke="{WEED_COLOR}" stroke-width="0.8"/>'
        '<ellipse cx="-3" cy="-4.5" rx="1.5" ry="1"'
        f' fill="{WEED_COLOR}" opacity="0.7"/>'
        '<ellipse cx="2.5" cy="-6.5" rx="1.3" ry="0.9"'
        f' fill="{WEED_COLOR}" opacity="0.7"/>'
        '<ellipse cx="0" cy="-5.5" rx="1.2" ry="0.8"'
        f' fill="{WEED_COLOR}" opacity="0.6"/>'
        '</symbol>'
    )

    return haiku + sonnet + opus + unknown + weed


def _plant_color(
    family: str,
    effort: str | None,
    vitality: float,
) -> str:
    base = PLANT_COLORS.get(family, PLANT_COLORS['unknown'])
    color = _blend_hex(PLANT_DORMANT, base, vitality)
    darkness = EFFORT_DARKNESS.get(effort or 'medium', 0.0)
    if abs(darkness) < OPACITY_EPSILON:
        return color
    channels = []
    for start in (1, 3, 5):
        val = int(color[start : start + 2], 16)
        val = max(0, min(255, int(val * (1.0 - darkness))))
        channels.append(val)
    return '#{:02x}{:02x}{:02x}'.format(*channels)


def _plant_scale(effort: str | None) -> float:
    return EFFORT_SCALE.get(effort or 'medium', 1.0)


# ── Weeds (dormancy) ──────────────────────────────────────────


def _weed_count(vitality: float) -> int:
    if vitality >= WEED_VITALITY_THRESHOLD:
        return 0
    frac = (WEED_VITALITY_THRESHOLD - vitality) / WEED_VITALITY_THRESHOLD
    raw = math.sqrt(frac) * WEED_MAX
    return max(1, min(WEED_MAX, int(raw)))


def _render_bed_weeds(
    bed: BedRect,
    vitality: float,
) -> str:
    n = _weed_count(vitality)
    if n <= 0:
        return ''
    rng = random.Random(f'weeds-{bed.repo}')
    pad = 6
    parts: list[str] = []
    for _ in range(n):
        wx = rng.uniform(bed.x + pad, bed.x + bed.w - pad)
        wy = rng.uniform(bed.y + pad, bed.y + bed.h - pad)
        size = rng.uniform(8, 12)
        rot = rng.uniform(-30, 30)
        parts.append(
            f'<use href="#plant-weed"'
            f' x="{wx - size / 2:.1f}" y="{wy - size / 2:.1f}"'
            f' width="{size:.1f}" height="{size:.1f}"'
            f' transform="rotate({rot:.0f} {wx:.1f} {wy:.1f})"/>'
        )
    return ''.join(parts)


# ── Bed rendering ──────────────────────────────────────────────


def _bed_plant_count(
    bed: BedRect,
    max_sessions: int,
) -> int:
    """How many plant icons to draw in this bed.

    Each bed fills up to BED_FILL_FRACTION of its grid capacity,
    scaled by the repo's sessions relative to the busiest repo.
    """
    pad = 8
    cols = max(1, int((bed.w - 2 * pad) / PLANT_SPACING_X))
    rows = max(1, int((bed.h - 2 * pad) / PLANT_SPACING_Y))
    capacity = cols * rows
    share = bed.branch.sessions / max_sessions if max_sessions > 0 else 1.0
    return max(1, round(capacity * BED_FILL_FRACTION * share))


FURROW_MAX = 8
FURROW_LINES_SATURATION = 5000
FURROW_MIN_BED_HEIGHT = 20


def _furrow_count(lines_added: int) -> int:
    if lines_added <= 0:
        return 0
    raw = (
        math.sqrt(
            min(lines_added, FURROW_LINES_SATURATION) / FURROW_LINES_SATURATION
        )
        * FURROW_MAX
    )
    return max(1, int(raw))


def _render_bed_soil(
    bed: BedRect,
    vitality: float,
) -> str:
    color = _blend_hex(SOIL_DORMANT, SOIL_COLOR, vitality)
    parts = [
        (
            f'<rect x="{bed.x:.1f}" y="{bed.y:.1f}"'
            f' width="{bed.w:.1f}" height="{bed.h:.1f}"'
            f' rx="3" fill="{color}" stroke="{FENCE_POST_COLOR}"'
            f' stroke-width="1"/>'
        )
    ]
    n = _furrow_count(bed.branch.lines_added)
    if n > 0 and bed.h > FURROW_MIN_BED_HEIGHT:
        pad = 6
        for i in range(1, n + 1):
            fy = bed.y + pad + i * (bed.h - 2 * pad) / (n + 1)
            parts.append(
                f'<line x1="{bed.x + pad:.1f}" y1="{fy:.1f}"'
                f' x2="{bed.x + bed.w - pad:.1f}" y2="{fy:.1f}"'
                f' stroke="{FENCE_POST_COLOR}" stroke-width="0.4"'
                f' opacity="0.25"/>'
            )
    return ''.join(parts)


def _render_bed_plants(
    bed: BedRect,
    max_sessions: int,
    vitality: float,
) -> str:
    specs = _plant_specs(bed.branch)
    if not specs:
        return ''

    total_count = sum(s.count for s in specs)
    rng = random.Random(f'plot-plants-{bed.repo}')

    pad = 8
    cols = max(1, int((bed.w - 2 * pad) / PLANT_SPACING_X))
    rows = max(1, int((bed.h - 2 * pad) / PLANT_SPACING_Y))
    max_plants = cols * rows
    num_plants = min(max_plants, _bed_plant_count(bed, max_sessions))

    plant_list: list[PlantSpec] = []
    for spec in specs:
        share = spec.count / total_count if total_count > 0 else 1.0
        n = max(1, round(share * num_plants))
        plant_list.extend([spec] * n)
    plant_list = plant_list[:max_plants]

    parts: list[str] = []
    idx = 0
    for row in range(rows):
        if idx >= len(plant_list):
            break
        for col in range(cols):
            if idx >= len(plant_list):
                break
            spec = plant_list[idx]
            offset = PLANT_ROW_OFFSET if row % 2 else 0
            cx = (
                bed.x
                + pad
                + col * PLANT_SPACING_X
                + offset
                + rng.uniform(-PLANT_JITTER, PLANT_JITTER)
            )
            cy = (
                bed.y
                + pad
                + row * PLANT_SPACING_Y
                + rng.uniform(-PLANT_JITTER, PLANT_JITTER)
            )
            if cx > bed.x + bed.w - pad or cy > bed.y + bed.h - pad:
                idx += 1
                continue
            color = _plant_color(spec.model_family, spec.effort, vitality)
            scale = _plant_scale(spec.effort)
            size = 12 * scale
            symbol = f'plant-{spec.model_family}'
            parts.append(
                f'<use href="#{symbol}"'
                f' x="{cx - size / 2:.1f}" y="{cy - size / 2:.1f}"'
                f' width="{size:.1f}" height="{size:.1f}"'
                f' color="{color}"/>'
            )
            idx += 1
    return ''.join(parts)


def _render_bed_label(bed: BedRect) -> str:
    cx = bed.x + bed.w / 2
    cy = bed.y + bed.h - 8
    name = _escape_xml(bed.repo)
    font_size = min(11, max(6, bed.w / len(bed.repo) * 0.85))
    return (
        f'<text x="{cx:.1f}" y="{cy:.1f}"'
        f' text-anchor="middle"'
        f' font-family="Georgia, serif" font-size="{font_size:.1f}"'
        f' fill="#fff" opacity="0.8"'
        f' paint-order="stroke" stroke="{SOIL_COLOR}"'
        f' stroke-width="2.5" stroke-linejoin="round">'
        f'{name}</text>'
    )


def _bed_tooltip(branch: RepoBranch) -> str:
    parts = [f'{branch.repo}']
    parts.append(
        f'{branch.sessions} sessions, +{branch.lines_added}'
        f'/-{branch.lines_removed} lines'
    )
    tok_k = (branch.input_tokens + branch.output_tokens) / 1000
    if tok_k > 0:
        parts.append(f'{tok_k:.0f}k tokens')
    if branch.cost > 0:
        parts.append(f'${branch.cost:.2f}')
    if branch.model_effort_counts:
        top = sorted(
            branch.model_effort_counts.items(),
            key=lambda kv: -kv[1],
        )[:3]
        total = sum(branch.model_effort_counts.values())
        breakdown = ', '.join(f'{k}: {v * 100 // total}%' for k, v in top)
        parts.append(breakdown)
    return ' | '.join(parts)


def _render_beds(
    beds: list[BedRect],
    branches: list[RepoBranch],
    vitality: float,
) -> str:
    max_sessions = max(b.sessions for b in branches) if branches else 1
    parts: list[str] = []
    for bed in beds:
        tt = _title(_bed_tooltip(bed.branch))
        parts.append(
            f'<g class="bed">{tt}'
            + _render_bed_soil(bed, vitality)
            + _render_bed_plants(bed, max_sessions, vitality)
            + _render_bed_weeds(bed, vitality)
            + _render_bed_label(bed)
            + '</g>'
        )
    return ''.join(parts)


# ── Paths (gravel between beds) ────────────────────────────────


STONE_RADIUS_MIN = 4
STONE_RADIUS_MAX = 7
STONE_COUNT = 30


def _render_paths(beds: list[BedRect]) -> str:
    gravel = (
        f'<rect x="{BED_ZONE_X}" y="{BED_ZONE_Y}"'
        f' width="{BED_ZONE_W}" height="{BED_ZONE_H}"'
        f' fill="{PATH_COLOR}" rx="2"/>'
    )
    rng = random.Random('stepping-stones')
    stones: list[str] = []
    for _ in range(STONE_COUNT):
        sx = rng.uniform(BED_ZONE_X + 4, BED_ZONE_X + BED_ZONE_W - 4)
        sy = rng.uniform(BED_ZONE_Y + 4, BED_ZONE_Y + BED_ZONE_H - 4)
        if _point_in_any_bed(sx, sy, beds):
            continue
        r = rng.uniform(STONE_RADIUS_MIN, STONE_RADIUS_MAX)
        rot = rng.uniform(0, 360)
        stones.append(
            f'<ellipse cx="{sx:.1f}" cy="{sy:.1f}"'
            f' rx="{r:.1f}" ry="{r * 0.7:.1f}"'
            f' fill="{STONE_COLOR}" opacity="0.6"'
            f' transform="rotate({rot:.0f} {sx:.1f} {sy:.1f})"/>'
        )
    return gravel + ''.join(stones)


def _point_in_any_bed(
    px: float,
    py: float,
    beds: list[BedRect],
) -> bool:
    return any(
        bed.x <= px <= bed.x + bed.w and bed.y <= py <= bed.y + bed.h
        for bed in beds
    )


# ── Fence ──────────────────────────────────────────────────────


def _render_fence() -> str:
    parts = [
        (
            f'<rect x="{FENCE_X}" y="{FENCE_Y}"'
            f' width="{FENCE_W}" height="{FENCE_H}"'
            f' fill="none" stroke="{FENCE_COLOR}"'
            f' stroke-width="4" rx="4"/>'
        ),
    ]
    post_size = 6
    for px, py in [
        (FENCE_X, FENCE_Y),
        (FENCE_X + FENCE_W - post_size, FENCE_Y),
        (FENCE_X, FENCE_Y + FENCE_H - post_size),
        (FENCE_X + FENCE_W - post_size, FENCE_Y + FENCE_H - post_size),
    ]:
        parts.append(
            f'<rect x="{px:.1f}" y="{py:.1f}"'
            f' width="{post_size}" height="{post_size}"'
            f' fill="{FENCE_POST_COLOR}" rx="1"/>'
        )
    return ''.join(parts)


# ── Periphery: Shed ────────────────────────────────────────────


def _render_shed(tools: list[ToolBush]) -> str:
    sx, sy, sw, sh = 8, 12, 46, 60
    parts = [
        (
            f'<g class="shed">'
            f'{_title("Tool shed")}'
            f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}"'
            f' rx="3" fill="{SHED_BODY}" stroke="{FENCE_POST_COLOR}"'
            f' stroke-width="1"/>'
            f'<line x1="{sx + sw // 2}" y1="{sy}"'
            f' x2="{sx + sw // 2}" y2="{sy + sh}"'
            f' stroke="{SHED_ROOF}" stroke-width="3"/>'
            f'<rect x="{sx}" y="{sy}" width="{sw // 2}" height="{sh}"'
            f' rx="3" fill="{SHED_ROOF}" opacity="0.5"/>'
        ),
    ]
    top_tools = sorted(tools, key=lambda t: t.count, reverse=True)[:4]
    for i, tool in enumerate(top_tools):
        tx = sx + 6 + (i % 2) * 20
        ty = sy + sh + 6 + (i // 2) * 12
        parts.append(
            f'<text x="{tx}" y="{ty}"'
            f' font-family="monospace" font-size="7"'
            f' fill="{FENCE_COLOR}">'
            f'{_escape_xml(tool.tool[:6])}'
            f'{_title(f"{tool.tool}: {tool.count} calls")}'
            f'</text>'
        )
    parts.append('</g>')
    return ''.join(parts)


# ── Periphery: Sundial ─────────────────────────────────────────


def _render_sundial(hour_counts: dict[int, int]) -> str:
    cx, cy, r = 755, 45, 30
    parts = [
        (
            f'<g class="sundial">'
            f'{_title("Activity by hour")}'
            f'<circle cx="{cx}" cy="{cy}" r="{r}"'
            f' fill="{SUNDIAL_STONE}" stroke="{FENCE_POST_COLOR}"'
            f' stroke-width="1"/>'
        ),
    ]
    if hour_counts:
        max_count = max(hour_counts.values()) or 1
        peak_hour = max(hour_counts, key=lambda h: hour_counts[h])
        for hour, count in hour_counts.items():
            angle = (hour / 24) * 2 * math.pi - math.pi / 2
            intensity = count / max_count
            ex = cx + (r - 4) * math.cos(angle)
            ey = cy + (r - 4) * math.sin(angle)
            parts.append(
                f'<circle cx="{ex:.1f}" cy="{ey:.1f}"'
                f' r="{2 + intensity * 2:.1f}"'
                f' fill="#f4c95d" opacity="{0.3 + intensity * 0.6:.2f}"/>'
            )
        shadow_angle = (peak_hour / 24) * 2 * math.pi - math.pi / 2
        sx = cx + (r - 8) * math.cos(shadow_angle)
        sy = cy + (r - 8) * math.sin(shadow_angle)
        parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{sx:.1f}" y2="{sy:.1f}"'
            f' stroke="{SUNDIAL_GNOMON}" stroke-width="2"'
            f' stroke-linecap="round"/>'
        )
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{SUNDIAL_GNOMON}"/>'
        )
    parts.append('</g>')
    return ''.join(parts)


# ── Periphery: Water Barrel ────────────────────────────────────


def _render_barrel(total_tokens: int) -> str:
    cx, cy = 30, 695
    rw, rh = 18, 24
    fill = min(1.0, total_tokens / BARREL_TOKEN_SATURATION)
    parts = [
        (
            f'<g class="barrel">'
            f'{_title(f"Tokens: {total_tokens:,}")}'
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rw}" ry="{rh}"'
            f' fill="{BARREL_WOOD}" stroke="{BARREL_BAND}"'
            f' stroke-width="1.5"/>'
        ),
    ]
    for band_y in (-rh * 0.5, 0, rh * 0.5):
        parts.append(
            f'<ellipse cx="{cx}" cy="{cy + band_y:.1f}"'
            f' rx="{rw - 1}" ry="2"'
            f' fill="none" stroke="{BARREL_BAND}"'
            f' stroke-width="1" opacity="0.6"/>'
        )
    water_ry = rh * fill * 0.7
    if water_ry > 1:
        parts.append(
            f'<ellipse cx="{cx}" cy="{cy + rh * 0.15:.1f}"'
            f' rx="{rw - 3}" ry="{water_ry:.1f}"'
            f' fill="{BARREL_WATER}" opacity="0.7"/>'
        )
    parts.append('</g>')
    return ''.join(parts)


# ── Periphery: Border Flowers ──────────────────────────────────


def _render_border_flowers(skills: list[SkillFruit]) -> str:
    if not skills:
        return ''
    x_start, x_end = 100, 740
    y = FENCE_Y + FENCE_H + 12
    span = x_end - x_start
    step = min(span / len(skills), 30)
    parts: list[str] = []
    for i, skill in enumerate(skills):
        fx = x_start + i * step + step / 2
        color = FLOWER_COLORS[i % len(FLOWER_COLORS)]
        radius = min(8, max(4, 3 + skill.count * 0.3))
        parts.append(f'<g>{_title(f"{skill.skill}: {skill.count}")}')
        for petal in range(5):
            angle = petal * 72
            parts.append(
                f'<ellipse cx="{fx:.1f}" cy="{y:.1f}"'
                f' rx="{radius * 0.45:.1f}" ry="{radius:.1f}"'
                f' transform="rotate({angle},{fx:.1f},{y:.1f})"'
                f' fill="{color}" opacity="0.8"/>'
            )
        parts.append(
            f'<circle cx="{fx:.1f}" cy="{y:.1f}" r="{radius * 0.3:.1f}"'
            f' fill="{FLOWER_CENTER}"/>'
            f'</g>'
        )
    return ''.join(parts)


# ── Night veil ─────────────────────────────────────────────────


def _render_plot_night(nightness: float) -> str:
    opacity = _saturated_nightness(nightness) * 0.55
    if opacity < OPACITY_EPSILON:
        return ''
    return (
        f'<rect x="0" y="0"'
        f' width="{PLOT_VIEWBOX_WIDTH}" height="{PLOT_VIEWBOX_HEIGHT}"'
        f' fill="{NIGHT_VEIL_COLOR}" opacity="{opacity:.3f}"'
        f' pointer-events="none"/>'
    )


# ── Rain overlay ───────────────────────────────────────────────


def _render_plot_rain(vitality: float) -> str:
    opacity = _rain_opacity(vitality)
    if opacity < OPACITY_EPSILON:
        return ''
    rng = random.Random('plot-rain')
    parts: list[str] = []
    for _ in range(80):
        rx = rng.uniform(0, PLOT_VIEWBOX_WIDTH)
        ry = rng.uniform(0, PLOT_VIEWBOX_HEIGHT)
        parts.append(
            f'<line x1="{rx:.1f}" y1="{ry:.1f}"'
            f' x2="{rx + 1.5:.1f}" y2="{ry + 8:.1f}"'
            f' stroke="#7799bb" stroke-width="0.8"'
            f' opacity="{opacity:.2f}"/>'
        )
    return ''.join(parts)


# ── Background ─────────────────────────────────────────────────


def _render_background(vitality: float) -> str:
    grass = _blend_hex(GRASS_DORMANT, GRASS_COLOR, vitality)
    return (
        f'<rect x="0" y="0"'
        f' width="{PLOT_VIEWBOX_WIDTH}"'
        f' height="{PLOT_VIEWBOX_HEIGHT}"'
        f' fill="{grass}"/>'
    )


# ── Defs ───────────────────────────────────────────────────────


def _render_plot_defs() -> str:
    return f'<defs>{_render_plant_defs()}</defs>'


# ── Legend ─────────────────────────────────────────────────────


def _render_plot_legend() -> str:
    ly = LEGEND_BAND_Y
    lh = LEGEND_BAND_HEIGHT
    lpad = 16
    parts = [
        (
            f'<rect x="0" y="{ly}" width="{PLOT_VIEWBOX_WIDTH}"'
            f' height="{lh}" fill="#3f5620"/>'
        ),
        (
            f'<rect x="{lpad}" y="{ly + 6}"'
            f' width="{PLOT_VIEWBOX_WIDTH - 2 * lpad}"'
            f' height="{lh - 12}" rx="6"'
            f' fill="#fbfbf3" opacity="0.88"/>'
        ),
    ]
    entries = [
        ('Beds', 'repos (area = lines added)'),
        ('Plants', 'model sessions (shape = model)'),
        ('Weeds', 'dormancy (low vitality)'),
        ('Flowers', 'skill usage'),
        ('Sundial', 'prompt hours'),
        ('Barrel', 'total tokens'),
        ('Shed', 'tool calls'),
    ]
    n_cols = 3
    col_w = (PLOT_VIEWBOX_WIDTH - 2 * lpad) / n_cols
    for i, (label, desc) in enumerate(entries):
        col = i % n_cols
        row = i // n_cols
        ex = lpad + 10 + col * col_w
        ey = ly + 22 + row * 36
        parts.append(
            f'<text x="{ex}" y="{ey}"'
            f' font-family="Georgia, serif" font-size="10"'
            f' font-weight="bold" fill="#333">'
            f'{_escape_xml(label)}</text>'
        )
        parts.append(
            f'<text x="{ex}" y="{ey + 13}"'
            f' font-family="Georgia, serif" font-size="8"'
            f' fill="#666">'
            f'{_escape_xml(desc)}</text>'
        )
    return ''.join(parts)


# ── Tap tooltip ───────────────────────────────────────────────

TOOLTIP_PAD = 8.0
TOOLTIP_FONT_SIZE = 11.0
TOOLTIP_HEIGHT = TOOLTIP_FONT_SIZE + TOOLTIP_PAD * 2


def _render_plot_tap_tooltip() -> str:
    box = (
        f'<rect id="plot-tooltip-box" x="0" y="0" width="10"'
        f' height="{TOOLTIP_HEIGHT:.1f}" rx="5"'
        f' fill="#fbfbf3" stroke="#3a2412"'
        f' stroke-width="1" opacity="0.95"/>'
    )
    text = (
        f'<text id="plot-tooltip-text"'
        f' x="{TOOLTIP_PAD:.1f}"'
        f' y="{TOOLTIP_PAD + TOOLTIP_FONT_SIZE * 0.8:.1f}"'
        f' font-family="Georgia, serif"'
        f' font-size="{TOOLTIP_FONT_SIZE:.1f}"'
        f' fill="#2f3b23"></text>'
    )
    group = (
        f'<g id="plot-tooltip" opacity="0"'
        f' style="pointer-events:none;">{box}{text}</g>'
    )
    script = (
        '<script><![CDATA[\n'
        '(function(){\n'
        '  var svg=document.documentElement;\n'
        '  var g=document.getElementById("plot-tooltip");\n'
        '  var bx=document.getElementById("plot-tooltip-box");\n'
        '  var tx=document.getElementById("plot-tooltip-text");\n'
        f'  var pad={TOOLTIP_PAD:.1f};\n'
        f'  var bh={TOOLTIP_HEIGHT:.1f};\n'
        f'  var vw={PLOT_VIEWBOX_WIDTH};\n'
        f'  var vh={LEGEND_BAND_Y + LEGEND_BAND_HEIGHT};\n'
        '  function findTooltip(n){\n'
        '    while(n&&n!==svg){\n'
        '      var c=n.childNodes||[];\n'
        '      for(var i=0;i<c.length;i++){\n'
        '        if(c[i].nodeName==="title")\n'
        '          return c[i].textContent;\n'
        '      }\n'
        '      n=n.parentNode;\n'
        '    }\n'
        '    return null;\n'
        '  }\n'
        '  function pt(e){\n'
        '    var m=svg.getScreenCTM();\n'
        '    if(!m)return null;\n'
        '    var p=svg.createSVGPoint();\n'
        '    p.x=e.clientX;p.y=e.clientY;\n'
        '    return p.matrixTransform(m.inverse());\n'
        '  }\n'
        '  function hide(){g.setAttribute("opacity","0");}\n'
        '  function show(l,at){\n'
        '    tx.textContent=l;\n'
        '    var w=tx.getComputedTextLength()+pad*2;\n'
        '    bx.setAttribute("width",w.toFixed(1));\n'
        '    var x=at.x-w/2,y=at.y-bh-10;\n'
        '    if(x<4)x=4;\n'
        '    if(x+w>vw-4)x=vw-4-w;\n'
        '    if(y<4)y=at.y+14;\n'
        '    if(y+bh>vh-4)y=vh-4-bh;\n'
        '    g.setAttribute("transform",'
        '"translate("+x.toFixed(1)+","+y.toFixed(1)+")");\n'
        '    g.setAttribute("opacity","1");\n'
        '  }\n'
        '  svg.addEventListener("pointerdown",function(e){\n'
        '    if(e.pointerType==="mouse")return;\n'
        '    var l=findTooltip(e.target);\n'
        '    var a=l?pt(e):null;\n'
        '    if(a)show(l,a);else hide();\n'
        '  });\n'
        '  svg.addEventListener("pointermove",function(e){\n'
        '    if(e.pointerType!=="mouse")return;\n'
        '    var l=findTooltip(e.target);\n'
        '    var a=l?pt(e):null;\n'
        '    if(a)show(l,a);else hide();\n'
        '  });\n'
        '  svg.addEventListener("pointerleave",function(e){\n'
        '    if(e.pointerType!=="mouse")return;\n'
        '    hide();\n'
        '  });\n'
        '})();\n'
        ']]></script>'
    )
    return group + script


# ── Main entry point ───────────────────────────────────────────


def render_plot_svg(garden: GardenData) -> str:
    beds = _layout_beds(garden.branches)

    total_h = LEGEND_BAND_Y + LEGEND_BAND_HEIGHT
    body = (
        _render_background(garden.vitality)
        + _render_paths(beds)
        + _render_fence()
        + _render_beds(beds, garden.branches, garden.vitality)
        + _render_shed(garden.tools)
        + _render_sundial(garden.hour_counts)
        + _render_barrel(garden.total_tokens)
        + _render_border_flowers(garden.skills)
        + _render_plot_rain(garden.vitality)
        + _render_plot_night(garden.nightness)
        + _render_plot_legend()
        + _render_plot_tap_tooltip()
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {PLOT_VIEWBOX_WIDTH} {total_h}"'
        f' width="{PLOT_VIEWBOX_WIDTH}" height="{total_h}">'
        f'{_render_plot_defs()}'
        f'{body}'
        f'</svg>'
    )
