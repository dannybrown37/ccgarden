"""Top-down plot-garden renderer.

An alternative to ``render.py``'s tree silhouette: raised beds seen
from above. Same ``GardenData`` / ``GardenTimeline`` input contract,
shares XML/color/animation helpers from ``render_utils``.
"""

from __future__ import annotations

import itertools
import math
import random
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

BORDER_PLANT_COLOR = '#5f8a4a'
BORDER_PLANT_SPACING = 14.0
BORDER_PLANT_RADIUS = 3.0

IRRIGATION_COLOR = '#5aa0c9'
IRRIGATION_TOKENS_SATURATION = 5_000_000
MIN_BEDS_FOR_IRRIGATION = 2

LEGEND_HEIGHT = 90.0
LEGEND_MARGIN = 12.0
TOTAL_HEIGHT = VIEWBOX_HEIGHT + LEGEND_HEIGHT
LEGEND_ROWS = (
    ('Bed', 'One repo, area grows with sessions'),
    ('Plant', 'One session; shape = tool, color = model'),
    ('Vegetable', 'Skill / slash-command usage'),
    ('Butterfly', 'Cartoon token savings'),
    ('Border plant', 'Effort level used in that repo'),
    ('Irrigation', 'Cache tokens shared between beds'),
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


def _render_bed(placement: BedPlacement, *, vitality: float) -> str:
    """A raised bed: rounded rect, wood-colored border, soil fill."""
    color = _blend_hex(BED_SOIL_DORMANT, BED_SOIL_LIVING, vitality)
    return (
        f'<g class="plot-bed" data-repo="{_escape_xml(placement.repo)}">'
        f'<rect x="{placement.x:.1f}" y="{placement.y:.1f}" '
        f'width="{placement.w:.1f}" height="{placement.h:.1f}" '
        f'rx="6" fill="{color}" stroke="{BED_WOOD}" stroke-width="3">'
        f'{_title(placement.repo)}</rect>'
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
    """One small plant, ~``PLANT_SIZE`` px across before ``scale``."""
    r = PLANT_SIZE / 2 * scale
    shapes = {
        'herb': (
            f'<line x1="{cx:.1f}" y1="{cy + r:.1f}" '
            f'x2="{cx:.1f}" y2="{cy - r:.1f}" stroke="{color}" '
            f'stroke-width="{max(scale, 0.5):.1f}" />'
        ),
        'tulip': (
            f'<ellipse cx="{cx:.1f}" cy="{cy - r / 2:.1f}" '
            f'rx="{r / 2:.1f}" ry="{r:.1f}" fill="{color}" />'
        ),
        'daisy': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{color}" />'
        ),
        'fern': (
            f'<path d="M {cx:.1f} {cy + r:.1f} L {cx:.1f} {cy - r:.1f} '
            f'M {cx - r:.1f} {cy:.1f} L {cx + r:.1f} {cy:.1f}" '
            f'stroke="{color}" stroke-width="{max(scale, 0.5):.1f}" />'
        ),
        'succulent': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="none" stroke="{color}" '
            f'stroke-width="{max(scale, 0.5):.1f}" />'
        ),
        'vine': (
            f'<path d="M {cx - r:.1f} {cy:.1f} '
            f'Q {cx:.1f} {cy - r:.1f} {cx + r:.1f} {cy:.1f}" '
            f'fill="none" stroke="{color}" '
            f'stroke-width="{max(scale, 0.5):.1f}" />'
        ),
        'wildflower': (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r / 2:.1f}" '
            f'fill="{color}" />'
        ),
    }
    shape = shapes.get(glyph, shapes['daisy'])
    return f'<g class="plot-plant-glyph" data-glyph="{glyph}">{shape}</g>'


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
            plants.append(f'<g class="plot-plant">{glyph_svg}</g>')
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


def _render_pollinators(
    birds: list[CartoonBird], area_width: float, area_height: float
) -> str:
    """One drifting butterfly per cartoon adapter, capped."""
    if not birds:
        return ''
    count = min(len(birds), POLLINATOR_COUNT_CAP)
    rng = random.Random('pollinators')
    markers = []
    for _ in range(count):
        cx = rng.uniform(0.1, 0.9) * area_width
        cy = rng.uniform(0.15, 0.6) * area_height
        markers.append(
            f'<circle class="plot-pollinator" cx="{cx:.1f}" cy="{cy:.1f}" '
            f'r="{POLLINATOR_SIZE:.1f}" fill="{POLLINATOR_COLOR}" '
            f'opacity="0.8" />'
        )
    return ''.join(markers)


def _render_bed_borders(
    efforts: list[EffortBush], beds: list[BedPlacement]
) -> str:
    """A ring of small border plants around each bed's perimeter."""
    if not efforts or not beds:
        return ''
    borders = []
    for placement in beds:
        perimeter_points = _perimeter_points(placement)
        dots = ''.join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" '
            f'r="{BORDER_PLANT_RADIUS:.1f}" fill="{BORDER_PLANT_COLOR}" />'
            for x, y in perimeter_points
        )
        borders.append(f'<g class="plot-bed-border">{dots}</g>')
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


def _render_irrigation(
    cache_read_tokens: int, cache_write_tokens: int, beds: list[BedPlacement]
) -> str:
    """Thin lines linking adjacent beds when cache tokens were used."""
    total_cache_tokens = cache_read_tokens + cache_write_tokens
    if total_cache_tokens <= 0 or len(beds) < MIN_BEDS_FOR_IRRIGATION:
        return ''
    opacity = math.sqrt(
        min(total_cache_tokens, IRRIGATION_TOKENS_SATURATION)
        / IRRIGATION_TOKENS_SATURATION
    )
    lines = []
    for a, b in itertools.pairwise(beds):
        ax, ay = a.x + a.w / 2, a.y + a.h / 2
        bx, by = b.x + b.w / 2, b.y + b.h / 2
        lines.append(
            f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
            f'stroke="{IRRIGATION_COLOR}" stroke-width="1.5" '
            f'opacity="{opacity:.2f}" />'
        )
    return f'<g class="plot-irrigation">{"".join(lines)}</g>'


def _render_legend(garden: GardenData) -> str:
    """A fixed key explaining the plot's visual language."""
    del garden
    y = VIEWBOX_HEIGHT + LEGEND_MARGIN
    row_height = (LEGEND_HEIGHT - LEGEND_MARGIN) / len(LEGEND_ROWS)
    rows = []
    for i, (label, description) in enumerate(LEGEND_ROWS):
        row_y = y + row_height * i + row_height / 2
        rows.append(
            f'<text x="{LEGEND_MARGIN:.1f}" y="{row_y:.1f}" '
            f'fill="#eee" font-size="11" font-weight="bold">'
            f'{_escape_xml(label)}</text>'
            f'<text x="140" y="{row_y:.1f}" fill="#bbb" font-size="10">'
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
    beds = ''.join(
        _render_bed(placement, vitality=garden.vitality)
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
    irrigation = _render_irrigation(
        garden.cache_read_tokens, garden.cache_write_tokens, placements
    )
    legend = _render_legend(garden)
    body = (
        _render_sky_band(garden.nightness)
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
    widths = []
    heights = []
    opacities = []
    for day in branch_days:
        if day.sessions <= 0:
            widths.append('0.0')
            heights.append('0.0')
            opacities.append('0')
        else:
            w, h = _bed_dimensions(day.sessions)
            widths.append(f'{w * scale_w:.1f}')
            heights.append(f'{h * scale_h:.1f}')
            opacities.append('1')
    color = _blend_hex(BED_SOIL_DORMANT, BED_SOIL_LIVING, vitality)
    return (
        f'<g class="plot-bed" data-repo="{_escape_xml(repo)}">'
        f'<rect x="{placement.x:.1f}" y="{placement.y:.1f}" '
        f'width="{widths[-1]}" height="{heights[-1]}" '
        f'rx="6" fill="{color}" stroke="{BED_WOOD}" stroke-width="3" '
        f'opacity="{opacities[-1]}">{_title(repo)}'
        f'{_animate_tag("width", widths, key_times, duration)}'
        f'{_animate_tag("height", heights, key_times, duration)}'
        f'{_animate_tag("opacity", opacities, key_times, duration)}'
        f'</rect>'
        f'</g>'
    )


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
            opacities = [
                '1' if sessions > i else '0' for sessions in day_sessions
            ]
            plants.append(
                f'<g class="plot-plant" opacity="{opacities[-1]}">'
                f'{glyph_svg}'
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
    irrigation = _render_irrigation(
        final_garden.cache_read_tokens,
        final_garden.cache_write_tokens,
        placements,
    )
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

    from ccgarden.render import SCRUBBER_TOTAL_HEIGHT, _render_scrubber

    timeline_height = TOTAL_HEIGHT + SCRUBBER_TOTAL_HEIGHT
    scrubber = _render_scrubber(
        timeline, key_times, duration, scrubber_top=TOTAL_HEIGHT
    )

    body = (
        sky
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
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {timeline_height:.1f}" '
        f'width="{VIEWBOX_WIDTH}" height="{timeline_height:.1f}">{body}</svg>'
    )
