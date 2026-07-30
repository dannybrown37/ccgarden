import pytest

from ccgarden.data import DayRing, GardenData, ModelCloud, RepoBranch
from ccgarden.render import (
    LEAVES_PER_SESSION,
    _cache_efficiency_flower_count,
    _cloud_radius,
    render_svg,
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
        cache_read_tokens=500,
        cache_write_tokens=100,
    )

    svg = render_svg(garden)

    assert svg.count('class="flower"') == 5


def test_render_svg_draws_no_flowers_without_cache_writes() -> None:
    garden = GardenData(
        rings=[],
        branches=[],
        cache_read_tokens=500,
        cache_write_tokens=0,
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
    garden = GardenData(rings=[], branches=[], models=models)

    svg = render_svg(garden)

    assert svg.count('class="cloud"') == model_count


def test_render_svg_draws_no_clouds_without_models() -> None:
    garden = GardenData(rings=[], branches=[], models=[])

    svg = render_svg(garden)

    assert svg.count('class="cloud"') == 0


def test_cloud_radius_grows_with_total_tokens() -> None:
    assert _cloud_radius(0) < _cloud_radius(1_000) < _cloud_radius(5_000_000)
