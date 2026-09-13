import itertools
import math
import re

import pytest

from ccgarden.data import (
    CartoonBird,
    DayRing,
    EffortBush,
    GardenData,
    GardenTimeline,
    ModelCloud,
    ModelUsageDay,
    RepoBranch,
    RepoBranchDay,
    SkillFruit,
    ToolBush,
    ToolUsageDay,
)
from ccgarden.render_plot import (
    BED_MAX_HEIGHT,
    BED_MAX_WIDTH,
    BED_MIN_HEIGHT,
    BED_MIN_WIDTH,
    MODEL_COLOR_FAMILIES,
    PLANT_DENSITY_CAP,
    PLANT_GLYPHS,
    POLLINATOR_COUNT_CAP,
    SKY_BAND_HEIGHT,
    STATS_BAR_HEIGHT,
    TOTAL_HEIGHT,
    VEGETABLE_DENSITY_CAP,
    VIEWBOX_HEIGHT,
    VIEWBOX_WIDTH,
    BedPlacement,
    _bed_dimensions,
    _model_color,
    _place_beds,
    _place_plants_in_bed,
    _render_bed,
    _render_bed_borders,
    _render_furrows,
    _render_irrigation,
    _render_legend,
    _render_plant_glyph,
    _render_plants,
    _render_pollinators,
    _render_sky_band,
    _render_soil,
    _render_stats_bar,
    _render_vegetables,
    _timeline_final_garden,
    _tool_glyph,
    render_plot_svg,
    render_plot_timeline_svg,
)


def ring(day: str, *, sessions: int = 1) -> DayRing:
    return DayRing(day=day, sessions=sessions, lines_added=10, lines_removed=1)


def branch(
    repo: str, *, sessions: int = 1, lines_added: int = 100
) -> RepoBranch:
    return RepoBranch(
        repo=repo,
        sessions=sessions,
        lines_added=lines_added,
        lines_removed=10,
        output_tokens=1000,
        input_tokens=100,
        cost=1.0,
    )


def test_render_plot_svg_wraps_content_in_svg_tag() -> None:
    garden = GardenData(
        rings=[ring('2026-07-26')], branches=[], total_tokens=500
    )

    svg = render_plot_svg(garden)

    assert svg.strip().startswith('<svg')
    assert svg.strip().endswith('</svg>')
    assert f'viewBox="0 0 {VIEWBOX_WIDTH} {TOTAL_HEIGHT}"' in svg


def test_render_plot_svg_empty_garden_still_renders() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = render_plot_svg(garden)

    assert '<svg' in svg
    assert 'plot-sky' in svg
    assert 'plot-soil' in svg
    assert 'plot-stats-bar' in svg


@pytest.mark.parametrize('nightness', [0.0, 0.5, 1.0])
def test_render_sky_band_always_full_width(nightness: float) -> None:
    band = _render_sky_band(nightness)

    assert f'width="{VIEWBOX_WIDTH}"' in band
    assert f'height="{SKY_BAND_HEIGHT}"' in band


@pytest.mark.parametrize('vitality', [0.0, 0.5, 1.0])
def test_render_soil_always_full_width(vitality: float) -> None:
    soil = _render_soil(vitality)

    assert f'width="{VIEWBOX_WIDTH}"' in soil
    assert 'plot-soil' in soil


def test_render_stats_bar_reports_sessions_and_tokens() -> None:
    garden = GardenData(
        rings=[],
        branches=[branch('a', sessions=2), branch('b', sessions=3)],
        total_tokens=1234,
    )

    bar = _render_stats_bar(garden)

    assert '5 sessions' in bar
    assert '1,234 tokens' in bar
    assert f'height="{STATS_BAR_HEIGHT}"' in bar


def test_render_plot_timeline_svg_falls_back_when_too_few_days() -> None:
    timeline = GardenTimeline(
        days=['2026-07-26'],
        daily_sessions=[3],
        cumulative_sessions=[3],
        branch_order=['dotfiles'],
        branch_days={
            'dotfiles': [
                RepoBranchDay(
                    day='2026-07-26',
                    sessions=3,
                    lines_added=10,
                    lines_removed=1,
                    output_tokens=100,
                    input_tokens=10,
                    cost=0.1,
                )
            ]
        },
    )

    svg = render_plot_timeline_svg(timeline)

    assert svg.strip().startswith('<svg')
    assert 'animate' not in svg


@pytest.mark.parametrize('sessions', [0, 1, 50, 10_000])
def test_bed_dimensions_stay_within_min_max(sessions: int) -> None:
    width, height = _bed_dimensions(sessions)

    assert BED_MIN_WIDTH <= width <= BED_MAX_WIDTH
    assert BED_MIN_HEIGHT <= height <= BED_MAX_HEIGHT


def test_bed_dimensions_grow_with_sessions() -> None:
    small_w, small_h = _bed_dimensions(1)
    big_w, big_h = _bed_dimensions(1000)

    assert big_w > small_w
    assert big_h > small_h


def test_place_beds_returns_one_placement_per_branch() -> None:
    branches = [branch('a', sessions=5), branch('b', sessions=50)]

    placements = _place_beds(
        branches, VIEWBOX_WIDTH, VIEWBOX_HEIGHT - SKY_BAND_HEIGHT
    )

    assert len(placements) == len(branches)
    assert {p.repo for p in placements} == {'a', 'b'}


def test_place_beds_stay_within_area_bounds() -> None:
    branches = [branch(f'repo-{i}', sessions=i * 10 + 1) for i in range(12)]
    area_width, area_height = VIEWBOX_WIDTH, VIEWBOX_HEIGHT - SKY_BAND_HEIGHT

    placements = _place_beds(branches, area_width, area_height)

    for placement in placements:
        assert placement.x >= 0
        assert placement.y >= 0
        assert placement.x + placement.w <= area_width
        assert placement.y + placement.h <= area_height


def test_place_beds_do_not_overlap() -> None:
    branches = [branch(f'repo-{i}', sessions=i * 7 + 1) for i in range(10)]

    placements = _place_beds(
        branches, VIEWBOX_WIDTH, VIEWBOX_HEIGHT - SKY_BAND_HEIGHT
    )

    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            overlaps_x = a.x < b.x + b.w and b.x < a.x + a.w
            overlaps_y = a.y < b.y + b.h and b.y < a.y + a.h
            assert not (overlaps_x and overlaps_y)


def test_place_beds_is_deterministic() -> None:
    branches = [branch(f'repo-{i}', sessions=i * 3 + 1) for i in range(8)]

    first = _place_beds(branches, VIEWBOX_WIDTH, VIEWBOX_HEIGHT)
    second = _place_beds(branches, VIEWBOX_WIDTH, VIEWBOX_HEIGHT)

    assert first == second


def test_place_beds_empty_branches_returns_empty_list() -> None:
    assert _place_beds([], VIEWBOX_WIDTH, VIEWBOX_HEIGHT) == []


def test_place_beds_shrinks_to_fit_when_rows_overflow_area_height() -> None:
    branches = [branch(f'repo-{i}', sessions=50) for i in range(20)]
    area_width, area_height = VIEWBOX_WIDTH, 200.0

    placements = _place_beds(branches, area_width, area_height)

    assert len(placements) == len(branches)
    for placement in placements:
        assert placement.y + placement.h <= area_height + 1e-6


def test_render_bed_includes_repo_title_and_position() -> None:
    placement = BedPlacement(repo='dotfiles', x=10.0, y=20.0, w=80.0, h=60.0)

    bed = _render_bed(placement, vitality=0.7)

    assert 'dotfiles' in bed
    assert 'x="10' in bed
    assert 'y="20' in bed
    assert 'width="80' in bed
    assert 'height="60' in bed


def test_render_furrows_stay_within_bed_bounds() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=100.0, h=100.0)
    rings = [ring('2026-07-2' + str(i)) for i in range(5)]

    furrows = _render_furrows(rings, placement)

    for y_value in [float(match) for match in _extract_furrow_ys(furrows)]:
        assert placement.y <= y_value <= placement.y + placement.h


def _extract_furrow_ys(svg: str) -> list[str]:
    return re.findall(r'y1="([\d.]+)"', svg)


def test_render_furrows_empty_rings_renders_nothing() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=100.0, h=100.0)

    assert _render_furrows([], placement) == ''


def test_tool_glyph_is_deterministic_and_cycles() -> None:
    tool_order = [
        'Bash',
        'Read',
        'Edit',
        'Write',
        'Grep',
        'Glob',
        'Task',
        'WebFetch',
    ]

    glyphs = [_tool_glyph(tool, tool_order) for tool in tool_order]

    assert glyphs == [_tool_glyph(tool, tool_order) for tool in tool_order]
    assert glyphs[0] == glyphs[len(PLANT_GLYPHS)]
    assert all(glyph in PLANT_GLYPHS for glyph in glyphs)


def test_tool_glyph_empty_order_falls_back_to_first_glyph() -> None:
    assert _tool_glyph('Bash', []) == PLANT_GLYPHS[0]


@pytest.mark.parametrize(
    ('model', 'expected_key'),
    [
        ('claude-opus-4-5', 'opus'),
        ('claude-sonnet-5', 'sonnet'),
        ('claude-haiku-4-5', 'haiku'),
        ('some-other-model', 'default'),
    ],
)
def test_model_color_matches_family_by_substring(
    model: str, expected_key: str
) -> None:
    assert _model_color(model) == MODEL_COLOR_FAMILIES[expected_key]


@pytest.mark.parametrize('glyph', PLANT_GLYPHS)
def test_render_plant_glyph_produces_svg_group(glyph: str) -> None:
    svg = _render_plant_glyph(
        glyph, cx=10.0, cy=20.0, scale=1.0, color='#ff00ff'
    )

    assert svg.startswith('<g')
    assert svg.endswith('</g>')
    assert '#ff00ff' in svg


def test_place_plants_in_bed_returns_requested_count() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=200.0, h=150.0)

    positions = _place_plants_in_bed(12, placement, seed='dotfiles')

    assert len(positions) == 12


def test_place_plants_in_bed_positions_stay_within_bounds() -> None:
    placement = BedPlacement(repo='dotfiles', x=50.0, y=30.0, w=200.0, h=150.0)

    positions = _place_plants_in_bed(20, placement, seed='dotfiles')

    for x, y in positions:
        assert placement.x <= x <= placement.x + placement.w
        assert placement.y <= y <= placement.y + placement.h


def test_place_plants_in_bed_is_deterministic() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=200.0, h=150.0)

    first = _place_plants_in_bed(15, placement, seed='dotfiles')
    second = _place_plants_in_bed(15, placement, seed='dotfiles')

    assert first == second


def test_place_plants_in_bed_zero_count_returns_empty() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=200.0, h=150.0)

    assert _place_plants_in_bed(0, placement, seed='dotfiles') == []


def test_place_plants_in_bed_rows_share_same_y() -> None:
    """A row of a neatly planted bed sits on one line, not jittered."""
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=200.0, h=150.0)

    positions = _place_plants_in_bed(9, placement, seed='dotfiles')

    columns = math.ceil(math.sqrt(9))
    for row_start in range(0, 9, columns):
        row = positions[row_start : row_start + columns]
        ys = {y for _, y in row}
        assert len(ys) == 1


def test_place_plants_in_bed_columns_evenly_spaced() -> None:
    """Plants within a row sit at equal spacing, not random offsets."""
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=200.0, h=150.0)

    positions = _place_plants_in_bed(9, placement, seed='dotfiles')

    columns = math.ceil(math.sqrt(9))
    row = positions[:columns]
    xs = [x for x, _ in row]
    gaps = [b - a for a, b in itertools.pairwise(xs)]
    assert all(math.isclose(gap, gaps[0]) for gap in gaps)


def test_render_plants_count_capped_at_density_cap() -> None:
    branches = [branch('dotfiles', sessions=PLANT_DENSITY_CAP * 5)]
    beds = _place_beds(branches, VIEWBOX_WIDTH, VIEWBOX_HEIGHT)
    tools = [ToolBush(tool='Bash', count=10)]
    models = [
        ModelCloud(model='claude-opus-4-5', output_tokens=10, input_tokens=1)
    ]

    plants_svg = _render_plants(branches, tools, models, beds)

    assert plants_svg.count('<g class="plot-plant"') == PLANT_DENSITY_CAP


def test_render_plants_empty_branches_renders_nothing() -> None:
    assert _render_plants([], [], [], []) == ''


def test_render_vegetables_placed_at_bed_edges() -> None:
    placement = BedPlacement(repo='dotfiles', x=10.0, y=10.0, w=100.0, h=80.0)
    skills = [SkillFruit(skill='code-review', count=5)]

    svg = _render_vegetables(skills, [placement])

    assert 'plot-vegetable' in svg


def test_render_vegetables_count_capped() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=300.0, h=300.0)
    skills = [SkillFruit(skill=f'skill-{i}', count=10) for i in range(20)]

    svg = _render_vegetables(skills, [placement])

    assert svg.count('class="plot-vegetable"') <= VEGETABLE_DENSITY_CAP


def test_render_vegetables_empty_skills_renders_nothing() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=100.0, h=80.0)

    assert _render_vegetables([], [placement]) == ''


def test_render_vegetables_empty_beds_renders_nothing() -> None:
    skills = [SkillFruit(skill='code-review', count=5)]

    assert _render_vegetables(skills, []) == ''


def test_render_pollinators_one_per_bird_capped() -> None:
    birds = [
        CartoonBird(adapter=f'adapter-{i}', calls=1, tokens_saved=1)
        for i in range(POLLINATOR_COUNT_CAP + 5)
    ]

    svg = _render_pollinators(birds, VIEWBOX_WIDTH, VIEWBOX_HEIGHT)

    assert svg.count('class="plot-pollinator"') == POLLINATOR_COUNT_CAP


def test_render_pollinators_empty_birds_renders_nothing() -> None:
    assert _render_pollinators([], VIEWBOX_WIDTH, VIEWBOX_HEIGHT) == ''


def test_render_bed_borders_surrounds_bed() -> None:
    placement = BedPlacement(repo='dotfiles', x=50.0, y=50.0, w=100.0, h=80.0)
    efforts = [EffortBush(effort='high', count=10)]

    svg = _render_bed_borders(efforts, [placement])

    assert 'plot-bed-border' in svg


def test_render_bed_borders_empty_efforts_renders_nothing() -> None:
    placement = BedPlacement(repo='dotfiles', x=50.0, y=50.0, w=100.0, h=80.0)

    assert _render_bed_borders([], [placement]) == ''


def test_render_irrigation_connects_beds_when_cache_tokens_present() -> None:
    beds = [
        BedPlacement(repo='a', x=0.0, y=0.0, w=50.0, h=50.0),
        BedPlacement(repo='b', x=100.0, y=0.0, w=50.0, h=50.0),
    ]

    svg = _render_irrigation(500_000, 100_000, beds)

    assert 'plot-irrigation' in svg


def test_render_irrigation_no_cache_tokens_renders_nothing() -> None:
    beds = [
        BedPlacement(repo='a', x=0.0, y=0.0, w=50.0, h=50.0),
        BedPlacement(repo='b', x=100.0, y=0.0, w=50.0, h=50.0),
    ]

    assert _render_irrigation(0, 0, beds) == ''


def test_render_irrigation_single_bed_renders_nothing() -> None:
    beds = [BedPlacement(repo='a', x=0.0, y=0.0, w=50.0, h=50.0)]

    assert _render_irrigation(500_000, 100_000, beds) == ''


def test_render_legend_includes_key_sections() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = _render_legend(garden)

    assert 'plot-legend' in svg
    assert 'Bed' in svg
    assert 'Plant' in svg


def test_render_plot_svg_extends_canvas_for_legend() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = render_plot_svg(garden)

    assert f'height="{TOTAL_HEIGHT}"' in svg
    assert TOTAL_HEIGHT > VIEWBOX_HEIGHT


def _two_day_timeline() -> GardenTimeline:
    days = ['2026-07-25', '2026-07-26']
    return GardenTimeline(
        days=days,
        daily_sessions=[2, 3],
        cumulative_sessions=[2, 5],
        branch_order=['dotfiles', 'ccgarden'],
        branch_days={
            'dotfiles': [
                RepoBranchDay(
                    day=days[0],
                    sessions=2,
                    lines_added=10,
                    lines_removed=1,
                    output_tokens=100,
                    input_tokens=10,
                    cost=0.1,
                ),
                RepoBranchDay(
                    day=days[1],
                    sessions=2,
                    lines_added=10,
                    lines_removed=1,
                    output_tokens=100,
                    input_tokens=10,
                    cost=0.1,
                ),
            ],
            'ccgarden': [
                RepoBranchDay(
                    day=days[0],
                    sessions=0,
                    lines_added=0,
                    lines_removed=0,
                    output_tokens=0,
                    input_tokens=0,
                    cost=0.0,
                ),
                RepoBranchDay(
                    day=days[1],
                    sessions=3,
                    lines_added=20,
                    lines_removed=2,
                    output_tokens=200,
                    input_tokens=20,
                    cost=0.2,
                ),
            ],
        },
        tool_order=['Bash'],
        tool_days={
            'Bash': [
                ToolUsageDay(day=days[0], count=5),
                ToolUsageDay(day=days[1], count=8),
            ]
        },
        model_order=['claude-opus-4-5'],
        model_days={
            'claude-opus-4-5': [
                ModelUsageDay(day=days[0], output_tokens=100, input_tokens=10),
                ModelUsageDay(day=days[1], output_tokens=300, input_tokens=30),
            ]
        },
        daily_nightness=[0.1, 0.4],
        daily_vitality=[1.0, 0.9],
        cumulative_total_tokens=[110, 330],
    )


def test_timeline_final_garden_uses_last_day_totals() -> None:
    timeline = _two_day_timeline()

    garden = _timeline_final_garden(timeline)

    assert {b.repo for b in garden.branches} == {'dotfiles', 'ccgarden'}
    dotfiles = next(b for b in garden.branches if b.repo == 'dotfiles')
    assert dotfiles.sessions == 2
    assert garden.total_tokens == 330
    assert garden.vitality == 0.9


def test_render_plot_timeline_svg_animates_beds_and_sky() -> None:
    timeline = _two_day_timeline()

    svg = render_plot_timeline_svg(timeline)

    assert svg.strip().startswith('<svg')
    assert 'plot-bed' in svg
    assert 'plot-sky' in svg
    assert '<animate' in svg


def test_render_plot_timeline_svg_new_repo_starts_at_zero_opacity() -> None:
    timeline = _two_day_timeline()

    svg = render_plot_timeline_svg(timeline)

    ccgarden_bed = re.search(
        r'<g class="plot-bed" data-repo="ccgarden">.*?</g>', svg, re.DOTALL
    )
    assert ccgarden_bed is not None
    opacity_animate = re.search(
        r'attributeName="opacity"[^>]*values="([^"]+)"', ccgarden_bed.group()
    )
    assert opacity_animate is not None
    assert opacity_animate.group(1).split(';')[0] == '0'


def test_render_plot_timeline_svg_includes_scrubber() -> None:
    timeline = _two_day_timeline()

    svg = render_plot_timeline_svg(timeline)

    assert 'ccgarden-scrubber' in svg
