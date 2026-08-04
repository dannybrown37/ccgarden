import itertools
import math
import re
from dataclasses import replace

import pytest


from ccgarden.data import (
    CartoonBird,
    DayRing,
    GardenData,
    GardenTimeline,
    ModelCloud,
    ModelUsageDay,
    RepoBranch,
    RepoBranchDay,
    ToolBush,
    ToolUsageDay,
)
from ccgarden.render import (
    BIRD_MARGIN,
    BRANCH_ANGLE_JITTER_DEGREES,
    BRANCH_LENGTH_MAX,
    BRANCH_LENGTH_MIN,
    BRANCH_LINES_SATURATION,
    BIRD_SIZE_MAX,
    BIRD_SIZE_MIN,
    BIRD_TOKENS_SATURATION,
    BIRD_Y_MAX,
    BIRD_Y_MIN,
    CLOUD_MARGIN,
    CLOUD_TOKENS_SATURATION,
    CLOUD_TREE_KEEPOUT_HALF_WIDTH,
    CLOUD_Y_MAX_AT_EDGE,
    CLOUD_Y_MAX_NEAR_TREE,
    LEAVES_PER_SESSION,
    MAX_BIRDS,
    MAX_BUSHES,
    MAX_SUNFLOWERS,
    SUN_HALO_RADIUS_FACTOR,
    SUN_TOKENS_SATURATION,
    SUNFLOWER_BAND_WIDTH,
    SUNFLOWER_MARGIN,
    TIMELINE_VIEWBOX_HEIGHT,
    TRUNK_CENTER_X,
    VIEWBOX_HEIGHT,
    VIEWBOX_WIDTH,
    _bird_size,
    _branch_bow,
    _branch_endpoint,
    _branch_length,
    _branch_placement,
    _bird_positions,
    _bird_slots,
    _bush_radius,
    _bush_x_positions,
    _cache_efficiency_flower_count,
    _cloud_positions,
    _cloud_radius,
    _cloud_y_max,
    _sun_position,
    _sun_radius,
    _sunflower_height,
    _sunflower_x_positions,
    render_svg,
    render_timeline_svg,
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


@pytest.mark.parametrize('branch_count', [1, 3, 5])
def test_render_svg_draws_one_branch_per_repo(branch_count: int) -> None:
    branches = [branch(f'repo-{i}') for i in range(branch_count)]
    garden = GardenData(rings=[], branches=branches)

    svg = render_svg(garden)

    assert svg.count('class="branch"') == branch_count


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
    # The trunk keeps a real (zero-width, so invisible) path so that `d`
    # stays interpolable; its outline stroke is what has to vanish.
    trunk = svg.split('class="trunk"')[1]
    trunk_d = _first_values(trunk, 'd')
    assert f'M {TRUNK_CENTER_X:.2f},' in trunk_d[0]
    assert trunk_d[0] != trunk_d[-1]
    assert float(_first_values(trunk, 'stroke-width')[0]) == 0.0


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
    assert translate_values is not None
    for frame in translate_values.group(1).split(';'):
        x, y = (float(v) for v in frame.strip().split(','))
        # Worst case is the last frame, where the sun is at full size.
        halo = final_radius * SUN_HALO_RADIUS_FACTOR
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

    flock = svg.split('class="birds"')[1].split('</g></g></g>')[0]
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
    assert '<animateTransform' not in svg.split('class="birds"')[1]
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
