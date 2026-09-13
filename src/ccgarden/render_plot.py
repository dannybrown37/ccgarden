"""Top-down plot-garden renderer.

An alternative to ``render.py``'s tree silhouette: raised beds seen
from above. Same ``GardenData`` / ``GardenTimeline`` input contract,
shares XML/color/animation helpers from ``render_utils``.
"""

from __future__ import annotations

import math
import random
import re
from typing import TYPE_CHECKING, NamedTuple

from ccgarden.data import (
    DayRing,
    EffortBush,
    GardenData,
    ModelCloud,
    RepoBranch,
    SkillFruit,
    ToolBush,
)
from ccgarden.render_utils import (
    TIMELINE_MIN_DAYS_TO_ANIMATE,
    _animate_tag,
    _blend_hex,
    _escape_xml,
    _frame_weights,
    _saturated_nightness,
    _timeline_duration,
    _title,
    _tt_attr,
    _weighted_key_times,
)

if TYPE_CHECKING:
    from ccgarden.data import CartoonBird, GardenTimeline, RepoBranchDay

VIEWBOX_WIDTH = 900
VIEWBOX_HEIGHT = 700

SKY_BAND_HEIGHT = 60
STATS_BAR_HEIGHT = 40

PLOT_MARGIN = 16.0
BED_GAP = 24.0

SOIL_DORMANT = '#6b4a35'
SOIL_LIVING = '#4a3524'

SKY_DAY = '#bfe3f7'
SKY_NIGHT = '#152238'

BED_MIN_WIDTH = 60.0
BED_MAX_WIDTH = 220.0
BED_MIN_HEIGHT = 50.0
BED_MAX_HEIGHT = 180.0
BED_SESSIONS_SATURATION = 100

BED_WOOD = '#5c4326'
BED_SOIL_DORMANT = '#8a6a4a'
BED_SOIL_LIVING = '#3f2c1c'
BED_EDGE_SHADOW = '#1c1108'

WOOD_GRAIN_PATTERN_ID = 'plotWoodGrain'
WOOD_GRAIN_SIZE = 18.0
WOOD_GRAIN_COLORS = ('#4a3620', '#5c4326', '#6b4f2e', '#523b22')

SOIL_TEXTURE_PATTERN_ID = 'plotSoilTexture'
SOIL_TEXTURE_SIZE = 9.0

FURROW_COLOR = '#2a1c11'
FURROW_MAX_COUNT = 8
FURROW_MARGIN = 6.0

PLANT_GLYPHS = (
    'herb',
    'tulip',
    'daisy',
    'fern',
    'succulent',
    'vine',
    'wildflower',
)
PLANT_SIZE = 12.0
PLANT_MARGIN = 10.0
PLANT_DENSITY_CAP = 40

MODEL_COLOR_FAMILIES = {
    'opus': '#8e5fd9',
    'sonnet': '#4a90d9',
    'haiku': '#4ad991',
    'default': '#9a9a9a',
}

VEGETABLE_COLOR = '#c9782e'
VEGETABLE_DENSITY_CAP = 20
VEGETABLE_SIZE = 6.0

POLLINATOR_COUNT_CAP = 6
POLLINATOR_COLOR = '#e8c04a'
POLLINATOR_SIZE = 5.0
POLLINATOR_DRIFT_X = 22.0
POLLINATOR_DRIFT_Y = 12.0
POLLINATOR_DRIFT_SECONDS_MIN = 6.0
POLLINATOR_DRIFT_SECONDS_MAX = 10.0
POLLINATOR_FLIT_CLASS = 'ccg-plot-flit'

BORDER_PLANT_COLOR = '#5f8a4a'
BORDER_PLANT_SPACING = 14.0
BORDER_PLANT_RADIUS = 3.0
BORDER_PLANT_SCALE = 0.45

IRRIGATION_COLOR = '#5aa0c9'
IRRIGATION_GLOW_COLOR = '#8fd0f0'
IRRIGATION_TOKENS_SATURATION = 5_000_000
IRRIGATION_DASH = '5,4'

SPRINKLER_HEAD_RADIUS = 3.0
SPRINKLER_ARM_COUNT = 6
SPRINKLER_MARGIN = 8.0
SPRINKLER_SPIN_SECONDS_MIN = 2.0
SPRINKLER_SPIN_SECONDS_MAX = 9.0
SPRINKLER_SPIN_CLASS = 'ccg-plot-spray'

LEGEND_HEIGHT = 90.0
LEGEND_MARGIN = 12.0
LEGEND_ICON_SIZE = 16.0
LEGEND_LABEL_X = LEGEND_MARGIN + LEGEND_ICON_SIZE + 10.0
LEGEND_DESC_X = 170.0
TOTAL_HEIGHT = VIEWBOX_HEIGHT + LEGEND_HEIGHT
LEGEND_ROWS = (
    ('Bed', 'One repo, area grows with sessions'),
    ('Plant', 'One session; shape = tool, color = model'),
    ('Vegetable', 'Skill / slash-command usage'),
    ('Butterfly', 'Cartoon token savings'),
    ('Border plant', 'Effort level used in that repo'),
    ('Irrigation', "That bed's own cache-token reuse"),
)


class BedPlacement(NamedTuple):
    repo: str
    x: float
    y: float
    w: float
    h: float


def _bed_dimensions(sessions: int) -> tuple[float, float]:
    """Sqrt-saturation sizing.

    Keeps a handful of huge repos from dwarfing everything else on
    the plot.
    """
    scale = math.sqrt(
        min(sessions, BED_SESSIONS_SATURATION) / BED_SESSIONS_SATURATION
    )
    width = BED_MIN_WIDTH + (BED_MAX_WIDTH - BED_MIN_WIDTH) * scale
    height = BED_MIN_HEIGHT + (BED_MAX_HEIGHT - BED_MIN_HEIGHT) * scale
    return width, height


def _place_beds(
    branches: list[RepoBranch], area_width: float, area_height: float
) -> list[BedPlacement]:
    """Row-packing layout.

    Biggest bed first, wrapping to a new row when the current one runs
    out of width. If the packed rows would run past ``area_height``, the
    whole layout is scaled down uniformly about the origin so every bed
    still fits — better a smaller garden than one that bleeds under the
    stats bar.
    """
    ordered = sorted(branches, key=lambda b: (-b.sessions, b.repo))

    placements = []
    x = PLOT_MARGIN
    y = PLOT_MARGIN
    row_height = 0.0
    bottom = PLOT_MARGIN
    for repo_branch in ordered:
        width, height = _bed_dimensions(repo_branch.sessions)
        if x + width > area_width - PLOT_MARGIN and x > PLOT_MARGIN:
            x = PLOT_MARGIN
            y += row_height + BED_GAP
            row_height = 0.0
        placements.append(
            BedPlacement(repo=repo_branch.repo, x=x, y=y, w=width, h=height)
        )
        x += width + BED_GAP
        row_height = max(row_height, height)
        bottom = max(bottom, y + height)

    if bottom > area_height and bottom > 0:
        scale = area_height / bottom
        placements = [
            placement._replace(
                x=placement.x * scale,
                y=placement.y * scale,
                w=placement.w * scale,
                h=placement.h * scale,
            )
            for placement in placements
        ]
    return placements


def _render_plot_defs() -> str:
    """Shared ``<defs>`` patterns: wood-grain border, soil-texture fill.

    One pair of patterns referenced by every bed, so the grain and dot
    texture don't have to be redrawn per bed (same reasoning as the
    tree renderer's shared paints).
    """
    stripe_height = WOOD_GRAIN_SIZE / len(WOOD_GRAIN_COLORS)
    grain_stripes = ''.join(
        f'<rect x="0" y="{i * stripe_height:.1f}" '
        f'width="{WOOD_GRAIN_SIZE:.1f}" height="{stripe_height:.1f}" '
        f'fill="{color}" />'
        for i, color in enumerate(WOOD_GRAIN_COLORS)
    )
    wood_grain = (
        f'<pattern id="{WOOD_GRAIN_PATTERN_ID}" '
        f'width="{WOOD_GRAIN_SIZE:.1f}" height="{WOOD_GRAIN_SIZE:.1f}" '
        f'patternUnits="userSpaceOnUse">{grain_stripes}</pattern>'
    )
    soil_texture = (
        f'<pattern id="{SOIL_TEXTURE_PATTERN_ID}" '
        f'width="{SOIL_TEXTURE_SIZE:.1f}" height="{SOIL_TEXTURE_SIZE:.1f}" '
        f'patternUnits="userSpaceOnUse">'
        f'<circle cx="2.0" cy="2.5" r="0.7" fill="#000" opacity="0.18" />'
        f'<circle cx="6.5" cy="5.5" r="0.5" fill="#000" opacity="0.14" />'
        f'<circle cx="4.0" cy="7.5" r="0.4" fill="#000" opacity="0.12" />'
        f'</pattern>'
    )
    return f'<defs>{wood_grain}{soil_texture}</defs>'


def _render_sky_band(nightness: float) -> str:
    """A thin band across the top, dark in proportion to night share."""
    color = _blend_hex(SKY_DAY, SKY_NIGHT, _saturated_nightness(nightness))
    return (
        f'<rect class="plot-sky" x="0" y="0" '
        f'width="{VIEWBOX_WIDTH}" height="{SKY_BAND_HEIGHT}" '
        f'fill="{color}">{_title("Sky")}</rect>'
    )


def _render_soil(vitality: float) -> str:
    """The bed field, darker and richer the more alive the garden is."""
    color = _blend_hex(SOIL_DORMANT, SOIL_LIVING, vitality)
    return (
        f'<rect class="plot-soil" x="0" y="{SKY_BAND_HEIGHT}" '
        f'width="{VIEWBOX_WIDTH}" '
        f'height="{VIEWBOX_HEIGHT - SKY_BAND_HEIGHT - STATS_BAR_HEIGHT}" '
        f'fill="{color}">{_title("Soil")}</rect>'
    )


def _render_stats_bar(garden: GardenData) -> str:
    """A one-line summary bar along the bottom of the plot."""
    total_sessions = sum(
        repo_branch.sessions for repo_branch in garden.branches
    )
    text = _escape_xml(
        f'{total_sessions} sessions — {garden.total_tokens:,} tokens'
    )
    y = VIEWBOX_HEIGHT - STATS_BAR_HEIGHT
    return (
        f'<g class="plot-stats-bar">'
        f'<rect x="0" y="{y}" width="{VIEWBOX_WIDTH}" '
        f'height="{STATS_BAR_HEIGHT}" fill="#222" />'
        f'<text x="12" y="{y + STATS_BAR_HEIGHT / 2 + 4:.1f}" '
        f'fill="#eee" font-size="14">{text}</text>'
        f'</g>'
    )


def _bed_tooltip_text(repo_branch: RepoBranch) -> str:
    """One line of stats for a bed's hover/tap tooltip."""
    total_tokens = repo_branch.input_tokens + repo_branch.output_tokens
    return (
        f'{repo_branch.repo} — {repo_branch.sessions} sessions, '
        f'{repo_branch.prompts} prompts, '
        f'+{repo_branch.lines_added:,}/-{repo_branch.lines_removed:,} '
        f'lines, {repo_branch.input_tokens:,} in / '
        f'{repo_branch.output_tokens:,} out tokens '
        f'({total_tokens:,} total), ${repo_branch.cost:,.2f}'
    )


def _plant_tooltip_text(tool: str, model: str) -> str:
    """The tool + model behind one session's plant glyph."""
    return f'{tool} · {model}' if tool or model else 'session'


def _bed_edge_shadow(placement: BedPlacement) -> str:
    """Darker bottom/right lines for a slight 3D lip on a bed."""
    return (
        f'<path d="M {placement.x + 3:.1f} '
        f'{placement.y + placement.h - 1.5:.1f} '
        f'L {placement.x + placement.w - 1.5:.1f} '
        f'{placement.y + placement.h - 1.5:.1f} '
        f'L {placement.x + placement.w - 1.5:.1f} {placement.y + 3:.1f}" '
        f'fill="none" stroke="{BED_EDGE_SHADOW}" stroke-width="2.5" '
        f'stroke-linecap="round" opacity="0.5" '
        f'pointer-events="none" />'
    )


def _render_bed(
    placement: BedPlacement, *, vitality: float, tooltip: str
) -> str:
    """A raised bed: rounded rect, wood-grain border, textured soil fill."""
    color = _blend_hex(BED_SOIL_DORMANT, BED_SOIL_LIVING, vitality)
    return (
        f'<g class="plot-bed" data-repo="{_escape_xml(placement.repo)}">'
        f'<rect x="{placement.x:.1f}" y="{placement.y:.1f}" '
        f'width="{placement.w:.1f}" height="{placement.h:.1f}" '
        f'rx="6" fill="{color}" '
        f'stroke="url(#{WOOD_GRAIN_PATTERN_ID})" stroke-width="3">'
        f'{_title(tooltip)}</rect>'
        f'<rect x="{placement.x:.1f}" y="{placement.y:.1f}" '
        f'width="{placement.w:.1f}" height="{placement.h:.1f}" '
        f'rx="6" fill="url(#{SOIL_TEXTURE_PATTERN_ID})" '
        f'pointer-events="none" />'
        f'{_bed_edge_shadow(placement)}'
        f'</g>'
    )


def _render_furrows(rings: list[DayRing], placement: BedPlacement) -> str:
    """Subtle horizontal lines inside a bed.

    One per day worked (capped), evenly spaced between the bed's
    margins.
    """
    worked_days = [day_ring for day_ring in rings if day_ring.sessions > 0]
    if not worked_days:
        return ''
    count = min(len(worked_days), FURROW_MAX_COUNT)
    top = placement.y + FURROW_MARGIN
    bottom = placement.y + placement.h - FURROW_MARGIN
    if bottom <= top:
        return ''
    lines = []
    for i in range(count):
        fraction = i / max(count - 1, 1)
        y_value = top + (bottom - top) * fraction
        lines.append(
            f'<line x1="{placement.x + FURROW_MARGIN:.1f}" '
            f'y1="{y_value:.1f}" '
            f'x2="{placement.x + placement.w - FURROW_MARGIN:.1f}" '
            f'y2="{y_value:.1f}" stroke="{FURROW_COLOR}" '
            f'stroke-width="1" opacity="0.4" />'
        )
    return f'<g class="plot-furrows">{"".join(lines)}</g>'


def _tool_glyph(tool: str, tool_order: list[str]) -> str:
    """Cycle tools through the fixed glyph set by rank.

    Same pattern as the tree renderer's
    ``bush_index = index % len(tool_order)``.
    """
    if not tool_order:
        return PLANT_GLYPHS[0]
    index = tool_order.index(tool) if tool in tool_order else 0
    return PLANT_GLYPHS[index % len(PLANT_GLYPHS)]


def _model_color(model: str) -> str:
    """Match a model name to its color family by substring."""
    lowered = model.lower()
    for key, color in MODEL_COLOR_FAMILIES.items():
        if key != 'default' and key in lowered:
            return color
    return MODEL_COLOR_FAMILIES['default']


def _render_plant_glyph(
    glyph: str, *, cx: float, cy: float, scale: float, color: str
) -> str:
    """One small top-down plant, ~``PLANT_SIZE`` px across before ``scale``.

    Every glyph is a real (if tiny) plant shape rather than an abstract
    mark, plus a shared drop shadow and stem stub so each reads as
    something planted in the soil, not floating on it.
    """
    r = PLANT_SIZE / 2 * scale
    sw = max(scale, 0.5)
    shadow = (
        f'<ellipse cx="{cx:.1f}" cy="{cy + r * 0.7:.1f}" rx="{r * 0.5:.1f}" '
        f'ry="{r * 0.2:.1f}" fill="#000" opacity="0.15" />'
    )
    stem = (
        f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx:.1f}" '
        f'y2="{cy + r * 0.6:.1f}" stroke="#3f2c1c" stroke-width="{sw:.1f}" />'
    )
    shapes = {
        'herb': (
            f'<path d="M {cx - r:.1f} {cy + r * 0.5:.1f} '
            f'L {cx:.1f} {cy:.1f} L {cx + r:.1f} {cy + r * 0.5:.1f} '
            f'M {cx - r * 0.6:.1f} {cy - r * 0.3:.1f} L {cx:.1f} {cy:.1f} '
            f'L {cx + r * 0.6:.1f} {cy - r * 0.3:.1f} '
            f'M {cx:.1f} {cy - r:.1f} L {cx:.1f} {cy:.1f}" '
            f'stroke="{color}" stroke-width="{sw:.1f}" fill="none" '
            f'stroke-linecap="round" />'
        ),
        'tulip': (
            f'<path d="M {cx:.1f} {cy - r:.1f} '
            f'Q {cx - r:.1f} {cy - r * 0.2:.1f} {cx:.1f} {cy + r:.1f} '
            f'Q {cx + r:.1f} {cy - r * 0.2:.1f} {cx:.1f} {cy - r:.1f} Z" '
            f'fill="{color}" />'
        ),
        'daisy': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.35:.1f}" '
            f'fill="{color}" />'
            + ''.join(
                f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{r * 0.35:.1f}" '
                f'ry="{r * 0.6:.1f}" fill="{color}" opacity="0.85" '
                f'transform="rotate({angle:.0f} {px:.1f} {py:.1f})" />'
                for angle, px, py in _petal_positions(cx, cy, r, count=6)
            )
        ),
        'fern': (
            f'<path d="M {cx:.1f} {cy + r:.1f} L {cx:.1f} {cy - r:.1f} '
            f'M {cx:.1f} {cy - r * 0.3:.1f} L {cx - r * 0.7:.1f} '
            f'{cy - r * 0.6:.1f} M {cx:.1f} {cy:.1f} L {cx + r * 0.7:.1f} '
            f'{cy - r * 0.3:.1f} M {cx:.1f} {cy + r * 0.3:.1f} '
            f'L {cx - r * 0.7:.1f} {cy:.1f} M {cx:.1f} {cy + r * 0.6:.1f} '
            f'L {cx + r * 0.7:.1f} {cy + r * 0.3:.1f}" '
            f'stroke="{color}" stroke-width="{sw:.1f}" fill="none" '
            f'stroke-linecap="round" />'
        ),
        'succulent': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{sw:.1f}" />'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.55:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{sw:.1f}" />'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.2:.1f}" '
            f'fill="{color}" />'
        ),
        'vine': (
            f'<path d="M {cx - r:.1f} {cy + r * 0.5:.1f} '
            f'C {cx - r * 0.3:.1f} {cy - r:.1f} '
            f'{cx + r * 0.3:.1f} {cy + r:.1f} '
            f'{cx + r:.1f} {cy - r * 0.5:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{sw:.1f}" '
            f'stroke-linecap="round" />'
        ),
        'wildflower': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.3:.1f}" '
            f'fill="{color}" />'
            + ''.join(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r * 0.28:.1f}" '
                f'fill="{color}" opacity="0.85" />'
                for _, px, py in _petal_positions(cx, cy, r, count=5)
            )
        ),
    }
    shape = shapes.get(glyph, shapes['daisy'])
    return (
        f'<g class="plot-plant-glyph" data-glyph="{glyph}">'
        f'{shadow}{stem}{shape}</g>'
    )


def _petal_positions(
    cx: float, cy: float, r: float, *, count: int
) -> list[tuple[float, float, float]]:
    """Angle plus (x, y) for ``count`` points evenly ringed at ``r``.

    Shared by every glyph that scatters small shapes (petals) around a
    center rather than drawing one continuous outline.
    """
    positions = []
    for i in range(count):
        angle = 360.0 * i / count
        radians = math.radians(angle)
        x = cx + r * 0.6 * math.sin(radians)
        y = cy - r * 0.6 * math.cos(radians)
        positions.append((angle, x, y))
    return positions


def _place_plants_in_bed(
    count: int, placement: BedPlacement, *, seed: str
) -> list[tuple[float, float]]:
    """Row-crop grid of plant positions inset within the bed."""
    del seed
    if count <= 0:
        return []
    inset_x = placement.x + PLANT_MARGIN
    inset_y = placement.y + PLANT_MARGIN
    inset_w = max(placement.w - 2 * PLANT_MARGIN, 0.0)
    inset_h = max(placement.h - 2 * PLANT_MARGIN, 0.0)
    columns = max(math.ceil(math.sqrt(count)), 1)
    rows = max(math.ceil(count / columns), 1)
    cell_w = inset_w / columns
    cell_h = inset_h / rows
    positions = []
    for i in range(count):
        col = i % columns
        row = i // columns
        x = inset_x + (col + 0.5) * cell_w
        y = inset_y + (row + 0.5) * cell_h
        positions.append((x, y))
    return positions


def _render_plants(
    branches: list[RepoBranch],
    tools: list[ToolBush],
    models: list[ModelCloud],
    beds: list[BedPlacement],
) -> str:
    """Scatter plant glyphs into each bed, one per session (capped)."""
    tool_order = [tool_bush.tool for tool_bush in tools]
    model_order = [model_cloud.model for model_cloud in models]
    beds_by_repo = {placement.repo: placement for placement in beds}
    plants = []
    for repo_branch in branches:
        placement = beds_by_repo.get(repo_branch.repo)
        if placement is None:
            continue
        count = min(repo_branch.sessions, PLANT_DENSITY_CAP)
        positions = _place_plants_in_bed(
            count, placement, seed=repo_branch.repo
        )
        for i, (x, y) in enumerate(positions):
            tool = tool_order[i % len(tool_order)] if tool_order else ''
            model = model_order[i % len(model_order)] if model_order else ''
            glyph = _tool_glyph(tool, tool_order)
            color = _model_color(model)
            glyph_svg = _render_plant_glyph(
                glyph, cx=x, cy=y, scale=1.0, color=color
            )
            tooltip = _title(_plant_tooltip_text(tool, model))
            plants.append(f'<g class="plot-plant">{glyph_svg}{tooltip}</g>')
    return ''.join(plants)


def _render_vegetables(
    skills: list[SkillFruit], beds: list[BedPlacement]
) -> str:
    """Produce markers along each bed's bottom edge.

    One per skill use (capped globally, then split evenly across beds),
    since ``SkillFruit`` has no per-repo breakdown.
    """
    if not skills or not beds:
        return ''
    total = min(sum(skill.count for skill in skills), VEGETABLE_DENSITY_CAP)
    if total <= 0:
        return ''
    per_bed = max(total // len(beds), 1)
    markers = []
    for placement in beds:
        edge_y = placement.y + placement.h - VEGETABLE_SIZE / 2
        spacing = placement.w / (per_bed + 1)
        for i in range(per_bed):
            cx = placement.x + spacing * (i + 1)
            markers.append(
                f'<circle class="plot-vegetable" cx="{cx:.1f}" '
                f'cy="{edge_y:.1f}" r="{VEGETABLE_SIZE / 2:.1f}" '
                f'fill="{VEGETABLE_COLOR}" />'
            )
            if len(markers) >= total:
                return ''.join(markers)
    return ''.join(markers)


def _render_plot_wind_style() -> str:
    """CSS keyframes for butterfly drift -- idle motion, so CSS not SMIL.

    One shared figure-8 keyframe; each butterfly only varies its own
    duration and (negative) delay inline, so a handful of butterflies
    don't flit in lockstep. Same reasoning as the tree's `_wind_style`.
    """
    x, y = POLLINATOR_DRIFT_X, POLLINATOR_DRIFT_Y
    return (
        '<style>'
        f'@keyframes {POLLINATOR_FLIT_CLASS}{{'
        f'0%,100%{{transform:translate(0,0)}}'
        f'25%{{transform:translate({x:.1f}px,{-y:.1f}px)}}'
        f'50%{{transform:translate(0,{-y * 1.4:.1f}px)}}'
        f'75%{{transform:translate({-x:.1f}px,{-y:.1f}px)}}}}'
        f'.{POLLINATOR_FLIT_CLASS}{{'
        f'animation-name:{POLLINATOR_FLIT_CLASS};'
        f'animation-timing-function:ease-in-out;'
        f'animation-iteration-count:infinite}}'
        f'@keyframes {SPRINKLER_SPIN_CLASS}{{'
        f'0%{{transform:rotate(0deg)}}100%{{transform:rotate(360deg)}}}}'
        f'.{SPRINKLER_SPIN_CLASS}{{'
        f'animation-name:{SPRINKLER_SPIN_CLASS};'
        f'animation-timing-function:linear;'
        f'animation-iteration-count:infinite}}'
        '.plot-legend .' + POLLINATOR_FLIT_CLASS + '{animation:none}'
        '.plot-legend .' + SPRINKLER_SPIN_CLASS + '{animation:none}'
        '</style>'
    )


def _render_butterfly(cx: float, cy: float, *, seed: str) -> str:
    """A tiny two-wing butterfly, drifting via CSS on its own group.

    The outer group places it on the plot; the inner group carries the
    drift animation, kept separate per the "never put a wind class on
    an element that already has a transform attribute" rule.
    """
    phase = random.Random(f'ccgarden-plot-flit:{seed}').uniform(0.0, 1.0)
    duration = POLLINATOR_DRIFT_SECONDS_MIN + phase * (
        POLLINATOR_DRIFT_SECONDS_MAX - POLLINATOR_DRIFT_SECONDS_MIN
    )
    delay = phase * duration
    r = POLLINATOR_SIZE
    wings = (
        f'<ellipse cx="{-r * 0.55:.1f}" cy="0" rx="{r * 0.6:.1f}" '
        f'ry="{r:.1f}" fill="{POLLINATOR_COLOR}" opacity="0.85" />'
        f'<ellipse cx="{r * 0.55:.1f}" cy="0" rx="{r * 0.6:.1f}" '
        f'ry="{r:.1f}" fill="{POLLINATOR_COLOR}" opacity="0.85" />'
        f'<line x1="0" y1="{-r * 0.8:.1f}" x2="0" y2="{r * 0.8:.1f}" '
        f'stroke="#3a2412" stroke-width="1" stroke-linecap="round" />'
    )
    return (
        f'<g class="plot-pollinator" transform="translate({cx:.1f},'
        f'{cy:.1f})">'
        f'<g class="{POLLINATOR_FLIT_CLASS}" '
        f'style="animation-duration:{duration:.2f}s;'
        f'animation-delay:-{delay:.2f}s">{wings}</g>'
        f'</g>'
    )


def _render_pollinators(
    birds: list[CartoonBird], area_width: float, area_height: float
) -> str:
    """One drifting butterfly per cartoon adapter, capped."""
    if not birds:
        return ''
    count = min(len(birds), POLLINATOR_COUNT_CAP)
    rng = random.Random('pollinators')
    markers = []
    for i in range(count):
        cx = rng.uniform(0.1, 0.9) * area_width
        cy = rng.uniform(0.15, 0.6) * area_height
        markers.append(_render_butterfly(cx, cy, seed=f'butterfly:{i}'))
    return ''.join(markers)


def _effort_slug(effort: str) -> str:
    """A CSS-safe class suffix for an effort level's border-plant group."""
    return re.sub(r'[^a-z0-9]+', '-', effort.lower()).strip('-') or 'effort'


def _effort_glyph(effort: str, effort_order: list[str]) -> str:
    """Cycle effort levels through the plant glyph set by rank."""
    if not effort_order:
        return PLANT_GLYPHS[0]
    index = effort_order.index(effort) if effort in effort_order else 0
    return PLANT_GLYPHS[index % len(PLANT_GLYPHS)]


def _render_bed_borders(
    efforts: list[EffortBush], beds: list[BedPlacement]
) -> str:
    """A ring of tiny plant glyphs around each bed's perimeter.

    One glyph shape per effort level (reusing the Phase 1 plant
    glyphs), muted green, slightly staggered in size for a less
    mechanical look than an even ring of identical dots.
    """
    if not efforts or not beds:
        return ''
    effort_order = [effort_bush.effort for effort_bush in efforts]
    borders = []
    for placement in beds:
        perimeter_points = _perimeter_points(placement)
        glyphs = []
        for i, (x, y) in enumerate(perimeter_points):
            effort = effort_order[i % len(effort_order)]
            glyph = _effort_glyph(effort, effort_order)
            scale = BORDER_PLANT_SCALE * (1.15 if i % 2 else 0.85)
            glyph_svg = _render_plant_glyph(
                glyph, cx=x, cy=y, scale=scale, color=BORDER_PLANT_COLOR
            )
            glyphs.append(
                f'<g class="plot-border-plant '
                f'plot-border-effort-{_effort_slug(effort)}">'
                f'{glyph_svg}</g>'
            )
        borders.append(f'<g class="plot-bed-border">{"".join(glyphs)}</g>')
    return ''.join(borders)


def _perimeter_points(placement: BedPlacement) -> list[tuple[float, float]]:
    """Evenly-spaced points just outside a bed's rounded-rect edge."""
    pad = BORDER_PLANT_RADIUS + 2.0
    top = placement.y - pad
    bottom = placement.y + placement.h + pad
    left = placement.x - pad
    right = placement.x + placement.w + pad
    points = []
    x_steps = max(int(placement.w // BORDER_PLANT_SPACING), 1)
    for i in range(x_steps + 1):
        x = placement.x + (placement.w / x_steps) * i
        points.append((x, top))
        points.append((x, bottom))
    y_steps = max(int(placement.h // BORDER_PLANT_SPACING), 1)
    for i in range(1, y_steps):
        y = placement.y + (placement.h / y_steps) * i
        points.append((left, y))
        points.append((right, y))
    return points


def _sprinkler_intensity(
    cache_read_tokens: int, cache_write_tokens: int
) -> float:
    """0..1 -- how much *that bed's own* cache usage was, saturating."""
    total = cache_read_tokens + cache_write_tokens
    if total <= 0:
        return 0.0
    return math.sqrt(
        min(total, IRRIGATION_TOKENS_SATURATION) / IRRIGATION_TOKENS_SATURATION
    )


def _render_sprinkler(
    cx: float, cy: float, max_radius: float, intensity: float, *, seed: str
) -> str:
    """A center sprinkler head with radiating water, one per bed.

    Unlike the old bed-to-bed lines, everything here is a fact about
    *this* bed alone: arm length/opacity and spin speed all scale with
    that repo's own cache-token share, so pointing at one sprinkler
    answers "how much did this repo reuse cache" directly instead of
    implying an invented relationship to its neighbor.
    """
    if intensity <= 0 or max_radius <= 0:
        return ''
    arm_length = max_radius * (0.4 + 0.6 * intensity)
    opacity = 0.35 + 0.55 * intensity
    duration = SPRINKLER_SPIN_SECONDS_MAX - intensity * (
        SPRINKLER_SPIN_SECONDS_MAX - SPRINKLER_SPIN_SECONDS_MIN
    )
    phase = random.Random(f'ccgarden-plot-spray:{seed}').uniform(0.0, 1.0)
    delay = phase * duration
    arms = ''.join(
        (
            f'<line x1="0" y1="0" '
            f'x2="{arm_length * math.cos(math.radians(angle)):.1f}" '
            f'y2="{arm_length * math.sin(math.radians(angle)):.1f}" '
            f'stroke="{IRRIGATION_COLOR}" stroke-width="1.2" '
            f'stroke-dasharray="{IRRIGATION_DASH}" opacity="{opacity:.2f}" />'
        )
        for angle in range(0, 360, 360 // SPRINKLER_ARM_COUNT)
    )
    head = (
        f'<circle cx="0" cy="0" r="{SPRINKLER_HEAD_RADIUS:.1f}" '
        f'fill="{IRRIGATION_GLOW_COLOR}" opacity="0.9" />'
    )
    return (
        f'<g class="plot-sprinkler" transform="translate({cx:.1f},{cy:.1f})">'
        f'<g class="{SPRINKLER_SPIN_CLASS}" '
        f'style="animation-duration:{duration:.2f}s;'
        f'animation-delay:-{delay:.2f}s">{arms}{head}</g>'
        f'</g>'
    )


def _render_irrigation(
    branches: list[RepoBranch], beds: list[BedPlacement]
) -> str:
    """One sprinkler per bed, driven by that repo's own cache tokens."""
    beds_by_repo = {placement.repo: placement for placement in beds}
    sprinklers = []
    for repo_branch in branches:
        placement = beds_by_repo.get(repo_branch.repo)
        if placement is None:
            continue
        intensity = _sprinkler_intensity(
            repo_branch.cache_read_tokens, repo_branch.cache_write_tokens
        )
        cx = placement.x + placement.w / 2
        cy = placement.y + placement.h / 2
        max_radius = min(placement.w, placement.h) / 2 - SPRINKLER_MARGIN
        sprinklers.append(
            _render_sprinkler(
                cx, cy, max_radius, intensity, seed=repo_branch.repo
            )
        )
    return ''.join(sprinklers)


def _render_legend_icon(label: str, cx: float, cy: float) -> str:
    """A tiny static rendering of the shape a legend row describes.

    Reuses the plot's own shape renderers rather than drawing a second,
    separate icon set -- same reasoning as the tree legend.
    """
    half = LEGEND_ICON_SIZE / 2
    sonnet_color = MODEL_COLOR_FAMILIES['sonnet']
    icons = {
        'Bed': (
            f'<rect x="{cx - half:.1f}" y="{cy - half:.1f}" '
            f'width="{LEGEND_ICON_SIZE:.1f}" height="{LEGEND_ICON_SIZE:.1f}" '
            f'rx="3" fill="{BED_SOIL_LIVING}" '
            f'stroke="url(#{WOOD_GRAIN_PATTERN_ID})" stroke-width="2" />'
        ),
        'Plant': _render_plant_glyph(
            'daisy', cx=cx, cy=cy, scale=0.9, color=sonnet_color
        ),
        'Vegetable': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" '
            f'r="{VEGETABLE_SIZE / 2:.1f}" fill="{VEGETABLE_COLOR}" />'
        ),
        'Butterfly': _render_butterfly(cx, cy, seed='legend'),
        'Border plant': _render_plant_glyph(
            'fern', cx=cx, cy=cy, scale=0.7, color=BORDER_PLANT_COLOR
        ),
        'Irrigation': _render_sprinkler(cx, cy, half, 1.0, seed='legend'),
    }
    return icons.get(label, '')


def _render_legend(garden: GardenData) -> str:
    """A fixed key explaining the plot's visual language."""
    del garden
    y = VIEWBOX_HEIGHT + LEGEND_MARGIN
    row_height = (LEGEND_HEIGHT - LEGEND_MARGIN) / len(LEGEND_ROWS)
    rows = []
    for i, (label, description) in enumerate(LEGEND_ROWS):
        row_y = y + row_height * i + row_height / 2
        icon_cx = LEGEND_MARGIN + LEGEND_ICON_SIZE / 2
        rows.append(
            f'<g class="plot-legend-icon">'
            f'{_render_legend_icon(label, icon_cx, row_y)}</g>'
            f'<text x="{LEGEND_LABEL_X:.1f}" y="{row_y:.1f}" '
            f'fill="#eee" font-size="11" font-weight="bold">'
            f'{_escape_xml(label)}</text>'
            f'<text x="{LEGEND_DESC_X:.1f}" y="{row_y:.1f}" '
            f'fill="#bbb" font-size="10">'
            f'{_escape_xml(description)}</text>'
        )
    return (
        f'<g class="plot-legend">'
        f'<rect x="0" y="{VIEWBOX_HEIGHT}" width="{VIEWBOX_WIDTH}" '
        f'height="{LEGEND_HEIGHT}" fill="#111" />'
        f'{"".join(rows)}</g>'
    )


def _layout_beds(branches: list[RepoBranch]) -> list[BedPlacement]:
    """Place beds in the soil area and shift them below the sky band."""
    beds_area_height = VIEWBOX_HEIGHT - SKY_BAND_HEIGHT - STATS_BAR_HEIGHT
    return [
        placement._replace(y=placement.y + SKY_BAND_HEIGHT)
        for placement in _place_beds(branches, VIEWBOX_WIDTH, beds_area_height)
    ]


def render_plot_svg(garden: GardenData) -> str:
    placements = _layout_beds(garden.branches)
    branches_by_repo = {
        repo_branch.repo: repo_branch for repo_branch in garden.branches
    }
    beds = ''.join(
        _render_bed(
            placement,
            vitality=garden.vitality,
            tooltip=_bed_tooltip_text(branches_by_repo[placement.repo]),
        )
        + _render_furrows(garden.rings, placement)
        for placement in placements
    )
    plants = _render_plants(
        garden.branches, garden.tools, garden.models, placements
    )
    vegetables = _render_vegetables(garden.skills, placements)
    pollinators = _render_pollinators(
        garden.birds, VIEWBOX_WIDTH, VIEWBOX_HEIGHT
    )
    borders = _render_bed_borders(garden.efforts, placements)
    irrigation = _render_irrigation(garden.branches, placements)
    legend = _render_legend(garden)
    body = (
        _render_plot_defs()
        + _render_plot_wind_style()
        + _render_sky_band(garden.nightness)
        + _render_soil(garden.vitality)
        + borders
        + beds
        + irrigation
        + plants
        + vegetables
        + pollinators
        + _render_stats_bar(garden)
        + legend
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {TOTAL_HEIGHT}" '
        f'width="{VIEWBOX_WIDTH}" height="{TOTAL_HEIGHT}">{body}</svg>'
    )


def _timeline_final_garden(timeline: GardenTimeline) -> GardenData:
    """The plot's final day.

    Used both for the fallback and for secondary elements that don't
    walk the timeline (vegetables, pollinators, borders, irrigation,
    legend, stats bar — see ``render_plot_timeline_svg``).
    """
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
            cache_read_tokens=timeline.branch_days[repo][-1].cache_read_tokens,
            cache_write_tokens=timeline.branch_days[repo][
                -1
            ].cache_write_tokens,
        )
        for repo in timeline.branch_order
    ]
    models = [
        ModelCloud(
            model=model,
            output_tokens=timeline.model_days[model][-1].output_tokens,
            input_tokens=timeline.model_days[model][-1].input_tokens,
        )
        for model in timeline.model_order
    ]
    tools = [
        ToolBush(tool=tool, count=timeline.tool_days[tool][-1].count)
        for tool in timeline.tool_order
    ]
    efforts = [
        EffortBush(effort=effort, count=timeline.effort_days[effort][-1].count)
        for effort in timeline.effort_order
    ]
    skills = [
        SkillFruit(skill=skill, count=timeline.skill_days[skill][-1].count)
        for skill in timeline.skill_order
    ]
    return GardenData(
        rings=rings,
        branches=branches,
        cache_read_tokens=timeline.cache_read_tokens,
        cache_write_tokens=timeline.cache_write_tokens,
        models=models,
        tools=tools,
        efforts=efforts,
        skills=skills,
        birds=timeline.birds,
        total_tokens=(
            timeline.cumulative_total_tokens[-1]
            if timeline.cumulative_total_tokens
            else 0
        ),
        nightness=(
            timeline.daily_nightness[-1] if timeline.daily_nightness else 0.0
        ),
        vitality=(
            timeline.daily_vitality[-1] if timeline.daily_vitality else 1.0
        ),
    )


def _render_timeline_bed(
    repo: str,
    placement: BedPlacement,
    branch_days: list[RepoBranchDay],
    key_times: list[float],
    duration: float,
    *,
    vitality: float,
) -> str:
    """A bed that grows with cumulative sessions.

    Fades in on the day its repo first appears.
    """
    final_sessions = branch_days[-1].sessions
    raw_final_w, raw_final_h = _bed_dimensions(final_sessions)
    scale_w = placement.w / raw_final_w if raw_final_w else 1.0
    scale_h = placement.h / raw_final_h if raw_final_h else 1.0
    center_x = placement.x + placement.w / 2
    center_y = placement.y + placement.h / 2
    widths = []
    heights = []
    xs = []
    ys = []
    opacities = []
    for day in branch_days:
        if day.sessions <= 0:
            widths.append('0.0')
            heights.append('0.0')
            xs.append(f'{center_x:.1f}')
            ys.append(f'{center_y:.1f}')
            opacities.append('0')
        else:
            w, h = _bed_dimensions(day.sessions)
            day_w = w * scale_w
            day_h = h * scale_h
            widths.append(f'{day_w:.1f}')
            heights.append(f'{day_h:.1f}')
            xs.append(f'{center_x - day_w / 2:.1f}')
            ys.append(f'{center_y - day_h / 2:.1f}')
            opacities.append('1')
    color = _blend_hex(BED_SOIL_DORMANT, BED_SOIL_LIVING, vitality)
    day_labels = [
        _bed_tooltip_text(
            RepoBranch(
                repo=repo,
                sessions=day.sessions,
                lines_added=day.lines_added,
                lines_removed=day.lines_removed,
                output_tokens=day.output_tokens,
                input_tokens=day.input_tokens,
                cost=day.cost,
                prompts=day.prompts,
            )
        )
        for day in branch_days
    ]
    tt = _tt_attr(day_labels)
    growth_animations = (
        f'{_animate_tag("width", widths, key_times, duration)}'
        f'{_animate_tag("height", heights, key_times, duration)}'
        f'{_animate_tag("x", xs, key_times, duration)}'
        f'{_animate_tag("y", ys, key_times, duration)}'
        f'{_animate_tag("opacity", opacities, key_times, duration)}'
    )
    return (
        f'<g class="plot-bed" data-repo="{_escape_xml(repo)}">'
        f'<rect x="{xs[-1]}" y="{ys[-1]}" '
        f'width="{widths[-1]}" height="{heights[-1]}" '
        f'rx="6" fill="{color}" '
        f'stroke="url(#{WOOD_GRAIN_PATTERN_ID})" stroke-width="3" '
        f'opacity="{opacities[-1]}" {tt}>'
        f'{growth_animations}'
        f'</rect>'
        f'<rect x="{xs[-1]}" y="{ys[-1]}" '
        f'width="{widths[-1]}" height="{heights[-1]}" '
        f'rx="6" fill="url(#{SOIL_TEXTURE_PATTERN_ID})" '
        f'opacity="{opacities[-1]}" pointer-events="none">'
        f'{growth_animations}'
        f'</rect>'
        f'</g>'
    )


PLANT_FADE_LEAD_OPACITY = '0.35'


def _plant_opacity_ramp(
    day_sessions: list[int], plant_index: int
) -> list[str]:
    """Opacity per day for one plant: a one-day fade-in, not a hard step.

    The day before a plant's session count is reached it shows a faint
    partial opacity, then reaches full the day it actually appears --
    so it grows into the bed rather than popping in.
    """
    opacities = []
    for j, sessions in enumerate(day_sessions):
        if sessions > plant_index:
            opacities.append('1')
        elif j + 1 < len(day_sessions) and day_sessions[j + 1] > plant_index:
            opacities.append(PLANT_FADE_LEAD_OPACITY)
        else:
            opacities.append('0')
    return opacities


def _render_timeline_plants(
    branches: list[RepoBranch],
    tools: list[ToolBush],
    models: list[ModelCloud],
    beds: list[BedPlacement],
    branch_days: dict[str, list[RepoBranchDay]],
    *,
    key_times: list[float],
    duration: float,
) -> str:
    """Plants fade in the day their session actually happened."""
    tool_order = [tool_bush.tool for tool_bush in tools]
    model_order = [model_cloud.model for model_cloud in models]
    beds_by_repo = {placement.repo: placement for placement in beds}
    plants = []
    for repo_branch in branches:
        placement = beds_by_repo.get(repo_branch.repo)
        days = branch_days.get(repo_branch.repo)
        if placement is None or not days:
            continue
        count = min(repo_branch.sessions, PLANT_DENSITY_CAP)
        positions = _place_plants_in_bed(
            count, placement, seed=repo_branch.repo
        )
        day_sessions = [day.sessions for day in days]
        for i, (x, y) in enumerate(positions):
            tool = tool_order[i % len(tool_order)] if tool_order else ''
            model = model_order[i % len(model_order)] if model_order else ''
            glyph = _tool_glyph(tool, tool_order)
            color = _model_color(model)
            glyph_svg = _render_plant_glyph(
                glyph, cx=x, cy=y, scale=1.0, color=color
            )
            opacities = _plant_opacity_ramp(day_sessions, i)
            tooltip = _title(_plant_tooltip_text(tool, model))
            plants.append(
                f'<g class="plot-plant" opacity="{opacities[-1]}">'
                f'{glyph_svg}{tooltip}'
                f'{_animate_tag("opacity", opacities, key_times, duration)}'
                f'</g>'
            )
    return ''.join(plants)


def render_plot_timeline_svg(timeline: GardenTimeline) -> str:
    """Replay the plot's real day-by-day history as growth.

    Beds and plants animate on the actual cumulative stats for each day
    in ``timeline.days``; secondary elements (vegetables, pollinators,
    bed borders, irrigation, legend, stats bar) render from the final
    day only, the same simplification the tree renderer makes for fruit
    — they decorate the finished garden rather than walking the
    timeline themselves. Falls back to the plain render when there's
    fewer than two days of history to replay.
    """
    day_count = len(timeline.days)
    final_garden = _timeline_final_garden(timeline)
    if day_count < TIMELINE_MIN_DAYS_TO_ANIMATE:
        return render_plot_svg(final_garden)

    daily_sessions = timeline.daily_sessions or [1] * day_count
    weather = (timeline.daily_nightness, timeline.daily_vitality)
    duration = _timeline_duration(
        1.0 + sum(_frame_weights(daily_sessions, *weather))
    )
    key_times = _weighted_key_times(daily_sessions, *weather)

    placements = _layout_beds(final_garden.branches)
    beds = ''.join(
        _render_timeline_bed(
            placement.repo,
            placement,
            timeline.branch_days[placement.repo],
            key_times,
            duration,
            vitality=final_garden.vitality,
        )
        for placement in placements
    )
    plants = _render_timeline_plants(
        final_garden.branches,
        final_garden.tools,
        final_garden.models,
        placements,
        timeline.branch_days,
        key_times=key_times,
        duration=duration,
    )
    vegetables = _render_vegetables(final_garden.skills, placements)
    pollinators = _render_pollinators(
        final_garden.birds, VIEWBOX_WIDTH, VIEWBOX_HEIGHT
    )
    borders = _render_bed_borders(final_garden.efforts, placements)
    irrigation = _render_irrigation(final_garden.branches, placements)
    legend = _render_legend(final_garden)

    sky_colors = [
        _blend_hex(SKY_DAY, SKY_NIGHT, _saturated_nightness(night))
        for night in (timeline.daily_nightness or [0.0] * day_count)
    ]
    soil_colors = [
        _blend_hex(SOIL_DORMANT, SOIL_LIVING, vitality)
        for vitality in (timeline.daily_vitality or [1.0] * day_count)
    ]
    sky_fill_animate = _animate_tag(
        'fill', sky_colors, key_times, duration, smooth=True
    )
    sky = (
        f'<rect class="plot-sky" x="0" y="0" width="{VIEWBOX_WIDTH}" '
        f'height="{SKY_BAND_HEIGHT}" fill="{sky_colors[-1]}">'
        f'{_title("Sky")}{sky_fill_animate}</rect>'
    )
    soil_fill_animate = _animate_tag(
        'fill', soil_colors, key_times, duration, smooth=True
    )
    soil = (
        f'<rect class="plot-soil" x="0" y="{SKY_BAND_HEIGHT}" '
        f'width="{VIEWBOX_WIDTH}" '
        f'height="{VIEWBOX_HEIGHT - SKY_BAND_HEIGHT - STATS_BAR_HEIGHT}" '
        f'fill="{soil_colors[-1]}">{_title("Soil")}{soil_fill_animate}</rect>'
    )

    from ccgarden.render import (
        SCRUBBER_TOTAL_HEIGHT,
        _render_scrubber,
        _render_tap_tooltip,
    )

    timeline_height = TOTAL_HEIGHT + SCRUBBER_TOTAL_HEIGHT
    scrubber = _render_scrubber(
        timeline,
        key_times,
        duration,
        scrubber_top=TOTAL_HEIGHT,
        start_paused_at_end=True,
    )
    tap_tooltip = _render_tap_tooltip(timeline_height, key_times, duration)

    body = (
        _render_plot_defs()
        + _render_plot_wind_style()
        + sky
        + soil
        + borders
        + beds
        + irrigation
        + plants
        + vegetables
        + pollinators
        + _render_stats_bar(final_garden)
        + legend
        + scrubber
        + tap_tooltip
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {timeline_height:.1f}" '
        f'width="{VIEWBOX_WIDTH}" height="{timeline_height:.1f}">{body}</svg>'
    )
