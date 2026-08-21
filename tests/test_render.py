import itertools
import math
import os
import re
import subprocess
import sys
from dataclasses import replace

import pytest


from ccgarden.data import (
    CartoonBird,
    DayRing,
    DORMANCY_HALF_LIFE_DAYS,
    DORMANCY_MIN_GAP_DAYS,
    GardenData,
    GardenTimeline,
    ModelCloud,
    ModelUsageDay,
    RepoBranch,
    RepoBranchDay,
    SkillFruit,
    SkillUsageDay,
    ToolBush,
    ToolUsageDay,
)
from ccgarden.render import (
    AUTUMN_COLORS,
    BIRD_MARGIN,
    _bird_positions,
    _bird_size,
    BIRD_SIZE_MAX,
    BIRD_SIZE_MIN,
    _bird_slots,
    BIRD_TOKENS_SATURATION,
    BIRD_Y_MAX,
    BIRD_Y_MIN,
    _blend_hex,
    BRANCH_ANGLE_JITTER_DEGREES,
    _branch_bow,
    _branch_endpoint,
    _branch_length,
    BRANCH_LENGTH_MAX,
    BRANCH_LENGTH_MIN,
    BRANCH_LINES_SATURATION,
    _branch_placement,
    _branch_side,
    _bush_radius,
    _bush_x_positions,
    _cache_efficiency_flower_count,
    CLOUD_MARGIN,
    _cloud_positions,
    _cloud_radius,
    CLOUD_TOKENS_SATURATION,
    CLOUD_TREE_KEEPOUT_HALF_WIDTH,
    _cloud_y_max,
    CLOUD_Y_MAX_AT_EDGE,
    CLOUD_Y_MAX_NEAR_TREE,
    _days_away,
    DORMANT_FRAME_DWELL,
    _frame_weights,
    _fruit_color,
    _fruit_count,
    _fruit_plan,
    _fruit_radius,
    FRUIT_RADIUS_MAX,
    FRUIT_RADIUS_MIN,
    FRUIT_RIPEN_FRACTION,
    _fruit_shape,
    FRUIT_SHAPE_BODIES,
    FRUIT_SHAPES,
    FRUIT_STEM_TIP,
    FRUIT_TOTAL_MAX,
    _leaf_color,
    LEAF_COLORS,
    _leaf_opacity,
    LEAF_OPACITY_DORMANT,
    LEAF_OPACITY_LIVING,
    LEAF_PAINT_ID,
    LEAVES_PER_SESSION,
    LEGEND_BAND_BOTTOM,
    LEGEND_GRID_ROWS,
    LEGEND_LINE_HEIGHT,
    LEGEND_ROWS,
    _Limb,
    _limb_counts,
    _limb_lead_weight,
    LIMB_MAX_SHARE,
    LIMB_SHARE_FALLOFF,
    _limb_share_of,
    LIVING_CANOPY_STOPS,
    LIVING_GROUND_STOPS,
    MAX_BIRDS,
    MAX_BUSHES,
    MAX_LIMBS_PER_REPO,
    MAX_SUNFLOWERS,
    MIN_LIMBS,
    NIGHT_VEIL_MAX_OPACITY,
    NIGHTNESS_SATURATION,
    _plan_limbs,
    RAIN_DROP_COUNT,
    _rain_field,
    RAIN_FULL_DAYS,
    _rain_intensity,
    RAIN_MAX_OPACITY,
    RAIN_MIN_INTENSITY,
    RAIN_ONSET_DAYS,
    _rain_opacity,
    RECOVERY_FRAME_DWELL,
    _render_rain,
    render_svg,
    render_timeline_svg,
    _saturated_nightness,
    _sky_body_opacities,
    STAR_COUNT,
    _star_field,
    STORM_GUST_COUNT,
    STORM_LEAF_COUNT,
    _storm_opacity,
    STORM_SCUD_COUNT,
    _sun_day_values,
    SUN_HALO_RADIUS_FACTOR,
    _sun_position,
    _sun_radius,
    SUN_STORM_MIN_OPACITY,
    _sun_storm_opacity,
    _sun_sweep_x,
    SUN_TOKENS_SATURATION,
    SUN_X_END,
    SUN_X_START,
    SUNFLOWER_BAND_WIDTH,
    _sunflower_height,
    SUNFLOWER_MARGIN,
    _sunflower_x_positions,
    _timeline_duration,
    TIMELINE_VIEWBOX_HEIGHT,
    TRUNK_BASE_HALF_WIDTH_MIN,
    TRUNK_CENTER_X,
    VIEWBOX_HEIGHT,
    VIEWBOX_WIDTH,
    _weighted_key_times,
    _wind_style,
)


def timeline_with_tools_and_cache(
    *,
    tool_counts_by_day: dict[str, list[int]],
    cache_read_by_day: list[int],
    cache_write_by_day: list[int],
) -> GardenTimeline:
    day_count = len(cache_read_by_day)
    days = [f'2026-07-{20 + i}' for i in range(day_count)]
    tool_days = {
        tool: [
            ToolUsageDay(day=day, count=count)
            for day, count in zip(days, counts, strict=True)
        ]
        for tool, counts in tool_counts_by_day.items()
    }

    cumulative_read = []
    cumulative_write = []
    running_read = running_write = 0
    for read, write in zip(cache_read_by_day, cache_write_by_day, strict=True):
        running_read += read
        running_write += write
        cumulative_read.append(running_read)
        cumulative_write.append(running_write)

    return GardenTimeline(
        days=days,
        daily_sessions=[1] * day_count,
        cumulative_sessions=list(range(1, day_count + 1)),
        branch_order=[],
        branch_days={},
        cache_read_tokens=cumulative_read[-1] if cumulative_read else 0,
        cache_write_tokens=cumulative_write[-1] if cumulative_write else 0,
        cumulative_cache_read=cumulative_read,
        cumulative_cache_write=cumulative_write,
        tool_order=list(tool_counts_by_day),
        tool_days=tool_days,
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


def test_render_svg_wraps_content_in_svg_tag() -> None:
    garden = GardenData(
        rings=[ring('2026-07-26')], branches=[branch('dotfiles')]
    )

    svg = render_svg(garden)

    assert svg.strip().startswith('<svg')
    assert svg.strip().endswith('</svg>')
    assert 'viewBox' in svg


def test_render_svg_empty_garden_still_renders_bare_trunk() -> None:
    garden = GardenData(rings=[], branches=[])

    svg = render_svg(garden)

    assert svg.strip().startswith('<svg')
    assert 'class="trunk"' in svg
    assert svg.count('class="ring"') == 0
    assert svg.count('class="branch"') == 0
    assert svg.count('class="leaf"') == 0


@pytest.mark.parametrize('ring_count', [1, 3, 5])
def test_render_svg_draws_one_ring_per_day(ring_count: int) -> None:
    rings = [ring(f'2026-07-{26 + i}') for i in range(ring_count)]
    garden = GardenData(rings=rings, branches=[])

    svg = render_svg(garden)

    assert svg.count('class="ring"') == ring_count


def test_the_rings_grow_with_the_trunk_they_sit_in() -> None:
    """A ring is a slice of the trunk, so it can't outgrow it.

    The rings are drawn once at the trunk's final width, so without a
    matching scale the first ring appears full width across a sapling.
    """
    timeline = GardenTimeline(
        days=['2026-07-20', '2026-07-21', '2026-07-22'],
        daily_sessions=[1, 20, 200],
        cumulative_sessions=[1, 21, 221],
        branch_order=[],
        branch_days={},
    )

    svg = render_timeline_svg(timeline)

    first_ring = svg.index('class="ring"')
    rings = svg[first_ring:]
    # The rings share one scale, on the group that wraps them.
    scale = [
        match
        for match in re.finditer(r'type="scale"[^>]*values="([^"]+)"', svg)
        if match.start() < first_ring
    ][-1]
    values = scale.group(1).split(';')
    factors = [float(value.split()[0]) for value in values]
    assert factors == sorted(factors)
    assert factors[0] < factors[-1]
    assert factors[-1] == pytest.approx(1.0)
    # The x scale must not squash the rings vertically off their trunk row.
    assert all(value.split()[1] == '1' for value in values)
    assert 'type="scale"' not in rings


@pytest.mark.parametrize('repo_count', [1, 3, 5, 9])
def test_render_svg_draws_a_limb_for_every_repo(repo_count: int) -> None:
    branches = [branch(f'repo-{i}') for i in range(repo_count)]
    garden = GardenData(rings=[], branches=branches)

    svg = render_svg(garden)

    # Never fewer limbs than repos, and never a skeleton too sparse to read
    # as a tree -- a one-repo garden is still a crown, not a pole.
    assert svg.count('class="branch"') == max(repo_count, MIN_LIMBS)
    for index in range(repo_count):
        assert f'data-repo="repo-{index}"' in svg


@pytest.mark.parametrize('sessions', [3, 40, 600])
def test_render_svg_leaf_count_scales_uncapped_with_sessions(
    sessions: int,
) -> None:
    garden = GardenData(
        rings=[], branches=[branch('dotfiles', sessions=sessions)]
    )

    svg = render_svg(garden)

    assert svg.count('class="leaf"') == sessions * LEAVES_PER_SESSION


def test_render_svg_leaf_positions_are_deterministic_across_renders() -> None:
    garden = GardenData(rings=[], branches=[branch('dotfiles', sessions=10)])

    first = render_svg(garden)
    second = render_svg(garden)

    assert first == second


@pytest.mark.parametrize(
    ('cache_read', 'cache_write', 'expected'),
    [
        (0, 0, 0),
        (100, 0, 0),
        (199, 100, 2),
        (260, 100, 3),
        (1000, 100, 10),
    ],
)
def test_cache_efficiency_flower_count_rounds_to_nearest_whole_ratio(
    cache_read: int, cache_write: int, expected: int
) -> None:
    assert _cache_efficiency_flower_count(cache_read, cache_write) == expected


def test_render_svg_draws_one_flower_per_whole_cache_efficiency_ratio() -> (
    None
):
    garden = GardenData(
        rings=[],
        branches=[],
        tools=[ToolBush(tool='Bash', count=50)],
        cache_read_tokens=500,
        cache_write_tokens=100,
    )

    svg = render_svg(garden)

    assert svg.count('class="flower"') == 5


def test_render_svg_draws_no_flowers_without_cache_writes() -> None:
    garden = GardenData(
        rings=[],
        branches=[],
        tools=[ToolBush(tool='Bash', count=50)],
        cache_read_tokens=500,
        cache_write_tokens=0,
    )

    svg = render_svg(garden)

    assert svg.count('class="flower"') == 0


def test_render_svg_draws_no_flowers_without_bushes() -> None:
    garden = GardenData(
        rings=[],
        branches=[],
        tools=[],
        cache_read_tokens=500,
        cache_write_tokens=100,
    )

    svg = render_svg(garden)

    assert svg.count('class="flower"') == 0


@pytest.mark.parametrize('model_count', [1, 2, 4])
def test_render_svg_draws_one_cloud_per_model(model_count: int) -> None:
    models = [
        ModelCloud(
            model=f'model-{i}', output_tokens=100_000, input_tokens=1_000
        )
        for i in range(model_count)
    ]
    garden = GardenData(rings=[], branches=[], model_efforts=models)

    svg = render_svg(garden)

    assert svg.count('class="cloud"') == model_count


def test_bush_x_positions_are_scattered_not_sorted_left_to_right() -> None:
    # Tools are always passed in biggest-first order, so if slots were
    # handed out in that same order the largest bush would always land
    # leftmost -- positions must be shuffled instead.
    positions = _bush_x_positions(6)

    assert positions != sorted(positions)


def test_bush_x_positions_are_deterministic_across_calls() -> None:
    assert _bush_x_positions(6) == _bush_x_positions(6)


def test_cloud_positions_are_scattered_not_sorted_left_to_right() -> None:
    positions = _cloud_positions(6)

    assert positions != sorted(positions)


def test_cloud_positions_are_deterministic_across_calls() -> None:
    assert _cloud_positions(6) == _cloud_positions(6)


def test_cloud_positions_avoid_the_column_the_tree_grows_into() -> None:
    for count in range(1, 13):
        for x, _ in _cloud_positions(count):
            assert abs(x - TRUNK_CENTER_X) >= CLOUD_TREE_KEEPOUT_HALF_WIDTH


def test_cloud_positions_hang_lower_the_further_from_the_tree() -> None:
    near = TRUNK_CENTER_X + CLOUD_TREE_KEEPOUT_HALF_WIDTH
    edge = VIEWBOX_WIDTH - CLOUD_MARGIN

    assert _cloud_y_max(near) == CLOUD_Y_MAX_NEAR_TREE
    assert _cloud_y_max(edge) == CLOUD_Y_MAX_AT_EDGE


def test_render_svg_draws_no_clouds_without_models() -> None:
    garden = GardenData(rings=[], branches=[], models=[])

    svg = render_svg(garden)

    assert svg.count('class="cloud"') == 0


def test_cloud_radius_grows_with_total_tokens() -> None:
    assert _cloud_radius(0) < _cloud_radius(1_000) < _cloud_radius(5_000_000)


@pytest.mark.parametrize('tool_count', [1, 2, 4])
def test_render_svg_draws_one_bush_per_tool(tool_count: int) -> None:
    tools = [ToolBush(tool=f'tool-{i}', count=50) for i in range(tool_count)]
    garden = GardenData(rings=[], branches=[], tools=tools)

    svg = render_svg(garden)

    assert svg.count('class="bush"') == tool_count


def test_render_svg_draws_no_bushes_without_tools() -> None:
    garden = GardenData(rings=[], branches=[], tools=[])

    svg = render_svg(garden)

    assert svg.count('class="bush"') == 0


def test_bush_radius_grows_with_tool_count() -> None:
    assert _bush_radius(0) < _bush_radius(10) < _bush_radius(1_000)


def test_render_svg_caps_bushes_at_max_bushes() -> None:
    tools = [
        ToolBush(tool=f'tool-{i}', count=50) for i in range(MAX_BUSHES + 5)
    ]
    garden = GardenData(rings=[], branches=[], tools=tools)

    svg = render_svg(garden)

    assert svg.count('class="bush"') == MAX_BUSHES


def timeline_with_sunflowers(
    prompts_by_day: dict[str, list[int]],
) -> GardenTimeline:
    day_count = len(next(iter(prompts_by_day.values())))
    days = [f'2026-07-{20 + i}' for i in range(day_count)]
    return GardenTimeline(
        days=days,
        daily_sessions=[1] * day_count,
        cumulative_sessions=list(range(1, day_count + 1)),
        branch_order=list(prompts_by_day),
        branch_days={
            repo: [
                RepoBranchDay(
                    day=day,
                    sessions=1,
                    lines_added=10,
                    lines_removed=1,
                    output_tokens=100,
                    input_tokens=10,
                    cost=0.1,
                    prompts=prompts,
                )
                for day, prompts in zip(days, counts, strict=True)
            ]
            for repo, counts in prompts_by_day.items()
        },
    )


def sunflower_branch(repo: str, *, prompts: int) -> RepoBranch:
    return RepoBranch(
        repo=repo,
        sessions=1,
        lines_added=100,
        lines_removed=10,
        output_tokens=1000,
        input_tokens=100,
        cost=1.0,
        prompts=prompts,
    )


@pytest.mark.parametrize('repo_count', [1, 2, 5])
def test_render_svg_draws_one_sunflower_per_repo(repo_count: int) -> None:
    branches = [
        sunflower_branch(f'repo-{i}', prompts=50) for i in range(repo_count)
    ]
    garden = GardenData(rings=[], branches=branches)

    svg = render_svg(garden)

    assert svg.count('class="sunflower"') == repo_count


def test_render_svg_draws_no_sunflower_for_a_repo_without_prompts() -> None:
    garden = GardenData(
        rings=[],
        branches=[
            sunflower_branch('quiet', prompts=0),
            sunflower_branch('busy', prompts=10),
        ],
    )

    svg = render_svg(garden)

    assert svg.count('class="sunflower"') == 1
    assert 'busy — 10 prompts' in svg
    assert 'quiet' not in svg.split('class="sunflower"')[1]


def test_render_svg_caps_sunflowers_at_max_sunflowers() -> None:
    branches = [
        sunflower_branch(f'repo-{i}', prompts=50)
        for i in range(MAX_SUNFLOWERS + 4)
    ]
    garden = GardenData(rings=[], branches=branches)

    svg = render_svg(garden)

    assert svg.count('class="sunflower"') == MAX_SUNFLOWERS


def test_render_svg_keeps_the_tallest_sunflowers_when_capped() -> None:
    branches = [
        sunflower_branch(f'repo-{i}', prompts=i + 1)
        for i in range(MAX_SUNFLOWERS + 2)
    ]
    garden = GardenData(rings=[], branches=branches)

    svg = render_svg(garden)

    # repo-0 and repo-1 have the fewest prompts, so they lose their slot.
    assert 'repo-0 — 1 prompts' not in svg
    assert 'repo-1 — 2 prompts' not in svg
    assert f'repo-{MAX_SUNFLOWERS + 1} — {MAX_SUNFLOWERS + 2} prompts' in svg


def test_sunflower_height_grows_with_prompts() -> None:
    assert _sunflower_height(0) < _sunflower_height(100)
    assert _sunflower_height(100) < _sunflower_height(5_000)


def test_sunflowers_are_planted_in_the_flank_bands() -> None:
    # The whole point of the sunflowers is the empty ground either side of
    # the tree -- a slot drifting in toward the trunk would defeat it.
    left_edge = SUNFLOWER_MARGIN
    left_inner = SUNFLOWER_MARGIN + SUNFLOWER_BAND_WIDTH
    right_inner = VIEWBOX_WIDTH - left_inner
    right_edge = VIEWBOX_WIDTH - SUNFLOWER_MARGIN

    for count in range(1, MAX_SUNFLOWERS + 1):
        for x in _sunflower_x_positions(count):
            assert left_edge <= x <= left_inner or right_inner <= x <= (
                right_edge
            )


def test_sunflowers_alternate_between_the_two_flank_bands() -> None:
    positions = _sunflower_x_positions(4)

    sides = [x > TRUNK_CENTER_X for x in positions]
    assert sides == [False, True, False, True]


def test_render_timeline_svg_sunflower_carries_per_day_prompt_totals() -> None:
    timeline = timeline_with_sunflowers({'ccgarden': [2, 5, 9]})

    svg = render_timeline_svg(timeline)

    group = svg.split('class="sunflower"')[1].split('</g>')[0]
    assert 'ccgarden — 2 prompts' in group
    assert 'ccgarden — 5 prompts' in group
    assert 'ccgarden — 9 prompts' in group


def test_render_timeline_svg_grows_sunflowers_out_of_the_ground() -> None:
    timeline = timeline_with_sunflowers({'ccgarden': [1, 500, 1500]})

    svg = render_timeline_svg(timeline)

    block = svg.split('class="sunflower"')[1]
    scales = [float(value) for value in _animate_values(block, 'transform')]
    assert scales == sorted(scales)
    assert scales[-1] == pytest.approx(1.0)


def _flower_blocks(svg: str) -> list[str]:
    return re.findall(r'<g class="flower".*?</g>', svg, re.DOTALL)


def _animate_values(block: str, attribute: str) -> list[str]:
    match = re.search(
        rf'attributeName="{attribute}"[^>]*values="([^"]*)"', block
    )
    assert match is not None
    return match.group(1).split(';')


def test_render_timeline_svg_draws_no_flowers_without_bushes() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={},
        cache_read_by_day=[100, 200],
        cache_write_by_day=[10, 20],
    )

    svg = render_timeline_svg(timeline)

    assert svg.count('class="flower"') == 0


def test_render_timeline_svg_flowers_track_bush_growth_not_final_size() -> (
    None
):
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [0, 600]},
        cache_read_by_day=[100, 100],
        cache_write_by_day=[0, 20],
    )

    svg = render_timeline_svg(timeline)

    blocks = _flower_blocks(svg)
    assert blocks
    translate_values = _animate_values(blocks[0], 'transform')
    first_y = float(translate_values[0].split(',')[1])
    final_y = float(translate_values[-1].split(',')[1])

    # The bush starts at its minimum radius and grows to its full size, so
    # a flower riding it should sit much lower on day one than on the final
    # day -- not already up at its resting height from the start.
    assert abs(final_y - first_y) > 5


def test_render_timeline_svg_flowers_fade_in_as_cache_efficiency_grows() -> (
    None
):
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [50, 50, 50, 50]},
        cache_read_by_day=[0, 20, 40, 60],
        cache_write_by_day=[10, 10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    assert svg.count('class="flower"') == 3
    blocks = _flower_blocks(svg)
    first_flower_opacity = _animate_values(blocks[0], 'opacity')

    # The cache-efficiency ratio only reaches 1 on day two, so the first
    # flower shouldn't be visible on day one -- it should fade in partway
    # through the timeline instead of existing from the very first frame.
    assert first_flower_opacity[0] == '0'
    assert '1' in first_flower_opacity


def test_render_svg_includes_tap_tooltip_layer() -> None:
    garden = GardenData(
        rings=[], branches=[], tools=[ToolBush(tool='Bash', count=50)]
    )

    svg = render_svg(garden)

    assert 'id="ccgarden-tooltip"' in svg
    assert 'id="ccgarden-tooltip-text"' in svg


def test_render_timeline_svg_includes_tap_tooltip_layer() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    assert 'id="ccgarden-tooltip"' in svg
    # The tooltip has to paint over the garden, so it must be the last
    # thing in the document -- an earlier layer would be drawn under the
    # bushes and clouds it describes.
    assert svg.index('id="ccgarden-tooltip"') > svg.index('class="bush"')


def test_tap_tooltip_ignores_the_scrubber_subtree() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    # Tapping the time-travel slider must keep scrubbing rather than
    # popping a tooltip over the control the tap was aimed at.
    walk_up = svg.split('function findTooltip')[1].split('function ')[0]
    assert 'node.id === "ccgarden-scrubber"' in walk_up
    assert 'return null' in walk_up


def test_tap_tooltip_clamps_to_the_timeline_viewbox_height() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    # The timeline SVG is taller than the static one (it carries the
    # scrubber strip); clamping against the short height would push
    # tooltips off the bottom of the garden.
    assert f'var viewHeight = {TIMELINE_VIEWBOX_HEIGHT:.1f};' in svg


def test_render_timeline_svg_starts_every_shape_at_nothing() -> None:
    # A leading day with no data at all -- the empty day 0 the timeline
    # loader prepends. Every shape has to open the animation at zero
    # rather than at its minimum size.
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [0, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[0, 10, 10],
    )
    timeline = replace(
        timeline,
        daily_sessions=[0, 1, 1],
        cumulative_sessions=[0, 1, 2],
        cumulative_total_tokens=[0, 100, 300],
    )

    svg = render_timeline_svg(timeline)

    bush_scale = _first_values(svg.split('class="bush"')[1], 'scale')
    assert bush_scale[0] == '0.0000'
    sun_scale = _first_values(svg.split('class="sun"')[1], 'scale')
    assert sun_scale[0] == '0.0000'
    # The trunk's own animation only carries width -- height comes from
    # the ground-hinged growth scale, which is what holds it to nothing
    # on the seed day.
    tree_scale = _first_values(svg.split('class="tree-growth"')[1], 'scale')
    assert tree_scale[0] == '0.0000 0.0000'
    assert tree_scale[-1] == '1.0000 1.0000'
    trunk = svg.split('class="trunk"')[1]
    trunk_d = _first_values(trunk, 'd')
    assert f'M {TRUNK_CENTER_X - TRUNK_BASE_HALF_WIDTH_MIN:.2f},' in trunk_d[0]
    assert trunk_d[0] != trunk_d[-1]
    assert float(_first_values(trunk, 'stroke-width')[0]) > 0.0


def _first_values(fragment: str, attribute: str) -> list[str]:
    """The `values` list of `fragment`'s first animation of `attribute`."""
    marker = (
        f'type="{attribute}"'
        if attribute in {'scale', 'translate'}
        else f'attributeName="{attribute}"'
    )
    tag = fragment.split(marker)[1].split('/>', maxsplit=1)[0]
    return tag.split('values="')[1].split('"')[0].split(';')


def test_render_timeline_svg_bush_carries_per_day_tooltip_data() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    bush_group = svg.split('class="bush"')[1].split('</g>')[0]
    assert 'Bash — used 10 times' in bush_group
    assert 'Bash — used 20 times' in bush_group
    assert 'Bash — used 30 times' in bush_group


def test_render_timeline_svg_trunk_carries_per_day_session_totals() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    trunk_group = svg.split('class="trunk-group"')[1].split('</g>')[0]
    assert 'Trunk — 1 total sessions' in trunk_group
    assert 'Trunk — 2 total sessions' in trunk_group
    assert 'Trunk — 3 total sessions' in trunk_group


def test_render_timeline_svg_cache_flowers_carry_per_day_ratios() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[10, 10, 10],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    flowers_group = svg.split('class="flowers"')[1].split('>', 1)[0]
    assert '10 cache reads per 10 cache writes' in flowers_group
    assert '20 cache reads per 20 cache writes' in flowers_group
    assert '30 cache reads per 30 cache writes' in flowers_group


def test_tap_tooltip_reads_day_index_from_the_smil_clock() -> None:
    timeline = timeline_with_tools_and_cache(
        tool_counts_by_day={'Bash': [10, 20, 30]},
        cache_read_by_day=[0, 10, 20],
        cache_write_by_day=[10, 10, 10],
    )

    svg = render_timeline_svg(timeline)

    assert 'function currentDayIndex' in svg
    assert 'svg.getCurrentTime()' in svg
    # Dynamic (per-day) elements must win over a static <title>, and mouse
    # hover -- not just touch -- has to pick it up, since a native
    # `<title>` can never be kept in sync with the scrub position.
    assert 'found.dynamic' in svg
    assert 'pointermove' in svg


def test_static_garden_tap_tooltip_has_no_day_sync_data() -> None:
    garden = GardenData(
        rings=[], branches=[], tools=[ToolBush(tool='Bash', count=50)]
    )

    svg = render_svg(garden)

    assert "data-tt='" not in svg


def sky_group_extent(
    svg: str, class_name: str
) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) of every point in `class_name` groups.

    Each sky group is a `<g class="..." transform="translate(cx,cy)">` wrapping
    shapes whose own coordinates are relative to that origin, so the group's
    translate has to be added back on to get viewBox-space extents.
    """
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')
    groups = re.findall(
        rf'<g class="{class_name}".*?</g></g>', svg, flags=re.DOTALL
    )
    assert groups, f'no {class_name} groups found in svg'
    for group in groups:
        offsets = re.findall(
            r'transform="translate\((-?[\d.]+),(-?[\d.]+)\)"', group
        )
        assert offsets, f'{class_name} group has no translate'
        origin_x, origin_y = (float(v) for v in offsets[0])

        points = []
        for path_d in re.findall(r' d="([^"]+)"', group):
            coords = re.findall(r'(-?[\d.]+),(-?[\d.]+)', path_d)
            points.extend((float(x), float(y)) for x, y in coords)
        # `<circle r="...">` (the sun's disc and halo) carries no explicit
        # center, so it sits on the group origin and reaches `r` each way.
        for radius in re.findall(r'<circle r="([\d.]+)"', group):
            r = float(radius)
            points.extend([(-r, -r), (r, r)])
        assert points, f'{class_name} group has no drawable points'

        for x, y in points:
            min_x = min(min_x, origin_x + x)
            max_x = max(max_x, origin_x + x)
            min_y = min(min_y, origin_y + y)
            max_y = max(max_y, origin_y + y)
    return min_x, min_y, max_x, max_y


def saturated_garden(model_count: int) -> GardenData:
    """A garden whose sun and every cloud are at their maximum size."""
    models = [
        ModelCloud(
            model=f'claude-opus-5[{effort}]',
            output_tokens=CLOUD_TOKENS_SATURATION,
            input_tokens=CLOUD_TOKENS_SATURATION,
        )
        for effort in ('max', 'xhigh', 'high', 'medium', 'low')[:model_count]
    ]
    return GardenData(
        rings=[],
        branches=[],
        model_efforts=models,
        total_tokens=SUN_TOKENS_SATURATION,
    )


@pytest.mark.parametrize('model_count', [1, 2, 3, 4, 5])
def test_max_size_clouds_stay_inside_the_viewbox(model_count: int) -> None:
    svg = render_svg(saturated_garden(model_count))

    min_x, min_y, max_x, max_y = sky_group_extent(svg, 'cloud')

    assert min_x >= 0
    assert min_y >= 0
    assert max_x <= VIEWBOX_WIDTH
    assert max_y <= VIEWBOX_HEIGHT


def test_max_size_sun_stays_inside_the_viewbox() -> None:
    svg = render_svg(saturated_garden(1))

    min_x, min_y, max_x, max_y = sky_group_extent(svg, 'sun')

    assert min_x >= 0
    assert min_y >= 0
    assert max_x <= VIEWBOX_WIDTH
    assert max_y <= VIEWBOX_HEIGHT


def test_small_clouds_keep_their_original_scattered_positions() -> None:
    # The clamp must only pull in shapes that would actually overflow --
    # a small cloud sits well inside every edge, so its slot is untouched.
    expected = _cloud_positions(4)
    small = [
        ModelCloud(model=f'model-{i}', output_tokens=1_000, input_tokens=1_000)
        for i in range(4)
    ]

    svg = render_svg(GardenData(rings=[], branches=[], model_efforts=small))

    translates = re.findall(
        r'<g class="cloud">.*?'
        r'<g transform="translate\((-?[\d.]+),(-?[\d.]+)\)"',
        svg,
    )
    actual = [(float(x), float(y)) for x, y in translates]
    assert actual == [(round(x, 1), round(y, 1)) for x, y in expected]


def saturated_timeline(model_count: int) -> GardenTimeline:
    """A timeline growing to a maximum-size sun and maximum-size clouds."""
    days = ['2026-07-20', '2026-07-21', '2026-07-22']
    models = [
        f'claude-opus-5[{effort}]'
        for effort in ('max', 'xhigh', 'high', 'medium', 'low')[:model_count]
    ]
    shares = (0.1, 0.5, 1.0)
    return GardenTimeline(
        days=days,
        daily_sessions=[1] * len(days),
        cumulative_sessions=[1, 2, 3],
        branch_order=[],
        branch_days={},
        cumulative_total_tokens=[
            int(SUN_TOKENS_SATURATION * share) for share in shares
        ],
        model_effort_order=models,
        model_effort_days={
            model: [
                ModelUsageDay(
                    day=day,
                    output_tokens=int(CLOUD_TOKENS_SATURATION * share),
                    input_tokens=int(CLOUD_TOKENS_SATURATION * share),
                )
                for day, share in zip(days, shares, strict=True)
            ]
            for model in models
        },
    )


@pytest.mark.parametrize('model_count', [1, 3, 5])
def test_timeline_clouds_stay_inside_the_viewbox(model_count: int) -> None:
    svg = render_timeline_svg(saturated_timeline(model_count))

    min_x, min_y, max_x, max_y = sky_group_extent(svg, 'cloud')

    assert min_x >= 0
    assert min_y >= 0
    assert max_x <= VIEWBOX_WIDTH
    assert max_y <= TIMELINE_VIEWBOX_HEIGHT


def test_timeline_sun_stays_inside_the_viewbox_on_every_frame() -> None:
    # The sun's animated positions are separate `values` on the group's
    # translate, so every keyframe -- not just the final one -- has to fit.
    svg = render_timeline_svg(saturated_timeline(1))

    sun_group = re.search(r'<g class="sun".*?</g></g>', svg, re.DOTALL)
    assert sun_group is not None
    final_radius = _sun_radius(SUN_TOKENS_SATURATION)

    translate_values = re.search(
        r'type="translate"[^>]*values="([^"]+)"', sun_group.group(0)
    )
    scale_values = re.search(
        r'type="scale"[^>]*values="([^"]+)"', sun_group.group(0)
    )
    assert translate_values is not None
    assert scale_values is not None
    frames = zip(
        translate_values.group(1).split(';'),
        scale_values.group(1).split(';'),
        strict=True,
    )
    for frame, scale in frames:
        x, y = (float(v) for v in frame.strip().split(','))
        # The sun sweeps while it grows, so each frame has to fit at the
        # size it is on that frame, not at the final size.
        halo = final_radius * float(scale) * SUN_HALO_RADIUS_FACTOR
        assert x - halo >= 0
        assert x + halo <= VIEWBOX_WIDTH
        assert y - halo >= 0


def cartoon_birds(*savings: int) -> list[CartoonBird]:
    return [
        CartoonBird(adapter=f'adapter-{i}', calls=10, tokens_saved=saved)
        for i, saved in enumerate(savings)
    ]


def test_bird_size_grows_with_tokens_saved() -> None:
    assert _bird_size(0) == BIRD_SIZE_MIN
    assert _bird_size(1_000) < _bird_size(50_000)
    assert _bird_size(BIRD_TOKENS_SATURATION * 100) == BIRD_SIZE_MAX


def test_bird_positions_stay_in_the_open_sky_band() -> None:
    for count in range(1, MAX_BIRDS + 1):
        for x, y in _bird_positions(count):
            assert BIRD_MARGIN <= x <= VIEWBOX_WIDTH - BIRD_MARGIN
            assert BIRD_Y_MIN <= y <= BIRD_Y_MAX


def test_bird_positions_are_deterministic_across_calls() -> None:
    assert _bird_positions(9) == _bird_positions(9)


def test_birds_are_pushed_clear_of_the_sun_halo() -> None:
    sun_x, sun_y = _sun_position(SUN_TOKENS_SATURATION)
    radius = _sun_radius(SUN_TOKENS_SATURATION)
    keepout = radius * SUN_HALO_RADIUS_FACTOR

    slots = _bird_slots(
        cartoon_birds(*([BIRD_TOKENS_SATURATION] * MAX_BIRDS)),
        (sun_x, sun_y, radius),
    )

    for x, y, _size in slots:
        assert math.hypot(x - sun_x, y - sun_y) >= keepout


def test_render_svg_draws_one_bird_per_cartoon_adapter() -> None:
    garden = GardenData(
        rings=[ring('2026-07-26')],
        branches=[branch('ccgarden')],
        birds=cartoon_birds(5_000, 60_000, 900),
        cartoon_since='7d',
    )

    svg = render_svg(garden)

    assert svg.count('class="bird"') == 3
    assert 'adapter-1 — 60,000 tokens saved over 10 calls (last 7d)' in svg


def test_render_svg_caps_the_flock() -> None:
    garden = GardenData(
        rings=[],
        branches=[],
        birds=cartoon_birds(*range(1_000, 1_000 + MAX_BIRDS + 5)),
    )

    assert render_svg(garden).count('class="bird"') == MAX_BIRDS


def test_render_svg_without_cartoon_draws_no_birds_and_no_legend_entry() -> (
    None
):
    # Cartoon is an optional external tool: a machine without it renders a
    # garden with an empty sky, not an error and not a key to a missing
    # shape.
    garden = GardenData(rings=[ring('2026-07-26')], branches=[], birds=[])

    svg = render_svg(garden)

    assert 'class="birds"' not in svg
    assert '>Birds<' not in svg


def test_render_svg_with_cartoon_adds_the_birds_legend_entry() -> None:
    garden = GardenData(rings=[], branches=[], birds=cartoon_birds(5_000))

    assert '>Birds<' in render_svg(garden)


def timeline_with_birds(birds: list[CartoonBird]) -> GardenTimeline:
    days = ['2026-07-20', '2026-07-21', '2026-07-22']
    return GardenTimeline(
        days=days,
        daily_sessions=[1] * len(days),
        cumulative_sessions=[1, 2, 3],
        branch_order=[],
        branch_days={},
        birds=birds,
        cartoon_since='7d',
    )


def test_render_timeline_svg_drifts_the_flock_without_growing_it() -> None:
    # Cartoon only reports a since-window snapshot, so there is no per-day
    # history to replay -- the birds may fly, but must not fake growth.
    timeline = timeline_with_birds(cartoon_birds(5_000, 60_000))

    svg = render_timeline_svg(timeline)

    flock = svg.split('class="birds"')[1].split('class="tree-growth"')[0]
    assert svg.count('class="bird"') == 2
    # Per bird: the @keyframes, its class rule, the animation: reference, and
    # the class on the element itself.
    assert flock.count('bird-drift-') == 8
    assert 'translate(' in flock
    assert 'type="scale"' not in flock
    assert 'adapter-0 — 5,000 tokens saved over 10 calls (last 7d)' in svg


def test_render_timeline_svg_drifts_the_flock_without_smil() -> None:
    # SMIL animateTransform is never composited, so a perpetually drifting
    # flock repaints the whole 3k-element document every frame and janks
    # scrolling on any page embedding the SVG. CSS transforms can be.
    timeline = timeline_with_birds(cartoon_birds(5_000, 60_000))

    svg = render_timeline_svg(timeline)

    assert 'repeatCount="indefinite"' not in svg
    flock = svg.split('class="birds"')[1].split('class="tree-growth"')[0]
    assert '<animateTransform' not in flock
    assert 'animation:bird-drift-0' in svg
    assert '@keyframes bird-drift-0' in svg


def test_render_timeline_svg_flock_honors_reduced_motion() -> None:
    timeline = timeline_with_birds(cartoon_birds(5_000, 60_000))

    svg = render_timeline_svg(timeline)

    assert '@media (prefers-reduced-motion:reduce)' in svg


def test_render_timeline_svg_without_cartoon_draws_no_birds() -> None:
    svg = render_timeline_svg(timeline_with_birds([]))

    assert 'class="birds"' not in svg
    assert '>Birds<' not in svg


def test_branch_placement_puts_the_longest_branch_lowest() -> None:
    count = 6
    ys = [
        _branch_placement(index, count, f'repo{index}', 20.0).origin_y
        for index in range(count)
    ]

    # Branches arrive longest-first, and origin_y grows downwards, so the
    # heights must descend: longest at the base, stubs in the crown.
    assert ys == sorted(ys, reverse=True)


def test_branch_placement_jitters_height_but_keeps_order() -> None:
    count = 6
    placements = [
        _branch_placement(index, count, f'repo{index}', 20.0)
        for index in range(count)
    ]

    ys = [placement.origin_y for placement in placements]
    assert ys == sorted(ys, reverse=True)
    # Jitter, not an even ladder: no two gaps come out the same.
    gaps = [round(b - a, 3) for a, b in itertools.pairwise(ys)]
    assert len(set(gaps)) == len(gaps)
    for placement in placements:
        assert abs(placement.angle_jitter) <= BRANCH_ANGLE_JITTER_DEGREES


def test_branch_placement_is_deterministic_per_repo() -> None:
    first = _branch_placement(2, 5, 'ccgarden', 20.0)
    second = _branch_placement(2, 5, 'ccgarden', 20.0)

    assert first == second
    assert _branch_placement(2, 5, 'other', 20.0) != first


@pytest.mark.parametrize('side', [-1, 1])
def test_long_branches_droop_towards_horizontal(side: int) -> None:
    def pitch(length: float) -> float:
        end_x, end_y = _branch_endpoint(400.0, 500.0, length, side, 0.5)
        return math.degrees(math.atan2(500.0 - end_y, abs(end_x - 400.0)))

    assert pitch(BRANCH_LENGTH_MAX) < pitch(BRANCH_LENGTH_MAX * 0.2)


@pytest.mark.parametrize('side', [-1, 1])
def test_branch_endpoint_stays_on_its_own_side(side: int) -> None:
    end_x, _ = _branch_endpoint(
        400.0, 500.0, BRANCH_LENGTH_MAX, side, 1.0, angle_jitter=8.0
    )

    assert (end_x - 400.0) * side > 0


def test_branch_bow_sags_harder_as_a_branch_lengthens() -> None:
    short = _branch_bow(BRANCH_LENGTH_MAX * 0.2, 1, 0.5)
    long = _branch_bow(BRANCH_LENGTH_MAX, 1, 0.5)

    assert 0 < short < long
    # Both flanks sag, so the sign follows `side`.
    assert _branch_bow(BRANCH_LENGTH_MAX, -1, 0.5) == -long


def test_branch_length_compresses_the_dominant_repo() -> None:
    small = _branch_length(600)
    large = _branch_length(6000)

    # 10x the lines must still read as clearly longer...
    assert large > small * 1.5
    # ...but not so much longer that it owns the whole crown, which is what
    # the old power curve did.
    assert large < small * 2.5


def test_branch_length_is_monotonic_and_bounded() -> None:
    lengths = [
        _branch_length(lines)
        for lines in (0, 100, 500, 2_000, BRANCH_LINES_SATURATION, 10**6)
    ]

    assert lengths == sorted(lengths)
    assert lengths[0] == pytest.approx(BRANCH_LENGTH_MIN)
    assert lengths[-1] == pytest.approx(BRANCH_LENGTH_MAX)
    # Saturation is a cap, not a cliff.
    assert lengths[-1] == pytest.approx(lengths[-2])


def test_nightness_saturates_rather_than_scaling_linearly() -> None:
    # A modest evening habit still shows, but a night owl maxes out.
    assert _saturated_nightness(0.0) == 0.0
    assert 0 < _saturated_nightness(0.1) < 1
    assert _saturated_nightness(NIGHTNESS_SATURATION) == pytest.approx(1.0)
    # Saturation is a cap, not a cliff.
    assert _saturated_nightness(0.99) == pytest.approx(1.0)


def test_a_daylit_garden_draws_no_night() -> None:
    svg = render_svg(GardenData(rings=[], branches=[], nightness=0.0))

    assert 'class="night"' in svg
    assert 'opacity="0.000"' in svg
    # No night to explain means no key entry for it.
    assert 'darkens with prompts' not in svg


def test_a_night_garden_darkens_and_gets_a_legend_entry() -> None:
    svg = render_svg(
        GardenData(
            rings=[],
            branches=[],
            nightness=1.0,
            hour_counts={2: 10},
        )
    )

    assert f'opacity="{NIGHT_VEIL_MAX_OPACITY:.3f}"' in svg
    assert 'darkens with prompts' in svg
    assert 'busiest hour 02:00' in svg


def test_the_night_veil_never_swallows_other_tooltips() -> None:
    svg = render_svg(GardenData(rings=[], branches=[], nightness=1.0))

    veil = re.search(r'<rect class="night"[^>]*>', svg)
    assert veil is not None
    assert 'pointer-events="none"' in veil.group(0)


def test_the_veil_stops_above_the_legend_band() -> None:
    svg = render_svg(GardenData(rings=[], branches=[], nightness=1.0))

    veil = re.search(r'<rect class="night"[^>]*>', svg)
    assert f'height="{VIEWBOX_HEIGHT}"' in veil.group(0)


def legend_label_positions(svg: str) -> dict[str, tuple[float, float]]:
    labels = {label for label, _, _ in LEGEND_ROWS}
    found = {}
    for match in re.finditer(
        r'<text x="([\d.]+)" y="([\d.]+)"[^>]*font-weight="bold"[^>]*>'
        r'([^<]+)</text>',
        svg,
    ):
        if match.group(3) in labels:
            found[match.group(3)] = (
                float(match.group(1)),
                float(match.group(2)),
            )
    return found


def test_the_legend_icons_hold_still() -> None:
    """The icons are the garden's own renderers, wind and all.

    A key is a table, not a scene -- a drifting cloud in a legend cell is
    just a distraction, so the band cancels the idle motion its icons
    inherit.
    """
    svg = render_svg(GardenData(rings=[], branches=[]))

    assert '.legend [class*="ccg-"]{animation:none}' in svg
    legend = svg[svg.index('<g class="legend">') :]
    assert '<animate' not in legend


def test_legend_columns_line_up_across_rows() -> None:
    # A short last row used to be centred, which put its text on top of the
    # dividers drawn for the rows above it.
    svg = render_svg(GardenData(rings=[], branches=[]))

    positions = legend_label_positions(svg)
    rows: dict[float, set[float]] = {}
    for x, y in positions.values():
        rows.setdefault(y, set()).add(x)
    assert len(rows) == LEGEND_GRID_ROWS
    columns = set.union(*rows.values())
    for row_columns in rows.values():
        assert row_columns <= columns
        assert row_columns == set(sorted(columns)[: len(row_columns)])


def test_every_legend_entry_stays_inside_the_band() -> None:
    svg = render_svg(GardenData(rings=[], branches=[]))

    bottoms = [
        y + LEGEND_LINE_HEIGHT * len(desc)
        for label, (x, y) in legend_label_positions(svg).items()
        for name, desc, _ in LEGEND_ROWS
        if name == label
    ]
    assert max(bottoms) < LEGEND_BAND_BOTTOM


def test_the_star_field_is_deterministic() -> None:
    assert _star_field() == _star_field()


def test_stars_twinkle_on_css_not_smil() -> None:
    """70 stars is 70 main-thread SMIL timelines that never settle.

    Idle motion is CSS keyframes here, and twinkle is idle motion.
    """
    timeline = GardenTimeline(
        days=['2026-01-01'],
        daily_sessions=[1],
        cumulative_sessions=[1],
        branch_order=[],
        branch_days={},
        daily_nightness=[1.0],
    )

    svg = render_timeline_svg(timeline)
    stars = re.search(r'<g class="stars".*?</g>', svg, re.S).group(0)

    assert '<animate' not in stars
    assert stars.count('class="ccg-twinkle"') == STAR_COUNT
    assert '@keyframes ccg-twinkle' in svg
    # Phase offset per star, or all 70 blink in lockstep.
    assert stars.count('animation-delay:-') == STAR_COUNT


def test_rain_falls_on_css_not_smil() -> None:
    """Same reason as the stars, and a downpour is more drops than stars."""
    svg = _render_rain(opacity=1.0)

    assert '<animateTransform' not in svg
    drops = re.findall(r'<line[^>]*class="ccg-fall"[^>]*>', svg)
    assert len(drops) == len(_rain_field())
    # Phase offset per drop, or the whole field falls as one sheet.
    assert all('animation-delay:-' in drop for drop in drops)


def test_timeline_animates_the_sky_day_by_day() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02', '2026-01-03'],
        daily_sessions=[1, 1, 1],
        cumulative_sessions=[1, 2, 3],
        branch_order=[],
        branch_days={},
        daily_nightness=[0.0, 1.0, 0.0],
    )

    svg = render_timeline_svg(timeline)

    # Stars and veil both ride the same per-day signal, dark in the middle.
    assert 'class="stars"' in svg
    assert '0.000;1.000;0.000' in svg
    assert f'0.000;{NIGHT_VEIL_MAX_OPACITY:.3f};0.000' in svg


def test_a_timeline_with_no_hour_data_draws_no_night_at_all() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02'],
        daily_sessions=[1, 1],
        cumulative_sessions=[1, 2],
        branch_order=[],
        branch_days={},
        daily_nightness=[0.0, 0.0],
    )

    svg = render_timeline_svg(timeline)

    assert 'class="stars"' not in svg
    assert 'class="night"' not in svg


def test_leaf_colour_blends_from_green_to_autumn() -> None:
    assert _leaf_color(0, 1.0) == LEAF_COLORS[0]
    assert _leaf_color(0, 0.0) == AUTUMN_COLORS[0]
    # Halfway is genuinely between the two, not one or the other.
    midway = _leaf_color(0, 0.5)
    assert midway not in (LEAF_COLORS[0], AUTUMN_COLORS[0])


def test_leaves_thin_out_as_the_garden_goes_dormant() -> None:
    assert _leaf_opacity(1.0) == pytest.approx(LEAF_OPACITY_LIVING)
    assert _leaf_opacity(0.0) == pytest.approx(LEAF_OPACITY_DORMANT)
    assert _leaf_opacity(0.5) < _leaf_opacity(1.0)


def test_blending_is_clamped_outside_the_unit_range() -> None:
    assert _blend_hex('#000000', '#ffffff', 2.0) == '#ffffff'
    assert _blend_hex('#000000', '#ffffff', -1.0) == '#000000'


def test_every_leaf_shares_a_paint_so_the_canopy_turns_at_once() -> None:
    """Thousands of leaves must not mean thousands of animations."""
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02'],
        daily_sessions=[4, 4],
        cumulative_sessions=[4, 8],
        branch_order=['repo'],
        branch_days={
            'repo': [
                RepoBranchDay('2026-01-01', 4, 100, 0, 10, 10, 0.0, 20),
                RepoBranchDay('2026-01-02', 8, 200, 0, 20, 20, 0.0, 40),
            ]
        },
        daily_vitality=[1.0, 0.1],
    )

    svg = render_timeline_svg(timeline)

    assert svg.count(f'url(#{LEAF_PAINT_ID}') > len(LEAF_COLORS)
    assert svg.count('attributeName="stop-color"') == (
        len(LEAF_COLORS) + len(LIVING_GROUND_STOPS) + len(LIVING_CANOPY_STOPS)
    )


def test_a_still_garden_is_rendered_in_the_season_it_has_reached() -> None:
    autumn = render_svg(GardenData(rings=[], branches=[], vitality=0.0))
    spring = render_svg(GardenData(rings=[], branches=[], vitality=1.0))

    assert AUTUMN_COLORS[0] in autumn
    assert LEAF_COLORS[0] in spring
    # A garden still being tended has no season to explain.
    assert 'longer you are away' in autumn
    assert 'longer you are away' not in spring


def _vitality_after(days: float) -> float:
    return 0.5 ** (days / DORMANCY_HALF_LIFE_DAYS)


@pytest.mark.parametrize(
    ('days', 'expected'),
    [
        (0.0, 0.0),
        (RAIN_ONSET_DAYS - 0.5, 0.0),
        (RAIN_ONSET_DAYS, RAIN_MIN_INTENSITY),
        (RAIN_FULL_DAYS, 1.0),
        (90.0, 1.0),
    ],
)
def test_rain_starts_only_once_a_gap_is_a_real_lapse(
    days: float, expected: float
) -> None:
    intensity = _rain_intensity(_vitality_after(days))

    assert intensity == pytest.approx(expected)


def test_the_shortest_real_lapse_already_rains_visibly() -> None:
    """`_with_dormant_days` can never hand us a gap shorter than this."""
    frame = _vitality_after(DORMANCY_MIN_GAP_DAYS // 2)

    assert _rain_intensity(frame) >= RAIN_MIN_INTENSITY


def test_rain_thickens_the_longer_the_garden_is_left() -> None:
    short = _rain_opacity(_vitality_after(3))
    long_gap = _rain_opacity(_vitality_after(8))

    assert short < long_gap <= RAIN_MAX_OPACITY


def test_days_away_inverts_the_vitality_decay() -> None:
    assert _days_away(1.0) == 0
    assert _days_away(0.5) == round(DORMANCY_HALF_LIFE_DAYS)
    assert _days_away(0.25) == round(DORMANCY_HALF_LIFE_DAYS * 2)
    # A garden long enough gone to have zero vitality has no day count.
    assert _days_away(0.0) is None


def test_a_tended_garden_never_rains() -> None:
    svg = render_svg(GardenData(rings=[], branches=[], vitality=1.0))

    assert 'class="rain"' not in svg
    assert 'you never showed up' not in svg


def test_an_abandoned_garden_rains_and_says_so() -> None:
    svg = render_svg(GardenData(rings=[], branches=[], vitality=0.1))

    assert 'class="rain"' in svg
    assert svg.count('<line') >= RAIN_DROP_COUNT
    # The lapse is named in the tooltip, and the legend explains it.
    assert 'no sessions for' in svg
    assert 'you never showed up' in svg


def test_the_overcast_wash_never_swallows_a_tooltip() -> None:
    svg = render_svg(GardenData(rings=[], branches=[], vitality=0.0))

    wash = svg.split('class="rain"')[1].split('<line')[0]
    assert 'pointer-events="none"' in wash


def test_timeline_rains_only_on_the_days_the_garden_was_left() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-15', '2026-01-16'],
        daily_sessions=[1, 0, 1],
        cumulative_sessions=[1, 1, 2],
        branch_order=[],
        branch_days={},
        daily_vitality=[1.0, 0.2, 1.0],
    )

    svg = render_timeline_svg(timeline)

    assert 'class="rain"' in svg
    assert f'0.000;{RAIN_MAX_OPACITY:.3f};0.000' in svg


def test_a_timeline_with_no_lapse_draws_no_rain() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02'],
        daily_sessions=[1, 1],
        cumulative_sessions=[1, 2],
        branch_order=[],
        branch_days={},
        daily_vitality=[1.0, 1.0],
    )

    svg = render_timeline_svg(timeline)

    assert 'class="rain"' not in svg


def test_dormant_frames_are_held_longer_than_working_days() -> None:
    key_times = _weighted_key_times([1, 1, 0, 1, 1])

    working = key_times[1] - key_times[0]
    dormant = key_times[2] - key_times[1]
    recovery = key_times[3] - key_times[2]
    assert dormant == pytest.approx(working * DORMANT_FRAME_DWELL)
    # Coming back takes about as long as going away, or the garden
    # snaps from drought to summer between two ordinary days.
    assert recovery == pytest.approx(working * RECOVERY_FRAME_DWELL)
    assert key_times[4] - key_times[3] == pytest.approx(working)
    assert key_times[0] == 0.0
    assert key_times[-1] == pytest.approx(1.0)


@pytest.mark.parametrize(
    'attribute_marker',
    ['class="rain"', 'class="stars"', 'id="leafPaint0"'],
)
def test_weather_and_season_are_eased_rather_than_ramped_linearly(
    attribute_marker: str,
) -> None:
    """These channels hold for days and then swing -- corners show."""
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-08', '2026-01-15', '2026-01-16'],
        daily_sessions=[1, 0, 0, 1],
        cumulative_sessions=[1, 1, 1, 2],
        branch_order=[],
        branch_days={},
        daily_vitality=[1.0, 0.5, 0.2, 1.0],
        daily_nightness=[0.1, 0.0, 0.0, 0.8],
    )

    svg = render_timeline_svg(timeline)
    animate = re.search(
        rf'{re.escape(attribute_marker)}.*?(<animate [^>]*>)', svg, re.S
    ).group(1)

    assert 'calcMode="spline"' in animate
    splines = re.search(r'keySplines="([^"]+)"', animate).group(1)
    key_times = re.search(r'keyTimes="([^"]+)"', animate).group(1)
    assert len(splines.split(';')) == len(key_times.split(';')) - 1


def test_growth_stays_linear_so_it_does_not_pulse_daily() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02', '2026-01-03'],
        daily_sessions=[1, 2, 3],
        cumulative_sessions=[1, 3, 6],
        branch_order=[],
        branch_days={},
    )

    svg = render_timeline_svg(timeline)
    trunk = re.search(r'class="trunk".*?(<animate [^>]*>)', svg, re.S).group(1)

    assert 'calcMode="linear"' in trunk


@pytest.mark.parametrize(
    'daily_sessions', [[], [3], [1, 1, 1], [0, 0, 0], [2, 0, 5, 0, 1]]
)
def test_key_times_stay_a_sorted_unit_interval(
    daily_sessions: list[int],
) -> None:
    key_times = _weighted_key_times(daily_sessions)

    assert len(key_times) == max(len(daily_sessions), 1)
    assert key_times == sorted(key_times)
    assert key_times[0] == 0.0
    assert key_times[-1] == pytest.approx(1.0 if len(key_times) > 1 else 0.0)


def test_a_lapse_lengthens_the_replay_rather_than_squeezing_it() -> None:
    """Dwelling on a gap must not cost the working days their time."""
    worked = [1] * 12
    lapsed = [*[1] * 11, 0]

    assert _timeline_duration(
        1.0 + sum(_frame_weights(lapsed))
    ) > _timeline_duration(1.0 + sum(_frame_weights(worked)))


def test_the_rain_gets_a_real_share_of_the_replay() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-08', '2026-01-15', '2026-01-16'],
        daily_sessions=[1, 0, 0, 1],
        cumulative_sessions=[1, 1, 1, 2],
        branch_order=[],
        branch_days={},
        daily_vitality=[1.0, 0.5, 0.2, 1.0],
    )

    svg = render_timeline_svg(timeline)

    key_times = [
        float(value)
        for value in re.search(
            r'class="rain"[^>]*>.*?keyTimes="([^"]+)"', svg, re.S
        )
        .group(1)
        .split(';')
    ]
    rainy_share = key_times[3] - key_times[1]
    assert rainy_share > 0.5


@pytest.mark.parametrize(
    'css_class',
    [
        'ccg-sway-limb',
        'ccg-sway-stalk',
        'ccg-sway-bush',
        'ccg-drift',
        'ccg-bob',
        'ccg-spin',
        'ccg-pulse',
        'ccg-flap',
        'ccg-gust',
        'ccg-tumble',
    ],
)
def test_every_wind_class_has_keyframes_and_stops_for_reduced_motion(
    css_class: str,
) -> None:
    style = _wind_style()

    assert f'@keyframes {css_class}{{' in style
    reduced = style.split('prefers-reduced-motion:reduce)')[1]
    assert f'.{css_class}' in reduced


@pytest.mark.parametrize('renderer', ['static', 'timeline'])
def test_the_sun_keeps_moving_after_it_stops_climbing(renderer: str) -> None:
    """It reaches its final height early and then has nowhere to go."""
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02'],
        daily_sessions=[1, 1],
        cumulative_sessions=[1, 2],
        branch_order=[],
        branch_days={},
        cumulative_total_tokens=[1_000, 2_000],
    )
    svg = (
        render_timeline_svg(timeline)
        if renderer == 'timeline'
        else render_svg(GardenData(rings=[], branches=[], total_tokens=2_000))
    )

    sun = svg.split('class="sun"')[1].split('</svg>')[0]
    assert 'ccg-bob' in sun
    assert 'ccg-spin' in sun
    assert 'ccg-pulse' in sun


@pytest.mark.parametrize(
    ('vitality', 'expected'),
    [
        (1.0, 1.0),
        # Half a day away is not yet weather; twelve is a downpour.
        (0.5 ** (0.5 / DORMANCY_HALF_LIFE_DAYS), 1.0),
        (0.5, SUN_STORM_MIN_OPACITY),
        (0.0, SUN_STORM_MIN_OPACITY),
    ],
)
def test_the_sun_is_swallowed_by_the_storm_and_comes_back(
    vitality: float, expected: float
) -> None:
    """Its height is frozen through a lapse; its brightness isn't."""
    assert _sun_storm_opacity(vitality) == pytest.approx(expected)


def test_the_timeline_sun_fades_rather_than_freezing_through_a_lapse() -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-08', '2026-01-16'],
        daily_sessions=[1, 0, 1],
        cumulative_sessions=[1, 1, 2],
        branch_order=[],
        branch_days={},
        cumulative_total_tokens=[1_000, 1_000, 2_000],
        daily_vitality=[1.0, 0.1, 1.0],
    )

    svg = render_timeline_svg(timeline)
    sun = svg.split('class="sun"')[1].split('</svg>')[0]
    opacity = re.search(
        r'<animate attributeName="opacity"[^>]*values="([^"]+)"', sun
    ).group(1)

    first, lapsed, last = (float(value) for value in opacity.split(';'))
    assert first == pytest.approx(1.0)
    assert lapsed < 0.5
    assert last == pytest.approx(1.0)


@pytest.mark.parametrize(
    ('progress', 'expected'),
    [
        (0.0, SUN_X_START),
        (0.5, (SUN_X_START + SUN_X_END) / 2),
        (1.0, SUN_X_END),
    ],
)
def test_the_sun_sweeps_on_replay_progress_not_on_data(
    progress: float, expected: float
) -> None:
    assert _sun_sweep_x(progress, 1.0) == pytest.approx(expected)


def test_the_sun_crosses_the_sky_even_while_the_totals_are_frozen() -> None:
    """The one channel a lapse cannot stop: it is keyed to the clock."""
    frozen = [5_000, 5_000, 5_000]
    key_times = [0.0, 0.5, 1.0]

    xs = [x for x, _, _ in _sun_day_values(frozen, 5_000, key_times)]

    assert xs[0] < xs[1] < xs[2]


def test_the_sun_travels_at_one_speed_whatever_the_data_does() -> None:
    """A lapse must not stall the climb any more than it stalls the sweep.

    Frame times are deliberately non-uniform (dormant days dwell), so the
    test measures distance per unit of replay time, not per frame.
    """
    key_times = [0.0, 0.1, 0.6, 0.8, 1.0]
    # Grows, then flatlines through a lapse, then grows again.
    tokens = [1_000, 4_000, 4_000, 4_000, 9_000]

    values = _sun_day_values(tokens, 9_000, key_times)
    speeds = [
        math.dist((x1, y1), (x2, y2)) / (t2 - t1)
        for (x1, y1, _), (x2, y2, _), t1, t2 in zip(
            values, values[1:], key_times, key_times[1:], strict=False
        )
    ]

    assert speeds == pytest.approx([speeds[0]] * len(speeds))


def test_the_moon_takes_over_from_the_sun_after_dark() -> None:
    day_sun, day_moon = _sky_body_opacities(0.0, 1.0)
    night_sun, night_moon = _sky_body_opacities(1.0, 1.0)

    assert day_sun > day_moon
    assert night_moon > night_sun
    assert day_sun + day_moon == pytest.approx(night_sun + night_moon)


def test_the_storm_dims_the_moon_as_well_as_the_sun() -> None:
    clear_sun, clear_moon = _sky_body_opacities(1.0, 1.0)
    stormy_sun, stormy_moon = _sky_body_opacities(1.0, 0.0)

    assert stormy_moon < clear_moon
    assert stormy_sun <= clear_sun


@pytest.mark.parametrize('renderer', ['static', 'timeline'])
def test_a_night_garden_draws_a_moon(renderer: str) -> None:
    timeline = GardenTimeline(
        days=['2026-01-01', '2026-01-02'],
        daily_sessions=[1, 1],
        cumulative_sessions=[1, 2],
        branch_order=[],
        branch_days={},
        cumulative_total_tokens=[1_000, 2_000],
        daily_nightness=[1.0, 1.0],
    )
    svg = (
        render_timeline_svg(timeline)
        if renderer == 'timeline'
        else render_svg(
            GardenData(
                rings=[], branches=[], total_tokens=2_000, nightness=1.0
            )
        )
    )

    moon = svg.split('class="moon-disc"')[1].split('</svg>')[0]
    assert 'url(#moonGradient)' in moon
    assert float(
        re.search(r'class="moon-disc" opacity="([\d.]+)"', svg).group(1)
    ) > float(re.search(r'class="sun-disc" opacity="([\d.]+)"', svg).group(1))


def test_the_storm_blows_harder_than_the_rain_is_wet() -> None:
    """At a short gap the rain is faint -- the wind still has to read."""
    garden = GardenData(rings=[], branches=[], vitality=0.0)

    svg = render_svg(garden)

    assert svg.count('class="ccg-gust"') == STORM_GUST_COUNT
    assert svg.count('class="ccg-tumble"') == STORM_LEAF_COUNT
    assert svg.count('class="ccg-scud"') == STORM_SCUD_COUNT
    assert 'class="storm"' in svg
    drizzle = _vitality_after(3)
    assert _storm_opacity(drizzle) > _rain_opacity(drizzle)


def test_a_tended_garden_gets_no_storm_layer_at_all() -> None:
    svg = render_svg(GardenData(rings=[], branches=[]))

    assert 'class="storm"' not in svg
    assert 'class="rain"' not in svg


def test_wind_groups_hinge_at_their_own_root_not_their_bounding_box() -> None:
    garden = GardenData(
        rings=[],
        branches=[branch('dotfiles', sessions=2)],
        tools=[ToolBush(tool='Bash', count=10)],
    )

    svg = render_svg(garden)

    for opener in re.findall(r'<g class="ccg-[a-z-]+"[^>]*>', svg):
        assert 'transform-origin:' in opener
        assert 'animation-delay:-' in opener
    assert 'transform-box:view-box' in svg


def test_the_downpour_is_deterministic() -> None:
    assert _rain_field() == _rain_field()
    assert len(_rain_field()) == RAIN_DROP_COUNT


def test_limb_counts_gives_every_repo_at_least_one_limb() -> None:
    counts = _limb_counts([9000.0, 400.0, 20.0], MIN_LIMBS)

    assert len(counts) == 3
    assert min(counts) >= 1
    assert sum(counts) >= MIN_LIMBS


@pytest.mark.parametrize(
    'weights',
    [
        [20000.0, 60.0, 40.0, 30.0, 20.0, 10.0],
        [9000.0, 400.0, 20.0],
        [5000.0],
        [float(1000 - 100 * i) for i in range(8)],
    ],
)
def test_limb_counts_leaves_no_limb_dominating_the_tree(
    weights: list[float],
) -> None:
    counts = _limb_counts(weights, MIN_LIMBS)

    leads = [
        _limb_lead_weight(weight, count)
        for weight, count in zip(weights, counts, strict=True)
    ]

    assert max(leads) <= LIMB_MAX_SHARE * sum(weights)


def test_limb_counts_splits_a_dominant_repo_past_the_minimum() -> None:
    # Enough repos to clear MIN_LIMBS on their own, but all the work is in
    # one of them -- the six-limb skeleton would be one limb and five twigs.
    counts = _limb_counts([20000.0, 60.0, 40.0, 30.0, 20.0, 10.0], MIN_LIMBS)

    assert counts[0] > 1
    assert sum(counts) > MIN_LIMBS
    assert counts[1:] == [1] * 5


def test_limb_counts_stops_splitting_a_runaway_repo() -> None:
    counts = _limb_counts([1e9, 1.0], MIN_LIMBS)

    assert max(counts) <= MAX_LIMBS_PER_REPO


def test_limb_counts_leaves_a_wide_garden_untouched() -> None:
    weights = [float(1000 - 100 * i) for i in range(MIN_LIMBS + 2)]

    assert _limb_counts(weights, MIN_LIMBS) == [1] * len(weights)


def test_limb_counts_favours_the_busiest_repo() -> None:
    counts = _limb_counts([9000.0, 400.0], MIN_LIMBS)

    assert counts[0] > counts[1]


@pytest.mark.parametrize('repo_count', [1, 2, 3, MIN_LIMBS, MIN_LIMBS + 3])
def test_plan_limbs_never_builds_a_sparse_skeleton(repo_count: int) -> None:
    repos = [(f'repo{i}', 5000.0 * 0.6**i) for i in range(repo_count)]

    limbs = _plan_limbs(repos)

    assert len(limbs) >= max(repo_count, MIN_LIMBS)
    assert len({limb.key for limb in limbs}) == len(limbs)
    for repo, _ in repos:
        shares = [limb.share for limb in limbs if limb.repo == repo]
        assert shares
        assert sum(shares) == pytest.approx(1.0)


def test_plan_limbs_orders_limbs_biggest_first() -> None:
    repos = [('big', 9000.0), ('small', 300.0)]

    limbs = _plan_limbs(repos)
    weights = [limb.share * dict(repos)[limb.repo] for limb in limbs]

    assert weights == sorted(weights, reverse=True)
    assert limbs[0].repo == 'big'


def test_plan_limbs_keeps_the_key_stable_for_an_unsplit_repo() -> None:
    repos = [(f'repo{i}', 100.0) for i in range(MIN_LIMBS)]

    assert [limb.key for limb in _plan_limbs(repos)] == [
        f'repo{i}' for i in range(MIN_LIMBS)
    ]


def test_limb_share_of_scales_every_total() -> None:
    branch = RepoBranch(
        repo='r',
        sessions=100,
        lines_added=1000,
        lines_removed=400,
        output_tokens=2000,
        input_tokens=6000,
        cost=8.0,
        prompts=500,
    )

    lower = _Limb('r#0', 'r', 0.5, 0.0)
    upper = _Limb('r#1', 'r', 0.5, 0.5)

    half = _limb_share_of(branch, lower)

    assert half.repo == 'r'
    assert (half.sessions, half.lines_added, half.prompts) == (50, 500, 250)
    assert half.cost == pytest.approx(4.0)
    assert half.sessions + _limb_share_of(branch, upper).sessions == 100
    assert _limb_share_of(branch, _Limb('r', 'r', 1.0)) == branch


def test_single_repo_garden_still_grows_a_full_crown() -> None:
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='only',
                sessions=180,
                lines_added=42000,
                lines_removed=15000,
                output_tokens=3_000_000,
                input_tokens=9_000_000,
                cost=400.0,
                prompts=2200,
            )
        ],
    )

    svg = render_svg(garden)

    assert svg.count('class="branch"') == MIN_LIMBS
    assert svg.count('data-repo="only"') == MIN_LIMBS


def test_branch_side_balances_the_two_flanks() -> None:
    # Weights of a repo split MIN_LIMBS ways, biggest first.
    falloff = [LIMB_SHARE_FALLOFF**rank for rank in range(MIN_LIMBS)]
    weights = [term / sum(falloff) for term in falloff]

    flanks = {-1: 0.0, 1: 0.0}
    for index, weight in enumerate(weights):
        flanks[_branch_side(index)] += weight

    assert abs(flanks[-1] - flanks[1]) < 0.1
    # Both flanks are used at every size a tree can be.
    for count in range(2, 12):
        assert len({_branch_side(i) for i in range(count)}) == 2


def test_render_svg_draws_fruit_when_skills_present() -> None:
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[SkillFruit(skill='code-review', count=8)],
    )

    svg = render_svg(garden)

    assert 'class="fruit"' in svg


def test_render_svg_draws_no_fruit_without_skills() -> None:
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[],
    )

    svg = render_svg(garden)

    assert 'class="fruit"' not in svg


def test_render_svg_draws_no_fruit_without_branches() -> None:
    garden = GardenData(
        rings=[],
        branches=[],
        skills=[SkillFruit(skill='code-review', count=8)],
    )

    svg = render_svg(garden)

    assert 'class="fruit"' not in svg


def test_render_svg_fruit_legend_shown_with_skills() -> None:
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[SkillFruit(skill='code-review', count=8)],
    )

    svg = render_svg(garden)

    assert 'Fruit' in svg
    assert 'one per skill you ran' in svg


def test_render_svg_fruit_legend_hidden_without_skills() -> None:
    garden = GardenData(
        rings=[],
        branches=[],
        skills=[],
    )

    svg = render_svg(garden)

    assert 'hangs on branches' not in svg


def _timeline_with_skills(**extra: list[int]) -> GardenTimeline:
    """Four days; `code-review` runs to 8 calls, plus any extra skill."""
    counts = {'code-review': [2, 4, 6, 8], **extra}
    days = ['2026-07-20', '2026-07-21', '2026-07-22', '2026-07-23']
    return GardenTimeline(
        days=days,
        daily_sessions=[1] * len(days),
        cumulative_sessions=[1, 2, 3, 4],
        branch_order=['my-repo'],
        branch_days={
            'my-repo': [
                RepoBranchDay(
                    day=day,
                    sessions=30,
                    lines_added=600,
                    lines_removed=60,
                    output_tokens=1000,
                    input_tokens=100,
                    cost=0.1,
                    prompts=5,
                )
                for day in days
            ]
        },
        skill_order=list(counts),
        skill_days={
            skill: [
                SkillUsageDay(day=day, count=count)
                for day, count in zip(days, running, strict=True)
            ]
            for skill, running in counts.items()
        },
    )


@pytest.mark.parametrize(
    ('uses', 'expected'),
    [(0, 1), (1, 1), (4, 2), (25, 6), (100, 11), (10_000, 14)],
)
def test_fruit_count_curve(uses: int, expected: int) -> None:
    assert _fruit_count(uses) == expected


def test_fruit_color_is_stable_across_processes() -> None:
    """`hash()` is salted per run; the garden must not repaint itself."""
    code = (
        'from ccgarden.render import _fruit_color;'
        "print(_fruit_color('skill-tree:handoff'))"
    )
    runs = {
        subprocess.run(  # noqa: S603
            [sys.executable, '-c', code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, 'PYTHONHASHSEED': seed},
        ).stdout.strip()
        for seed in ('1', '2', '3')
    }
    assert runs == {_fruit_color('skill-tree:handoff')}


def test_fruit_plan_scales_down_past_the_total_cap() -> None:
    skills = [SkillFruit(skill=f's{i}', count=400) for i in range(30)]

    plan = _fruit_plan(skills)

    assert sum(n for _, n in plan) <= FRUIT_TOTAL_MAX
    assert all(n >= 1 for _, n in plan)


def test_heavier_skill_grows_more_fruit() -> None:
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[
            SkillFruit(skill='often', count=100),
            SkillFruit(skill='once', count=1),
        ],
    )

    svg = render_svg(garden)

    assert svg.count('often — 100 calls') > svg.count('once — 1 call')
    assert 'once — 1 calls' not in svg


def test_timeline_fruit_ripens_only_at_the_end() -> None:
    """Fruit is the harvest, not a shape that grows across the replay."""
    svg = render_timeline_svg(_timeline_with_skills(latecomer=[0, 0, 0, 9]))

    ripen = re.search(
        r'<g class="fruit-crop" opacity="0"><animate[^>]*'
        r'keyTimes="([^"]+)" values="([^"]+)"',
        svg,
    )
    assert ripen is not None
    key_times = [float(t) for t in ripen.group(1).split(';')]
    assert ripen.group(2) == '0;0;1'
    assert key_times == [0.0, 1.0 - FRUIT_RIPEN_FRACTION, 1.0]
    # One shared fade for the whole crop, not one animation per fruit.
    assert svg.count('class="fruit"') > 1
    assert svg.count('class="fruit-crop"') == 1


def test_timeline_fruit_labels_use_final_counts() -> None:
    svg = render_timeline_svg(_timeline_with_skills(latecomer=[0, 0, 0, 9]))

    assert 'code-review — 8 calls' in svg
    assert 'latecomer — 9 calls' in svg


def _fruit_spots(svg: str) -> list[tuple[float, float, float]]:
    """(x, y, radius) per fruit, off the group transform it is drawn with."""
    return [
        (float(x), float(y), float(r))
        for x, y, r in re.findall(
            r'class="fruit" transform="translate\((-?[\d.]+),(-?[\d.]+)\) '
            r'scale\(([\d.]+)\)"',
            svg,
        )
    ]


def _canopy_disks_in(svg: str) -> list[tuple[float, float, float]]:
    """(cx, cy, r) per foliage blob, read back off the rendered paths."""
    disks = []
    for blob_d in re.findall(r'class="canopy" d="([^"]+)"', svg):
        numbers = [float(n) for n in re.findall(r'(-?[\d.]+)', blob_d)]
        points = list(zip(numbers[0::2], numbers[1::2], strict=True))
        cx = sum(x for x, _ in points) / len(points)
        cy = sum(y for _, y in points) / len(points)
        radius = max(math.hypot(x - cx, y - cy) for x, y in points)
        disks.append((cx, cy, radius))
    return disks


def _fruit_garden() -> GardenData:
    return GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo=f'repo-{i}',
                sessions=40,
                lines_added=800,
                lines_removed=80,
                output_tokens=5000,
                input_tokens=1000,
                cost=1.0,
                prompts=60,
            )
            for i in range(3)
        ],
        skills=[
            SkillFruit(skill=f'skill-{i}', count=(i + 1) * 20)
            for i in range(6)
        ],
    )


def test_every_fruit_hangs_inside_the_canopy() -> None:
    """Fruit used to land in bare sky past the branch tip."""
    svg = render_svg(_fruit_garden())
    disks = _canopy_disks_in(svg)
    spots = _fruit_spots(svg)

    assert spots
    assert disks
    stranded = [
        (x, y)
        for x, y, _ in spots
        if not any(math.hypot(x - cx, y - cy) <= r for cx, cy, r in disks)
    ]
    assert stranded == []


def test_no_fruit_stem_pokes_above_the_canopy() -> None:
    """The stem clears the greenery long before the fruit does."""
    svg = render_svg(_fruit_garden())
    disks = _canopy_disks_in(svg)

    poking = [
        (x, y)
        for x, y, radius in _fruit_spots(svg)
        if not any(
            math.hypot(x - cx, y + radius * FRUIT_STEM_TIP - cy) <= r
            for cx, cy, r in disks
        )
    ]
    assert poking == []


def test_fruit_do_not_bunch_on_top_of_each_other() -> None:
    spots = _fruit_spots(render_svg(_fruit_garden()))

    overlapping = [
        (a, b)
        for a, b in itertools.combinations(spots, 2)
        if math.hypot(a[0] - b[0], a[1] - b[1]) < (a[2] + b[2])
    ]
    assert overlapping == []


def test_fruit_size_tracks_skill_usage() -> None:
    """A skill you lean on hangs heavier than one you tried once."""
    assert _fruit_radius(1) < _fruit_radius(10) < _fruit_radius(60)
    assert _fruit_radius(0) == pytest.approx(FRUIT_RADIUS_MIN)
    assert _fruit_radius(10_000) == pytest.approx(FRUIT_RADIUS_MAX)


def test_rendered_fruit_is_bigger_for_a_heavier_skill() -> None:
    svg = render_svg(_fruit_garden())
    drawn = re.findall(
        r'class="fruit" transform="[^"]*scale\(([\d.]+)\)"><title>'
        r'([^ ]+) — ([\d,]+) calls?</title>',
        svg,
    )

    assert drawn
    by_skill = {
        skill: (float(scale), int(count.replace(',', '')))
        for scale, skill, count in drawn
    }
    ranked = sorted(by_skill.values(), key=lambda pair: pair[1])
    assert [scale for scale, _ in ranked] == sorted(
        scale for scale, _ in ranked
    )


def test_fruit_shapes_vary_between_skills() -> None:
    shapes = {_fruit_shape(f'skill-{i}') for i in range(40)}

    assert shapes == set(FRUIT_SHAPES)
    assert len(FRUIT_SHAPES) > 1
    # Shape and colour must not move together.
    pairs = {
        (_fruit_shape(f'skill-{i}'), _fruit_color(f'skill-{i}'))
        for i in range(40)
    }
    assert len({shape for shape, _ in pairs}) > 1
    assert len({color for _, color in pairs}) > 1


def test_rendered_garden_draws_more_than_one_fruit_shape() -> None:
    svg = render_svg(_fruit_garden())

    drawn = {
        shape
        for shape in FRUIT_SHAPES
        if FRUIT_SHAPE_BODIES[shape].format(fill='#e74c3c') in svg
        or FRUIT_SHAPE_BODIES[shape].split('{fill}')[0] in svg
    }
    assert len(drawn) > 1


def test_fruit_placement_is_deterministic() -> None:
    garden = _fruit_garden()

    assert _fruit_spots(render_svg(garden)) == _fruit_spots(render_svg(garden))


def test_fruit_has_its_own_sway_group() -> None:
    """Each fruit gets a nested sway group so it swings more than its limb."""
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[SkillFruit(skill='code-review', count=8)],
    )
    svg = render_svg(garden)
    assert 'ccg-sway-fruit' in svg


def test_fruit_legend_shows_each_skill() -> None:
    """Per-skill fruit entries appear in the legend."""
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[
            SkillFruit(skill='code-review', count=8),
            SkillFruit(skill='simplify', count=6),
        ],
    )
    svg = render_svg(garden)
    assert 'code-review' in svg
    assert 'simplify' in svg
    # Each skill should have its own fruit icon in the legend
    assert svg.count('class="fruit-key-icon"') >= 2


def test_fruit_excluded_below_min_calls() -> None:
    """Skills with fewer than FRUIT_MIN_CALLS are not shown."""
    garden = GardenData(
        rings=[],
        branches=[
            RepoBranch(
                repo='my-repo',
                sessions=10,
                lines_added=500,
                lines_removed=50,
                output_tokens=1000,
                input_tokens=500,
                cost=0.0,
                prompts=20,
            ),
        ],
        skills=[
            SkillFruit(skill='rare-skill', count=3),
        ],
    )
    svg = render_svg(garden)
    assert 'class="fruit"' not in svg
    assert 'fruit-key-icon' not in svg
