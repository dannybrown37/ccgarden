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
    LEGEND_ROWS,
    MODEL_COLOR_FAMILIES,
    PLANT_DENSITY_CAP,
    PLANT_FADE_LEAD_OPACITY,
    PLANT_GLYPHS,
    POLLINATOR_COUNT_CAP,
    POLLINATOR_FLIT_CLASS,
    SKY_BAND_HEIGHT,
    SOIL_TEXTURE_PATTERN_ID,
    STATS_BAR_HEIGHT,
    TOTAL_HEIGHT,
    VEGETABLE_DENSITY_CAP,
    VIEWBOX_HEIGHT,
    VIEWBOX_WIDTH,
    WOOD_GRAIN_PATTERN_ID,
    BedPlacement,
    _bed_dimensions,
    _bed_tooltip_text,
    _effort_slug,
    _model_color,
    _plant_opacity_ramp,
    _plant_tooltip_text,
    _render_plot_defs,
    _place_beds,
    _place_plants_in_bed,
    _render_bed,
    _perimeter_points,
    _render_bed_borders,
    _render_furrows,
    _render_irrigation,
    _render_legend,
    _render_legend_icon,
    _render_plant_glyph,
    _render_plants,
    _render_plot_wind_style,
    _render_pollinators,
    _render_sky_band,
    _render_soil,
    _render_sprinkler,
    _render_stats_bar,
    _render_timeline_bed,
    _render_vegetables,
    _sprinkler_intensity,
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

    bed = _render_bed(placement, vitality=0.7, tooltip='dotfiles — stats')

    assert 'dotfiles' in bed
    assert 'x="10' in bed
    assert 'y="20' in bed
    assert 'width="80' in bed
    assert 'height="60' in bed


def test_bed_tooltip_text_reports_stats() -> None:
    repo_branch = branch('dotfiles', sessions=3, lines_added=100)

    text = _bed_tooltip_text(repo_branch)

    assert 'dotfiles' in text
    assert '3 sessions' in text
    assert '+100' in text
    assert '$1.00' in text


def test_plant_tooltip_text_combines_tool_and_model() -> None:
    assert _plant_tooltip_text('Bash', 'sonnet-5') == 'Bash · sonnet-5'


def test_render_plants_include_tool_model_tooltip() -> None:
    branches = [branch('dotfiles', sessions=1)]
    tools = [ToolBush(tool='Bash', count=1)]
    models = [ModelCloud(model='sonnet-5', output_tokens=1, input_tokens=1)]
    beds = _place_beds(branches, VIEWBOX_WIDTH, VIEWBOX_HEIGHT)

    svg = _render_plants(branches, tools, models, beds)

    assert 'Bash · sonnet-5' in svg


def test_render_timeline_bed_uses_data_tt_per_day() -> None:
    placement = BedPlacement(repo='dotfiles', x=0.0, y=0.0, w=80.0, h=60.0)
    branch_days = [
        RepoBranchDay(
            day='2026-07-01',
            sessions=1,
            lines_added=10,
            lines_removed=1,
            output_tokens=100,
            input_tokens=10,
            cost=0.1,
            prompts=2,
        ),
        RepoBranchDay(
            day='2026-07-02',
            sessions=2,
            lines_added=20,
            lines_removed=2,
            output_tokens=200,
            input_tokens=20,
            cost=0.2,
            prompts=4,
        ),
    ]

    bed = _render_timeline_bed(
        'dotfiles', placement, branch_days, [0.0, 1.0], 10.0, vitality=0.7
    )

    assert 'data-tt=' in bed
    assert '1 sessions' in bed
    assert '2 sessions' in bed


def test_render_plot_defs_declares_wood_grain_and_soil_texture() -> None:
    defs = _render_plot_defs()

    assert f'id="{WOOD_GRAIN_PATTERN_ID}"' in defs
    assert f'id="{SOIL_TEXTURE_PATTERN_ID}"' in defs


def test_render_bed_references_pattern_defs() -> None:
    placement = BedPlacement(repo='dotfiles', x=10.0, y=20.0, w=80.0, h=60.0)

    bed = _render_bed(placement, vitality=0.7, tooltip='dotfiles — stats')

    assert f'url(#{WOOD_GRAIN_PATTERN_ID})' in bed
    assert f'url(#{SOIL_TEXTURE_PATTERN_ID})' in bed


def test_render_plot_svg_includes_pattern_defs() -> None:
    garden = GardenData(
        rings=[],
        branches=[branch('dotfiles', sessions=3)],
        cache_read_tokens=0,
        cache_write_tokens=0,
        models=[],
        tools=[],
        efforts=[],
        skills=[],
        birds=[],
        total_tokens=100,
        nightness=0.0,
        vitality=1.0,
    )

    svg = render_plot_svg(garden)

    assert f'id="{WOOD_GRAIN_PATTERN_ID}"' in svg
    assert f'id="{SOIL_TEXTURE_PATTERN_ID}"' in svg


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


def test_render_pollinators_render_butterfly_shapes() -> None:
    birds = [CartoonBird(adapter='adapter-0', calls=1, tokens_saved=1)]

    svg = _render_pollinators(birds, VIEWBOX_WIDTH, VIEWBOX_HEIGHT)

    assert svg.count('<ellipse') == 2
    assert POLLINATOR_FLIT_CLASS in svg
    assert 'animation-duration' in svg
    assert 'animation-delay' in svg


def test_render_plot_wind_style_declares_flit_keyframes() -> None:
    style = _render_plot_wind_style()

    assert f'@keyframes {POLLINATOR_FLIT_CLASS}' in style
    assert f'.{POLLINATOR_FLIT_CLASS}' in style


def test_render_plot_svg_includes_wind_style() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = render_plot_svg(garden)

    assert f'@keyframes {POLLINATOR_FLIT_CLASS}' in svg


def test_render_bed_borders_surrounds_bed() -> None:
    placement = BedPlacement(repo='dotfiles', x=50.0, y=50.0, w=100.0, h=80.0)
    efforts = [EffortBush(effort='high', count=10)]

    svg = _render_bed_borders(efforts, [placement])

    assert 'plot-bed-border' in svg


def test_render_bed_borders_have_effort_specific_classes() -> None:
    placement = BedPlacement(repo='dotfiles', x=50.0, y=50.0, w=100.0, h=80.0)
    efforts = [
        EffortBush(effort='low', count=1),
        EffortBush(effort='high', count=10),
    ]

    svg = _render_bed_borders(efforts, [placement])

    assert 'plot-border-effort-low' in svg
    assert 'plot-border-effort-high' in svg
    assert 'plot-border-plant' in svg


def test_effort_slug_is_css_safe() -> None:
    assert _effort_slug('Ultra High') == 'ultra-high'


def test_render_bed_borders_empty_efforts_renders_nothing() -> None:
    placement = BedPlacement(repo='dotfiles', x=50.0, y=50.0, w=100.0, h=80.0)

    assert _render_bed_borders([], [placement]) == ''


def test_perimeter_points_cover_all_four_sides() -> None:
    """Border plants must ring the whole bed, not just top and bottom."""
    placement = BedPlacement(repo='dotfiles', x=50.0, y=50.0, w=100.0, h=80.0)

    points = _perimeter_points(placement)

    left_edge = placement.x
    right_edge = placement.x + placement.w
    xs = {x for x, _ in points}
    assert any(x < left_edge for x in xs), 'no points left of the bed'
    assert any(x > right_edge for x in xs), 'no points right of the bed'
    top_edge = placement.y
    bottom_edge = placement.y + placement.h
    ys = {y for _, y in points}
    assert any(y < top_edge for y in ys), 'no points above the bed'
    assert any(y > bottom_edge for y in ys), 'no points below the bed'


def test_sprinkler_intensity_scales_with_cache_tokens() -> None:
    assert _sprinkler_intensity(0, 0) == 0.0
    low = _sprinkler_intensity(1_000, 0)
    high = _sprinkler_intensity(5_000_000, 5_000_000)
    assert 0.0 < low < high <= 1.0


def test_render_sprinkler_scales_arm_length_with_intensity() -> None:
    faint = _render_sprinkler(50.0, 50.0, 40.0, 0.1, seed='a')
    strong = _render_sprinkler(50.0, 50.0, 40.0, 1.0, seed='a')

    def max_arm_length(svg: str) -> float:
        xs = [abs(float(x)) for x in re.findall(r'x2="(-?[\d.]+)"', svg)]
        return max(xs)

    assert max_arm_length(strong) > max_arm_length(faint)


def test_render_sprinkler_zero_intensity_renders_nothing() -> None:
    assert _render_sprinkler(50.0, 50.0, 40.0, 0.0, seed='a') == ''


def test_render_irrigation_one_sprinkler_per_repo_with_cache_tokens() -> None:
    branches = [
        RepoBranch(
            repo='a',
            sessions=1,
            lines_added=1,
            lines_removed=0,
            output_tokens=1,
            input_tokens=1,
            cost=0.0,
            cache_read_tokens=500_000,
            cache_write_tokens=0,
        ),
        RepoBranch(
            repo='b',
            sessions=1,
            lines_added=1,
            lines_removed=0,
            output_tokens=1,
            input_tokens=1,
            cost=0.0,
        ),
    ]
    beds = [
        BedPlacement(repo='a', x=0.0, y=0.0, w=50.0, h=50.0),
        BedPlacement(repo='b', x=100.0, y=0.0, w=50.0, h=50.0),
    ]

    svg = _render_irrigation(branches, beds)

    assert svg.count('plot-sprinkler') == 1


def test_render_irrigation_no_cache_tokens_renders_nothing() -> None:
    branches = [branch('a', sessions=1)]
    beds = [BedPlacement(repo='a', x=0.0, y=0.0, w=50.0, h=50.0)]

    assert _render_irrigation(branches, beds) == ''


def test_render_legend_includes_key_sections() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = _render_legend(garden)

    assert 'plot-legend' in svg
    assert 'Bed' in svg
    assert 'Plant' in svg


def test_render_legend_includes_mini_icons_not_just_text() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = _render_legend(garden)

    assert 'plot-legend-icon' in svg
    assert svg.count('plot-legend-icon') == len(LEGEND_ROWS)
    assert '<ellipse' in svg
    assert '<path' in svg


@pytest.mark.parametrize('label', [row[0] for row in LEGEND_ROWS])
def test_render_legend_icon_produces_svg_for_every_row(label: str) -> None:
    icon = _render_legend_icon(label, 10.0, 10.0)

    assert icon != ''


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


def test_render_timeline_bed_final_size_matches_placement() -> None:
    """A bed scaled down to fit must animate to its own placement size.

    Not the unscaled size for that session count -- or it grows into
    its neighbors.
    """
    placement = BedPlacement(repo='dotfiles', x=100.0, y=50.0, w=80.0, h=60.0)
    branch_days = [
        RepoBranchDay(
            day='2026-01-01',
            sessions=200,
            lines_added=0,
            lines_removed=0,
            output_tokens=0,
            input_tokens=0,
            cost=0.0,
        )
    ]

    svg = _render_timeline_bed(
        'dotfiles', placement, branch_days, [0.0], 1.0, vitality=1.0
    )

    width_match = re.search(r'attributeName="width"[^>]*values="([^"]+)"', svg)
    height_match = re.search(
        r'attributeName="height"[^>]*values="([^"]+)"', svg
    )
    assert width_match is not None
    assert height_match is not None
    assert float(width_match.group(1).split(';')[-1]) == placement.w


def test_render_timeline_bed_grows_from_center() -> None:
    placement = BedPlacement(repo='dotfiles', x=100.0, y=50.0, w=80.0, h=60.0)
    branch_days = [
        RepoBranchDay(
            day='2026-01-01',
            sessions=1,
            lines_added=0,
            lines_removed=0,
            output_tokens=0,
            input_tokens=0,
            cost=0.0,
        ),
        RepoBranchDay(
            day='2026-01-02',
            sessions=200,
            lines_added=0,
            lines_removed=0,
            output_tokens=0,
            input_tokens=0,
            cost=0.0,
        ),
    ]

    svg = _render_timeline_bed(
        'dotfiles', placement, branch_days, [0.0, 1.0], 1.0, vitality=1.0
    )

    x_match = re.search(r'attributeName="x"[^>]*values="([^"]+)"', svg)
    y_match = re.search(r'attributeName="y"[^>]*values="([^"]+)"', svg)
    assert x_match is not None
    assert y_match is not None
    first_x, last_x = (
        x_match.group(1).split(';')[0],
        x_match.group(1).split(';')[-1],
    )
    assert float(first_x) != float(last_x)
    assert float(last_x) == placement.x
    assert float(y_match.group(1).split(';')[-1]) == placement.y


def test_plant_opacity_ramp_fades_in_over_one_day() -> None:
    day_sessions = [0, 0, 1]

    opacities = _plant_opacity_ramp(day_sessions, plant_index=0)

    assert opacities == ['0', PLANT_FADE_LEAD_OPACITY, '1']


def test_render_plot_timeline_svg_includes_scrubber() -> None:
    timeline = _two_day_timeline()

    svg = render_plot_timeline_svg(timeline)

    assert 'ccgarden-scrubber' in svg


def test_render_plot_timeline_svg_starts_paused_on_last_day() -> None:
    """The plot skips auto-play: it should load paused at the final day.

    Not necessary to watch a replay when the scrubber can jump anywhere
    directly -- see docs/handoffs/NARRATIVE.md.
    """
    timeline = _two_day_timeline()

    svg = render_plot_timeline_svg(timeline)

    assert 'seek(keyTimes.length - 1)' in svg
    assert 'svg.pauseAnimations();\n  seek' in svg
