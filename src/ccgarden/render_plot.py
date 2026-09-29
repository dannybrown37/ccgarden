"""Top-down garden plot renderer for ccgarden.

Renders a bird's-eye view of a kitchen garden where repos are raised
beds, model-effort combos are plant species, tools live in a shed,
and skills bloom as border flowers.  Driven by the same GardenData
that feeds the tree renderer, emitting SVG via string concatenation.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import replace
from typing import TYPE_CHECKING, NamedTuple

from ccgarden.data import RECENT_WORK_DAYS
from ccgarden.plot_species import (
    SPECIES,
    assign_species,
    combo_name,
    model_family,
)
from ccgarden.render_utils import (
    EPSILON,
    _animate_tag,
    _animate_transform_tag,
    _blend_hex,
    _escape_xml,
    _exact_days_away,
    _frame_weights,
    _format_day,
    _format_tokens,
    _lerp_hex,
    _rain_opacity,
    _saturated_nightness,
    _timeline_duration,
    _title,
    _weighted_key_times,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ccgarden.data import (
        GardenData,
        GardenTimeline,
        RepoBranch,
        RepoBranchDay,
        SkillFruit,
        ToolBush,
    )

# ── Viewbox and layout constants ───────────────────────────────

PLOT_VIEWBOX_WIDTH = 800

FENCE_X = 40
FENCE_Y = 146
FENCE_W = 720
FENCE_H = 560

BED_ZONE_PAD = 12
BED_ZONE_X = FENCE_X + BED_ZONE_PAD
BED_ZONE_Y = FENCE_Y + BED_ZONE_PAD
BED_ZONE_W = FENCE_W - 2 * BED_ZONE_PAD
BED_ZONE_H = FENCE_H - 2 * BED_ZONE_PAD
BED_GUTTER = 14
BED_MIN_DIM = 40
# A floored bed still loses its gutter and may come out oblong, so the
# floor is set above BED_MIN_DIM² to leave room for both.
BED_MIN_AREA_SLACK = 1.6
BED_MIN_SHARE_CAP = 0.5

FLOWER_SPACING = 28
FLOWER_ROW_HEIGHT = 26
FLOWER_BORDER_PAD = 6
FLOWER_BORDER_X0 = FENCE_X + 10
FLOWER_BORDER_X1 = FENCE_X + FENCE_W - 10
FLOWER_BORDER_TOP = FENCE_Y + FENCE_H + 8
FLOWERS_PER_ROW = int((FLOWER_BORDER_X1 - FLOWER_BORDER_X0) // FLOWER_SPACING)

LEGEND_GAP = 16
PLOT_SCRUBBER_H = 44
LEGEND_COLS = 4
LEGEND_ROW_H = 36
LEGEND_TOP_PAD = 12
LEGEND_BOTTOM_PAD = 8
LEGEND_KEY_HEADER = 26

# ── Features above the fence ─────────────────────────────────

SHED_BOX = (22.0, 16.0, 124.0, 92.0)
BARREL_CX = 180.0
BARREL_CY = 96.0
BARREL_R = 25.0
BARREL_RIM = 5.0
BARREL_MIN_WATER = 0.35
BENCH_BOX = (222.0, 20.0, 262.0, 96.0)
BENCH_PAD = 8.0
BENCH_MAX_TOOLS = 8
TOOL_MIN_LEN = 34.0
TOOL_MAX_LEN = 72.0
TOOL_HEAD_LEN = 12.0
TOOL_LABEL_CHARS = 8
TOOL_KINDS = ('spade', 'rake', 'fork', 'trowel', 'hoe', 'shears')
TOOL_HANDLE = '#c0925a'
TOOL_METAL = '#8d969c'
SIGN_BOX = (500.0, 38.0, 144.0, 56.0)
SUNDIAL_CX = 718.0
SUNDIAL_CY = 70.0
SUNDIAL_R = 50.0
SUNDIAL_PATIO_R = 58.0
SUNDIAL_DAY = '#e8b64c'
SUNDIAL_NIGHT = '#7d8fd6'
NIGHT_START_HOUR = 21
NIGHT_END_HOUR = 6

# ── Motion ───────────────────────────────────────────────────

SWAY_VARIANTS = (
    ('', 'ccp-sway-a'),
    ('-b', 'ccp-sway-b'),
    ('-c', 'ccp-sway-c'),
)
SWAY_TIMING = ((5.3, 0.0), (6.1, 2.0), (7.4, 4.5))
SWAY_DEGREES = 4
FLOWER_MIN_R = 5.0
FLOWER_MAX_R = 11.0
MULCH_COLOR = '#4a3524'
BUTTERFLY_MAX = 5
BUTTERFLY_PER_SKILLS = 6
BUTTERFLY_WAYPOINTS = 6
FIREFLY_COUNT = 24
RAIN_STREAKS = 50
RAIN_RIPPLES = 40
NIGHT_VEIL_MAX = 0.55
# Shadows swing from morning (cast west) to the static render's
# afternoon offset as the replay runs, like the tree's sun.
SUN_SWEEP_START_DX = -6.0

# ── Light and depth ───────────────────────────────────────────

# One sun for the whole plot, up and to the left: every shadow falls
# down-right by this offset and every bevel is lit on its top-left.
LIGHT_DX = 4.0
LIGHT_DY = 5.0
SHADOW_BLUR = 2.5
SHADOW_OPACITY = 0.4
FRAME_WIDTH = 5.0
INNER_SHADE = 7.0
LAWN_STRIPE_WIDTH = 34

FENCE_POST_SPACING = 40
FENCE_POST_SIZE = 7
GATE_X = FENCE_X + FENCE_W / 2
GATE_WIDTH = 56
SHED_GATE_X = SHED_BOX[0] + SHED_BOX[2] / 2

# ── Color palette ──────────────────────────────────────────────

SOIL_COLOR = '#6b4a33'
FRAME_WOOD = '#a57a4c'
WEATHERED_WOOD = '#8f8a7e'
WOOD_WEATHER_MAX = 0.45
WOOD_TONE_RANGE = 0.12
MARKER_W = 6.0
MARKER_H = 8.0
SOIL_DORMANT = '#7a6b5a'
FENCE_COLOR = '#8b6f47'
FENCE_POST_COLOR = '#5a3d1a'
PATH_COLOR = '#9e8a6d'
STONE_COLOR = '#c4a87a'
GRASS_COLOR = '#5a8f4a'
GRASS_DORMANT = '#8a7a5a'

SHED_BODY = '#7a4230'
SHED_ROOF = '#8a5a3a'
SHED_MOSS = '#6f8a3a'
SHINGLE_COURSE = 9.0
SHINGLE_MIN_W = 3.5
SHINGLE_MAX_W = 7.0
SHINGLE_TONE = 0.1
SHED_MOSS_TUFTS = 7
SUNDIAL_STONE = '#d4c9a8'
SUNDIAL_GNOMON = '#3a3a3a'
BARREL_WOOD = '#8b6914'
BARREL_BAND = '#4a4a4a'
BARREL_WATER = '#4a90c4'

PLANT_DORMANT = '#b8a88a'
WEED_COLOR = '#b5bf4a'
WEED_FLOWER = '#f5cd2e'
# A dandelion leaf, pointing up from the rosette's heart: toothed edges
# are what make it read as a weed next to a crop's smooth foliage.
WEED_LEAF = (
    'M0 0 L-1.9 -1.6 L-0.9 -2.4 L-2.8 -3.5 L-1.2 -4.3 L-2.4 -5.6 L0 -7.6'
    ' L2.4 -5.6 L1.2 -4.3 L2.8 -3.5 L0.9 -2.4 L1.9 -1.6 Z'
)
# In days away, like rain: the first weed has to come up inside the
# shortest lapse the timeline inserts, or a working rhythm never shows one.
WEED_ONSET_DAYS = 2
WEED_FULL_DAYS = 10
WEED_MAX = 8
# Days after you last worked a bed until its sprinkler is off; the
# spray shrinks steadily across the window rather than cutting out.
SPRINKLER_DAYS = RECENT_WORK_DAYS
# Sessions in that window for a bed's sprinkler to reach ~63% of full
# strength; the curve flattens so one huge bed can't dwarf the rest.
SPRINKLER_SATURATION = 20.0
SPRINKLER_MIN_SCALE = 0.25
# Heads sit on a grid of cells about this wide; a huge bed widens the
# cells rather than going past SPRINKLER_MAX_HEADS.
SPRINKLER_CELL = 80.0
SPRINKLER_MAX_HEADS = 12
# A head looks for bare soil on this many points across each side of
# its cell, so it stands between plants rather than on one.
SPRINKLER_SEARCH_STEPS = 9
# The soil of a bed worked today, darkened as if just watered; it dries
# back to plain soil across the sprinkler window.
WET_SOIL = '#141a26'
WET_SOIL_MAX_OPACITY = 0.55
SPRINKLER_SPIN_SECS = 3.6
SPRINKLER_JET_DEGREES = 26
SPRINKLER_JET_DROPS = 5
SPRINKLER_HEAD_R = 3.0
SPRINKLER_SPRAY = '#e4f3fc'

FLOWER_COLORS = ('#f4c95d', '#f27ab0', '#fdfdf6', '#c98bdb', '#f2896d')
FLOWER_CENTER = '#5a3d1a'

NIGHT_VEIL_COLOR = '#0a1628'

# ── Dark-theme colors ─────────────────────────────────────────

DARK_FRAME_STROKE = '#2a3a1a'
DARK_GRASS = '#3d6630'
DARK_LEGEND_BG = '#2a3d18'
DARK_LEGEND_INNER = '#2c3422'
DARK_LEGEND_TEXT = '#d4d4c8'
DARK_LEGEND_DESC = '#a0a090'
DARK_TOOLTIP_BG = '#2c3422'
DARK_TOOLTIP_BORDER = '#5a6a3a'
DARK_TOOLTIP_TEXT = '#d4d4c8'

# ── Plant grid constants ───────────────────────────────────────

PLANT_MIN_SPACING = 19.0
PLANT_MAX_SPACING = 34.0
PLANT_OVERLAP = 0.85
# One size for every bed: a quiet bed spaces its plants out rather than
# growing them bigger, or a tiny bed's two plants dwarf everything.
PLANT_BASE_SIZE = PLANT_MIN_SPACING * PLANT_OVERLAP
PATCH_GAP = 10.0
PLANT_FILL_MIN = 0.2
PLANT_JITTER_FRACTION = 0.06
PLANT_SIZE_JITTER = 0.08
PLANT_EDGE_PAD = 4.0
SPROUT_SPAN = 0.25
HEX_ROW_RATIO = math.sqrt(3) / 2

LABEL_FONT_SIZE = 9.0
LABEL_MIN_FONT = 5.5
LABEL_CHAR_WIDTH = 0.55
LABEL_PAD = 4.0
LABEL_TURN_RATIO = 1.5
TAG_FILL = '#efe3c4'
TAG_EDGE = '#7a5a36'
TAG_TEXT = '#3a2a18'
BED_AREA_SESSION_BONUS = 50

# ── Effort → plant scale ──────────────────────────────────────

EFFORT_SCALE = {
    'low': 0.7,
    'medium': 1.0,
    'high': 1.2,
    'xhigh': 1.3,
    'max': 1.4,
}

# ── Token saturation for barrel ────────────────────────────────

# Totals include cache reads, which run to billions within weeks.
BARREL_TOKEN_SATURATION = 10_000_000_000

OPACITY_EPSILON = 0.01


# ── Data types ─────────────────────────────────────────────────


class BedRect(NamedTuple):
    repo: str
    x: float
    y: float
    w: float
    h: float
    branch: RepoBranch


class PlotLayout(NamedTuple):
    flower_rows: int
    legend_y: float
    total_h: int


class PlantSpec(NamedTuple):
    model_family: str
    effort: str | None
    replies: int
    label: str = ''
    species: str = 'sprout'


class BedTag(NamedTuple):
    text: str
    font: float
    cx: float
    cy: float
    w: float
    h: float
    vertical: bool

    @property
    def box(self) -> tuple[float, float, float, float]:
        """Its footprint on the page, after any turn."""
        hw, hh = (self.h, self.w) if self.vertical else (self.w, self.h)
        return (
            self.cx - hw / 2,
            self.cy - hh / 2,
            self.cx + hw / 2,
            self.cy + hh / 2,
        )


class RowMarker(NamedTuple):
    x: float
    y: float
    species: str
    label: str


class Stone(NamedTuple):
    x: float
    y: float
    r: float
    repos: tuple[str, str]


class ToolPlacement(NamedTuple):
    tool: ToolBush
    x: float
    y: float
    length: float
    kind: str


class SundialWedge(NamedTuple):
    hour: int
    length: float
    night: bool


class WaterDisc(NamedTuple):
    cx: float
    cy: float
    r: float


class PlantPlacement(NamedTuple):
    x: float
    y: float
    size: float
    spec: PlantSpec
    variant: int = 0


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


def _floored_metrics(metrics: list[float]) -> list[float]:
    """Raise tiny values so no bed's slot drops below a usable size.

    Inflating a bed *after* the treemap pushes it out of its slot and
    past the fence, so the floor has to go in before the layout runs.
    """
    zone_area = BED_ZONE_W * BED_ZONE_H
    slot = (BED_MIN_DIM + BED_GUTTER) ** 2 * BED_MIN_AREA_SLACK
    share = min(slot / zone_area, BED_MIN_SHARE_CAP / len(metrics))
    floored: set[int] = set()
    while True:
        free = sum(v for i, v in enumerate(metrics) if i not in floored)
        total = free / (1 - len(floored) * share)
        grown = {i for i, v in enumerate(metrics) if v < share * total}
        if grown <= floored:
            break
        floored |= grown
    return [
        share * total if i in floored else v for i, v in enumerate(metrics)
    ]


def _layout_beds(branches: list[RepoBranch]) -> list[BedRect]:
    if not branches:
        return []

    metrics = _floored_metrics([_bed_area_metric(b) for b in branches])
    rects = _squarify(
        metrics, (BED_ZONE_X, BED_ZONE_Y, BED_ZONE_W, BED_ZONE_H)
    )

    beds = []
    half = BED_GUTTER / 2
    for branch, (x, y, w, h) in zip(branches, rects, strict=True):
        bw = max(w - BED_GUTTER, 0.0)
        bh = max(h - BED_GUTTER, 0.0)
        beds.append(BedRect(branch.repo, x + half, y + half, bw, bh, branch))
    return beds


def _flower_rows(n_skills: int) -> int:
    return math.ceil(n_skills / FLOWERS_PER_ROW)


def _legend_height(n_combos: int) -> float:
    rows = math.ceil(len(LEGEND_ENTRIES) / LEGEND_COLS)
    plant_rows = math.ceil(n_combos / LEGEND_COLS)
    key = LEGEND_KEY_HEADER + plant_rows * LEGEND_ROW_H if plant_rows else 0
    return LEGEND_TOP_PAD + rows * LEGEND_ROW_H + key + LEGEND_BOTTOM_PAD


def _plot_layout(n_skills: int, n_combos: int = 0) -> PlotLayout:
    rows = _flower_rows(n_skills)
    border_h = rows * FLOWER_ROW_HEIGHT + (
        2 * FLOWER_BORDER_PAD if rows else 0
    )
    legend_y = FLOWER_BORDER_TOP + border_h + LEGEND_GAP
    return PlotLayout(
        rows, legend_y, math.ceil(legend_y + _legend_height(n_combos))
    )


def _flower_positions(n_skills: int) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    span = FLOWER_BORDER_X1 - FLOWER_BORDER_X0
    for row in range(_flower_rows(n_skills)):
        in_row = min(FLOWERS_PER_ROW, n_skills - row * FLOWERS_PER_ROW)
        x0 = FLOWER_BORDER_X0 + (span - in_row * FLOWER_SPACING) / 2
        y = (
            FLOWER_BORDER_TOP
            + FLOWER_BORDER_PAD
            + (row + 0.5) * FLOWER_ROW_HEIGHT
        )
        positions.extend(
            (x0 + (i + 0.5) * FLOWER_SPACING, y) for i in range(in_row)
        )
    return positions


# ── Model family detection ─────────────────────────────────────


def _effort_from_label(label: str) -> str | None:
    """Extract effort level from a 'model (effort)' label."""
    if '(' in label and ')' in label:
        after = label.split('(', maxsplit=1)[1]
        return after.split(')', maxsplit=1)[0].strip()
    return None


def _plant_specs(
    branch: RepoBranch,
    species: dict[str, str] | None = None,
) -> list[PlantSpec]:
    """A bed's combos, busiest first, each with its garden-wide plant.

    ``species`` is assigned once per garden (``_garden_species``) so the
    same combo is the same plant in every bed; without it the bed
    assigns its own, which only a lone bed should rely on.
    """
    usage = {lbl: n for lbl, n in branch.model_effort_counts.items() if n > 0}
    labels = list(usage)
    plants = species or assign_species(usage)
    specs = [
        PlantSpec(
            model_family=model_family(label),
            effort=_effort_from_label(label),
            replies=branch.model_effort_counts[label],
            label=label,
            species=plants.get(label) or assign_species({label: 1})[label],
        )
        for label in labels
    ]
    return sorted(specs, key=lambda s: s.replies, reverse=True)


def _combo_totals(branches: list[RepoBranch]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for branch in branches:
        for label, n in branch.model_effort_counts.items():
            totals[label] = totals.get(label, 0) + n
    return totals


def _garden_species(branches: list[RepoBranch]) -> dict[str, str]:
    return assign_species(_combo_totals(branches))


class Combo(NamedTuple):
    label: str
    species: str
    share: float


def _garden_combos(branches: list[RepoBranch]) -> list[Combo]:
    """Every combo the garden grows, most-used first, with its share."""
    totals = _combo_totals(branches)
    species = assign_species(totals)
    grand = sum(n for n in totals.values() if n > 0)
    return [
        Combo(label, species[label], totals[label] / grand)
        for label in sorted(totals, key=lambda k: (-totals[k], k))
        if totals[label] > 0
    ]


def _percent(share: float) -> str:
    text = f'{share:.0%}'
    return '<1%' if share > 0 and text == '0%' else text


# ── Plant shapes (SVG symbols) ─────────────────────────────────


def _plant_symbol(family: str, shadow_r: float, body: str) -> str:
    """One top-down plant: cast shadow, leaves, then a shared highlight.

    Leaves are ``currentColor`` so each `<use>` tints its own plant,
    while the shine is one gradient shared by every plant on the plot.
    Each family comes in ``SWAY_VARIANTS`` copies on different wind
    clocks: a CSS animation inside a symbol moves every `<use>` of it,
    so one copy per phase is what keeps a bed from twitching in step.
    """
    symbols = []
    for suffix, sway in (*SWAY_VARIANTS, ('-still', 'plant-still')):
        symbols.append(
            f'<symbol id="plant-{family}{suffix}" viewBox="-10 -10 20 20"'
            f' overflow="visible">'
            f'<ellipse class="plant-shadow" cx="{LIGHT_DX * 0.45:.1f}"'
            f' cy="{LIGHT_DY * 0.45:.1f}" rx="{shadow_r:.1f}"'
            f' ry="{shadow_r * 0.92:.1f}" fill="#000" opacity="0.3"/>'
            f'<g class="{sway}" stroke="#000" stroke-opacity="0.28"'
            f' stroke-width="0.4">{body}</g>'
            f'<circle r="{shadow_r:.1f}" fill="url(#plantShine)"/>'
            f'</symbol>'
        )
    return ''.join(symbols)


def _render_plant_defs(species: set[str] | None = None) -> str:
    """Symbols for the plants this garden actually grows, plus weeds.

    Only the species in use are emitted -- each costs four symbols
    (three wind phases and a still copy for the legend).
    """
    wanted = sorted(species) if species else ['sprout']
    plants = ''.join(
        _plant_symbol(name, SPECIES[name].shadow_r, SPECIES[name].body)
        for name in wanted
    )
    weed = (
        '<symbol id="plant-weed" viewBox="-8 -8 16 16">'
        + ''.join(
            f'<path d="{WEED_LEAF}" transform="rotate({angle})"'
            f' fill="{WEED_COLOR}" stroke="{_shade(WEED_COLOR, -0.45)}"'
            ' stroke-width="0.35" stroke-linejoin="round"/>'
            for angle in (0, 55, 125, 180, 235, 300)
        )
        + f'<circle r="2" fill="{WEED_FLOWER}"'
        f' stroke="{_shade(WEED_FLOWER, -0.3)}" stroke-width="0.3"/>'
        f'<circle r="0.7" fill="{_shade(WEED_FLOWER, -0.25)}"/>'
        '</symbol>'
    )
    shine = (
        '<radialGradient id="plantShine" cx="0.32" cy="0.28" r="0.7">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0.5"/>'
        '<stop offset="0.55" stop-color="#fff" stop-opacity="0"/>'
        '</radialGradient>'
    )
    return shine + plants + weed


def _plant_color(species: str, vitality: float) -> str:
    base = SPECIES.get(species, SPECIES['sprout']).color
    return _blend_hex(PLANT_DORMANT, base, vitality)


def _plant_scale(spec: PlantSpec) -> float:
    art = SPECIES.get(spec.species, SPECIES['sprout'])
    return EFFORT_SCALE.get(spec.effort or 'medium', 1.0) * art.scale


# ── Weeds (dormancy) ──────────────────────────────────────────


def _weed_count(vitality: float) -> int:
    days = _exact_days_away(vitality)
    if days < WEED_ONSET_DAYS - EPSILON:
        return 0
    ramp = (days - WEED_ONSET_DAYS) / (WEED_FULL_DAYS - WEED_ONSET_DAYS)
    return 1 + round(min(1.0, ramp) * (WEED_MAX - 1))


class Weed(NamedTuple):
    x: float
    y: float
    size: float
    rot: float


def _bed_weeds(bed: BedRect) -> list[Weed]:
    """Every spot a weed can come up in this bed, in the order they do."""
    rng = random.Random(f'weeds-{bed.repo}')
    pad = 6
    return [
        Weed(
            rng.uniform(bed.x + pad, bed.x + bed.w - pad),
            rng.uniform(bed.y + pad, bed.y + bed.h - pad),
            rng.uniform(10, 15),
            rng.uniform(-30, 30),
        )
        for _ in range(WEED_MAX)
    ]


def _weed_use(weed: Weed) -> str:
    x, y, size = weed.x, weed.y, weed.size
    return (
        f'<use href="#plant-weed"'
        f' x="{x - size / 2:.1f}" y="{y - size / 2:.1f}"'
        f' width="{size:.1f}" height="{size:.1f}"'
        f' transform="rotate({weed.rot:.0f} {x:.1f} {y:.1f})"/>'
    )


def _render_bed_weeds(
    bed: BedRect,
    vitality: float,
) -> str:
    n = _weed_count(vitality)
    return ''.join(_weed_use(w) for w in _bed_weeds(bed)[:n])


def _render_timeline_weeds(
    bed: BedRect,
    vitality: list[float],
    clock: tuple[list[float], float],
) -> str:
    """Weeds come up through a lapse and are pulled when you're back."""
    counts = [_weed_count(v) for v in vitality]
    return ''.join(
        _grow_about(
            'weed-grow',
            (weed.x, weed.y),
            [1.0 if c > k else 0.0 for c in counts],
            clock,
            _weed_use(weed),
        )
        for k, weed in enumerate(_bed_weeds(bed)[: max(counts, default=0)])
    )


# ── Sprinklers ─────────────────────────────────────────────────


def _sprinkler_strength(
    idle_days: int | None, recent_sessions: int | None = None
) -> float:
    """How recently (fade) times how much (saturating) you worked a bed.

    ``recent_sessions=None`` means no opinion on the amount: full.
    """
    if idle_days is None:
        return 0.0
    recency = max(0.0, 1.0 - idle_days / SPRINKLER_DAYS)
    if recent_sessions is None:
        return recency
    amount = 1.0 - math.exp(-recent_sessions / SPRINKLER_SATURATION)
    return recency * amount


def _sprinkler_scale(strength: float) -> float:
    """Zero only when off, so an idle bed's last day still shows spray."""
    if strength <= 0:
        return 0.0
    return SPRINKLER_MIN_SCALE + (1 - SPRINKLER_MIN_SCALE) * strength


class SprinklerGrid(NamedTuple):
    heads: list[tuple[float, float]]
    reach: float


def _bare_spot(
    cell: tuple[float, float, float, float],
    plants: Sequence[PlantPlacement],
) -> tuple[float, float]:
    """The spot nearest the cell's centre that is clear of foliage.

    Clearance counts only up to the head's own radius, so a head takes
    the first gap between plants instead of fleeing to the bed's edge.
    """
    x, y, w, h = cell
    cx, cy = x + w / 2, y + h / 2
    if not plants:
        return cx, cy
    steps = SPRINKLER_SEARCH_STEPS
    spots = [
        (x + w * (i + 0.5) / steps, y + h * (j + 0.5) / steps)
        for i in range(steps)
        for j in range(steps)
    ]

    def clearance(spot: tuple[float, float]) -> tuple[float, float]:
        px, py = spot
        gap = min(math.hypot(px - p.x, py - p.y) - p.size / 2 for p in plants)
        return min(gap, SPRINKLER_HEAD_R), -math.hypot(px - cx, py - cy)

    return max(spots, key=clearance)


def _sprinkler_grid(
    bed: BedRect, plants: Sequence[PlantPlacement] = ()
) -> SprinklerGrid:
    """One head per cell, stood in bare soil, reaching its cell's corners.

    Reaching the corners means the circles overlap enough to wet the
    whole bed; the spill past the soil is clipped off.
    """
    sx, sy, sw, sh = _soil_rect(bed)
    cell = max(SPRINKLER_CELL, math.sqrt(sw * sh / SPRINKLER_MAX_HEADS))
    cols = max(1, round(sw / cell))
    rows = max(1, round(sh / cell))
    cw, ch = sw / cols, sh / rows
    heads: list[tuple[float, float]] = []
    reach = 0.0
    for r in range(rows):
        for c in range(cols):
            x, y = sx + c * cw, sy + r * ch
            hx, hy = _bare_spot((x, y, cw, ch), plants)
            heads.append((hx, hy))
            reach = max(
                reach,
                *(
                    math.hypot(hx - kx, hy - ky)
                    for kx in (x, x + cw)
                    for ky in (y, y + ch)
                ),
            )
    return SprinklerGrid(heads, reach)


def _sprinkler_clip(bed: BedRect) -> tuple[str, str]:
    """A clipPath to the soil, and the attribute that uses it."""
    clip_id = f'sprinkler-soil-{zlib.crc32(bed.repo.encode()):08x}'
    soil = _rect(_soil_rect(bed), '')
    return (
        f'<clipPath id="{clip_id}">{soil}</clipPath>',
        f'clip-path="url(#{clip_id})"',
    )


def _sprinkler_jet(cx: float, cy: float, reach: float) -> str:
    half = math.radians(SPRINKLER_JET_DEGREES / 2)
    x0, y0 = cx + reach * math.cos(-half), cy + reach * math.sin(-half)
    x1, y1 = cx + reach * math.cos(half), cy + reach * math.sin(half)
    drops = ''.join(
        f'<circle cx="{cx + reach * t:.1f}" cy="{cy:.1f}"'
        f' r="{1.5 - 0.7 * t:.2f}"/>'
        for t in (
            (k + 1) / SPRINKLER_JET_DROPS for k in range(SPRINKLER_JET_DROPS)
        )
    )
    return (
        f'<path d="M{cx:.1f},{cy:.1f} L{x0:.1f},{y0:.1f}'
        f' A{reach:.1f},{reach:.1f} 0 0 1 {x1:.1f},{y1:.1f}z"'
        f' fill="{SPRINKLER_SPRAY}" fill-opacity="0.4"/>'
        f'<g fill="{SPRINKLER_SPRAY}">{drops}</g>'
    )


def _sprinkler(
    cx: float, cy: float, reach: float, *, delay: float | None = None
) -> str:
    """A riser with its jet sweeping a circle of ``reach``.

    The invisible full circle pins the spinning group's box to the
    head, so ``fill-box`` turns it about the riser. ``delay=None`` is
    the legend's still copy.
    """
    jet = (
        f'<circle class="sprinkler-reach" cx="{cx:.1f}" cy="{cy:.1f}"'
        f' r="{reach:.1f}" fill="none"/>' + _sprinkler_jet(cx, cy, reach)
    )
    if delay is not None:
        jet = (
            f'<g class="ccp-spin" style="animation-delay:-{delay:.2f}s">'
            f'{jet}</g>'
        )
    head = (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{SPRINKLER_HEAD_R}"'
        f' fill="{TOOL_METAL}" stroke="#4d5357" stroke-width="0.8"/>'
        f'<circle cx="{cx - 0.8:.1f}" cy="{cy - 0.8:.1f}" r="1"'
        f' fill="#d7dde0"/>'
    )
    return (
        jet
        + _drop_shadow(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{SPRINKLER_HEAD_R}"/>'
        )
        + head
    )


def _bed_sprinklers(
    bed: BedRect,
    plants: Sequence[PlantPlacement],
    scales: list[float] | None = None,
    clock: tuple[list[float], float] | None = None,
    scale: float = 1.0,
) -> str:
    """Every head in the bed, clipped to the soil.

    With a ``clock`` each head grows about itself through ``scales``;
    without one they're drawn at ``scale``.
    """
    grid = _sprinkler_grid(bed, plants)
    rng = random.Random(f'sprinkler-{bed.repo}')
    heads = []
    for cx, cy in grid.heads:
        delay = rng.uniform(0, SPRINKLER_SPIN_SECS)
        if clock is None or scales is None:
            heads.append(_sprinkler(cx, cy, grid.reach * scale, delay=delay))
        else:
            heads.append(
                _grow_about(
                    'sprinkler-grow',
                    (cx, cy),
                    scales,
                    clock,
                    _sprinkler(cx, cy, grid.reach, delay=delay),
                )
            )
    clip, clip_attr = _sprinkler_clip(bed)
    return (
        f'{clip}<g class="sprinkler" pointer-events="none" {clip_attr}>'
        f'{"".join(heads)}</g>'
    )


def _render_bed_sprinkler(
    bed: BedRect, plants: Sequence[PlantPlacement]
) -> str:
    scale = _sprinkler_scale(
        _sprinkler_strength(bed.branch.idle_days, bed.branch.recent_sessions)
    )
    if scale <= 0:
        return ''
    return _bed_sprinklers(bed, plants, scale=scale)


def _render_timeline_sprinkler(
    bed: BedRect,
    plants: Sequence[PlantPlacement],
    strengths: list[float],
    clock: tuple[list[float], float],
) -> str:
    """Comes on the day you work the bed and winds down after."""
    scales = [_sprinkler_scale(v) for v in strengths]
    if not any(scales):
        return ''
    return _bed_sprinklers(bed, plants, scales, clock)


def _timeline_sprinkler_strengths(
    timeline: GardenTimeline, repo: str
) -> list[float]:
    idle = timeline.branch_idle_days.get(repo) or []
    counts = timeline.branch_recent_sessions.get(repo)
    recent: list[int | None] = list(counts) if counts else [None] * len(idle)
    return [
        _sprinkler_strength(d, n) for d, n in zip(idle, recent, strict=True)
    ]


def _wet_opacity(strength: float) -> str:
    return f'{WET_SOIL_MAX_OPACITY * strength:.3f}'


def _wet_rect(bed: BedRect, opacity: str, anim: str = '') -> str:
    return _rect(
        _soil_rect(bed),
        f'class="bed-wet" fill="{WET_SOIL}" opacity="{opacity}"'
        ' pointer-events="none"',
        anim,
    )


def _render_bed_wet(bed: BedRect) -> str:
    strength = _sprinkler_strength(
        bed.branch.idle_days, bed.branch.recent_sessions
    )
    if strength <= 0:
        return ''
    return _wet_rect(bed, _wet_opacity(strength))


def _render_timeline_wet(
    bed: BedRect,
    strengths: list[float],
    clock: tuple[list[float], float],
) -> str:
    """Soaked the day you work the bed, drying out day by day after."""
    if not any(strengths):
        return ''
    values = [_wet_opacity(v) for v in strengths]
    key_times, dur = clock
    return _wet_rect(
        bed, values[0], _animate_tag('opacity', values, key_times, dur)
    )


# ── Bed rendering ──────────────────────────────────────────────


def _tag_fit(name: str, length: float) -> tuple[str, float]:
    """The largest font that fits, cutting the name short at the floor."""
    room = length - 2 * LABEL_PAD
    font = min(LABEL_FONT_SIZE, room / (LABEL_CHAR_WIDTH * max(len(name), 1)))
    if font >= LABEL_MIN_FONT:
        return name, font
    chars = max(1, int(room / (LABEL_CHAR_WIDTH * LABEL_MIN_FONT)) - 1)
    return name[:chars].rstrip('-_. ') + '…', LABEL_MIN_FONT


def _bed_tag(bed: BedRect) -> BedTag:
    """A bed's name tag: pinned to the bottom board, or to the left one.

    A narrow bed turns its tag on its side rather than shrinking the
    text into illegibility; a name too long either way is cut short --
    the full name is still in the bed's tooltip.
    """
    sx, sy, sw, sh = _soil_rect(bed)
    flat_text, flat_font = _tag_fit(bed.repo, sw)
    vertical = flat_font < LABEL_FONT_SIZE and sh > sw * LABEL_TURN_RATIO
    text, font = _tag_fit(bed.repo, sh) if vertical else (flat_text, flat_font)
    w = LABEL_CHAR_WIDTH * len(text) * font + 2 * LABEL_PAD
    h = font + 5
    if vertical:
        cx, cy = bed.x + h / 2 + 1, sy + sh - w / 2 - 2
    else:
        cx, cy = sx + w / 2 + 2, bed.y + bed.h - h / 2 - 1
    return BedTag(text, font, cx, cy, w, h, vertical=vertical)


def _plant_area(bed: BedRect) -> tuple[float, float, float, float]:
    """The soil a bed's plants may be centred in: clear of the tag."""
    sx, sy, sw, sh = _soil_rect(bed)
    pad = PLANT_EDGE_PAD
    tag = _bed_tag(bed)
    _, y0, x1, _ = tag.box
    if tag.vertical:
        reserve = max(0.0, x1 - sx)
        return (
            sx + pad + reserve,
            sy + pad,
            sw - 2 * pad - reserve,
            sh - 2 * pad,
        )
    reserve = max(0.0, sy + sh - y0)
    return (sx + pad, sy + pad, sw - 2 * pad, sh - 2 * pad - reserve)


def _hex_rows(
    area: tuple[float, float, float, float],
    spacing: float,
) -> list[list[tuple[float, float]]]:
    """Staggered rows centred in ``area``, running along its long side.

    Points sit at cell centres rather than on the area's edges, so a
    plant's foliage stays inside the area instead of spilling half its
    width over a patch boundary.
    """
    ax, ay, aw, ah = area
    if ah > aw:
        return [
            [(x, y) for y, x in row]
            for row in _hex_rows((ay, ax, ah, aw), spacing)
        ]
    row_step = spacing * HEX_ROW_RATIO
    n_rows = max(1, int(ah / row_step))
    cols = max(1, int(aw / spacing))
    y0 = ay + (ah - (n_rows - 1) * row_step) / 2
    rows: list[list[tuple[float, float]]] = []
    for row in range(n_rows):
        n = cols - 1 if row % 2 and cols > 1 else cols
        x0 = ax + (aw - (n - 1) * spacing) / 2
        rows.append(
            [(x0 + col * spacing, y0 + row * row_step) for col in range(n)]
        )
    return rows


def _hex_grid(
    area: tuple[float, float, float, float],
    spacing: float,
) -> list[tuple[float, float]]:
    return [p for row in _hex_rows(area, spacing) for p in row]


def _patch_sizes(specs: list[PlantSpec], total: int) -> list[int]:
    """Split ``total`` plants across species by largest remainder."""
    weight = sum(s.replies for s in specs)
    exact = [s.replies / weight * total for s in specs]
    sizes = [int(e) for e in exact]
    by_remainder = sorted(
        range(len(specs)), key=lambda i: exact[i] - sizes[i], reverse=True
    )
    for i in by_remainder[: total - sum(sizes)]:
        sizes[i] += 1
    return sizes


def _strip_split(
    area: tuple[float, float, float, float],
    weights: list[float],
    floor: float,
) -> list[tuple[float, float, float, float]]:
    """Cut ``area`` along its long side into strips sized by weight.

    A bare path of ``PATCH_GAP`` runs between strips, the way a
    kitchen bed is planted in blocks rather than sown as one carpet.
    """
    ax, ay, aw, ah = area
    along_x = aw > ah
    length = aw if along_x else ah
    n = len(weights)
    gap = min(PATCH_GAP, length / (4 * n)) if n > 1 else 0.0
    usable = length - gap * (n - 1)
    floor = min(floor, usable / n)
    total = sum(weights)
    strips = []
    pos = ax if along_x else ay
    for weight in weights:
        span = floor + (usable - n * floor) * weight / total
        strips.append((pos, ay, span, ah) if along_x else (ax, pos, aw, span))
        pos += span + gap
    return strips


def _patch_groups(
    planting: list[tuple[PlantSpec, int]],
    row_capacity: int,
) -> list[list[tuple[PlantSpec, int]]]:
    """Species big enough for a block each; the rest share one block.

    A species with less than a row of plants would otherwise get a
    whole strip to itself and dot two plants across it.
    """
    major = [[p] for p in planting if p[1] >= row_capacity]
    minor = [p for p in planting if p[1] < row_capacity]
    return [*major, minor] if minor else major


class BedPlanting(NamedTuple):
    spacings: list[float]
    groups: list[list[tuple[PlantSpec, int]]]
    strips: list[tuple[float, float, float, float]]


def _group_scale(group: list[tuple[PlantSpec, int]]) -> float:
    return max(1.0, *(_plant_scale(spec) for spec, _ in group))


def _bed_planting(
    bed: BedRect,
    max_sessions: int,
    species: dict[str, str] | None = None,
) -> BedPlanting | None:
    """How a bed is planted: each block's strip and plant spacing.

    Density follows the repo's sessions relative to the busiest repo,
    so a busy bed is fuller and a quiet one is spread thin -- but
    always across the whole bed, and never so full the soil vanishes:
    a block's tightest spacing is set by its biggest (highest-effort)
    plant, or a block of big plants would pack into a carpet. Blocks
    are sized by the ground their plants cover, not just their count.
    Each busy species gets its own block of the bed and the stragglers
    share one, so a bed's model mix reads at a glance.
    """
    area = _plant_area(bed)
    ax, ay, aw, ah = area
    if aw <= 0 or ah <= 0:
        return None
    specs = _plant_specs(bed.branch, species) or [
        PlantSpec('unknown', None, 1)
    ]
    capacity = len(_hex_grid(area, PLANT_MIN_SPACING))
    share = bed.branch.sessions / max_sessions if max_sessions > 0 else 1.0
    fill = PLANT_FILL_MIN + (1 - PLANT_FILL_MIN) * math.sqrt(min(share, 1.0))
    target = max(1, round(capacity * fill))
    spacing = math.sqrt(aw * ah / (target * HEX_ROW_RATIO))
    spacing = max(PLANT_MIN_SPACING, min(PLANT_MAX_SPACING, spacing))

    planting = [
        (spec, n)
        for spec, n in zip(specs, _patch_sizes(specs, target), strict=True)
        if n > 0
    ]
    row_area = (ax, ay, aw, spacing) if aw > ah else (ax, ay, spacing, ah)
    groups = _patch_groups(planting, len(_hex_grid(row_area, spacing)))
    strips = _strip_split(
        area,
        [sum(n * _plant_scale(spec) ** 2 for spec, n in g) for g in groups],
        spacing,
    )
    spacings = [
        max(spacing, PLANT_MIN_SPACING * _group_scale(g)) for g in groups
    ]
    return BedPlanting(spacings, groups, strips)


def _plant_layout(
    bed: BedRect,
    max_sessions: int,
    species: dict[str, str] | None = None,
) -> list[PlantPlacement]:
    """Where every plant in a bed goes, how big, and which species."""
    planting = _bed_planting(bed, max_sessions, species)
    if planting is None:
        return []
    rng = random.Random(f'plot-plants-{bed.repo}')
    base = PLANT_BASE_SIZE
    plants: list[PlantPlacement] = []
    for group, strip, spacing in zip(
        planting.groups, planting.strips, planting.spacings, strict=True
    ):
        jitter = spacing * PLANT_JITTER_FRACTION
        grid = _hex_grid(strip, spacing)
        sown = [spec for spec, n in group for _ in range(n)]
        count = min(len(sown), len(grid))
        sx, sy, sw, sh = strip
        for i in range(count):
            px, py = grid[(2 * i + 1) * len(grid) // (2 * count)]
            spec = sown[i * len(sown) // count]
            plants.append(
                PlantPlacement(
                    x=min(max(px + rng.uniform(-jitter, jitter), sx), sx + sw),
                    y=min(max(py + rng.uniform(-jitter, jitter), sy), sy + sh),
                    size=base
                    * _plant_scale(spec)
                    * rng.uniform(
                        1 - PLANT_SIZE_JITTER, 1 + PLANT_SIZE_JITTER
                    ),
                    spec=spec,
                    variant=rng.randrange(len(SWAY_VARIANTS)),
                )
            )
    return plants


def _grow_about(
    cls: str,
    centre: tuple[float, float],
    scales: list[float],
    clock: tuple[list[float], float],
    inner: str,
) -> str:
    """Scale ``inner`` about its own centre, one value per replay day.

    SMIL scales about the origin, so the animated group sits between a
    shift to the centre and a shift back.
    """
    x, y = centre
    key_times, dur = clock
    values = [f'{min(1.0, s):.3f}'.rstrip('0').rstrip('.') for s in scales]
    return (
        f'<g class="{cls}" transform="translate({x:.1f} {y:.1f})"><g>'
        + _animate_transform_tag('scale', values, key_times, dur)
        + f'<g transform="translate({-x:.1f} {-y:.1f})">{inner}</g>'
        '</g></g>'
    )


def _plant_use(plant: PlantPlacement, color: str, inner: str = '') -> str:
    half = plant.size / 2
    suffix = SWAY_VARIANTS[plant.variant][0]
    open_tag = (
        f'<use href="#plant-{plant.spec.species}{suffix}"'
        f' x="{plant.x - half:.1f}" y="{plant.y - half:.1f}"'
        f' width="{plant.size:.1f}" height="{plant.size:.1f}"'
        f' color="{color}" data-species="{plant.spec.species}"'
    )
    return f'{open_tag}>{inner}</use>' if inner else f'{open_tag}/>'


FURROW_LINES_SATURATION = 5000
FURROW_WIDTH = 0.5
FURROW_MIN_OPACITY = 0.08
FURROW_MAX_OPACITY = 0.26


class Furrow(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    width: float


def _furrow_depth(lines_added: int) -> float:
    """How deeply a bed is tilled, 0..1, from the code written in it."""
    if lines_added <= 0:
        return 0.0
    return math.sqrt(
        min(lines_added, FURROW_LINES_SATURATION) / FURROW_LINES_SATURATION
    )


def _bed_furrows(
    bed: BedRect,
    max_sessions: int,
    species: dict[str, str] | None = None,
) -> list[Furrow]:
    """One drill under each row of plants, running the row's length."""
    planting = _bed_planting(bed, max_sessions, species)
    if planting is None or _furrow_depth(bed.branch.lines_added) <= 0:
        return []
    furrows = []
    for (sx, sy, sw, sh), spacing in zip(
        planting.strips, planting.spacings, strict=True
    ):
        half = spacing / 2
        for row in _hex_rows((sx, sy, sw, sh), spacing):
            (x1, y1), (x2, y2) = row[0], row[-1]
            if sh > sw:
                y1, y2 = max(y1 - half, sy), min(y2 + half, sy + sh)
            else:
                x1, x2 = max(x1 - half, sx), min(x2 + half, sx + sw)
            furrows.append(
                Furrow(x1, y1, x2, y2, PLANT_BASE_SIZE * FURROW_WIDTH)
            )
    return furrows


def _render_furrows(furrows: list[Furrow], lines_added: int) -> str:
    """Grooves whose far wall catches the top-left light."""
    depth = _furrow_depth(lines_added)
    opacity = (
        FURROW_MIN_OPACITY + (FURROW_MAX_OPACITY - FURROW_MIN_OPACITY) * depth
    )
    parts = []
    for f in furrows:
        lit = f.width * 0.35
        dx, dy = (lit, 0.0) if f.x1 == f.x2 else (0.0, lit)
        parts.append(
            f'<line class="furrow" x1="{f.x1:.1f}" y1="{f.y1:.1f}"'
            f' x2="{f.x2:.1f}" y2="{f.y2:.1f}" stroke="#000"'
            f' stroke-width="{f.width:.1f}" stroke-linecap="round"'
            f' opacity="{opacity:.2f}"/>'
            f'<line x1="{f.x1 + dx:.1f}" y1="{f.y1 + dy:.1f}"'
            f' x2="{f.x2 + dx:.1f}" y2="{f.y2 + dy:.1f}" stroke="#fff"'
            f' stroke-width="{f.width * 0.25:.1f}" stroke-linecap="round"'
            f' opacity="{opacity * 0.5:.2f}"/>'
        )
    return ''.join(parts)


def _shade(color: str, amount: float) -> str:
    """Lighten (``amount`` > 0) or darken (< 0) toward white or black."""
    target = '#ffffff' if amount > 0 else '#000000'
    return _lerp_hex(color, target, abs(amount))


def _bed_wood(bed: BedRect) -> str:
    """Each bed's own boards: some new cedar, some silvered by weather."""
    rng = random.Random(f'bed-wood-{bed.repo}')
    weathered = _lerp_hex(
        FRAME_WOOD, WEATHERED_WOOD, rng.uniform(0, WOOD_WEATHER_MAX)
    )
    return _shade(weathered, rng.uniform(-WOOD_TONE_RANGE, WOOD_TONE_RANGE))


def _frame_planks(
    bed: BedRect,
) -> list[tuple[str, tuple[float, float, float, float], str]]:
    """The four boards of a raised bed, shaded for top-left light.

    Sides are listed first so the top and bottom boards overlap them at
    the corners, the way a real frame's end boards cover the sides.
    """
    fw = min(FRAME_WIDTH, bed.w / 4, bed.h / 4)
    wood = _bed_wood(bed)
    return [
        ('left', (bed.x, bed.y, fw, bed.h), _shade(wood, 0.08)),
        (
            'right',
            (bed.x + bed.w - fw, bed.y, fw, bed.h),
            _shade(wood, -0.28),
        ),
        ('top', (bed.x, bed.y, bed.w, fw), _shade(wood, 0.2)),
        (
            'bottom',
            (bed.x, bed.y + bed.h - fw, bed.w, fw),
            _shade(wood, -0.2),
        ),
    ]


def _rect(
    rect: tuple[float, float, float, float],
    attrs: str,
    inner: str = '',
) -> str:
    x, y, w, h = rect
    open_tag = (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
        f' {attrs}'
    )
    return f'{open_tag}>{inner}</rect>' if inner else f'{open_tag}/>'


def _soil_rect(bed: BedRect) -> tuple[float, float, float, float]:
    fw = min(FRAME_WIDTH, bed.w / 4, bed.h / 4)
    return (bed.x + fw, bed.y + fw, bed.w - 2 * fw, bed.h - 2 * fw)


def _render_bed_shadow(bed: BedRect) -> str:
    return _rect(
        (bed.x, bed.y, bed.w, bed.h),
        f'class="bed-shadow" rx="3" fill="#000"'
        f' opacity="{SHADOW_OPACITY}" filter="url(#softShadow)"',
    )


def _bed_furrow_marks(
    bed: BedRect,
    max_sessions: int,
    species: dict[str, str],
) -> str:
    return _render_furrows(
        _bed_furrows(bed, max_sessions, species), bed.branch.lines_added
    )


def _render_bed_body(
    bed: BedRect,
    soil_color: str,
    soil_anim: str = '',
    *,
    shadow: bool = True,
    furrows: str = '',
) -> str:
    """Shadow, soil and frame of one raised bed.

    The static and timeline renderers both draw beds through here, so
    the timelapse ends on exactly the bed the static render shows.
    """
    soil = _soil_rect(bed)
    sx, sy, sw, sh = soil
    edge = min(INNER_SHADE, sw / 2, sh / 2)
    parts = [
        _render_bed_shadow(bed) if shadow else '',
        _rect(soil, f'fill="{soil_color}"', soil_anim),
        _rect(soil, 'fill="url(#soilTexture)"'),
        furrows,
        _rect((sx, sy, sw, edge), 'fill="url(#shadeDown)"'),
        _rect((sx, sy, edge, sh), 'fill="url(#shadeRight)"'),
    ]
    parts.extend(
        _rect(rect, f'fill="{color}"') for _, rect, color in _frame_planks(bed)
    )
    fw = min(FRAME_WIDTH, bed.w / 4, bed.h / 4)
    post = _shade(_bed_wood(bed), -0.4)
    parts.extend(
        _rect((px, py, fw, fw), f'fill="{post}"')
        for px in (bed.x, bed.x + bed.w - fw)
        for py in (bed.y, bed.y + bed.h - fw)
    )
    return ''.join(parts)


def _render_bed_soil(
    bed: BedRect,
    vitality: float,
    furrows: str = '',
) -> str:
    return _render_bed_body(
        bed, _blend_hex(SOIL_DORMANT, SOIL_COLOR, vitality), furrows=furrows
    )


def _render_bed_plants(
    bed: BedRect,
    max_sessions: int,
    vitality: float,
    species: dict[str, str] | None = None,
) -> str:
    return ''.join(
        _plant_use(
            plant,
            _plant_color(plant.spec.species, vitality),
        )
        for plant in _plant_layout(bed, max_sessions, species)
    )


def _row_markers(
    bed: BedRect,
    max_sessions: int,
    species: dict[str, str] | None = None,
) -> list[RowMarker]:
    """A seed-packet stake at the head of each single-species block.

    The stake is pushed into the frame where the block's rows start --
    the left board for rows across the bed, the top board for rows down
    it -- and moves to the right board when a turned name tag already
    holds the left one.
    """
    planting = _bed_planting(bed, max_sessions, species)
    if planting is None:
        return []
    fw = min(FRAME_WIDTH, bed.w / 4, bed.h / 4)
    left = bed.x + fw / 2
    if _bed_tag(bed).vertical:
        left = bed.x + bed.w - fw / 2
    markers = []
    for group, (sx, sy, sw, sh) in zip(
        planting.groups, planting.strips, strict=True
    ):
        spec = group[0][0]
        if len(group) != 1 or not spec.label:
            continue
        if sh > sw:
            x, y = sx + sw / 2, bed.y + fw / 2
        else:
            x, y = left, sy + sh / 2
        markers.append(RowMarker(x, y, spec.species, spec.label))
    return markers


def _render_row_markers(
    bed: BedRect,
    max_sessions: int,
    species: dict[str, str] | None = None,
) -> str:
    parts = []
    for m in _row_markers(bed, max_sessions, species):
        art = SPECIES.get(m.species, SPECIES['sprout'])
        x, y = m.x - MARKER_W / 2, m.y - MARKER_H / 2
        parts.append(
            f'<g class="row-marker">'
            f'{_title(f"{art.name} · {combo_name(m.label)}")}'
            f'<rect x="{x + 1:.1f}" y="{y + 1.4:.1f}" width="{MARKER_W}"'
            f' height="{MARKER_H}" rx="1" fill="#000" opacity="0.3"/>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{MARKER_W}"'
            f' height="{MARKER_H}" rx="1" fill="{TAG_FILL}"'
            f' stroke="{TAG_EDGE}" stroke-width="0.6"/>'
            f'<circle cx="{m.x:.1f}" cy="{m.y - 0.8:.1f}" r="2.1"'
            f' fill="{art.color}"/>'
            f'</g>'
        )
    return ''.join(parts)


def _render_bed_label(bed: BedRect) -> str:
    """A wooden plant marker pinned to the bed's frame."""
    tag = _bed_tag(bed)
    cx, cy = tag.cx, tag.cy
    x, y = cx - tag.w / 2, cy - tag.h / 2
    turn = (
        f' transform="rotate(-90 {cx:.1f} {cy:.1f})"' if tag.vertical else ''
    )
    return (
        f'<g class="bed-tag"{turn}>'
        f'<rect x="{x + 1.5:.1f}" y="{y + 2:.1f}" width="{tag.w:.1f}"'
        f' height="{tag.h:.1f}" rx="2" fill="#000" opacity="0.3"/>'
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{tag.w:.1f}"'
        f' height="{tag.h:.1f}" rx="2" fill="{TAG_FILL}"'
        f' stroke="{TAG_EDGE}" stroke-width="0.8"/>'
        f'<text x="{cx:.1f}" y="{cy + tag.font * 0.35:.1f}"'
        f' text-anchor="middle" font-family="Georgia, serif"'
        f' font-size="{tag.font:.1f}" fill="{TAG_TEXT}">'
        f'{_escape_xml(tag.text)}</text></g>'
    )


def _tooltip_specs(
    branch: RepoBranch,
    species: dict[str, str] | None,
) -> list[PlantSpec]:
    return _plant_specs(branch, species)[:TOOLTIP_MAX_PLANTS]


def _last_worked(idle_days: int) -> str:
    if idle_days == 0:
        return 'worked today'
    if idle_days == 1:
        return 'last worked yesterday'
    return f'last worked {idle_days} days ago'


def _bed_tooltip(
    branch: RepoBranch,
    species: dict[str, str] | None = None,
) -> str:
    """One item per line; the plant lines come last, one per combo.

    The tap tooltip draws an icon beside each plant line, matched up
    by order with the bed's ``data-plants`` (``_bed_tooltip_plants``).
    """
    lines = [
        branch.repo,
        f'{branch.sessions:,} sessions',
        f'+{branch.lines_added:,}/-{branch.lines_removed:,} lines',
    ]
    tokens = branch.input_tokens + branch.output_tokens
    if tokens > 0:
        lines.append(_format_tokens(tokens))
    if branch.idle_days is not None:
        lines.append(_last_worked(branch.idle_days))
    specs = _tooltip_specs(branch, species)
    total = sum(s.replies for s in _plant_specs(branch, species))
    lines.extend(
        f'{_percent(s.replies / total)} {SPECIES[s.species].name}'
        f' ({combo_name(s.label)})'
        for s in specs
    )
    return '\n'.join(lines)


def _bed_tooltip_plants(
    branch: RepoBranch,
    species: dict[str, str] | None = None,
) -> str:
    """``data-plants``: species and tint for each tooltip plant line."""
    specs = _tooltip_specs(branch, species)
    if not specs:
        return ''
    plants = ','.join(
        f'{s.species} {_plant_color(s.species, 1.0)}' for s in specs
    )
    return f' data-plants="{plants}"'


def _render_beds(
    beds: list[BedRect],
    branches: list[RepoBranch],
    vitality: float,
) -> str:
    max_sessions = max(b.sessions for b in branches) if branches else 1
    species = _garden_species(branches)
    parts: list[str] = []
    for bed in beds:
        tt = _title(_bed_tooltip(bed.branch, species))
        data = _bed_tooltip_plants(bed.branch, species)
        parts.append(
            f'<g class="bed"{data}>{tt}'
            + _render_bed_soil(
                bed, vitality, _bed_furrow_marks(bed, max_sessions, species)
            )
            + _render_bed_wet(bed)
            + _render_bed_plants(bed, max_sessions, vitality, species)
            + _render_bed_weeds(bed, vitality)
            + _render_bed_sprinkler(
                bed, _plant_layout(bed, max_sessions, species)
            )
            + _render_row_markers(bed, max_sessions, species)
            + _render_bed_label(bed)
            + '</g>'
        )
    return ''.join(parts)


# ── Paths (gravel between beds) ────────────────────────────────


STONE_RADIUS_MIN = 4.2
STONE_RADIUS_MAX = 5.4
STONE_STEP = 15.0
STONE_GUTTER_MAX = BED_GUTTER * 1.5
STONE_SIDES = 7


def _gutters(
    beds: list[BedRect],
) -> list[tuple[tuple[float, float, float, float], tuple[str, str]]]:
    """Centre lines of the paths between facing beds, and the two beds."""
    lines = []
    for a in beds:
        for b in beds:
            gap_x = b.x - (a.x + a.w)
            lo_y, hi_y = max(a.y, b.y), min(a.y + a.h, b.y + b.h)
            if 0 < gap_x <= STONE_GUTTER_MAX and hi_y > lo_y:
                mid = a.x + a.w + gap_x / 2
                lines.append(((mid, lo_y, mid, hi_y), (a.repo, b.repo)))
            gap_y = b.y - (a.y + a.h)
            lo_x, hi_x = max(a.x, b.x), min(a.x + a.w, b.x + b.w)
            if 0 < gap_y <= STONE_GUTTER_MAX and hi_x > lo_x:
                mid = a.y + a.h + gap_y / 2
                lines.append(((lo_x, mid, hi_x, mid), (a.repo, b.repo)))
    return lines


def _stepping_stones(beds: list[BedRect]) -> list[Stone]:
    """Flagstones set down the middle of every path, one pace apart.

    Where two paths cross, a stone already laid wins, so junctions
    don't pile up into a heap.
    """
    rng = random.Random('stepping-stones')
    stones: list[Stone] = []
    for (x1, y1, x2, y2), repos in _gutters(beds):
        length = math.hypot(x2 - x1, y2 - y1)
        n = int(length / STONE_STEP)
        if n < 1:
            continue
        lead = (length - (n - 1) * STONE_STEP) / 2
        for i in range(n):
            t = (lead + i * STONE_STEP) / length
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            r = rng.uniform(STONE_RADIUS_MIN, STONE_RADIUS_MAX)
            if _point_in_any_bed(x, y, beds, margin=r * 0.5):
                continue
            if any(
                math.dist((x, y), (other.x, other.y)) < STONE_STEP * 0.6
                for other in stones
            ):
                continue
            stones.append(Stone(x, y, r, repos))
    return stones


def _flagstone_points(x: float, y: float, r: float, seed: str) -> str:
    rng = random.Random(seed)
    turn = rng.uniform(0, math.tau)
    return ' '.join(
        f'{x + rr * math.cos(a):.1f},{y + rr * math.sin(a):.1f}'
        for a, rr in (
            (
                turn + i * math.tau / STONE_SIDES,
                r * rng.uniform(0.78, 1.05),
            )
            for i in range(STONE_SIDES)
        )
    )


def _render_stone(stone: Stone) -> str:
    seed = f'stone-{stone.x:.0f}-{stone.y:.0f}'
    points = _flagstone_points(stone.x, stone.y, stone.r, seed)
    shadow = _flagstone_points(
        stone.x + LIGHT_DX / 3, stone.y + LIGHT_DY / 3, stone.r, seed
    )
    return (
        f'<polygon points="{shadow}" fill="#000" opacity="0.25"/>'
        f'<polygon class="stone" points="{points}"'
        f' fill="url(#stoneShade)" stroke="#000" stroke-opacity="0.15"'
        f' stroke-width="0.5" stroke-linejoin="round"/>'
    )


def _render_paths(
    beds: list[BedRect],
    first_days: dict[str, int] | None = None,
    key_times: list[float] | None = None,
    dur: float = 0.0,
) -> str:
    """Gravel, and stepping stones down the middle of every path.

    In the timeline a path is laid on the day the first of the two beds
    it runs between is dug, so no path leads between beds not yet there.
    """
    gravel = (
        f'<rect x="{BED_ZONE_X}" y="{BED_ZONE_Y}"'
        f' width="{BED_ZONE_W}" height="{BED_ZONE_H}"'
        f' fill="url(#gravel)" rx="2"/>'
    )
    stones = _stepping_stones(beds)
    if first_days is None or key_times is None:
        return gravel + ''.join(_render_stone(s) for s in stones)
    by_day: dict[int, list[Stone]] = {}
    for stone in stones:
        day = min(first_days.get(repo, 0) for repo in stone.repos)
        by_day.setdefault(day, []).append(stone)
    parts = [gravel]
    for day, laid in sorted(by_day.items()):
        values = ['0' if i < day else '1' for i in range(len(key_times))]
        parts.append(
            f'<g class="path-stones" opacity="0">'
            f'{_animate_tag("opacity", values, key_times, dur)}'
            f'{"".join(_render_stone(s) for s in laid)}</g>'
        )
    return ''.join(parts)


def _point_in_any_bed(
    px: float,
    py: float,
    beds: list[BedRect],
    *,
    margin: float = 0.0,
) -> bool:
    return any(
        bed.x - margin <= px <= bed.x + bed.w + margin
        and bed.y - margin <= py <= bed.y + bed.h + margin
        for bed in beds
    )


# ── Fence ──────────────────────────────────────────────────────


def _in_gate(x: float, y: float) -> bool:
    half = GATE_WIDTH / 2
    gate_x = SHED_GATE_X if y == FENCE_Y else GATE_X
    return gate_x - half < x < gate_x + half


def _fence_posts() -> list[tuple[float, float]]:
    """Post centres around the fence, skipping both gate openings."""
    posts: list[tuple[float, float]] = []
    x0, y0 = FENCE_X, FENCE_Y
    x1, y1 = FENCE_X + FENCE_W, FENCE_Y + FENCE_H
    nx = max(1, round(FENCE_W / FENCE_POST_SPACING))
    ny = max(1, round(FENCE_H / FENCE_POST_SPACING))
    for i in range(nx + 1):
        x = x0 + i * FENCE_W / nx
        posts.extend((x, y) for y in (y0, y1) if not _in_gate(x, y))
    for j in range(1, ny):
        y = y0 + j * FENCE_H / ny
        posts.extend(((x0, y), (x1, y)))
    return posts


def _fence_rails() -> list[tuple[float, float, float, float]]:
    x0, y0 = FENCE_X, FENCE_Y
    x1, y1 = FENCE_X + FENCE_W, FENCE_Y + FENCE_H
    half = GATE_WIDTH / 2
    return [
        (x0, y0, SHED_GATE_X - half, y0),
        (SHED_GATE_X + half, y0, x1, y0),
        (x0, y0, x0, y1),
        (x1, y0, x1, y1),
        (x0, y1, GATE_X - half, y1),
        (GATE_X + half, y1, x1, y1),
    ]


def _render_fence() -> str:
    rails = _fence_rails()
    posts = _fence_posts()
    half = FENCE_POST_SIZE / 2
    shadow = ''.join(
        f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}"/>'
        for ax, ay, bx, by in rails
    ) + ''.join(
        f'<rect x="{px - half:.1f}" y="{py - half:.1f}"'
        f' width="{FENCE_POST_SIZE}" height="{FENCE_POST_SIZE}"'
        f' stroke="none"/>'
        for px, py in posts
    )
    rail_lines = ''.join(
        f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}"/>'
        for ax, ay, bx, by in rails
    )
    rail_shine = ''.join(
        f'<line x1="{ax - 0.8:.1f}" y1="{ay - 0.8:.1f}"'
        f' x2="{bx - 0.8:.1f}" y2="{by - 0.8:.1f}"/>'
        for ax, ay, bx, by in rails
    )
    post_rects = ''.join(
        f'<rect x="{px - half:.1f}" y="{py - half:.1f}"'
        f' width="{FENCE_POST_SIZE}" height="{FENCE_POST_SIZE}" rx="1"/>'
        f'<rect x="{px - half:.1f}" y="{py - half:.1f}"'
        f' width="{FENCE_POST_SIZE - 2}" height="{FENCE_POST_SIZE - 2}"'
        f' rx="1" fill="{_shade(FENCE_POST_COLOR, 0.25)}"/>'
        for px, py in posts
    )
    return (
        f'<g class="fence">'
        f'<g stroke="#000" stroke-width="3" fill="#000" opacity="0.25"'
        f' filter="url(#softShadow)">{shadow}</g>'
        f'<g stroke="{FENCE_COLOR}" stroke-width="3"'
        f' stroke-linecap="round">{rail_lines}</g>'
        f'<g stroke="{_shade(FENCE_COLOR, 0.3)}" stroke-width="1"'
        f' stroke-linecap="round">{rail_shine}</g>'
        f'<g fill="{FENCE_POST_COLOR}">{post_rects}</g>'
        f'</g>'
    )


# ── Periphery: Shed ────────────────────────────────────────────


def _feature_boxes() -> dict[str, tuple[float, float, float, float]]:
    """Footprint of every object in the band above the fence."""
    return {
        'shed': SHED_BOX,
        'barrel': (
            BARREL_CX - BARREL_R,
            BARREL_CY - BARREL_R,
            2 * BARREL_R,
            2 * BARREL_R,
        ),
        'bench': BENCH_BOX,
        'sign': SIGN_BOX,
        'sundial': (
            SUNDIAL_CX - SUNDIAL_PATIO_R,
            SUNDIAL_CY - SUNDIAL_PATIO_R,
            2 * SUNDIAL_PATIO_R,
            2 * SUNDIAL_PATIO_R,
        ),
    }


def _drop_shadow(shape: str) -> str:
    return (
        f'<g fill="#000" opacity="{SHADOW_OPACITY}"'
        f' filter="url(#softShadow)">'
        f'{shape}</g>'
    )


def _shed_shingles(
    slope: tuple[float, float, float, float], lit: float
) -> str:
    """Cedar shakes on one slope, each board its own weathered tone.

    Courses are laid from the eave up, so every course's exposed lower
    edge -- the dark line -- faces the eave it drains to.
    """
    x, y, w, h = slope
    rng = random.Random(f'shed-{y:.0f}')
    top_slope = lit > 0
    parts = []
    courses = max(1, round(h / SHINGLE_COURSE))
    course_h = h / courses
    for c in range(courses):
        cy = y + c * course_h
        cx = x - rng.uniform(0, SHINGLE_MAX_W)
        while cx < x + w:
            sw = rng.uniform(SHINGLE_MIN_W, SHINGLE_MAX_W)
            left, right = max(cx, x), min(cx + sw, x + w)
            if right - left > 1:
                tone = lit + rng.uniform(-SHINGLE_TONE, SHINGLE_TONE)
                parts.append(
                    f'<rect class="shingle" fill="{_shade(SHED_ROOF, tone)}"'
                    f' x="{left:.1f}" y="{cy:.1f}" width="{right - left:.1f}"'
                    f' height="{course_h:.1f}" stroke="#000"'
                    f' stroke-opacity="0.22" stroke-width="0.5"/>'
                )
            cx += sw
        edge = cy if top_slope else cy + course_h
        parts.append(
            f'<line x1="{x:.1f}" y1="{edge:.1f}" x2="{x + w:.1f}"'
            f' y2="{edge:.1f}" stroke="#000" stroke-opacity="0.4"'
            f' stroke-width="1.1"/>'
        )
    return ''.join(parts)


def _shed_moss(slope: tuple[float, float, float, float]) -> str:
    """Moss creeping up from the shaded eave, where the roof stays damp."""
    x, y, w, h = slope
    rng = random.Random('shed-moss')
    dots = []
    for _ in range(SHED_MOSS_TUFTS):
        cx = rng.uniform(x + 6, x + w - 6)
        cy = y + h - rng.uniform(3, h * 0.4)
        for _ in range(rng.randint(4, 8)):
            r = rng.uniform(0.9, 2.2)
            tone = rng.uniform(-0.15, 0.25)
            dots.append(
                f'<circle cx="{cx + rng.uniform(-4, 4):.1f}"'
                f' cy="{cy + rng.uniform(-2.5, 2.5):.1f}" r="{r:.1f}"'
                f' fill="{_shade(SHED_MOSS, tone)}"/>'
            )
    return f'<g class="moss" opacity="0.8">{"".join(dots)}</g>'


def _render_shed(
    tools: list[ToolBush], growth: ToolGrowth | None = None
) -> str:
    """The shed from above: a cedar-shake gable, ridge running east-west."""
    x, y, w, h = SHED_BOX
    ridge = y + h / 2
    frame = _shade(SHED_ROOF, -0.55)
    glass_x, glass_y = x + w * 0.6, y + 9
    pipe_x, pipe_y = x + w * 0.22, y + h * 0.3
    calls = sum(t.count for t in tools)
    return (
        f'<g class="shed">'
        f'{_title(f"Tool shed: {calls:,} tool calls, {len(tools)} tools")}'
        + _drop_shadow(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>')
        + _shed_shingles((x, y, w, h / 2), 0.06)
        + _shed_shingles((x, ridge, w, h / 2), -0.22)
        + f'<linearGradient id="shedSlopeLit" x1="0" y1="1" x2="0" y2="0">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="0.12"/>'
        f'<stop offset="1" stop-color="#000" stop-opacity="0.08"/>'
        f'</linearGradient>'
        f'<linearGradient id="shedSlopeDim" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#000" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="#000" stop-opacity="0.22"/>'
        f'</linearGradient>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h / 2}"'
        f' fill="url(#shedSlopeLit)"/>'
        f'<rect x="{x}" y="{ridge}" width="{w}" height="{h / 2}"'
        f' fill="url(#shedSlopeDim)"/>'
        + _shed_moss((x, ridge, w, h / 2))
        + f'<g class="skylight">'
        f'<linearGradient id="shedGlass" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#dcebf2"/>'
        f'<stop offset="0.45" stop-color="#9fbfd0"/>'
        f'<stop offset="1" stop-color="#6d8fa3"/></linearGradient>'
        f'<rect x="{glass_x:.1f}" y="{glass_y + 1.5:.1f}" width="24"'
        f' height="17" fill="#000" opacity="0.3"/>'
        f'<rect x="{glass_x:.1f}" y="{glass_y:.1f}" width="24" height="17"'
        f' fill="url(#shedGlass)" stroke="{frame}" stroke-width="1.6"/>'
        f'<line x1="{glass_x + 12:.1f}" y1="{glass_y:.1f}"'
        f' x2="{glass_x + 12:.1f}" y2="{glass_y + 17:.1f}"'
        f' stroke="{frame}" stroke-width="1"/>'
        f'<line x1="{glass_x + 3:.1f}" y1="{glass_y + 12:.1f}"'
        f' x2="{glass_x + 9:.1f}" y2="{glass_y + 4:.1f}"'
        f' stroke="#fff" stroke-opacity="0.6" stroke-width="1.2"/>'
        f'</g>'
        f'<g class="stovepipe">'
        f'<circle cx="{pipe_x + 2.5:.1f}" cy="{pipe_y + 3:.1f}" r="5"'
        f' fill="#000" opacity="0.3"/>'
        f'<circle cx="{pipe_x:.1f}" cy="{pipe_y:.1f}" r="5" fill="#4a4a4a"/>'
        f'<circle cx="{pipe_x:.1f}" cy="{pipe_y:.1f}" r="3.2"'
        f' fill="#2a2a2a"/>'
        f'<circle cx="{pipe_x - 1.4:.1f}" cy="{pipe_y - 1.4:.1f}" r="1.3"'
        f' fill="#8a8a8a"/>'
        f'</g>'
        f'<g class="ridge-cap">'
        f'<rect x="{x - 2}" y="{ridge - 3}" width="{w + 4}" height="6"'
        f' rx="1.5" fill="{_shade(SHED_ROOF, -0.35)}"/>'
        + ''.join(
            f'<line x1="{cx:.1f}" y1="{ridge - 3}" x2="{cx:.1f}"'
            f' y2="{ridge + 3}" stroke="#000" stroke-opacity="0.3"'
            f' stroke-width="0.6"/>'
            for cx in range(int(x) + 8, int(x + w), 10)
        )
        + f'<rect x="{x - 2}" y="{ridge - 3}" width="{w + 4}" height="2"'
        f' rx="1" fill="#fff" opacity="0.12"/>'
        f'</g>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none"'
        f' stroke="{frame}" stroke-width="1.5"/>'
        f'<path d="M{x + w},{y + h - 6} H{BARREL_CX - 4}'
        f' V{BARREL_CY - BARREL_R * 0.5}" fill="none"'
        f' stroke="{BARREL_BAND}" stroke-width="3" stroke-linejoin="round"/>'
        f'</g>' + _render_bench(tools, growth)
    )


def _bench_tools(tools: list[ToolBush]) -> list[ToolPlacement]:
    """The busiest tools laid on the potting bench, longest = most used."""
    top = sorted(tools, key=lambda t: t.count, reverse=True)[:BENCH_MAX_TOOLS]
    if not top:
        return []
    bx, by, bw, _ = BENCH_BOX
    slot = (bw - 2 * BENCH_PAD) / len(top)
    peak = top[0].count or 1
    return [
        ToolPlacement(
            tool=tool,
            x=bx + BENCH_PAD + (i + 0.5) * slot,
            y=by + BENCH_PAD,
            length=_tool_length(tool.count, peak),
            kind=TOOL_KINDS[i % len(TOOL_KINDS)],
        )
        for i, tool in enumerate(top)
    ]


def _tool_length(count: int, peak: int) -> float:
    share = math.sqrt(count / peak) if peak > 0 else 0.0
    return TOOL_MIN_LEN + (TOOL_MAX_LEN - TOOL_MIN_LEN) * share


def _tool_head(kind: str, x: float, y: float) -> str:
    """A tool's metal end, drawn around its tip at (x, y)."""
    metal = f'fill="url(#metal)" stroke="{BARREL_BAND}" stroke-width="0.5"'
    tine = f'stroke="{TOOL_METAL}" stroke-width="1.1" stroke-linecap="round"'
    heads = {
        'spade': (
            f'<path d="M{x - 4.5},{y - 2} h9 v8 q0,4 -4.5,5'
            f' q-4.5,-1 -4.5,-5 z" {metal}/>'
        ),
        'rake': (
            f'<rect x="{x - 7}" y="{y - 1}" width="14" height="2.4" {metal}/>'
            + ''.join(
                f'<line x1="{x + dx}" y1="{y + 1}" x2="{x + dx}" y2="{y + 5}"'
                f' {tine}/>'
                for dx in (-6, -3.6, -1.2, 1.2, 3.6, 6)
            )
        ),
        'fork': (
            f'<rect x="{x - 4}" y="{y - 1}" width="8" height="2.2" {metal}/>'
            + ''.join(
                f'<line x1="{x + dx}" y1="{y + 1}" x2="{x + dx}" y2="{y + 9}"'
                f' {tine}/>'
                for dx in (-3.2, -1.1, 1.1, 3.2)
            )
        ),
        'trowel': (
            f'<path d="M{x},{y - 1} q5,3 3.5,9 l-3.5,4 l-3.5,-4'
            f' q-1.5,-6 3.5,-9 z" {metal}/>'
        ),
        'hoe': (
            f'<rect x="{x - 6}" y="{y - 1}" width="12" height="4" {metal}/>'
        ),
        'shears': (
            f'<path d="M{x - 1},{y} l-3,11 l2,0.5 z M{x + 1},{y}'
            f' l3,11 l-2,0.5 z" {metal}/>'
        ),
    }
    return heads[kind]


class ToolGrowth(NamedTuple):
    counts: dict[str, list[int]]
    key_times: list[float]
    dur: float


class ToolAnims(NamedTuple):
    group: str
    handle: str
    head: str


def _tool_growth(
    placed: ToolPlacement,
    peak: int,
    growth: ToolGrowth,
) -> ToolAnims | None:
    """A tool's handle lengthening day by day, its head riding the tip."""
    counts = growth.counts.get(placed.tool.tool, [])
    if len(counts) != len(growth.key_times):
        return None
    lengths = [
        _tool_length(c, peak) if c > 0 else TOOL_HEAD_LEN for c in counts
    ]
    tips = [placed.y + n - TOOL_HEAD_LEN for n in lengths]
    clock = (growth.key_times, growth.dur)
    return ToolAnims(
        group=_animate_tag(
            'opacity', ['1' if c > 0 else '0' for c in counts], *clock
        ),
        handle=_animate_tag('y2', [f'{t:.1f}' for t in tips], *clock),
        head=_animate_transform_tag(
            'translate',
            [f'0 {t - tips[-1]:.1f}' for t in tips],
            *clock,
        ),
    )


def _render_tool(
    placed: ToolPlacement,
    label_y: float,
    anims: ToolAnims | None = None,
) -> str:
    """One tool hanging on the bench, its label on the bottom plank."""
    grow = anims or ToolAnims('', '', '')
    tip_y = placed.y + placed.length - TOOL_HEAD_LEN
    name = _escape_xml(placed.tool.tool[:TOOL_LABEL_CHARS])
    handle = (
        f'<line x1="{placed.x:.1f}" y1="{placed.y:.1f}"'
        f' x2="{placed.x:.1f}" y2="{tip_y:.1f}"'
    )
    return (
        f'<g class="tool">{grow.group}'
        f'{_title(f"{placed.tool.tool}: {placed.tool.count:,} calls")}'
        f'<g opacity="0.3" transform="translate(1.5 2)">'
        f'{handle} stroke="#000" stroke-width="2.6"'
        f' stroke-linecap="round">{grow.handle}</line></g>'
        f'{handle} stroke="{TOOL_HANDLE}" stroke-width="2.4"'
        f' stroke-linecap="round">{grow.handle}</line>'
        f'<g>{grow.head}{_tool_head(placed.kind, placed.x, tip_y)}</g>'
        f'<text x="{placed.x:.1f}" y="{label_y:.1f}"'
        f' text-anchor="middle" font-family="Georgia, serif"'
        f' font-size="6.5" fill="{TAG_TEXT}">{name}</text>'
        f'</g>'
    )


def _bench_tooltip(tools: list[ToolBush]) -> str:
    """Every tool, not just the ones hung on the bench, busiest first."""
    total = sum(t.count for t in tools)
    if total == 0:
        return 'Potting bench\nno tool calls yet'
    ranked = sorted(tools, key=lambda t: t.count, reverse=True)
    return '\n'.join(
        [
            'Potting bench',
            f'{total:,} tool calls, {len(tools)} tools',
            *(
                f'{_percent(t.count / total)} {t.tool} ({t.count:,})'
                for t in ranked
            ),
        ]
    )


def _render_bench(
    tools: list[ToolBush], growth: ToolGrowth | None = None
) -> str:
    x, y, w, h = BENCH_BOX
    planks = ''.join(
        f'<rect x="{x}" y="{y + i * h / 3:.1f}" width="{w}"'
        f' height="{h / 3 - 1:.1f}"'
        f' fill="{_shade(FRAME_WOOD, 0.1 - i * 0.08)}"/>'
        for i in range(3)
    )
    parts = [
        f'<g class="bench">{_title(_bench_tooltip(tools))}',
        _drop_shadow(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>'),
        (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}"'
            f' fill="{_shade(FRAME_WOOD, -0.5)}"/>'
        ),
        planks,
        (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none"'
            f' stroke="{_shade(FRAME_WOOD, -0.4)}" stroke-width="1"/>'
        ),
    ]
    placements = _bench_tools(tools)
    peak = placements[0].tool.count if placements else 0
    for placed in placements:
        anims = _tool_growth(placed, peak, growth) if growth else None
        parts.append(_render_tool(placed, y + h - 3, anims))
    parts.append('</g>')
    return ''.join(parts)


# ── Periphery: Sundial ─────────────────────────────────────────


def _sundial_wedges(hour_counts: dict[int, int]) -> list[SundialWedge]:
    """One wedge per active hour; length is that hour's share of the peak."""
    if not hour_counts:
        return []
    peak = max(hour_counts.values()) or 1
    return [
        SundialWedge(
            hour=hour,
            length=count / peak,
            night=hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR,
        )
        for hour, count in sorted(hour_counts.items())
        if count > 0
    ]


def _hour_angle(hour: float) -> float:
    return hour / 24 * math.tau - math.pi / 2


def _polar(r: float, angle: float) -> tuple[float, float]:
    return SUNDIAL_CX + r * math.cos(angle), SUNDIAL_CY + r * math.sin(angle)


def _wedge_path(r0: float, r1: float, a0: float, a1: float) -> str:
    (x0, y0), (x1, y1) = _polar(r0, a0), _polar(r1, a0)
    (x2, y2), (x3, y3) = _polar(r1, a1), _polar(r0, a1)
    return (
        f'M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f}'
        f' A{r1:.1f},{r1:.1f} 0 0 1 {x2:.1f},{y2:.1f}'
        f' L{x3:.1f},{y3:.1f} A{r0:.1f},{r0:.1f} 0 0 0 {x0:.1f},{y0:.1f}Z'
    )


def _render_sundial(hour_counts: dict[int, int]) -> str:
    """A 24-hour stone dial whose petals are a histogram of prompt hours.

    Midnight is at the top, noon at the bottom; night hours are tinted
    moonlight blue so a night-owl habit shows as a blue crown.
    """
    cx, cy, r = SUNDIAL_CX, SUNDIAL_CY, SUNDIAL_R
    wedges = _sundial_wedges(hour_counts)
    r0 = r * 0.28
    reach = r * 0.62
    half = math.tau / 48 * 0.82
    petals = ''.join(
        f'<path d="{
            _wedge_path(
                r0,
                r0 + reach * max(w.length, 0.06),
                _hour_angle(w.hour + 0.5) - half,
                _hour_angle(w.hour + 0.5) + half,
            )
        }"'
        f' fill="{SUNDIAL_NIGHT if w.night else SUNDIAL_DAY}"'
        f' opacity="{0.55 + 0.45 * w.length:.2f}">'
        f'{_title(f"{w.hour:02d}:00 — {hour_counts[w.hour]:,} prompts")}'
        f'</path>'
        for w in wedges
    )
    ticks = ''.join(
        '<line x1="{:.1f}" y1="{:.1f}" x2="{:.1f}" y2="{:.1f}"/>'.format(
            *_polar(r - 2, _hour_angle(h)),
            *_polar(r - (6 if h % 6 == 0 else 3.5), _hour_angle(h)),
        )
        for h in range(24)
    )
    numerals = ''.join(
        f'<text x="{nx:.1f}" y="{ny:.1f}">{h}</text>'
        for h in (0, 6, 12, 18)
        for nx, ny in (_polar(r - 11, _hour_angle(h)),)
    )
    gnomon = ''
    if wedges:
        peak = max(wedges, key=lambda w: w.length).hour + 0.5
        angle = _hour_angle(peak)
        tip = _polar(reach + r0, angle)
        left = _polar(4, angle - math.pi / 2)
        right = _polar(4, angle + math.pi / 2)
        tri = (
            f'M{left[0]:.1f},{left[1]:.1f} L{tip[0]:.1f},{tip[1]:.1f}'
            f' L{right[0]:.1f},{right[1]:.1f}Z'
        )
        gnomon = (
            f'<path d="{tri}" fill="#000" opacity="0.3"'
            f' transform="translate({LIGHT_DX * 0.8} {LIGHT_DY * 0.8})"/>'
            f'<path d="{tri}" fill="url(#metal)" stroke="{SUNDIAL_GNOMON}"'
            f' stroke-width="0.8"/>'
        )
    peak_note = (
        f' — peak {max(wedges, key=lambda w: w.length).hour:02d}:00'
        if wedges
        else ''
    )
    return (
        f'<g class="sundial">{_title(f"Prompts by hour{peak_note}")}'
        + _drop_shadow(f'<circle cx="{cx}" cy="{cy}" r="{SUNDIAL_PATIO_R}"/>')
        + f'<circle cx="{cx}" cy="{cy}" r="{SUNDIAL_PATIO_R}"'
        f' fill="url(#gravel)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{SUNDIAL_PATIO_R}" fill="none"'
        f' stroke="{_shade(STONE_COLOR, -0.3)}" stroke-width="1"/>'
        f'<circle cx="{cx + 2}" cy="{cy + 3}" r="{r}" fill="#000"'
        f' opacity="0.3"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#dialStone)"'
        f' stroke="{_shade(SUNDIAL_STONE, -0.35)}" stroke-width="1.5"/>'
        f'{petals}'
        f'<g stroke="{SUNDIAL_GNOMON}" stroke-width="1" opacity="0.6">'
        f'{ticks}</g>'
        f'<g font-family="Georgia, serif" font-size="7"'
        f' fill="{SUNDIAL_GNOMON}" text-anchor="middle"'
        f' dominant-baseline="central" opacity="0.7">'
        f'{numerals}</g>'
        f'{gnomon}'
        f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{SUNDIAL_GNOMON}"/>'
        f'</g>'
    )


# ── Periphery: Water Barrel ────────────────────────────────────


def _barrel_water(total_tokens: int) -> WaterDisc:
    """The water surface seen from above: fuller sits nearer the rim.

    Looking into a half-empty barrel from above and to the side, the
    surface shrinks and slides away from the viewer -- so fill reads as
    both size and offset, and a full barrel's water meets its rim.
    """
    fill = math.sqrt(min(1.0, total_tokens / BARREL_TOKEN_SATURATION))
    inner = BARREL_R - BARREL_RIM
    r = inner * (BARREL_MIN_WATER + (1 - BARREL_MIN_WATER) * fill) - 0.5
    slack = inner - r - 0.5
    return WaterDisc(
        cx=BARREL_CX + slack * 0.45,
        cy=BARREL_CY + slack * 0.55,
        r=r,
    )


def _render_barrel_shell(total_tokens: int, water: str) -> str:
    cx, cy, r = BARREL_CX, BARREL_CY, BARREL_R
    inner = r - BARREL_RIM
    staves = ''.join(
        f'<line x1="{cx + inner * math.cos(a):.1f}"'
        f' y1="{cy + inner * math.sin(a):.1f}"'
        f' x2="{cx + r * math.cos(a):.1f}" y2="{cy + r * math.sin(a):.1f}"/>'
        for a in (i * math.tau / 20 for i in range(20))
    )
    return (
        f'<g class="barrel">{_title(f"Rain barrel: {total_tokens:,} tokens")}'
        + _drop_shadow(f'<circle cx="{cx}" cy="{cy}" r="{r}"/>')
        + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{BARREL_WOOD}"/>'
        f'<g stroke="#000" stroke-opacity="0.3" stroke-width="0.8">'
        f'{staves}</g>'
        f'<circle cx="{cx}" cy="{cy}" r="{r - 1.2}" fill="none"'
        f' stroke="{BARREL_BAND}" stroke-width="2"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{inner}" fill="#2e2012"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{inner}" fill="url(#shadeDown)"/>'
        f'{water}'
        f'<circle cx="{cx}" cy="{cy}" r="{inner}" fill="none"'
        f' stroke="{BARREL_BAND}" stroke-width="1.5"/>'
        f'</g>'
    )


def _render_water(disc: WaterDisc, anims: str = '') -> str:
    return (
        f'<circle class="water" cx="{disc.cx:.1f}" cy="{disc.cy:.1f}"'
        f' r="{disc.r:.1f}" fill="url(#waterFill)">{anims}</circle>'
    )


def _render_barrel(total_tokens: int) -> str:
    return _render_barrel_shell(
        total_tokens, _render_water(_barrel_water(total_tokens))
    )


def _render_signboard(garden: GardenData) -> str:
    sessions = sum(b.sessions for b in garden.branches)
    span = ''
    if garden.rings:
        first, last = garden.rings[0].day, garden.rings[-1].day
        span = f'{_format_day(first)} to {_format_day(last)}'
    return _signboard(sessions, span)


def _signboard(sessions: int, subtitle: str, *, live: bool = False) -> str:
    """A painted garden sign: the plot's headline number and its dates.

    ``live`` gives the date line the id the timeline's clock script
    rewrites as the replay advances.
    """
    x, y, w, h = SIGN_BOX
    date_attrs = ' id="plot-date"' if live else ''
    count_attrs = ' id="plot-sessions"' if live else ''
    return (
        '<g class="signboard">'
        + _drop_shadow(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>')
        + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4"'
        f' fill="{_shade(FRAME_WOOD, -0.15)}"'
        f' stroke="{_shade(FRAME_WOOD, -0.45)}" stroke-width="1.5"/>'
        f'<rect x="{x + 4}" y="{y + 4}" width="{w - 8}" height="{h - 8}"'
        f' rx="2" fill="{TAG_FILL}"/>'
        f'<text x="{x + w / 2}" y="{y + h * 0.48:.1f}" text-anchor="middle"'
        f' font-family="Georgia, serif" font-size="14" font-weight="bold"'
        f' fill="{TAG_TEXT}"{count_attrs}>{sessions:,} sessions</text>'
        f'<text class="date-label"{date_attrs} x="{x + w / 2}"'
        f' y="{y + h * 0.78:.1f}" text-anchor="middle"'
        f' font-family="Georgia, serif" font-size="8.5"'
        f' fill="{TAG_EDGE}">{_escape_xml(subtitle)}</text>'
        f'</g>'
    )


# ── Periphery: Border Flowers ──────────────────────────────────


def _flower_color(skill: str) -> str:
    return random.Random(f'flower-{skill}').choice(FLOWER_COLORS)


def _flower_radius(count: int, peak: int) -> float:
    share = math.sqrt(count / peak) if peak > 0 else 0.0
    return FLOWER_MIN_R + (FLOWER_MAX_R - FLOWER_MIN_R) * share


def _render_flower(
    skill: SkillFruit,
    x: float,
    y: float,
    peak: int,
    *,
    tooltip: bool = True,
) -> str:
    """One top-down bloom over two leaves, sized by the skill's calls."""
    r = _flower_radius(skill.count, peak)
    color = _flower_color(skill.skill)
    rng = random.Random(f'flower-sway-{skill.skill}')
    sway = SWAY_VARIANTS[rng.randrange(len(SWAY_VARIANTS))][1]
    leaves = ''.join(
        f'<ellipse cx="{x:.1f}" cy="{y - r * 0.9:.1f}" rx="{r * 0.32:.1f}"'
        f' ry="{r * 0.75:.1f}" fill="#4f8a3c"'
        f' transform="rotate({angle} {x:.1f} {y:.1f})"/>'
        for angle in (rng.uniform(100, 150), rng.uniform(210, 260))
    )
    petals = ''.join(
        f'<ellipse cx="{x:.1f}" cy="{y - r * 0.5:.1f}" rx="{r * 0.36:.1f}"'
        f' ry="{r * 0.55:.1f}" fill="{color}" stroke="#000"'
        f' stroke-opacity="0.18" stroke-width="0.4"'
        f' transform="rotate({i * 60} {x:.1f} {y:.1f})"/>'
        for i in range(6)
    )
    title = _title(f'{skill.skill}: {skill.count:,} calls') if tooltip else ''
    return (
        f'<g class="flower">{title}'
        f'<ellipse cx="{x + 1.5:.1f}" cy="{y + 2:.1f}" rx="{r:.1f}"'
        f' ry="{r * 0.9:.1f}" fill="#000" opacity="0.25"/>'
        f'<g class="{sway}">{leaves}{petals}'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.3:.1f}"'
        f' fill="{FLOWER_CENTER}"/>'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"'
        f' fill="url(#plantShine)"/></g></g>'
    )


def _render_flower_bed(n_skills: int) -> str:
    rows = _flower_rows(n_skills)
    if not rows:
        return ''
    x = FLOWER_BORDER_X0 - 8
    w = FLOWER_BORDER_X1 - FLOWER_BORDER_X0 + 16
    h = rows * FLOWER_ROW_HEIGHT + 2 * FLOWER_BORDER_PAD
    y = FLOWER_BORDER_TOP
    rect = (x, y, w, h)
    return (
        _rect(
            rect,
            'rx="10" fill="#000" filter="url(#softShadow)"'
            f' opacity="{SHADOW_OPACITY}"',
        )
        + _rect(rect, f'rx="10" fill="{MULCH_COLOR}"')
        + _rect(rect, 'rx="10" fill="url(#soilTexture)"')
        + _rect(
            rect,
            f'rx="10" fill="none" stroke="{_shade(STONE_COLOR, -0.1)}"'
            ' stroke-width="3" stroke-dasharray="9 3"',
        )
    )


def _render_border_flowers(skills: list[SkillFruit]) -> str:
    if not skills:
        return ''
    peak = max(s.count for s in skills)
    return _render_flower_bed(len(skills)) + ''.join(
        _render_flower(skill, x, y, peak)
        for skill, (x, y) in zip(
            skills, _flower_positions(len(skills)), strict=True
        )
    )


def _render_butterflies(n_skills: int, opacity: str, anim: str = '') -> str:
    """Butterflies working the beds and border -- only on a dry day."""
    count = min(BUTTERFLY_MAX, 1 + n_skills // BUTTERFLY_PER_SKILLS)
    if n_skills <= 0:
        return ''
    parts = []
    for i in range(count):
        color = FLOWER_COLORS[(i * 2 + 1) % len(FLOWER_COLORS)]
        wing = (
            f'<ellipse cx="-3" cy="-1.5" rx="3" ry="2.4" fill="{color}"/>'
            f'<ellipse cx="3" cy="-1.5" rx="3" ry="2.4" fill="{color}"/>'
            f'<ellipse cx="-2.2" cy="2" rx="2" ry="1.6" fill="{color}"/>'
            f'<ellipse cx="2.2" cy="2" rx="2" ry="1.6" fill="{color}"/>'
        )
        parts.append(
            f'<g class="ccp-fly-{i}"><g class="ccp-flap"'
            f' style="animation-delay:-{i * 0.11:.2f}s"'
            f' stroke="#3a2a18" stroke-width="0.3">{wing}</g>'
            f'<line x1="0" y1="-3" x2="0" y2="3.5" stroke="#2a1d10"'
            f' stroke-width="1.1" stroke-linecap="round"/></g>'
        )
    return (
        f'<g class="butterfly" opacity="{opacity}" pointer-events="none">'
        f'{anim}{"".join(parts)}</g>'
    )


def _butterfly_keyframes(n_skills: int, garden_h: float) -> str:
    count = min(BUTTERFLY_MAX, 1 + n_skills // BUTTERFLY_PER_SKILLS)
    rules = []
    for i in range(count):
        rng = random.Random(f'butterfly-{i}')
        points = [
            (
                rng.uniform(FENCE_X + 20, FENCE_X + FENCE_W - 20),
                rng.uniform(BED_ZONE_Y, garden_h - 20),
            )
            for _ in range(BUTTERFLY_WAYPOINTS)
        ]
        points.append(points[0])
        steps = ''.join(
            f'{k * 100 / BUTTERFLY_WAYPOINTS:.0f}%'
            f'{{transform:translate({x:.0f}px,{y:.0f}px)}}'
            for k, (x, y) in enumerate(points)
        )
        rules.append(
            f'@keyframes ccp-fly-{i}{{{steps}}}'
            f'.ccp-fly-{i}{{animation:ccp-fly-{i}'
            f' {rng.uniform(22, 34):.1f}s ease-in-out infinite;'
            f'transform-box:view-box;transform-origin:0 0}}'
        )
    return ''.join(rules)


# ── Night veil ─────────────────────────────────────────────────


def _render_fireflies(opacity: str, anim: str = '') -> str:
    rng = random.Random('fireflies')
    flies = []
    for _ in range(FIREFLY_COUNT):
        x = rng.uniform(FENCE_X, FENCE_X + FENCE_W)
        y = rng.uniform(FENCE_Y, FENCE_Y + FENCE_H)
        flies.append(
            f'<g class="ccp-wander"'
            f' style="animation-delay:-{rng.uniform(0, 11):.1f}s">'
            f'<circle class="ccp-glow" cx="{x:.1f}" cy="{y:.1f}" r="6"'
            f' fill="url(#fireflyGlow)"'
            f' style="animation-delay:-{rng.uniform(0, 3):.1f}s"/></g>'
        )
    return (
        f'<g class="fireflies" opacity="{opacity}" pointer-events="none">'
        f'{anim}{"".join(flies)}</g>'
    )


def _render_night_veil(garden_h: float, opacity: str, anim: str = '') -> str:
    return (
        f'<rect x="0" y="0"'
        f' width="{PLOT_VIEWBOX_WIDTH}" height="{garden_h:.0f}"'
        f' fill="{NIGHT_VEIL_COLOR}" opacity="{opacity}"'
        f' pointer-events="none">{anim}</rect>'
    )


def _render_plot_night(nightness: float, garden_h: float) -> str:
    level = _saturated_nightness(nightness)
    if level < OPACITY_EPSILON:
        return ''
    return _render_night_veil(
        garden_h, f'{level * NIGHT_VEIL_MAX:.3f}'
    ) + _render_fireflies(f'{level:.3f}')


# ── Rain overlay ───────────────────────────────────────────────


def _render_rain_layer(garden_h: float, opacity: str, anim: str = '') -> str:
    """Rain from above: slanting streaks and rings spreading on the ground."""
    rng = random.Random('plot-rain')
    streaks = []
    for _ in range(RAIN_STREAKS):
        x = rng.uniform(0, PLOT_VIEWBOX_WIDTH)
        y = rng.uniform(0, garden_h)
        streaks.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}"'
            f' x2="{x + 1.5:.1f}" y2="{y + 8:.1f}"/>'
        )
    ripples = ''.join(
        f'<circle class="ccp-ripple"'
        f' cx="{rng.uniform(0, PLOT_VIEWBOX_WIDTH):.1f}"'
        f' cy="{rng.uniform(0, garden_h):.1f}" r="5"'
        f' style="animation-delay:-{rng.uniform(0, 1.6):.2f}s"/>'
        for _ in range(RAIN_RIPPLES)
    )
    return (
        f'<g class="rain" opacity="{opacity}" pointer-events="none">{anim}'
        f'<g stroke="#9bb8d3" stroke-width="0.8">{"".join(streaks)}</g>'
        f'<g fill="none" stroke="#d7e8f5" stroke-width="0.9">{ripples}</g>'
        f'</g>'
    )


def _render_plot_rain(vitality: float, garden_h: float) -> str:
    opacity = _rain_opacity(vitality)
    if opacity < OPACITY_EPSILON:
        return ''
    return _render_rain_layer(garden_h, f'{opacity:.2f}')


# ── Background ─────────────────────────────────────────────────


def _render_lawn(
    grass: str,
    total_h: int,
    garden_h: float,
    fill_anim: str = '',
) -> str:
    """Grass, mown stripes, tufts and a soft vignette.

    Stripes and tufts are translucent overlays in shared patterns, so
    the grass colour underneath can animate with vitality while the
    texture stays put.
    """
    base = _rect(
        (0, 0, PLOT_VIEWBOX_WIDTH, total_h),
        f'class="plot-frame" rx="6" fill="{grass}"',
        fill_anim,
    )
    lawn = (0, 0, PLOT_VIEWBOX_WIDTH, garden_h)
    return (
        base
        + _rect(lawn, 'rx="6" fill="url(#lawnStripes)"')
        + _rect(lawn, 'rx="6" fill="url(#lawnTufts)"')
        + _rect(lawn, 'rx="6" fill="url(#vignette)" pointer-events="none"')
    )


def _render_background(
    vitality: float,
    total_h: int,
    garden_h: float,
) -> str:
    grass = _blend_hex(GRASS_DORMANT, GRASS_COLOR, vitality)
    return _render_lawn(grass, total_h, garden_h)


# ── Defs ───────────────────────────────────────────────────────


def _render_motion_style(n_skills: int, garden_h: float) -> str:
    """Every idle-motion rule, emitted once.

    CSS keyframes, never SMIL, for the same reason as the tree's wind:
    it runs on the compositor and on its own clock, so a paused or
    scrubbed timelapse is still alive.
    """
    sway = ''.join(
        f'.{cls}{{animation:ccp-sway {secs}s ease-in-out -{delay}s infinite}}'
        for (_, cls), (secs, delay) in zip(
            SWAY_VARIANTS, SWAY_TIMING, strict=True
        )
    )
    return (
        f'@keyframes ccp-sway{{0%,100%{{transform:rotate(-{SWAY_DEGREES}deg)}}'
        f'50%{{transform:rotate({SWAY_DEGREES}deg)}}}}'
        f'{sway}'
        '[class*="ccp-sway"]{transform-box:fill-box;transform-origin:center}'
        '@keyframes ccp-flap{0%,100%{transform:scaleX(1)}'
        '50%{transform:scaleX(0.2)}}'
        '.ccp-flap{animation:ccp-flap 0.32s ease-in-out infinite;'
        'transform-box:fill-box;transform-origin:center}'
        '@keyframes ccp-ripple{0%{transform:scale(0.2);opacity:0.9}'
        '100%{transform:scale(1.8);opacity:0}}'
        '.ccp-ripple{animation:ccp-ripple 1.6s ease-out infinite;'
        'transform-box:fill-box;transform-origin:center}'
        '@keyframes ccp-glow{0%,100%{opacity:0.1}50%{opacity:1}}'
        '.ccp-glow{animation:ccp-glow 3s ease-in-out infinite}'
        '@keyframes ccp-wander{0%,100%{transform:translate(0,0)}'
        '33%{transform:translate(9px,-6px)}66%{transform:translate(-7px,5px)}}'
        '.ccp-wander{animation:ccp-wander 11s ease-in-out infinite}'
        '@keyframes ccp-spin{to{transform:rotate(360deg)}}'
        f'.ccp-spin{{animation:ccp-spin {SPRINKLER_SPIN_SECS}s linear'
        ' infinite;'
        'transform-box:fill-box;transform-origin:center}'
        + _butterfly_keyframes(n_skills, garden_h)
        + '.legend [class*="ccp-"]{animation:none}'
        '@media (prefers-reduced-motion:reduce){[class*="ccp-"]'
        '{animation:none}}'
    )


def _render_plot_style(n_skills: int = 0, garden_h: float = 0.0) -> str:
    return (
        '<style>'
        + _render_motion_style(n_skills, garden_h)
        + '@media (prefers-color-scheme:dark){'
        f'.plot-frame{{fill:{DARK_GRASS};'
        f'stroke:{DARK_FRAME_STROKE};stroke-width:2}}'
        f'.legend-bg{{fill:{DARK_LEGEND_BG}}}'
        f'.legend-inner{{fill:{DARK_LEGEND_INNER}}}'
        f'.legend-label{{fill:{DARK_LEGEND_TEXT}}}'
        f'.legend-desc{{fill:{DARK_LEGEND_DESC}}}'
        f'#plot-tooltip-box{{fill:{DARK_TOOLTIP_BG};'
        f'stroke:{DARK_TOOLTIP_BORDER}}}'
        f'#plot-tooltip-text{{fill:{DARK_TOOLTIP_TEXT}}}'
        '}'
        '</style>'
    )


def _seeded_marks(
    seed: str,
    size: int,
    count: int,
    colors: tuple[str, ...],
    radius: tuple[float, float],
) -> str:
    rng = random.Random(seed)
    marks = []
    for _ in range(count):
        cx, cy = rng.uniform(0, size), rng.uniform(0, size)
        r = rng.uniform(*radius)
        marks.append(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{r:.1f}"'
            f' ry="{r * rng.uniform(0.6, 1.0):.1f}"'
            f' fill="{rng.choice(colors)}"'
            f' opacity="{rng.uniform(0.35, 0.8):.2f}"/>'
        )
    return ''.join(marks)


def _render_tufts(seed: str, size: int, count: int) -> str:
    rng = random.Random(seed)
    tufts = []
    for _ in range(count):
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        color = rng.choice(('#000', '#fff'))
        opacity = 0.1 if color == '#000' else 0.07
        for lean in (-2.0, 0.0, 2.0):
            tufts.append(
                f'<path d="M{x:.1f},{y:.1f} q{lean * 0.4:.1f},-2'
                f' {lean:.1f},-4" stroke="{color}" stroke-width="0.8"'
                f' fill="none" opacity="{opacity}"/>'
            )
    return ''.join(tufts)


def _render_paint_defs(sun_anim: str = '') -> str:
    """Shared textures and gradients, referenced by url() everywhere."""
    stripe = LAWN_STRIPE_WIDTH
    gradient_stop = '<stop offset="{}" stop-color="{}" stop-opacity="{}"/>'
    return (
        f'<filter id="softShadow" x="-30%" y="-30%"'
        f' width="160%" height="160%">'
        f'<feOffset dx="{LIGHT_DX}" dy="{LIGHT_DY}">{sun_anim}</feOffset>'
        f'<feGaussianBlur stdDeviation="{SHADOW_BLUR}"/></filter>'
        '<radialGradient id="fireflyGlow">'
        '<stop offset="0" stop-color="#fffbd0"/>'
        '<stop offset="0.25" stop-color="#f3ef7a" stop-opacity="0.9"/>'
        '<stop offset="1" stop-color="#f3ef7a" stop-opacity="0"/>'
        '</radialGradient>'
        f'<pattern id="lawnStripes" width="{stripe * 2}" height="10"'
        f' patternUnits="userSpaceOnUse" patternTransform="rotate(-8)">'
        f'<rect width="{stripe}" height="10" fill="#fff" opacity="0.07"/>'
        f'<rect x="{stripe}" width="{stripe}" height="10" fill="#000"'
        f' opacity="0.05"/></pattern>'
        f'<pattern id="lawnTufts" width="70" height="70"'
        f' patternUnits="userSpaceOnUse">'
        f'{_render_tufts("lawn-tufts", 70, 9)}</pattern>'
        f'<pattern id="gravel" width="22" height="22"'
        f' patternUnits="userSpaceOnUse">'
        f'<rect width="22" height="22" fill="{PATH_COLOR}"/>'
        + _seeded_marks(
            'gravel',
            22,
            14,
            ('#b8a484', '#7d6a50', '#cdbd9c', '#8f7b5e'),
            (0.6, 1.6),
        )
        + '</pattern>'
        '<pattern id="soilTexture" width="18" height="18"'
        ' patternUnits="userSpaceOnUse">'
        + _seeded_marks(
            'soil',
            18,
            10,
            ('#2e1d12', '#8a6448', '#3d2819'),
            (0.5, 1.4),
        )
        + '</pattern>'
        '<linearGradient id="shadeDown" x1="0" y1="0" x2="0" y2="1">'
        + gradient_stop.format(0, '#000', 0.45)
        + gradient_stop.format(1, '#000', 0)
        + '</linearGradient>'
        '<linearGradient id="shadeRight" x1="0" y1="0" x2="1" y2="0">'
        + gradient_stop.format(0, '#000', 0.35)
        + gradient_stop.format(1, '#000', 0)
        + '</linearGradient>'
        '<radialGradient id="stoneShade" cx="0.35" cy="0.3" r="0.8">'
        + gradient_stop.format(0, _shade(STONE_COLOR, 0.35), 1)
        + gradient_stop.format(1, _shade(STONE_COLOR, -0.2), 1)
        + '</radialGradient>'
        '<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1">'
        + gradient_stop.format(0, '#e4e9ec', 1)
        + gradient_stop.format(1, TOOL_METAL, 1)
        + '</linearGradient>'
        '<radialGradient id="waterFill" cx="0.35" cy="0.3" r="0.8">'
        + gradient_stop.format(0, '#9fd3f0', 1)
        + gradient_stop.format(0.5, BARREL_WATER, 1)
        + gradient_stop.format(1, _shade(BARREL_WATER, -0.45), 1)
        + '</radialGradient>'
        '<radialGradient id="dialStone" cx="0.38" cy="0.32" r="0.8">'
        + gradient_stop.format(0, _shade(SUNDIAL_STONE, 0.3), 1)
        + gradient_stop.format(1, _shade(SUNDIAL_STONE, -0.18), 1)
        + '</radialGradient>'
        '<radialGradient id="vignette" cx="0.5" cy="0.45" r="0.75">'
        + gradient_stop.format(0.6, '#000', 0)
        + gradient_stop.format(1, '#000', 0.28)
        + '</radialGradient>'
    )


def _render_plot_defs(
    sun_anim: str = '',
    species: set[str] | None = None,
) -> str:
    return (
        f'<defs>{_render_paint_defs(sun_anim)}'
        f'{_render_plant_defs(species)}</defs>'
    )


# ── Legend ─────────────────────────────────────────────────────


def _legend_plant(species: str, x: float, y: float) -> str:
    color = _plant_color(species, 1.0)
    return (
        f'<use href="#plant-{species}-still" x="{x - 10:.1f}"'
        f' y="{y - 10:.1f}" width="20" height="20" color="{color}"/>'
    )


def _legend_bed(x: float, y: float) -> str:
    from ccgarden.data import RepoBranch as Branch

    bed = BedRect('', x - 11, y - 8, 22, 16, Branch('', 0, 0, 0, 0, 0, 0))
    return _render_bed_body(bed, SOIL_COLOR, shadow=False)


def _legend_flower(x: float, y: float) -> str:
    from ccgarden.data import SkillFruit as Fruit

    return _render_flower(Fruit('legend', 1), x, y, 1, tooltip=False)


def _legend_tool(x: float, y: float) -> str:
    return (
        f'<line x1="{x}" y1="{y - 10}" x2="{x}" y2="{y + 1}"'
        f' stroke="{TOOL_HANDLE}" stroke-width="2.4"'
        f' stroke-linecap="round"/>' + _tool_head('spade', x, y + 1)
    )


def _legend_sundial(x: float, y: float) -> str:
    return (
        f'<circle cx="{x}" cy="{y}" r="9.5" fill="url(#dialStone)"'
        f' stroke="{_shade(SUNDIAL_STONE, -0.35)}"/>'
        f'<path d="M{x},{y} l-3,-8 a8.5,8.5 0 0 1 6,0z"'
        f' fill="{SUNDIAL_NIGHT}"/>'
        f'<path d="M{x},{y} l3,8 a8.5,8.5 0 0 1 -6,0z"'
        f' fill="{SUNDIAL_DAY}"/>'
    )


def _legend_butterfly(x: float, y: float) -> str:
    c = FLOWER_COLORS[1]
    wings = ''.join(
        f'<ellipse cx="{x + dx}" cy="{y + dy}" rx="{rx}" ry="{ry}"'
        f' fill="{c}"/>'
        for dx, dy, rx, ry in (
            (-3.5, -2, 3.6, 3),
            (3.5, -2, 3.6, 3),
            (-2.6, 2.5, 2.4, 2),
            (2.6, 2.5, 2.4, 2),
        )
    )
    return (
        f'{wings}<line x1="{x}" y1="{y - 4}" x2="{x}" y2="{y + 4}"'
        f' stroke="#2a1d10" stroke-width="1.2"/>'
    )


def _legend_firefly(x: float, y: float) -> str:
    return (
        f'<circle cx="{x}" cy="{y}" r="10" fill="{NIGHT_VEIL_COLOR}"/>'
        f'<circle cx="{x - 3}" cy="{y - 2}" r="5"'
        f' fill="url(#fireflyGlow)"/>'
        f'<circle cx="{x + 4}" cy="{y + 3}" r="4"'
        f' fill="url(#fireflyGlow)"/>'
    )


def _legend_rain(x: float, y: float) -> str:
    return (
        f'<circle cx="{x - 3}" cy="{y + 2}" r="6" fill="none"'
        f' stroke="#6f93b6" stroke-width="1"/>'
        f'<use href="#plant-weed" x="{x - 2}" y="{y - 10}" width="14"'
        f' height="14"/>'
    )


def _legend_sprinkler(x: float, y: float) -> str:
    return (
        f'<circle cx="{x}" cy="{y}" r="10" fill="{WET_SOIL}"'
        f' fill-opacity="{WET_SOIL_MAX_OPACITY}"/>' + _sprinkler(x, y, 10)
    )


def _legend_icon(kind: str, x: float, y: float) -> str:
    """A key icon centred on (x, y), drawn by the plot's own renderers."""
    if kind.startswith('plant-'):
        return _legend_plant(kind.removeprefix('plant-'), x, y)
    icons = {
        'bed': _legend_bed,
        'flower': _legend_flower,
        'tool': _legend_tool,
        'sundial': _legend_sundial,
        'butterfly': _legend_butterfly,
        'firefly': _legend_firefly,
        'rain': _legend_rain,
        'sprinkler': _legend_sprinkler,
    }
    return icons[kind](x, y)


LEGEND_ENTRIES = (
    ('bed', 'Bed', 'a repo; area = lines + sessions'),
    ('flower', 'Flower', 'a skill; bigger = more calls'),
    ('tool', 'Tools', 'busiest tools; longer = more'),
    ('sundial', 'Sundial', 'prompts by hour; blue = night'),
    ('butterfly', 'Butterflies', 'a dry, working streak'),
    ('firefly', 'Fireflies', 'late-night prompting'),
    ('rain', 'Rain, weeds', 'days away from the garden'),
    ('sprinkler', 'Sprinklers', 'wider + wetter = more work lately'),
)


def _legend_entry(
    icon: str,
    ix: float,
    iy: float,
    label: str,
    desc: str,
    *,
    note: str = '',
) -> str:
    note_span = (
        f'<tspan class="legend-desc" font-weight="normal" fill="#666">'
        f' {_escape_xml(note)}</tspan>'
        if note
        else ''
    )
    return (
        f'{icon}'
        f'<text class="legend-label" x="{ix + 20:.1f}" y="{iy - 2:.1f}"'
        f' font-family="Georgia, serif" font-size="10"'
        f' font-weight="bold" fill="#333">'
        f'{_escape_xml(label)}{note_span}</text>'
        f'<text class="legend-desc" x="{ix + 20:.1f}" y="{iy + 10:.1f}"'
        f' font-family="Georgia, serif" font-size="8"'
        f' fill="#666">{_escape_xml(desc)}</text>'
    )


def _plant_highlight_style(combos: list[Combo]) -> str:
    """Hovering a plant's key dims every other plant on the plot.

    CSS only (``:has``), so it costs no script; a rule per species
    because a selector can't compare two elements' attributes.
    """
    rules = ''.join(
        f'svg:has(.legend-plant[data-species="{c.species}"]:hover)'
        f' .bed use[data-species]:not([data-species="{c.species}"])'
        f'{{opacity:0.15}}'
        for c in combos
    )
    return (
        '<style>.bed use[data-species]{transition:opacity 0.2s}'
        f'{rules}</style>'
    )


def _legend_plant_entry(
    combo: Combo, ix: float, iy: float, col_w: float
) -> str:
    return (
        f'<g class="legend-plant" data-species="{combo.species}">'
        f'<rect x="{ix - 14:.1f}" y="{iy - 16:.1f}" width="{col_w - 8:.1f}"'
        f' height="{LEGEND_ROW_H - 4}" rx="4" fill="#000" fill-opacity="0"/>'
        + _legend_entry(
            _legend_plant(combo.species, ix, iy),
            ix,
            iy,
            SPECIES[combo.species].name,
            combo_name(combo.label),
            note=_percent(combo.share),
        )
        + '</g>'
    )


def _render_plot_legend(
    ly: float,
    combos: list[Combo] | None = None,
) -> str:
    """The key, in a `.legend` group so every icon holds still.

    Below the fixed entries sits the plant key: one row per model and
    effort combo the garden grows, most-used first, with its share of
    replies. Hovering one picks its plants out on the plot.
    """
    combos = combos or []
    lh = _legend_height(len(combos))
    lpad = 16
    parts = [
        '<g class="legend">',
        (
            f'<rect class="legend-bg" x="0" y="{ly}"'
            f' width="{PLOT_VIEWBOX_WIDTH}"'
            f' height="{lh}" fill="#3f5620"/>'
        ),
        (
            f'<rect class="legend-inner" x="{lpad}" y="{ly + 6}"'
            f' width="{PLOT_VIEWBOX_WIDTH - 2 * lpad}"'
            f' height="{lh - 12}" rx="6"'
            f' fill="#fbfbf3" opacity="0.92"/>'
        ),
    ]
    col_w = (PLOT_VIEWBOX_WIDTH - 2 * lpad) / LEGEND_COLS
    top = ly + LEGEND_TOP_PAD + 11
    for i, (kind, label, desc) in enumerate(LEGEND_ENTRIES):
        ix = lpad + 22 + (i % LEGEND_COLS) * col_w
        iy = top + (i // LEGEND_COLS) * LEGEND_ROW_H
        parts.append(
            _legend_entry(_legend_icon(kind, ix, iy), ix, iy, label, desc)
        )
    if combos:
        rows = math.ceil(len(LEGEND_ENTRIES) / LEGEND_COLS)
        header_y = ly + LEGEND_TOP_PAD + rows * LEGEND_ROW_H + 8
        parts.append(
            f'<line x1="{lpad + 12}" y1="{header_y - 10:.1f}"'
            f' x2="{PLOT_VIEWBOX_WIDTH - lpad - 12}" y2="{header_y - 10:.1f}"'
            f' stroke="#000" stroke-opacity="0.12"/>'
            f'<text class="legend-label" x="{lpad + 12}" y="{header_y:.1f}"'
            f' font-family="Georgia, serif" font-size="10" font-weight="bold"'
            f' fill="#333">Plants'
            f'<tspan class="legend-desc" font-weight="normal" font-size="8"'
            f' fill="#666"> — one per model and effort, % of replies;'
            f' bigger = more effort, more plants = more sessions;'
            f' hover to find</tspan></text>'
        )
        key_top = header_y + LEGEND_KEY_HEADER - 4
        for i, combo in enumerate(combos):
            ix = lpad + 22 + (i % LEGEND_COLS) * col_w
            iy = key_top + (i // LEGEND_COLS) * LEGEND_ROW_H
            parts.append(_legend_plant_entry(combo, ix, iy, col_w))
        parts.append(_plant_highlight_style(combos))
    parts.append('</g><!--/legend-->')
    return ''.join(parts)


# ── Tap tooltip ───────────────────────────────────────────────

TOOLTIP_PAD = 8.0
TOOLTIP_FONT_SIZE = 11.0
TOOLTIP_LINE_H = 16.0
TOOLTIP_ICON = 14.0
TOOLTIP_MAX_PLANTS = 5


def _render_plot_tap_tooltip(total_h: int) -> str:
    """A tooltip that reads each shape's ``<title>``, one line per line.

    A shape carrying ``data-plants`` gets that plant's icon beside each
    of its last lines, so a bed's breakdown shows what each plant looks
    like instead of just its name.
    """
    box = (
        '<rect id="plot-tooltip-box" x="0" y="0" width="10" height="10"'
        ' rx="5" fill="#fbfbf3" stroke="#3a2412"'
        ' stroke-width="1" opacity="0.95"/>'
    )
    text = (
        f'<g id="plot-tooltip-icons"/>'
        f'<text id="plot-tooltip-text" font-family="Georgia, serif"'
        f' font-size="{TOOLTIP_FONT_SIZE:.1f}" fill="#2f3b23"></text>'
    )
    group = (
        f'<g id="plot-tooltip" opacity="0"'
        f' style="pointer-events:none;">{box}{text}</g>'
    )
    script = (
        '<script><![CDATA[\n'
        '(function(){\n'
        '  var NS="http://www.w3.org/2000/svg";\n'
        '  var svg=document.documentElement;\n'
        '  var g=document.getElementById("plot-tooltip");\n'
        '  var bx=document.getElementById("plot-tooltip-box");\n'
        '  var tx=document.getElementById("plot-tooltip-text");\n'
        '  var ic=document.getElementById("plot-tooltip-icons");\n'
        f'  var pad={TOOLTIP_PAD:.1f};\n'
        f'  var lh={TOOLTIP_LINE_H:.1f};\n'
        f'  var isz={TOOLTIP_ICON:.1f};\n'
        f'  var vw={PLOT_VIEWBOX_WIDTH};\n'
        f'  var vh={total_h};\n'
        '  function titleOf(n){\n'
        '    var c=n.childNodes||[];\n'
        '    for(var i=0;i<c.length;i++){\n'
        '      if(c[i].nodeName==="title")return c[i].textContent;\n'
        '    }\n'
        '    return null;\n'
        '  }\n'
        '  function findTooltip(n){\n'
        '    while(n&&n!==svg){\n'
        '      if(titleOf(n)!==null)return n;\n'
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
        '  function clear(n){\n'
        '    while(n.firstChild)n.removeChild(n.firstChild);\n'
        '  }\n'
        '  function hide(){g.setAttribute("opacity","0");}\n'
        '  function show(n,at){\n'
        '    var lines=titleOf(n).split("\\n");\n'
        '    var plants=(n.getAttribute("data-plants")||"")'
        '.split(",").filter(Boolean);\n'
        '    var first=lines.length-plants.length;\n'
        '    clear(tx);clear(ic);\n'
        '    var w=0;\n'
        '    for(var i=0;i<lines.length;i++){\n'
        '      var x=pad,y=pad+lh*i;\n'
        '      if(i>=first){\n'
        '        var p=plants[i-first].split(" ");\n'
        '        var u=document.createElementNS(NS,"use");\n'
        '        u.setAttribute("href","#plant-"+p[0]+"-still");\n'
        '        u.setAttribute("x",x);\n'
        '        u.setAttribute("y",y+(lh-isz)/2);\n'
        '        u.setAttribute("width",isz);\n'
        '        u.setAttribute("height",isz);\n'
        '        u.setAttribute("color",p[1]);\n'
        '        ic.appendChild(u);\n'
        '        x+=isz+4;\n'
        '      }\n'
        '      var ts=document.createElementNS(NS,"tspan");\n'
        '      ts.setAttribute("x",x);\n'
        '      ts.setAttribute("y",y+lh*0.72);\n'
        '      if(i===0)ts.setAttribute("font-weight","bold");\n'
        '      ts.textContent=lines[i];\n'
        '      tx.appendChild(ts);\n'
        '      w=Math.max(w,x+ts.getComputedTextLength());\n'
        '    }\n'
        '    w+=pad;\n'
        '    var bh=lines.length*lh+pad*2;\n'
        '    bx.setAttribute("width",w.toFixed(1));\n'
        '    bx.setAttribute("height",bh.toFixed(1));\n'
        '    var x0=at.x-w/2,y0=at.y-bh-10;\n'
        '    if(x0<4)x0=4;\n'
        '    if(x0+w>vw-4)x0=vw-4-w;\n'
        '    if(y0<4)y0=at.y+14;\n'
        '    if(y0+bh>vh-4)y0=vh-4-bh;\n'
        '    g.setAttribute("transform",'
        '"translate("+x0.toFixed(1)+","+y0.toFixed(1)+")");\n'
        '    g.setAttribute("opacity","1");\n'
        '  }\n'
        '  function onPointer(e){\n'
        '    var n=findTooltip(e.target);\n'
        '    var a=n?pt(e):null;\n'
        '    if(a)show(n,a);else hide();\n'
        '  }\n'
        '  svg.addEventListener("pointerdown",function(e){\n'
        '    if(e.pointerType!=="mouse")onPointer(e);\n'
        '  });\n'
        '  svg.addEventListener("pointermove",function(e){\n'
        '    if(e.pointerType==="mouse")onPointer(e);\n'
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
    combos = _garden_combos(garden.branches)
    layout = _plot_layout(len(garden.skills), len(combos))
    total_h = layout.total_h
    body = (
        _render_background(garden.vitality, total_h, layout.legend_y)
        + _render_paths(beds)
        + _render_fence()
        + _render_beds(beds, garden.branches, garden.vitality)
        + _render_shed(garden.tools)
        + _render_sundial(garden.hour_counts)
        + _render_barrel(garden.total_tokens)
        + _render_signboard(garden)
        + _render_border_flowers(garden.skills)
        + (
            _render_butterflies(len(garden.skills), '1')
            if _rain_opacity(garden.vitality) < OPACITY_EPSILON
            else ''
        )
        + _render_plot_rain(garden.vitality, layout.legend_y)
        + _render_plot_night(garden.nightness, layout.legend_y)
        + _render_plot_legend(layout.legend_y, combos)
        + _render_plot_tap_tooltip(total_h)
    )

    species = {c.species for c in combos} | {'sprout'}
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {PLOT_VIEWBOX_WIDTH} {total_h}"'
        f' width="{PLOT_VIEWBOX_WIDTH}" height="{total_h}">'
        f'{_render_plot_style(len(garden.skills), layout.legend_y)}'
        f'{_render_plot_defs(species=species)}'
        f'{body}'
        f'</svg>'
    )


# ── Timeline helpers ──────────────────────────────────────────


def _branch_at_day(
    days: list[RepoBranchDay],
    repo: str,
    day_idx: int,
    *,
    model_effort_counts: dict[str, int] | None = None,
) -> RepoBranch:
    from ccgarden.data import RepoBranch as Branch

    d = days[day_idx]
    return Branch(
        repo=repo,
        sessions=d.sessions,
        lines_added=d.lines_added,
        lines_removed=d.lines_removed,
        output_tokens=d.output_tokens,
        input_tokens=d.input_tokens,
        cost=d.cost,
        prompts=d.prompts,
        cache_read_tokens=d.cache_read_tokens,
        cache_write_tokens=d.cache_write_tokens,
        model_effort_counts=model_effort_counts or {},
    )


def _final_branches(
    timeline: GardenTimeline,
    repo_model_efforts: dict[str, dict[str, int]] | None = None,
) -> list[RepoBranch]:
    last = len(timeline.days) - 1
    efforts = repo_model_efforts or {}
    return [
        replace(
            _branch_at_day(
                timeline.branch_days[repo],
                repo,
                last,
                model_effort_counts=efforts.get(repo),
            ),
            idle_days=(timeline.branch_idle_days.get(repo) or [None])[-1],
            recent_sessions=next(
                reversed(timeline.branch_recent_sessions.get(repo) or []),
                None,
            ),
        )
        for repo in timeline.branch_order
        if repo in timeline.branch_days
    ]


def _bed_first_day(
    timeline: GardenTimeline,
    repo: str,
) -> int:
    days = timeline.branch_days.get(repo, [])
    for i, d in enumerate(days):
        if d.sessions > 0:
            return i
    return 0


def _render_timeline_beds(
    beds: list[BedRect],
    timeline: GardenTimeline,
    key_times: list[float],
    dur: float,
) -> str:
    n = len(timeline.days)
    max_sessions = max((b.branch.sessions for b in beds), default=1)
    species = _garden_species([b.branch for b in beds])
    parts: list[str] = []

    for bed in beds:
        repo = bed.repo
        days = timeline.branch_days.get(repo, [])
        if not days:
            continue

        first = _bed_first_day(timeline, repo)
        opacity_vals = ['0' if i < first else '1' for i in range(n)]
        opacity_anim = _animate_tag(
            'opacity',
            opacity_vals,
            key_times,
            dur,
        )

        vit_vals = timeline.daily_vitality or [1.0] * n
        soil_vals = [
            _blend_hex(SOIL_DORMANT, SOIL_COLOR, vit_vals[i]) for i in range(n)
        ]
        soil_anim = _animate_tag(
            'fill',
            soil_vals,
            key_times,
            dur,
            smooth=True,
        )

        bed_soil = _render_bed_body(
            bed,
            soil_vals[-1],
            soil_anim,
            furrows=_bed_furrow_marks(bed, max_sessions, species),
        )

        plant_parts = _render_timeline_bed_plants(
            bed,
            days,
            vit_vals,
            max_sessions=max_sessions,
            species=species,
            key_times=key_times,
            dur=dur,
        )

        clock = (key_times, dur)
        strengths = _timeline_sprinkler_strengths(timeline, repo)
        sprinkler = _render_timeline_sprinkler(
            bed,
            _plant_layout(bed, max_sessions, species),
            strengths,
            clock,
        )
        wet = _render_timeline_wet(bed, strengths, clock)
        tt = _title(_bed_tooltip(bed.branch, species))
        data = _bed_tooltip_plants(bed.branch, species)
        parts.append(
            f'<g class="bed"{data} opacity="0">{tt}'
            f'{opacity_anim}'
            f'{bed_soil}'
            f'{wet}'
            f'{plant_parts}'
            f'{_render_timeline_weeds(bed, vit_vals, clock)}'
            f'{sprinkler}'
            f'{_render_row_markers(bed, max_sessions, species)}'
            f'{_render_bed_label(bed)}'
            f'</g>'
        )
    return ''.join(parts)


def _render_timeline_bed_plants(
    bed: BedRect,
    days: list[RepoBranchDay],
    vitality: list[float],
    *,
    max_sessions: int,
    species: dict[str, str],
    key_times: list[float],
    dur: float,
) -> str:
    """The static bed's own plants, each sprouting on its share of days.

    Laid out from the final totals, so the replay ends on exactly the
    bed ``render_plot_svg`` draws; plants come up in planting order as
    the repo's cumulative sessions pass each one's share.
    """
    final_sessions = days[-1].sessions
    plants = _plant_layout(bed, max_sessions, species)
    if final_sessions <= 0 or not plants:
        return ''
    parts: list[str] = []
    for i, plant in enumerate(plants):
        start = i / len(plants) * (1 - SPROUT_SPAN)
        scales = [
            max(0.0, d.sessions / final_sessions - start) / SPROUT_SPAN
            for d in days
        ]
        color = _plant_color(plant.spec.species, vitality[-1])
        parts.append(
            _grow_about(
                'plant-grow',
                (plant.x, plant.y),
                scales,
                (key_times, dur),
                _plant_use(plant, color),
            )
        )
    return ''.join(parts)


def _render_timeline_barrel(
    timeline: GardenTimeline,
    key_times: list[float],
    dur: float,
) -> str:
    n = len(timeline.days)
    tokens = timeline.cumulative_total_tokens or [0] * n
    discs = [_barrel_water(t) for t in tokens]
    anims = ''.join(
        _animate_tag(
            attr, [f'{getattr(d, attr):.1f}' for d in discs], key_times, dur
        )
        for attr in ('cx', 'cy', 'r')
    )
    return _render_barrel_shell(tokens[-1], _render_water(discs[0], anims))


def _render_timeline_grass(
    vitality: list[float],
    total_h: int,
    garden_h: float,
    key_times: list[float],
    dur: float,
) -> str:
    fill_vals = [_blend_hex(GRASS_DORMANT, GRASS_COLOR, v) for v in vitality]
    anim = _animate_tag('fill', fill_vals, key_times, dur, smooth=True)
    return _render_lawn(fill_vals[0], total_h, garden_h, anim)


def _render_timeline_night(
    nightness: list[float],
    garden_h: float,
    key_times: list[float],
    dur: float,
) -> str:
    levels = [_saturated_nightness(n) for n in nightness]
    veil = [f'{v * NIGHT_VEIL_MAX:.3f}' for v in levels]
    glow = [f'{v:.3f}' for v in levels]
    out = _render_night_veil(
        garden_h,
        veil[0],
        _animate_tag('opacity', veil, key_times, dur, smooth=True),
    )
    if max(levels) >= OPACITY_EPSILON:
        out += _render_fireflies(
            glow[0], _animate_tag('opacity', glow, key_times, dur, smooth=True)
        )
    return out


def _render_timeline_rain(
    vitality: list[float],
    garden_h: float,
    key_times: list[float],
    dur: float,
) -> str:
    vals = [f'{_rain_opacity(v):.2f}' for v in vitality]
    anim = _animate_tag('opacity', vals, key_times, dur, smooth=True)
    return _render_rain_layer(garden_h, vals[0], anim)


def _render_date_label(
    timeline: GardenTimeline,
    key_times: list[float],
    dur: float,
) -> str:
    """The signboard, with a script that walks its date line day by day.

    SMIL can't animate text content, so one script reads the document
    clock and swaps the label -- one element instead of one per day.
    Where scripts don't run (an ``<img>`` embed) the sign keeps its
    static text: the finished garden's total and its span of days.
    """
    days = [_format_day(d) for d in timeline.days]
    counts = timeline.cumulative_sessions or [0] * len(days)
    first = next((i for i, c in enumerate(counts) if c), 0)
    spans = [
        day if i <= first else f'{days[first]} to {day}'
        for i, day in enumerate(days)
    ]
    days_json = ','.join(f'"{_escape_xml(d)}"' for d in spans)
    counts_json = ','.join(f'"{c:,} sessions"' for c in counts)
    kt_json = ','.join(f'{t:.4f}' for t in key_times)
    script = (
        '<script><![CDATA[\n'
        '(function(){\n'
        f'  var ds=[{days_json}];\n'
        f'  var cs=[{counts_json}];\n'
        f'  var kt=[{kt_json}];\n'
        f'  var dur={dur:.3f};\n'
        '  var el=document.getElementById("plot-date");\n'
        '  var ct=document.getElementById("plot-sessions");\n'
        '  if(!el)return;\n'
        '  var svg=el.ownerSVGElement;\n'
        '  function upd(){\n'
        '    var t=svg.getCurrentTime()/dur;\n'
        '    if(t<0)t=0;if(t>1)t=1;\n'
        '    var idx=0;\n'
        '    for(var i=1;i<kt.length;i++){\n'
        '      if(t>=kt[i])idx=i;\n'
        '    }\n'
        '    el.textContent=ds[idx];ct.textContent=cs[idx];\n'
        '  }\n'
        '  svg.addEventListener("ccp-seek",upd);\n'
        '  setInterval(upd,200);\n'
        '})();\n'
        ']]></script>'
    )
    return _signboard(counts[-1], spans[-1], live=True) + script


def _render_plot_scrubber(
    timeline: GardenTimeline,
    key_times: list[float],
    dur: float,
    top: float,
    *,
    start_paused_at_end: bool = False,
) -> str:
    """Play/pause and a day slider that seek the replay's own SMIL clock.

    Every animation shares one ``key_times``/``dur`` pair, so a single
    document time fixes every frame: seeking is ``setCurrentTime``, and
    the signboard's date script follows on its own. Hidden until the
    first playthrough ends; ``start_paused_at_end`` (poster mode) skips
    that playthrough and opens on the finished garden.
    """
    last = len(timeline.days) - 1
    kt_json = ','.join(f'{t:.4f}' for t in key_times)
    x = 16
    w = PLOT_VIEWBOX_WIDTH - 32
    panel = (
        f'<foreignObject id="plot-scrubber" x="{x}" y="{top + 4:.1f}"'
        f' width="{w}" height="{PLOT_SCRUBBER_H - 8}"'
        f' style="opacity:0;pointer-events:none;transition:opacity 0.6s">'
        '<div xmlns="http://www.w3.org/1999/xhtml" style="height:100%;'
        'box-sizing:border-box;display:flex;align-items:center;gap:10px;'
        'padding:0 12px;border-radius:8px;background:#fbfbf3;'
        'border:1px solid #3a2412;font-family:Georgia,serif;'
        'color:#2f3b23">'
        '<button id="plot-play" type="button" style="font:inherit;'
        'border:1px solid #7a5a36;background:#efe3c4;border-radius:5px;'
        'padding:2px 10px;cursor:pointer">Replay</button>'
        '<input id="plot-scrub-input" type="range" min="0"'
        f' max="{last}" value="{last}" step="1" style="flex:1"/>'
        '</div></foreignObject>'
    )
    startup = (
        '  svg.pauseAnimations();paused=true;seek(kt.length-1);reveal();\n'
        if start_paused_at_end
        else '  window.setTimeout(reveal,dur*1000+150);\n'
    )
    script = (
        '<script><![CDATA[\n'
        '(function(){\n'
        '  var box=document.getElementById("plot-scrubber");\n'
        '  var svg=box.ownerSVGElement;\n'
        '  var input=document.getElementById("plot-scrub-input");\n'
        '  var play=document.getElementById("plot-play");\n'
        f'  var kt=[{kt_json}];\n'
        f'  var dur={dur:.3f};\n'
        '  var paused=false;\n'
        '  function reveal(){\n'
        '    box.style.opacity="1";box.style.pointerEvents="auto";\n'
        '  }\n'
        '  function seek(i){\n'
        '    if(!paused){svg.pauseAnimations();paused=true;}\n'
        '    svg.setCurrentTime(kt[i]*dur);input.value=i;\n'
        '    svg.dispatchEvent(new Event("ccp-seek"));\n'
        '  }\n'
        '  input.addEventListener("input",function(){\n'
        '    seek(parseInt(input.value,10));\n'
        '  });\n'
        '  play.addEventListener("click",function(){\n'
        '    svg.setCurrentTime(0);svg.unpauseAnimations();paused=false;\n'
        '    window.setTimeout(function(){\n'
        '      if(!paused){seek(kt.length-1);}\n'
        '    },dur*1000+50);\n'
        '  });\n'
        f'{startup}'
        '})();\n'
        ']]></script>'
    )
    return panel + script


def _timeline_final_skills(timeline: GardenTimeline) -> list[SkillFruit]:
    from ccgarden.data import SkillFruit as Fruit

    return [
        Fruit(
            skill=s,
            count=timeline.skill_days[s][-1].count
            if timeline.skill_days.get(s)
            else 0,
        )
        for s in timeline.skill_order
    ]


def _render_timeline_flowers(
    timeline: GardenTimeline,
    key_times: list[float],
    dur: float,
) -> str:
    skills = _timeline_final_skills(timeline)
    if not skills:
        return ''
    peak = max(s.count for s in skills)
    parts = [_render_flower_bed(len(skills))]
    for skill, (x, y) in zip(
        skills, _flower_positions(len(skills)), strict=True
    ):
        days = timeline.skill_days.get(skill.skill, [])
        counts = [d.count for d in days]
        counts += [0] * (len(timeline.days) - len(counts))
        final_r = _flower_radius(skill.count, peak)
        scales = [
            _flower_radius(c, peak) / final_r if c > 0 else 0.0 for c in counts
        ]
        parts.append(
            _grow_about(
                'flower-grow',
                (x, y),
                scales,
                (key_times, dur),
                _render_flower(skill, x, y, peak),
            )
        )
    return ''.join(parts)


# ── Timeline entry point ──────────────────────────────────────


def render_plot_timeline_svg(
    timeline: GardenTimeline,
    *,
    repo_model_efforts: dict[str, dict[str, int]] | None = None,
    start_paused_at_end: bool = False,
) -> str:
    n = len(timeline.days)
    if n == 0:
        return '<svg xmlns="http://www.w3.org/2000/svg"/>'

    key_times = _weighted_key_times(
        timeline.daily_sessions,
        timeline.daily_nightness or None,
        timeline.daily_vitality or None,
    )
    dur = _timeline_duration(
        1.0
        + sum(
            _frame_weights(
                timeline.daily_sessions or [1] * n,
                timeline.daily_nightness or None,
                timeline.daily_vitality or None,
            )
        )
    )
    vitality = timeline.daily_vitality or [1.0] * n
    nightness = timeline.daily_nightness or [0.0] * n

    branches = _final_branches(timeline, repo_model_efforts)
    beds = _layout_beds(branches)
    combos = _garden_combos(branches)

    layout = _plot_layout(len(timeline.skill_order), len(combos))
    total_h = layout.total_h + PLOT_SCRUBBER_H
    body = (
        _render_timeline_grass(
            vitality, total_h, layout.legend_y, key_times, dur
        )
        + _render_paths(
            beds,
            {b.repo: _bed_first_day(timeline, b.repo) for b in beds},
            key_times,
            dur,
        )
        + _render_fence()
        + _render_timeline_beds(beds, timeline, key_times, dur)
        + _render_shed(
            [_tool_bush_final(timeline, t) for t in timeline.tool_order],
            ToolGrowth(
                {
                    t: [d.count for d in timeline.tool_days.get(t, [])]
                    for t in timeline.tool_order
                },
                key_times,
                dur,
            ),
        )
        + _render_sundial(timeline.hour_counts)
        + _render_timeline_barrel(timeline, key_times, dur)
        + _render_timeline_flowers(timeline, key_times, dur)
        + _render_timeline_butterflies(timeline, vitality, key_times, dur)
        + _render_timeline_rain(vitality, layout.legend_y, key_times, dur)
        + _render_timeline_night(nightness, layout.legend_y, key_times, dur)
        + _render_date_label(timeline, key_times, dur)
        + _render_plot_legend(layout.legend_y, combos)
        + _render_plot_scrubber(
            timeline,
            key_times,
            dur,
            layout.total_h,
            start_paused_at_end=start_paused_at_end,
        )
        + _render_plot_tap_tooltip(total_h)
    )

    species = {c.species for c in combos} | {'sprout'}
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {PLOT_VIEWBOX_WIDTH} {total_h}"'
        f' width="{PLOT_VIEWBOX_WIDTH}" height="{total_h}">'
        f'{_render_plot_style(len(timeline.skill_order), layout.legend_y)}'
        f'{_render_plot_defs(_sun_sweep(key_times, dur), species)}'
        f'{body}'
        f'</svg>'
    )


def _sun_sweep(key_times: list[float], dur: float) -> str:
    dx = [
        f'{SUN_SWEEP_START_DX + (LIGHT_DX - SUN_SWEEP_START_DX) * t:.2f}'
        for t in key_times
    ]
    return _animate_tag('dx', dx, key_times, dur, collapse=False)


def _render_timeline_butterflies(
    timeline: GardenTimeline,
    vitality: list[float],
    key_times: list[float],
    dur: float,
) -> str:
    vals = [
        '1' if _rain_opacity(v) < OPACITY_EPSILON else '0' for v in vitality
    ]
    return _render_butterflies(
        len(timeline.skill_order),
        vals[0],
        _animate_tag('opacity', vals, key_times, dur, smooth=True),
    )


def _tool_bush_final(
    timeline: GardenTimeline,
    tool: str,
) -> ToolBush:
    from ccgarden.data import ToolBush as ToolEntry

    days = timeline.tool_days.get(tool, [])
    count = days[-1].count if days else 0
    return ToolEntry(tool=tool, count=count)
