import re

import pytest

from ccgarden.data import (
    DayRing,
    GardenData,
    GardenTimeline,
    ModelCloud,
    RepoBranch,
    ToolBush,
    ToolUsageDay,
)
from ccgarden.render import (
    LEAVES_PER_SESSION,
    MAX_BUSHES,
    TIMELINE_VIEWBOX_HEIGHT,
    _bush_radius,
    _bush_x_positions,
    _cache_efficiency_flower_count,
    _cloud_positions,
    _cloud_radius,
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
    walk_up = svg.split('function labelFor')[1].split('function ')[0]
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
