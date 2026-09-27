"""Tests for the top-down garden plot renderer."""

from __future__ import annotations

import math
from dataclasses import replace
import re
from itertools import combinations, pairwise
import xml.etree.ElementTree as ET

import pytest

from ccgarden.data import (
    GardenData,
    GardenTimeline,
    RepoBranch,
    RepoBranchDay,
    SkillFruit,
    SkillUsageDay,
    ToolBush,
    ToolUsageDay,
)
from ccgarden.data import DORMANCY_HALF_LIFE_DAYS, DORMANCY_MIN_GAP_DAYS
from ccgarden.plot_species import FAMILY_POOLS, SPECIES, model_family
from ccgarden.render_plot import (
    BedRect,
    BED_MIN_DIM,
    BED_ZONE_H,
    BED_ZONE_W,
    BED_ZONE_X,
    BED_ZONE_Y,
    FENCE_H,
    FENCE_Y,
    FRAME_WOOD,
    FRAME_WIDTH,
    LEGEND_COLS,
    LEGEND_ENTRIES,
    PATCH_GAP,
    STONE_STEP,
    PLANT_MAX_SPACING,
    PLOT_VIEWBOX_WIDTH,
    SHED_BOX,
    SHED_ROOF,
    SOIL_COLOR,
    TOOL_HEAD_LEN,
    SOIL_DORMANT,
    WEED_COLOR,
    WEED_FLOWER,
    WEED_FULL_DAYS,
    WEED_MAX,
    WEED_ONSET_DAYS,
    _bed_area_metric,
    _bed_planting,
    _bed_tag,
    _bed_tooltip,
    _barrel_water,
    _bench_tools,
    _butterfly_keyframes,
    _feature_boxes,
    _flower_positions,
    _frame_planks,
    _bed_wood,
    _render_paths,
    _render_row_markers,
    _row_markers,
    _shade,
    _stepping_stones,
    _bed_furrows,
    _furrow_depth,
    _layout_beds,
    _plant_area,
    _plant_layout,
    _plant_specs,
    _render_bed_label,
    _render_shed,
    _render_signboard,
    _sundial_wedges,
    _soil_rect,
    _plot_layout,
    _point_in_any_bed,
    _squarify,
    _weed_count,
    SPRINKLER_DAYS,
    SPRINKLER_MAX_HEADS,
    _sprinkler_grid,
    _sprinkler_scale,
    _sprinkler_strength,
    render_plot_svg,
    render_plot_timeline_svg,
)

TOP_OPUS = FAMILY_POOLS['opus'][0]
TOP_SONNET = FAMILY_POOLS['sonnet'][0]


# ── Treemap layout ──────────────────────────────────────────────


class TestBedAreaMetric:
    def test_lines_dominate(self):
        branch = _branch(lines_added=5000, sessions=10)
        assert _bed_area_metric(branch) == 5000 + 10 * 50

    def test_zero_lines_still_visible(self):
        branch = _branch(lines_added=0, sessions=20)
        assert _bed_area_metric(branch) > 0


class TestSquarify:
    def test_single_value_fills_rect(self):
        rects = _squarify([100.0], (0, 0, 200, 100))
        assert len(rects) == 1
        _x, _y, w, h = rects[0]
        assert abs(w * h - 200 * 100) < 1

    def test_two_equal_values(self):
        rects = _squarify([50.0, 50.0], (0, 0, 200, 100))
        assert len(rects) == 2
        total_area = sum(w * h for _, _, w, h in rects)
        assert abs(total_area - 200 * 100) < 1

    def test_areas_proportional(self):
        rects = _squarify([75.0, 25.0], (0, 0, 200, 100))
        areas = [w * h for _, _, w, h in rects]
        assert areas[0] > areas[1]
        assert abs(areas[0] / areas[1] - 3.0) < 0.1

    def test_many_values_fill_rect(self):
        values = [100.0, 80.0, 60.0, 40.0, 20.0]
        rects = _squarify(values, (10, 10, 300, 200))
        total_area = sum(w * h for _, _, w, h in rects)
        assert abs(total_area - 300 * 200) < 1
        assert len(rects) == 5

    def test_no_overlap(self):
        values = [100.0, 80.0, 60.0, 40.0]
        rects = _squarify(values, (0, 0, 200, 200))
        for i, (x1, y1, w1, h1) in enumerate(rects):
            for x2, y2, w2, h2 in rects[i + 1 :]:
                overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                overlap_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                assert overlap_x * overlap_y < 1

    def test_empty_input(self):
        assert _squarify([], (0, 0, 200, 100)) == []

    def test_offset_rect(self):
        rects = _squarify([100.0], (50, 30, 200, 100))
        x, y, _w, _h = rects[0]
        assert x >= 50
        assert y >= 30


class TestLayoutBeds:
    def test_beds_match_branches(self):
        branches = [
            _branch('repo-a', lines_added=3000, sessions=50),
            _branch('repo-b', lines_added=1000, sessions=20),
        ]
        beds = _layout_beds(branches)
        assert len(beds) == 2
        repos = {b.repo for b in beds}
        assert repos == {'repo-a', 'repo-b'}

    def test_bigger_repo_gets_bigger_bed(self):
        branches = [
            _branch('big', lines_added=10000, sessions=100),
            _branch('small', lines_added=100, sessions=5),
        ]
        beds = _layout_beds(branches)
        big = next(b for b in beds if b.repo == 'big')
        small = next(b for b in beds if b.repo == 'small')
        assert big.w * big.h > small.w * small.h

    def test_single_repo_fills_zone(self):
        beds = _layout_beds([_branch('solo', lines_added=5000)])
        assert len(beds) == 1

    def test_empty_branches(self):
        assert _layout_beds([]) == []


def _skewed_branches(n_tiny: int) -> list[RepoBranch]:
    return [
        _branch('huge', lines_added=90_000, sessions=300),
        *(
            _branch(f'tiny-{i}', lines_added=5, sessions=1)
            for i in range(n_tiny)
        ),
    ]


def _even_branches(n: int) -> list[RepoBranch]:
    return [
        _branch(f'r{i}', lines_added=1000 * (i + 1), sessions=10 + i)
        for i in range(n)
    ]


LAYOUT_CASES = [
    pytest.param(_skewed_branches, 3, id='one-huge-three-tiny'),
    pytest.param(_skewed_branches, 14, id='one-huge-fourteen-tiny'),
    pytest.param(_even_branches, 15, id='fifteen-graded'),
    pytest.param(_even_branches, 40, id='forty-graded'),
]


class TestLayoutContainment:
    @pytest.mark.parametrize(('build', 'n'), LAYOUT_CASES)
    def test_every_bed_inside_zone(self, build, n):
        eps = 0.01
        for bed in _layout_beds(build(n)):
            assert bed.x >= BED_ZONE_X - eps
            assert bed.y >= BED_ZONE_Y - eps
            assert bed.x + bed.w <= BED_ZONE_X + BED_ZONE_W + eps
            assert bed.y + bed.h <= BED_ZONE_Y + BED_ZONE_H + eps

    @pytest.mark.parametrize(('build', 'n'), LAYOUT_CASES)
    def test_beds_never_overlap(self, build, n):
        beds = _layout_beds(build(n))
        for i, a in enumerate(beds):
            for b in beds[i + 1 :]:
                ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
                oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
                assert ox <= 0 or oy <= 0, (a.repo, b.repo)

    @pytest.mark.parametrize('n_tiny', [3, 14])
    def test_tiny_repo_still_gets_a_usable_bed(self, n_tiny):
        beds = _layout_beds(_skewed_branches(n_tiny))
        for bed in beds:
            assert bed.w * bed.h >= BED_MIN_DIM**2 * 0.8, bed.repo


class TestFlowerBorder:
    @pytest.mark.parametrize('n', [1, 10, 42, 90])
    def test_flowers_sit_below_fence_and_above_legend(self, n):
        layout = _plot_layout(n)
        positions = _flower_positions(n)
        assert len(positions) == n
        for x, y in positions:
            assert y > FENCE_Y + FENCE_H
            assert y < layout.legend_y
            assert 0 < x < PLOT_VIEWBOX_WIDTH

    def test_no_flowers_means_no_border(self):
        assert _flower_positions(0) == []

    def test_many_flowers_wrap_to_more_rows(self):
        rows = {round(y) for _, y in _flower_positions(90)}
        assert len(rows) > 1


class TestViewbox:
    @pytest.mark.parametrize('n_skills', [0, 5, 60])
    def test_size_matches_viewbox(self, n_skills):
        skills = [SkillFruit(f's{i}', i + 1) for i in range(n_skills)]
        svg = render_plot_svg(_garden(skills=skills))
        total = _plot_layout(n_skills).total_h
        assert f'viewBox="0 0 {PLOT_VIEWBOX_WIDTH} {total}"' in svg
        assert f'height="{total}"' in svg


# ── Depth and light ─────────────────────────────────────────


def _luma(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b


class TestDepthAndLight:
    @pytest.mark.parametrize(
        'pattern', ['lawnStripes', 'gravel', 'soilTexture', 'softShadow']
    )
    def test_shared_paint_defined_and_used(self, pattern):
        svg = render_plot_svg(_garden())
        assert f'id="{pattern}"' in svg
        assert f'url(#{pattern})' in svg

    def test_one_shadow_per_bed(self):
        branches = _even_branches(6)
        svg = render_plot_svg(_garden(branches=branches))
        assert svg.count('class="bed-shadow"') == len(branches)

    def test_frame_lit_from_top_left(self):
        bed = _layout_beds([_branch()])[0]
        planks = {side: color for side, _, color in _frame_planks(bed)}
        assert _luma(planks['top']) > _luma(planks['bottom'])
        assert _luma(planks['left']) > _luma(planks['right'])

    def test_planks_stay_inside_bed(self):
        bed = _layout_beds([_branch()])[0]
        for _, rect, _ in _frame_planks(bed):
            x, y, w, h = rect
            assert x >= bed.x
            assert y >= bed.y
            assert x + w <= bed.x + bed.w + 0.01
            assert y + h <= bed.y + bed.h + 0.01

    def test_timeline_shares_the_same_bed_look(self):
        svg = render_plot_timeline_svg(_timeline())
        assert 'url(#soilTexture)' in svg
        assert 'class="bed-shadow"' in svg


# ── Plants ─────────────────────────────────────────────────


def _bed(repo='r', x=100.0, y=100.0, w=200.0, h=160.0, **branch_kw) -> BedRect:
    return BedRect(repo, x, y, w, h, _branch(repo, **branch_kw))


MIXED = {'claude-sonnet-5 (high)': 60, 'claude-opus-5 (max)': 40}


class TestPlantLayout:
    def test_plants_inside_soil(self):
        bed = _bed(sessions=50, model_effort_counts=MIXED)
        sx, sy, sw, sh = _soil_rect(bed)
        plants = _plant_layout(bed, 50)
        assert plants
        for p in plants:
            assert sx <= p.x <= sx + sw
            assert sy <= p.y <= sy + sh

    def test_busier_bed_is_lusher(self):
        quiet = _bed(sessions=5, model_effort_counts=MIXED)
        busy = _bed(sessions=50, model_effort_counts=MIXED)
        assert len(_plant_layout(busy, 50)) > len(_plant_layout(quiet, 50))

    def test_plants_spread_over_the_bed(self):
        bed = _bed(sessions=10, model_effort_counts=MIXED)
        _, _, _, sh = _soil_rect(bed)
        ys = [p.y for p in _plant_layout(bed, 50)]
        assert max(ys) - min(ys) >= 0.5 * sh

    def test_species_planted_in_patches(self):
        bed = _bed(sessions=50, model_effort_counts=MIXED)
        families = [p.spec.model_family for p in _plant_layout(bed, 50)]
        changes = sum(a != b for a, b in pairwise(families))
        assert changes == len(set(families)) - 1

    @pytest.mark.parametrize(
        ('small', 'big'),
        [('low', 'medium'), ('medium', 'high'), ('high', 'max')],
    )
    def test_effort_grows_plants(self, small, big):
        def size_for(effort: str) -> float:
            bed = _bed(
                sessions=20,
                model_effort_counts={f'claude-sonnet-5 ({effort})': 1},
            )
            return _plant_layout(bed, 20)[0].size

        assert size_for(big) > size_for(small)

    def test_no_model_data_still_plants_something(self):
        bed = _bed(sessions=20)
        assert _plant_layout(bed, 20)

    def test_deterministic(self):
        bed = _bed(sessions=30, model_effort_counts=MIXED)
        assert _plant_layout(bed, 30) == _plant_layout(bed, 30)

    @pytest.mark.parametrize(
        ('w', 'h'), [(200.0, 160.0), (400.0, 90.0), (90.0, 400.0)]
    )
    def test_busiest_bed_still_shows_soil(self, w, h):
        bed = _bed(w=w, h=h, sessions=50, model_effort_counts=MIXED)
        medium = [
            p
            for p in _plant_layout(bed, 50)
            if p.spec.effort in {'medium', 'high'}
        ]
        for a, b in combinations(medium, 2):
            gap = math.dist((a.x, a.y), (b.x, b.y)) - (a.size + b.size) / 2
            assert gap > -0.2 * min(a.size, b.size)

    @pytest.mark.parametrize(
        ('w', 'h'), [(40.0, 160.0), (45.0, 200.0), (200.0, 45.0)]
    )
    def test_sparse_bed_is_planted_evenly_not_top_heavy(self, w, h):
        combo = {'claude-sonnet-5 (medium)': 1}
        bed = _bed(w=w, h=h, sessions=1, model_effort_counts=combo)
        plants = _plant_layout(bed, 50)
        ax, ay, aw, ah = _plant_area(bed)
        mean_x = sum(p.x for p in plants) / len(plants)
        mean_y = sum(p.y for p in plants) / len(plants)
        assert mean_x == pytest.approx(ax + aw / 2, abs=0.06 * aw)
        assert mean_y == pytest.approx(ay + ah / 2, abs=0.06 * ah)

    def test_one_big_plant_does_not_thin_the_whole_bed(self):
        low = {'claude-opus-4-6 (low)': 40, 'claude-sonnet-5 (low)': 40}
        bed = _bed(w=300.0, h=240.0, sessions=50, model_effort_counts=low)
        with_big = _bed(
            w=300.0,
            h=240.0,
            sessions=50,
            model_effort_counts={**low, 'claude-opus-5 (max)': 1},
        )

        def low_spacings(b: BedRect) -> list[float]:
            planting = _bed_planting(b, 50)
            return [
                spacing
                for group, spacing in zip(
                    planting.groups, planting.spacings, strict=True
                )
                if all(spec.effort == 'low' for spec, _ in group)
            ]

        assert low_spacings(with_big) == pytest.approx(low_spacings(bed))

    @pytest.mark.parametrize('effort', ['high', 'xhigh', 'max'])
    def test_big_plants_are_spaced_for_their_size(self, effort):
        combo = {f'claude-opus-5 ({effort})': 50}
        bed = _bed(w=300.0, h=240.0, sessions=50, model_effort_counts=combo)
        plants = _plant_layout(bed, 50)
        for a, b in combinations(plants, 2):
            gap = math.dist((a.x, a.y), (b.x, b.y)) - (a.size + b.size) / 2
            assert gap > -0.1 * min(a.size, b.size)

    @pytest.mark.parametrize('species', ['corn', 'lettuce'])
    def test_plant_size_follows_its_species(self, species):
        label = 'claude-opus-5 (medium)'
        bed = _bed(sessions=20, model_effort_counts={label: 1})
        plant = _plant_layout(bed, 20, {label: species})[0]
        base = _plant_layout(bed, 20, {label: 'cauliflower'})[0]
        assert plant.size / base.size == pytest.approx(SPECIES[species].scale)

    def test_big_species_is_spaced_for_its_size(self):
        combo = {'claude-opus-5 (high)': 50}
        bed = _bed(w=300.0, h=240.0, sessions=50, model_effort_counts=combo)
        plants = _plant_layout(bed, 50, dict.fromkeys(combo, 'corn'))
        for a, b in combinations(plants, 2):
            gap = math.dist((a.x, a.y), (b.x, b.y)) - (a.size + b.size) / 2
            assert gap > -0.1 * min(a.size, b.size)

    @pytest.mark.parametrize(
        ('w', 'h', 'sessions'),
        [(40.0, 40.0, 50), (60.0, 90.0, 2), (400.0, 300.0, 5)],
    )
    def test_plant_size_is_the_same_in_every_bed(self, w, h, sessions):
        combo = {'claude-sonnet-5 (medium)': 1}
        busy = _bed(w=400.0, h=300.0, sessions=50, model_effort_counts=combo)
        other = _bed(w=w, h=h, sessions=sessions, model_effort_counts=combo)
        reference = _plant_layout(busy, 50)[0].size
        for p in _plant_layout(other, 50):
            assert p.size == pytest.approx(reference, rel=0.2)

    @pytest.mark.parametrize(
        ('w', 'h', 'axis'),
        [(200.0, 300.0, 'y'), (400.0, 120.0, 'x')],
    )
    def test_species_patches_are_separate_strips(self, w, h, axis):
        bed = _bed(w=w, h=h, sessions=50, model_effort_counts=MIXED)
        plants = _plant_layout(bed, 50)
        by_species: dict[str, list[float]] = {}
        for p in plants:
            by_species.setdefault(p.spec.species, []).append(
                p.y if axis == 'y' else p.x
            )
        first, second = by_species.values()
        assert max(first) < min(second)

    def test_patches_have_a_path_between_them(self):
        bed = _bed(w=200.0, h=300.0, sessions=50, model_effort_counts=MIXED)
        plants = _plant_layout(bed, 50)
        first = [p for p in plants if p.spec.species == plants[0].spec.species]
        second = [p for p in plants if p not in first]
        bottom = max(p.y + p.size / 2 for p in first)
        top = min(p.y - p.size / 2 for p in second)
        assert top - bottom >= PATCH_GAP * 0.5


class TestPlantSymbols:
    @pytest.mark.parametrize('species', [TOP_OPUS, TOP_SONNET, 'sprout'])
    def test_symbol_has_shine_and_shadow(self, species):
        branch = _branch(
            model_effort_counts={
                'claude-opus-4-6 (low)': 5,
                'claude-sonnet-5 (low)': 5,
            }
        )
        svg = render_plot_svg(_garden(branches=[branch]))
        start = svg.index(f'id="plant-{species}"')
        symbol = svg[start : svg.index('</symbol>', start)]
        assert 'url(#plantShine)' in symbol
        assert 'class="plant-shadow"' in symbol


def _side_by_side(gap=14.0) -> list[BedRect]:
    return [
        _bed('a', x=100.0, y=100.0, w=100.0, h=200.0),
        _bed('b', x=200.0 + gap, y=140.0, w=100.0, h=200.0),
    ]


class TestSteppingStones:
    def test_stones_follow_the_gutter_centre(self):
        stones = _stepping_stones(_side_by_side())
        assert len(stones) >= 5
        for stone in stones:
            assert stone.x == pytest.approx(207.0, abs=2.0)

    def test_stones_only_where_beds_overlap(self):
        for stone in _stepping_stones(_side_by_side()):
            assert 140.0 <= stone.y <= 300.0

    def test_stones_never_in_a_bed(self):
        beds = _side_by_side()
        for stone in _stepping_stones(beds):
            assert not _point_in_any_bed(
                stone.x, stone.y, beds, margin=stone.r * 0.5
            )

    def test_stones_do_not_pile_up(self):
        stones = _stepping_stones(_side_by_side())
        for a, b in combinations(stones, 2):
            assert math.dist(a[:2], b[:2]) >= STONE_STEP * 0.6

    def test_far_apart_beds_get_no_path(self):
        assert _stepping_stones(_side_by_side(gap=80.0)) == []

    def test_stones_know_which_beds_they_join(self):
        for stone in _stepping_stones(_side_by_side()):
            assert set(stone.repos) == {'a', 'b'}

    def test_static_path_does_not_animate(self):
        assert '<animate' not in _render_paths(_side_by_side())

    def test_timeline_path_is_laid_with_its_first_bed(self):
        paths = _render_paths(
            _side_by_side(),
            first_days={'a': 3, 'b': 1},
            key_times=[0.0, 0.25, 0.5, 0.75, 1.0],
            dur=10.0,
        )
        assert '<g class="path-stones" opacity="0">' in paths
        assert 'keyTimes="0.0000;0.2500;1.0000" values="0;1;1"' in paths

    def test_real_layout_gets_a_path(self):
        assert _stepping_stones(_layout_beds(_even_branches(6)))


class TestBedWood:
    def test_same_repo_same_wood(self):
        assert _bed_wood(_bed('x')) == _bed_wood(_bed('x'))

    def test_beds_are_not_all_one_board(self):
        tones = {_bed_wood(_bed(f'repo-{i}')) for i in range(8)}
        assert len(tones) >= 6

    @pytest.mark.parametrize('repo', [f'repo-{i}' for i in range(12)])
    def test_wood_stays_wood(self, repo):
        assert abs(_luma(_bed_wood(_bed(repo))) - _luma(FRAME_WOOD)) < 40

    def test_frame_uses_the_bed_wood(self):
        bed = _bed('cedar')
        wood = _bed_wood(bed)
        _, _, colour = next(p for p in _frame_planks(bed) if p[0] == 'top')
        assert colour == _shade(wood, 0.2)


MARKER_MIX = {
    'claude-opus-4-6 (low)': 60,
    'claude-sonnet-5 (low)': 40,
}


class TestRowMarkers:
    def test_one_marker_per_single_species_block(self):
        bed = _bed(
            w=200.0, h=300.0, sessions=50, model_effort_counts=MARKER_MIX
        )
        markers = _row_markers(bed, 50)
        assert sorted(m.species for m in markers) == sorted(
            [TOP_OPUS, TOP_SONNET]
        )

    @pytest.mark.parametrize(('w', 'h'), [(200.0, 300.0), (400.0, 90.0)])
    def test_markers_sit_on_the_frame(self, w, h):
        bed = _bed(w=w, h=h, sessions=50, model_effort_counts=MARKER_MIX)
        for m in _row_markers(bed, 50):
            assert bed.x <= m.x <= bed.x + bed.w
            assert bed.y <= m.y <= bed.y + bed.h
            to_edge = min(
                m.x - bed.x,
                bed.x + bed.w - m.x,
                m.y - bed.y,
                bed.y + bed.h - m.y,
            )
            assert to_edge <= FRAME_WIDTH

    def test_marker_names_the_combo(self):
        bed = _bed(sessions=50, model_effort_counts=MARKER_MIX)
        svg = _render_row_markers(bed, 50)
        assert 'class="row-marker"' in svg
        assert 'Opus 4.6 · low' in svg

    def test_marker_dodges_a_turned_label(self):
        bed = _bed('a-very-long-repo-name', w=40.0, h=300.0, sessions=50)
        assert _bed_tag(bed).vertical
        for m in _row_markers(bed, 50):
            assert m.x > bed.x + bed.w / 2

    @pytest.mark.parametrize('timeline', [False, True])
    def test_both_renders_draw_markers(self, timeline):
        svg = (
            render_plot_timeline_svg(
                _timeline(), repo_model_efforts={'test-repo': MARKER_MIX}
            )
            if timeline
            else render_plot_svg(
                _garden(branches=[_branch(model_effort_counts=MARKER_MIX)])
            )
        )
        assert 'class="row-marker"' in svg

    def test_no_marker_without_model_data(self):
        assert _row_markers(_bed(sessions=50), 50) == []


class TestBedLabel:
    def test_label_is_a_wooden_tag(self):
        label = _render_bed_label(_bed('my-repo'))
        assert 'class="bed-tag"' in label
        assert 'my-repo' in label

    def test_tall_thin_bed_turns_its_label(self):
        label = _render_bed_label(_bed('a-long-name', w=30.0, h=200.0))
        assert 'rotate(-90' in label

    def test_wide_bed_keeps_label_flat(self):
        label = _render_bed_label(_bed('short', w=200.0, h=100.0))
        assert 'rotate(' not in label

    @pytest.mark.parametrize(
        ('repo', 'w', 'h'),
        [
            ('my-repo', 200.0, 160.0),
            ('fast-pr', 38.0, 76.0),
            ('maad-goat-site', 53.0, 55.0),
            ('a-very-very-long-repo-name', 30.0, 60.0),
        ],
    )
    def test_tag_stays_on_its_bed(self, repo, w, h):
        bed = _bed(repo, w=w, h=h)
        x0, y0, x1, y1 = _bed_tag(bed).box
        assert x0 >= bed.x
        assert y0 >= bed.y
        assert x1 <= bed.x + bed.w
        assert y1 <= bed.y + bed.h

    def test_name_too_long_for_the_bed_is_cut_short(self):
        tag = _bed_tag(_bed('maad-goat-site', w=53.0, h=55.0))
        assert tag.text.endswith('…')
        assert tag.text.startswith('maad')
        assert '-…' not in tag.text

    def test_squarish_bed_keeps_label_flat(self):
        assert not _bed_tag(_bed('maad-goat-site', w=53.0, h=55.0)).vertical

    @pytest.mark.parametrize(
        ('repo', 'w', 'h'),
        [
            ('fast-pr', 38.0, 76.0),
            ('a-long-name', 40.0, 200.0),
            ('my-repo', 200.0, 160.0),
            ('maad-goat-site', 53.0, 55.0),
        ],
    )
    def test_no_plant_rooted_under_the_tag(self, repo, w, h):
        bed = _bed(repo, w=w, h=h, sessions=50, model_effort_counts=MIXED)
        x0, y0, x1, y1 = _bed_tag(bed).box
        for p in _plant_layout(bed, 50):
            assert not (x0 < p.x < x1 and y0 < p.y < y1), (p.x, p.y)


class TestTimelinePlants:
    def test_timeline_uses_repo_model_efforts(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(
            tl,
            repo_model_efforts={'test-repo': {'claude-opus-5 (low)': 9}},
        )
        assert f'href="#plant-{TOP_OPUS}' in svg
        garden_part = svg[: svg.index('<g class="legend"')]
        used = set(
            re.findall(r'href="#plant-([a-z-]+?)(?:-[bc])?"', garden_part)
        )
        assert used <= set(FAMILY_POOLS['opus'])

    def test_plants_grow_out_of_the_soil(self):
        svg = render_plot_timeline_svg(_timeline(n_days=8))
        grows = _grow_scales(svg, 'plant-grow')
        assert grows
        for scales in grows:
            assert scales[-1] == 1
            assert scales == sorted(scales)
        assert any(scales[0] == 0 for scales in grows)

    def test_some_plant_takes_more_than_a_day_to_grow(self):
        svg = render_plot_timeline_svg(_timeline(n_days=8))
        assert any(
            0 < s < 1
            for scales in _grow_scales(svg, 'plant-grow')
            for s in scales
        )

    def test_flowers_grow_with_their_calls(self):
        svg = render_plot_timeline_svg(_timeline(n_days=8))
        (scales,) = _grow_scales(svg, 'flower-grow')
        assert scales[0] > 0
        assert scales[-1] == 1
        assert scales == sorted(scales)
        assert len(set(scales)) > 2


def _grow_scales(svg: str, cls: str) -> list[list[float]]:
    return [
        [float(v.split()[0]) for v in m.group(1).split(';')]
        for m in re.finditer(
            rf'<g class="{cls}"[^>]*><g><animateTransform[^>]*'
            r'type="scale"[^>]*values="([^"]+)"',
            svg,
        )
    ]


# ── Garden features ──────────────────────────────────────────


TOOLS = [ToolBush('Read', 40), ToolBush('Edit', 20)]


class TestShed:
    def test_shingles_are_not_one_flat_colour(self):
        shed = _render_shed(TOOLS)
        fills = set(re.findall(r'class="shingle" fill="(#[0-9a-f]{6})"', shed))
        assert len(fills) >= 5

    @pytest.mark.parametrize(
        'part',
        [
            'class="ridge-cap"',
            'class="skylight"',
            'class="moss"',
            'class="stovepipe"',
        ],
    )
    def test_roof_has_its_details(self, part):
        assert part in _render_shed(TOOLS)

    def test_roof_is_warm_wood_not_slate(self):
        r, _, b = (int(SHED_ROOF[i : i + 2], 16) for i in (1, 3, 5))
        assert r > b

    def test_moss_grows_on_the_shaded_slope(self):
        _, y, _, h = SHED_BOX
        shed = _render_shed(TOOLS)
        start = shed.index('class="moss"')
        moss = shed[start : shed.index('</g>', start)]
        for cy in re.findall(r'cy="([\d.]+)"', moss):
            assert float(cy) > y + h / 2

    def test_shingles_stay_on_the_roof(self):
        x, y, w, h = SHED_BOX
        shed = _render_shed(TOOLS)
        for m in re.finditer(
            r'class="shingle" fill="#[0-9a-f]{6}" x="([\d.]+)" y="([\d.]+)"'
            r' width="([\d.]+)" height="([\d.]+)"',
            shed,
        ):
            sx, sy, sw, sh = map(float, m.groups())
            assert sx >= x - 0.01
            assert sy >= y - 0.01
            assert sx + sw <= x + w + 0.01
            assert sy + sh <= y + h + 0.01

    def test_shed_is_deterministic(self):
        assert _render_shed(TOOLS) == _render_shed(TOOLS)


class TestFeatureLayout:
    def test_features_clear_of_each_other(self):
        boxes = list(_feature_boxes().items())
        for i, (na, (ax, ay, aw, ah)) in enumerate(boxes):
            for nb, (bx, by, bw, bh) in boxes[i + 1 :]:
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                assert ox <= 0 or oy <= 0, (na, nb)

    def test_features_above_fence_and_on_canvas(self):
        for name, (x, y, w, h) in _feature_boxes().items():
            assert x >= 0, name
            assert y >= 0, name
            assert x + w <= PLOT_VIEWBOX_WIDTH, name
            assert y + h < FENCE_Y, name


class TestToolBench:
    def test_busier_tool_is_longer(self):
        placed = _bench_tools([ToolBush('Read', 400), ToolBush('Edit', 40)])
        by_name = {p.tool.tool: p for p in placed}
        assert by_name['Read'].length > by_name['Edit'].length

    def test_bench_caps_tool_count(self):
        tools = [ToolBush(f't{i}', i + 1) for i in range(30)]
        placed = _bench_tools(tools)
        assert 0 < len(placed) < len(tools)
        assert placed[0].tool.count == 30

    def test_tools_fit_on_bench(self):
        box = _feature_boxes()['bench']
        tools = [ToolBush(f't{i}', 10 * (i + 1)) for i in range(12)]
        for p in _bench_tools(tools):
            assert box[0] <= p.x <= box[0] + box[2]
            assert box[1] <= p.y
            assert p.y + p.length <= box[1] + box[3]

    def test_tool_tooltip_in_svg(self):
        svg = render_plot_svg(_garden(tools=[ToolBush('Bash', 77)]))
        assert 'Bash: 77 calls' in svg

    def test_no_tools_still_renders_bench(self):
        assert 'class="bench"' in render_plot_svg(_garden(tools=[]))

    def test_replay_tools_lengthen_with_their_calls(self):
        svg = render_plot_timeline_svg(_timeline(n_days=6))
        tools = re.findall(r'<g class="tool">.*?</text></g>', svg)
        assert len(tools) == 2
        for tool in tools:
            ys = re.search(r'attributeName="y2"[^>]*values="([^"]+)"', tool)
            tips = [float(v) for v in ys.group(1).split(';')]
            assert tips == sorted(tips)
            assert tips[0] < tips[-1]

    def test_replay_tools_end_where_the_static_bench_does(self):
        tl = _timeline(n_days=6)
        final = [ToolBush(t, tl.tool_days[t][-1].count) for t in tl.tool_order]
        replay = render_plot_timeline_svg(tl)
        for placed in _bench_tools(final):
            tip = placed.y + placed.length - TOOL_HEAD_LEN
            assert re.search(
                rf'attributeName="y2"[^>]*values="[^"]*;{tip:.1f}"', replay
            )


class TestSundial:
    def test_peak_hour_has_longest_wedge(self):
        wedges = _sundial_wedges({9: 2, 14: 10, 23: 4})
        longest = max(wedges, key=lambda w: w.length)
        assert longest.hour == 14

    @pytest.mark.parametrize(('hour', 'night'), [(3, True), (14, False)])
    def test_night_hours_tinted(self, hour, night):
        wedge = _sundial_wedges({hour: 5})[0]
        assert wedge.night is night

    def test_empty_hours(self):
        assert _sundial_wedges({}) == []


class TestBarrel:
    def test_more_tokens_more_water(self):
        low = _barrel_water(100_000)
        high = _barrel_water(4_000_000)
        assert high.r > low.r

    def test_water_stays_inside_barrel(self):
        from ccgarden.render_plot import BARREL_CX, BARREL_CY, BARREL_R

        for tokens in (0, 1, 10**6, 10**10):
            w = _barrel_water(tokens)
            gap = math.hypot(w.cx - BARREL_CX, w.cy - BARREL_CY)
            assert gap + w.r < BARREL_R


class TestSignboard:
    def test_shows_totals(self):
        garden = _garden(branches=_even_branches(3))
        sign = _render_signboard(garden)
        total = sum(b.sessions for b in garden.branches)
        assert f'{total:,} sessions' in sign

    def test_timeline_sign_carries_date_label(self):
        svg = render_plot_timeline_svg(_timeline())
        assert 'class="signboard"' in svg
        assert 'id="plot-date"' in svg
        assert 'id="plot-sessions"' in svg
        assert '"3 sessions"' in svg

    def test_timeline_sign_reads_right_without_its_script(self):
        tl = _timeline(n_days=6)
        seeded = replace(
            tl, cumulative_sessions=[0, *tl.cumulative_sessions[1:]]
        )
        svg = render_plot_timeline_svg(seeded)
        label = re.search(r'id="plot-date"[^>]*>([^<]*)<', svg).group(1)
        assert label == 'Jan 2, 2026 to Jan 6, 2026'
        assert '>18 sessions</text>' in svg

    def test_replay_sign_counts_from_the_first_day(self):
        tl = _timeline(n_days=4)
        seeded = replace(
            tl, cumulative_sessions=[0, *tl.cumulative_sessions[1:]]
        )
        svg = render_plot_timeline_svg(seeded)
        days = re.findall(r'"([^"]*)"', re.search(r'var ds=\[(.*?)\]', svg)[1])
        assert days == [
            'Jan 1, 2026',
            'Jan 2, 2026',
            'Jan 2, 2026 to Jan 3, 2026',
            'Jan 2, 2026 to Jan 4, 2026',
        ]


# ── Life and motion ─────────────────────────────────────────


class TestMotion:
    @pytest.mark.parametrize(
        'keyframes', ['ccp-sway', 'ccp-flap', 'ccp-ripple', 'ccp-glow']
    )
    def test_keyframes_defined(self, keyframes):
        assert f'@keyframes {keyframes}' in render_plot_svg(_garden())

    def test_reduced_motion_respected(self):
        svg = render_plot_svg(_garden())
        assert '@media (prefers-reduced-motion:reduce)' in svg

    def test_legend_icons_hold_still(self):
        assert '.legend [class*="ccp-"]{animation:none}' in render_plot_svg(
            _garden()
        )

    @pytest.mark.parametrize('renderer', ['static', 'timeline'])
    def test_wind_never_shares_a_transform(self, renderer):
        svg = (
            render_plot_svg(_garden(skills=[SkillFruit('s', 4)]))
            if renderer == 'static'
            else render_plot_timeline_svg(_timeline())
        )
        for tag in re.findall(r'<[^>]*class="[^"]*ccp-[^>]*>', svg):
            assert ' transform=' not in tag, tag

    def test_plants_sway_out_of_step(self):
        garden = _garden(
            branches=[_branch(sessions=40, model_effort_counts=MIXED)]
        )
        svg = render_plot_svg(garden)
        variants = set(re.findall(r'href="#plant-\w+(-[bc])?"', svg))
        assert len(variants) > 1


class TestWeatherLife:
    def test_butterflies_on_a_good_day(self):
        garden = _garden(skills=[SkillFruit('s', 9)], vitality=1.0)
        assert 'class="butterfly"' in render_plot_svg(garden)

    def test_no_butterflies_in_a_lapse(self):
        garden = _garden(skills=[SkillFruit('s', 9)], vitality=0.1)
        assert 'class="butterfly"' not in render_plot_svg(garden)

    @pytest.mark.parametrize(
        ('nightness', 'present'), [(0.0, False), (0.8, True)]
    )
    def test_fireflies_at_night(self, nightness, present):
        svg = render_plot_svg(_garden(nightness=nightness))
        assert ('class="fireflies"' in svg) is present

    @pytest.mark.parametrize(
        ('vitality', 'present'), [(1.0, False), (0.1, True)]
    )
    def test_rain_ripples_in_a_lapse(self, vitality, present):
        svg = render_plot_svg(_garden(vitality=vitality))
        assert ('class="ccp-ripple"' in svg) is present

    def test_timeline_shadows_follow_the_sun(self):
        svg = render_plot_timeline_svg(_timeline())
        start = svg.index('<feOffset')
        assert (
            'attributeName="dx"' in svg[start : svg.index('</filter>', start)]
        )

    def test_timeline_weather_life_animated(self):
        tl = replace(_timeline(), daily_nightness=[0.0, 0.0, 0.9, 0.0, 0.0])
        svg = render_plot_timeline_svg(tl)
        assert 'class="fireflies"' in svg
        assert 'class="butterfly"' in svg


# ── Legend ─────────────────────────────────────────────────


def _legend(svg: str) -> str:
    start = svg.index('<g class="legend"')
    return svg[start : svg.index('<!--/legend-->', start)]


class TestLegend:
    @pytest.mark.parametrize(
        'label',
        [
            'Bed',
            'Flower',
            'Tools',
            'Sundial',
            'Butterflies',
            'Fireflies',
            'Rain, weeds',
            'Sprinklers',
        ],
    )
    def test_entry_present(self, label):
        assert f'>{label}<' in _legend(render_plot_svg(_garden()))

    def test_barrel_left_to_its_tooltip(self):
        assert 'Rain barrel' not in _legend(render_plot_svg(_garden()))

    def test_entries_fill_every_row(self):
        assert len(LEGEND_ENTRIES) % LEGEND_COLS == 0

    def test_icons_carry_no_tooltip(self):
        assert '<title>' not in _legend(render_plot_svg(_garden()))

    def test_plant_key_lists_every_combo_used(self):
        garden = _garden(branches=[_branch(model_effort_counts=MIXED)])
        legend = _legend(render_plot_svg(garden))
        assert '>Sonnet 5 · high<' in legend
        assert '>Opus 5 · max<' in legend

    def test_plant_icons_are_the_real_symbols_held_still(self):
        branch = _branch(model_effort_counts={'claude-opus-4-6 (low)': 3})
        legend = _legend(render_plot_svg(_garden(branches=[branch])))
        assert f'href="#plant-{TOP_OPUS}-still"' in legend
        assert f'>{SPECIES[TOP_OPUS].name}<' in legend

    def test_busiest_combo_gets_the_first_plant_and_heads_the_key(self):
        branch = _branch(
            model_effort_counts={
                'claude-opus-5 (low)': 2,
                'claude-opus-4-6 (low)': 9,
            }
        )
        svg = render_plot_svg(_garden(branches=[branch]))
        species = re.findall(
            r'class="legend-plant" data-species="([\w-]+)"', svg
        )
        assert species == list(FAMILY_POOLS['opus'][:2])

    def test_plant_key_shows_each_combos_share(self):
        branches = [
            _branch('a', model_effort_counts={'claude-opus-4-6 (low)': 3}),
            _branch('b', model_effort_counts={'claude-sonnet-5 (high)': 1}),
        ]
        legend = _legend(render_plot_svg(_garden(branches=branches)))
        name = re.escape(SPECIES[TOP_OPUS].name)
        assert re.search(rf'>{name}<tspan[^>]*> 75%</tspan>', legend)
        assert re.search(r'> 25%</tspan>', legend)

    def test_hovering_a_plant_key_dims_the_other_plants(self):
        branch = _branch(model_effort_counts=MIXED)
        svg = render_plot_svg(_garden(branches=[branch]))
        species = re.findall(r'class="legend-plant" data-species="(\w+)"', svg)
        assert len(species) == len(MIXED)
        for sp in species:
            assert (
                f'svg:has(.legend-plant[data-species="{sp}"]:hover)'
                f' .bed use[data-species]:not([data-species="{sp}"])'
            ) in svg
        garden_part = svg[: svg.index('<g class="legend"')]
        assert all(f'data-species="{sp}"' in garden_part for sp in species)

    def test_timeline_plants_carry_their_species(self):
        svg = render_plot_timeline_svg(
            _timeline(),
            repo_model_efforts={'test-repo': {'claude-opus-4-6 (low)': 9}},
        )
        assert f'data-species="{TOP_OPUS}"' in svg
        assert f'class="legend-plant" data-species="{TOP_OPUS}"' in svg

    def test_legend_grows_with_combos(self):
        few = _plot_layout(0, 2).total_h
        many = _plot_layout(0, 15).total_h
        assert many > few

    def test_still_symbols_have_no_wind(self):
        branch = _branch(model_effort_counts={'claude-opus-4-6 (low)': 3})
        svg = render_plot_svg(_garden(branches=[branch]))
        start = svg.index(f'id="plant-{TOP_OPUS}-still"')
        symbol = svg[start : svg.index('</symbol>', start)]
        assert 'ccp-' not in symbol

    def test_timeline_has_same_legend(self):
        svg = render_plot_timeline_svg(
            _timeline(),
            repo_model_efforts={'test-repo': {'claude-opus-4-6 (low)': 9}},
        )
        assert f'>{SPECIES[TOP_OPUS].name}<' in _legend(svg)


# ── Scrubber and poster ─────────────────────────────────────


class TestPlotScrubber:
    def test_scrubber_seeks_every_day(self):
        svg = render_plot_timeline_svg(_timeline(n_days=5))
        assert 'id="plot-scrubber"' in svg
        assert 'type="range"' in svg
        assert 'max="4"' in svg

    def test_scrubber_has_play_button(self):
        svg = render_plot_timeline_svg(_timeline())
        assert 'id="plot-play"' in svg

    def test_scrubber_sits_below_legend(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        legend_y = _plot_layout(len(tl.skill_order)).legend_y
        legend_bottom = legend_y + float(
            re.search(r'class="legend-bg"[^>]*height="([\d.]+)"', svg)[1]
        )
        y = float(re.search(r'id="plot-scrubber"[^>]*y="([\d.]+)"', svg)[1])
        assert y >= legend_bottom

    def test_autoplay_reveals_scrubber_after_replay(self):
        svg = render_plot_timeline_svg(_timeline())
        assert 'setTimeout(reveal' in svg

    def test_poster_starts_paused_on_final_day(self):
        svg = render_plot_timeline_svg(_timeline(), start_paused_at_end=True)
        assert 'setTimeout(reveal' not in svg
        assert 'seek(kt.length-1)' in svg

    def test_static_has_no_scrubber(self):
        assert 'plot-scrubber' not in render_plot_svg(_garden())


# ── Model family detection ──────────────────────────────────────


class TestModelFamily:
    @pytest.mark.parametrize(
        ('label', 'expected'),
        [
            ('claude-haiku-4-5-20251001', 'haiku'),
            ('claude-sonnet-5 (high)', 'sonnet'),
            ('claude-opus-4-6 (low)', 'opus'),
            ('claude-opus-5 (low)', 'opus'),
            ('<synthetic>', 'unknown'),
            ('some-other-model', 'unknown'),
        ],
    )
    def test_family_detection(self, label, expected):
        assert model_family(label) == expected


class TestPlantSpecs:
    def test_specs_from_model_effort_counts(self):
        branch = _branch(
            model_effort_counts={
                'claude-sonnet-5 (high)': 100,
                'claude-opus-5 (low)': 50,
            }
        )
        specs = _plant_specs(branch)
        assert len(specs) == 2
        families = {s.model_family for s in specs}
        assert families == {'sonnet', 'opus'}

    def test_empty_counts(self):
        branch = _branch(model_effort_counts={})
        specs = _plant_specs(branch)
        assert specs == []


# ── Tooltips ──────────────────────────────────────────────────


class TestBedTooltip:
    def test_basic_fields(self):
        branch = _branch(
            'my-repo',
            sessions=42,
            lines_added=500,
            lines_removed=30,
        )
        tt = _bed_tooltip(branch)
        assert 'my-repo' in tt
        assert '42 sessions' in tt
        assert '+500/-30' in tt

    def test_tokens_without_cost(self):
        branch = _branch(
            input_tokens=50000,
            output_tokens=10000,
            cost=3.50,
        )
        tt = _bed_tooltip(branch)
        assert '60k tokens' in tt
        assert '$' not in tt

    def test_one_line_per_item(self):
        branch = _branch(
            'my-repo',
            sessions=42,
            input_tokens=50000,
            model_effort_counts=MIXED,
        )
        lines = _bed_tooltip(branch).split('\n')
        assert lines[0] == 'my-repo'
        assert lines[1] == '42 sessions'
        assert len(lines) == 4 + len(MIXED)

    def test_plant_lines_are_listed_for_their_icons(self):
        branch = _branch(model_effort_counts=MIXED)
        svg = render_plot_svg(_garden(branches=[branch]))
        plants = re.search(r'class="bed" data-plants="([^"]*)"', svg)[1]
        species = [p.split(' ')[0] for p in plants.split(',')]
        assert len(species) == len(MIXED)
        assert all(f'id="plant-{s}-still"' in svg for s in species)

    def test_tooltip_draws_plant_icons(self):
        svg = render_plot_svg(_garden())
        script = svg[svg.index('id="plot-tooltip"') :]
        assert 'data-plants' in script
        assert '-still' in script

    def test_model_breakdown(self):
        branch = _branch(
            model_effort_counts={
                'claude-sonnet-5 (high)': 80,
                'claude-opus-5 (low)': 20,
            }
        )
        tt = _bed_tooltip(branch)
        assert 'Sonnet 5 · high' in tt
        assert SPECIES[TOP_SONNET].name in tt
        assert '80%' in tt


# ── Furrows ───────────────────────────────────────────────────


class TestFurrowDepth:
    @pytest.mark.parametrize(
        ('lines', 'expected_range'),
        [
            (0, (0.0, 0.0)),
            (100, (0.1, 0.3)),
            (5000, (1.0, 1.0)),
            (500_000, (1.0, 1.0)),
        ],
    )
    def test_furrow_depth_scaling(self, lines, expected_range):
        lo, hi = expected_range
        assert lo <= _furrow_depth(lines) <= hi


def _furrow_bed(w=200.0, h=160.0, lines_added=3000) -> BedRect:
    return _bed(
        w=w,
        h=h,
        sessions=50,
        lines_added=lines_added,
        model_effort_counts=MIXED,
    )


def _dist_to_segment(px, py, f) -> float:
    dx, dy = f.x2 - f.x1, f.y2 - f.y1
    length_sq = dx * dx + dy * dy
    t = 0.0
    if length_sq:
        t = ((px - f.x1) * dx + (py - f.y1) * dy) / length_sq
    t = min(max(t, 0.0), 1.0)
    return math.dist((px, py), (f.x1 + t * dx, f.y1 + t * dy))


class TestFurrowsFollowRows:
    @pytest.mark.parametrize(
        ('w', 'h'), [(200.0, 160.0), (400.0, 90.0), (90.0, 400.0)]
    )
    def test_every_plant_sits_in_a_furrow(self, w, h):
        bed = _furrow_bed(w, h)
        furrows = _bed_furrows(bed, 50)
        assert furrows
        for p in _plant_layout(bed, 50):
            nearest = min(_dist_to_segment(p.x, p.y, f) for f in furrows)
            assert nearest <= 0.1 * PLANT_MAX_SPACING

    @pytest.mark.parametrize(
        ('w', 'h', 'vertical'),
        [(400.0, 70.0, False), (120.0, 400.0, True)],
    )
    def test_furrows_run_along_the_strip(self, w, h, vertical):
        for f in _bed_furrows(_furrow_bed(w, h), 50):
            if vertical:
                assert f.x1 == pytest.approx(f.x2)
            else:
                assert f.y1 == pytest.approx(f.y2)

    def test_furrows_stay_in_the_soil(self):
        bed = _furrow_bed()
        sx, sy, sw, sh = _soil_rect(bed)
        for f in _bed_furrows(bed, 50):
            for x, y in ((f.x1, f.y1), (f.x2, f.y2)):
                assert sx <= x <= sx + sw
                assert sy <= y <= sy + sh

    def test_untilled_bed_has_no_furrows(self):
        assert _bed_furrows(_furrow_bed(lines_added=0), 50) == []

    def test_static_render_draws_furrows(self):
        svg = render_plot_svg(_garden())
        assert 'class="furrow"' in svg


# ── Weeds (dormancy) ─────────────────────────────────────────


def _vitality_after(days: float) -> float:
    return 0.5 ** (days / DORMANCY_HALF_LIFE_DAYS)


class TestWeedCount:
    @pytest.mark.parametrize(
        ('days', 'expected'),
        [
            (0, 0),
            (WEED_ONSET_DAYS - 0.5, 0),
            (WEED_ONSET_DAYS, 1),
            (WEED_FULL_DAYS, WEED_MAX),
            (90, WEED_MAX),
        ],
    )
    def test_weeds_keyed_to_days_away(self, days, expected):
        assert _weed_count(_vitality_after(days)) == expected

    def test_grows_with_days_away(self):
        counts = [
            _weed_count(_vitality_after(d)) for d in range(WEED_FULL_DAYS + 1)
        ]
        assert counts == sorted(counts)

    def test_the_shortest_real_lapse_grows_weeds(self):
        longest_away = DORMANCY_MIN_GAP_DAYS - 1
        assert _weed_count(_vitality_after(longest_away)) >= 1


class TestWeedsInSvg:
    def test_no_weeds_at_full_vitality(self):
        garden = _garden(vitality=1.0)
        svg = render_plot_svg(garden)
        garden_part = svg[: svg.index('<g class="legend"')]
        assert 'href="#plant-weed"' not in garden_part

    def test_weeds_appear_at_low_vitality(self):
        garden = _garden(vitality=0.3)
        svg = render_plot_svg(garden)
        assert 'plant-weed' in svg

    @pytest.mark.parametrize('soil', [SOIL_COLOR, SOIL_DORMANT])
    def test_weeds_stand_out_from_the_soil(self, soil):
        assert abs(_luma(WEED_COLOR) - _luma(soil)) > 40

    def test_weeds_flower_like_dandelions(self):
        svg = render_plot_svg(_garden(vitality=0.3))
        start = svg.index('<symbol id="plant-weed"')
        weed = svg[start : svg.index('</symbol>', start)]
        assert f'fill="{WEED_FLOWER}"' in weed

    def test_replay_grows_weeds_in_a_lapse_and_pulls_them_after(self):
        tl = replace(
            _timeline(n_days=6),
            daily_vitality=[1.0, 1.0, 0.2, 0.1, 1.0, 1.0],
        )
        grows = _grow_scales(render_plot_timeline_svg(tl), 'weed-grow')
        assert grows
        assert any(max(scales) == 1 for scales in grows)
        for scales in grows:
            assert scales[0] == 0
            assert scales[-1] == 0

    def test_no_replay_weeds_without_a_lapse(self):
        svg = render_plot_timeline_svg(_timeline())
        assert 'class="weed-grow"' not in svg

    def test_worse_lapse_grows_more_weeds(self):
        def grown(vitality: float) -> int:
            tl = replace(
                _timeline(n_days=4), daily_vitality=[1.0, vitality, 1.0, 1.0]
            )
            svg = render_plot_timeline_svg(tl)
            return sum(
                max(scales) == 1 for scales in _grow_scales(svg, 'weed-grow')
            )

        assert grown(0.0) > grown(0.6) > 0

    def test_weed_symbol_defined(self):
        garden = _garden(vitality=0.3)
        svg = render_plot_svg(garden)
        assert 'id="plant-weed"' in svg


# ── Stepping stones ──────────────────────────────────────────


class TestPointInAnyBed:
    def test_inside(self):
        from ccgarden.render_plot import BedRect

        bed = BedRect('r', 10, 10, 50, 50, _branch())
        assert _point_in_any_bed(35, 35, [bed])

    def test_outside(self):
        from ccgarden.render_plot import BedRect

        bed = BedRect('r', 10, 10, 50, 50, _branch())
        assert not _point_in_any_bed(100, 100, [bed])


# ── Tap tooltip ──────────────────────────────────────────────────


class TestTapTooltip:
    def test_tooltip_group_present(self):
        svg = render_plot_svg(_garden())
        assert 'id="plot-tooltip"' in svg

    def test_tooltip_script_present(self):
        svg = render_plot_svg(_garden())
        assert '<script>' in svg or '<script><![CDATA[' in svg

    def test_tooltip_finds_title(self):
        svg = render_plot_svg(_garden())
        assert 'findTooltip' in svg


# ── Dark theme ───────────────────────────────────────────────────


class TestDarkTheme:
    def test_dark_media_query_present(self):
        svg = render_plot_svg(_garden())
        assert '@media (prefers-color-scheme:dark)' in svg

    def test_dark_outer_frame_class(self):
        svg = render_plot_svg(_garden())
        assert 'class="plot-frame"' in svg

    def test_dark_legend_class(self):
        svg = render_plot_svg(_garden())
        assert 'class="legend-bg"' in svg

    def test_dark_legend_inner_class(self):
        svg = render_plot_svg(_garden())
        assert 'class="legend-inner"' in svg

    def test_dark_tooltip_styles(self):
        svg = render_plot_svg(_garden())
        assert '#plot-tooltip-box{' in svg

    def test_style_block_present(self):
        svg = render_plot_svg(_garden())
        assert '<style>' in svg


# ── SVG output ──────────────────────────────────────────────────


class TestWellFormed:
    @pytest.mark.parametrize('vitality', [1.0, 0.2])
    def test_static_parses_as_xml(self, vitality):
        garden = _garden(
            branches=_even_branches(5),
            skills=[SkillFruit('s', 3)],
            tools=[ToolBush('Read', 40)],
            hour_counts={9: 3, 22: 5},
            vitality=vitality,
            nightness=0.6,
        )
        ET.fromstring(render_plot_svg(garden))  # noqa: S314 -- our own output

    def test_timeline_parses_as_xml(self):
        svg = render_plot_timeline_svg(_timeline())
        ET.fromstring(svg)  # noqa: S314 -- our own output


def _dangling_refs(svg: str) -> set[str]:
    refs = set(re.findall(r'url\(#([\w-]+)\)', svg))
    refs |= set(re.findall(r'href="#([\w-]+)"', svg))
    ids = set(re.findall(r'\bid="([\w-]+)"', svg))
    return refs - ids


class TestReferencesResolve:
    def test_static(self):
        garden = _garden(
            branches=_even_branches(4),
            tools=[ToolBush('Read', 40), ToolBush('Edit', 9)],
            skills=[SkillFruit('s', 3)],
            hour_counts={9: 3, 22: 5},
            vitality=0.2,
        )
        assert _dangling_refs(render_plot_svg(garden)) == set()

    def test_timeline(self):
        assert _dangling_refs(render_plot_timeline_svg(_timeline())) == set()


class TestRenderPlotSvg:
    def test_produces_valid_svg(self):
        garden = _garden(
            branches=[
                _branch('repo-a', lines_added=3000, sessions=50),
                _branch('repo-b', lines_added=1000, sessions=20),
            ]
        )
        svg = render_plot_svg(garden)
        assert svg.startswith('<svg')
        assert '</svg>' in svg

    def test_contains_fence(self):
        svg = render_plot_svg(_garden())
        assert 'fence' in svg.lower() or 'rect' in svg

    def test_contains_repo_names(self):
        garden = _garden(branches=[_branch('my-project', lines_added=1000)])
        svg = render_plot_svg(garden)
        assert 'my-project' in svg

    def test_contains_stepping_stones(self):
        garden = _garden(
            branches=[
                _branch('repo-a', lines_added=3000, sessions=50),
                _branch('repo-b', lines_added=1000, sessions=20),
            ]
        )
        svg = render_plot_svg(garden)
        assert 'class="stone"' in svg

    def test_bed_tooltip_in_svg(self):
        garden = _garden(
            branches=[
                _branch('my-repo', sessions=42, lines_added=500),
            ]
        )
        svg = render_plot_svg(garden)
        assert '42 sessions' in svg


# ── Timeline animation ─────────────────────────────────────────


class TestPlotTimeline:
    def test_produces_valid_svg(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        assert svg.startswith('<svg')
        assert '</svg>' in svg

    def test_contains_animate_tags(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        assert '<animate' in svg

    def test_beds_present(self):
        tl = _timeline(repos=['repo-a', 'repo-b'])
        svg = render_plot_timeline_svg(tl)
        assert 'repo-a' in svg
        assert 'repo-b' in svg

    def test_bed_opacity_animated(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        assert 'attributeName="opacity"' in svg

    def test_barrel_animated(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        assert 'class="barrel"' in svg

    def test_date_label_present(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        assert 'class="date-label"' in svg

    def test_dark_theme_in_timeline(self):
        tl = _timeline()
        svg = render_plot_timeline_svg(tl)
        assert '@media (prefers-color-scheme:dark)' in svg

    def test_single_day_no_crash(self):
        tl = _timeline(n_days=1)
        svg = render_plot_timeline_svg(tl)
        assert '<svg' in svg


# ── Test helpers ────────────────────────────────────────────────


def _branch(
    repo: str = 'test-repo',
    *,
    sessions: int = 10,
    lines_added: int = 100,
    lines_removed: int = 0,
    output_tokens: int = 0,
    input_tokens: int = 0,
    cost: float = 0.0,
    prompts: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    model_effort_counts: dict[str, int] | None = None,
    idle_days: int | None = None,
) -> RepoBranch:
    return RepoBranch(
        repo=repo,
        sessions=sessions,
        lines_added=lines_added,
        lines_removed=lines_removed,
        output_tokens=output_tokens,
        input_tokens=input_tokens,
        cost=cost,
        prompts=prompts,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        model_effort_counts=model_effort_counts or {},
        idle_days=idle_days,
    )


def _garden(
    *,
    branches: list[RepoBranch] | None = None,
    tools: list[ToolBush] | None = None,
    skills: list[SkillFruit] | None = None,
    total_tokens: int = 100_000,
    hour_counts: dict[int, int] | None = None,
    nightness: float = 0.0,
    vitality: float = 1.0,
) -> GardenData:
    return GardenData(
        rings=[],
        branches=branches or [_branch()],
        tools=tools or [],
        skills=skills or [],
        total_tokens=total_tokens,
        hour_counts=hour_counts or {},
        nightness=nightness,
        vitality=vitality,
    )


def _timeline(
    *,
    n_days: int = 5,
    repos: list[str] | None = None,
) -> GardenTimeline:
    repos = repos or ['test-repo']
    days = [f'2026-01-{d + 1:02d}' for d in range(n_days)]
    daily_sessions = [3] * n_days
    cumulative_sessions = [3 * (i + 1) for i in range(n_days)]
    branch_days: dict[str, list[RepoBranchDay]] = {}
    for repo in repos:
        branch_days[repo] = [
            RepoBranchDay(
                day=d,
                sessions=3 * (i + 1),
                lines_added=100 * (i + 1),
                lines_removed=10 * (i + 1),
                output_tokens=5000 * (i + 1),
                input_tokens=20000 * (i + 1),
                cost=0.50 * (i + 1),
            )
            for i, d in enumerate(days)
        ]
    cumulative_tokens = [25000 * (i + 1) * len(repos) for i in range(n_days)]
    return GardenTimeline(
        days=days,
        daily_sessions=daily_sessions,
        cumulative_sessions=cumulative_sessions,
        branch_order=repos,
        branch_days=branch_days,
        cumulative_total_tokens=cumulative_tokens,
        daily_nightness=[0.0] * n_days,
        daily_vitality=[1.0] * n_days,
        tool_order=['Read', 'Edit'],
        tool_days={
            'Read': [
                ToolUsageDay(d, 10 * (i + 1)) for i, d in enumerate(days)
            ],
            'Edit': [ToolUsageDay(d, 5 * (i + 1)) for i, d in enumerate(days)],
        },
        skill_order=['code-review'],
        skill_days={
            'code-review': [
                SkillUsageDay(d, i + 1) for i, d in enumerate(days)
            ],
        },
        hour_counts={10: 5, 14: 8, 16: 3},
    )


def test_butterflies_roam_the_whole_fenced_garden():
    garden_h = FENCE_Y + FENCE_H + 80
    css = _butterfly_keyframes(30, garden_h)
    ys = [
        float(y) for y in re.findall(r'translate\([\d.]+px,([\d.]+)px\)', css)
    ]
    assert min(ys) >= BED_ZONE_Y
    assert max(ys) <= garden_h
    assert min(ys) < FENCE_Y + FENCE_H / 3


# ── Sprinklers ──────────────────────────────────────────────


def _garden_part(svg: str) -> str:
    return svg[: svg.index('<g class="legend"')]


class TestSprinklers:
    @pytest.mark.parametrize(
        ('idle', 'expected'),
        [
            (None, 0.0),
            (0, 1.0),
            (SPRINKLER_DAYS // 2, 0.5),
            (SPRINKLER_DAYS - 1, 1 / SPRINKLER_DAYS),
            (SPRINKLER_DAYS, 0.0),
            (SPRINKLER_DAYS * 3, 0.0),
        ],
    )
    def test_strength_fades_over_the_window(self, idle, expected):
        assert _sprinkler_strength(idle) == pytest.approx(expected)

    def test_scale_is_zero_only_when_off(self):
        assert _sprinkler_scale(0.0) == 0
        assert 0 < _sprinkler_scale(0.01) < _sprinkler_scale(0.5)
        assert _sprinkler_scale(1.0) == 1

    @pytest.mark.parametrize(
        ('w', 'h'),
        [(40.0, 40.0), (60.0, 200.0), (200.0, 160.0), (700.0, 500.0)],
    )
    def test_spray_reaches_every_part_of_the_soil(self, w, h):
        bed = _bed(w=w, h=h)
        sx, sy, sw, sh = _soil_rect(bed)
        grid = _sprinkler_grid(bed)
        steps = 12
        for i in range(steps + 1):
            for j in range(steps + 1):
                px, py = sx + sw * i / steps, sy + sh * j / steps
                assert any(
                    math.hypot(px - hx, py - hy) <= grid.reach + 1e-6
                    for hx, hy in grid.heads
                ), (px, py)

    @pytest.mark.parametrize(
        ('w', 'h'),
        [(40.0, 40.0), (60.0, 200.0), (200.0, 160.0), (700.0, 500.0)],
    )
    def test_heads_stand_in_the_soil(self, w, h):
        bed = _bed(w=w, h=h)
        sx, sy, sw, sh = _soil_rect(bed)
        for hx, hy in _sprinkler_grid(bed).heads:
            assert sx < hx < sx + sw
            assert sy < hy < sy + sh

    def test_a_big_bed_gets_several_heads_but_not_a_carpet(self):
        assert len(_sprinkler_grid(_bed(w=40.0, h=40.0)).heads) == 1
        big = _sprinkler_grid(_bed(w=700.0, h=500.0)).heads
        assert 1 < len(big) <= SPRINKLER_MAX_HEADS

    def test_spray_is_clipped_to_the_soil(self):
        svg = render_plot_svg(_garden(branches=[_branch(idle_days=0)]))
        m = re.search(
            r'<g class="sprinkler"[^>]*clip-path="url\(#([\w-]+)\)"', svg
        )
        assert m
        assert f'<clipPath id="{m.group(1)}">' in svg

    @pytest.mark.parametrize(
        ('idle', 'wet'),
        [(0, 0.55), (SPRINKLER_DAYS // 2, 0.275), (SPRINKLER_DAYS, None)],
    )
    def test_soil_is_wet_after_work_and_dries_out(self, idle, wet):
        svg = render_plot_svg(_garden(branches=[_branch(idle_days=idle)]))
        m = re.search(r'class="bed-wet"[^>]*opacity="([\d.]+)"', svg)
        if wet is None:
            assert m is None
        else:
            assert m
            assert float(m.group(1)) == pytest.approx(wet)

    def test_wet_soil_sits_under_the_plants(self):
        svg = render_plot_svg(_garden(branches=[_branch(idle_days=0)]))
        assert svg.index('class="bed-wet"') < svg.index('data-species=')

    def test_replay_soil_dries_between_visits(self):
        tl = replace(
            _timeline(n_days=4),
            branch_idle_days={
                'test-repo': [None, 0, SPRINKLER_DAYS // 2, SPRINKLER_DAYS]
            },
        )
        svg = render_plot_timeline_svg(tl)
        m = re.search(
            r'class="bed-wet"[^>]*><animate attributeName="opacity"'
            r'[^>]*values="([^"]+)"',
            svg,
        )
        assert m
        values = [float(v) for v in m.group(1).split(';')]
        assert values[0] == 0
        assert values[1] == pytest.approx(0.55)
        assert values[-1] == 0

    @pytest.mark.parametrize(
        ('idle', 'watered'),
        [
            (0, True),
            (SPRINKLER_DAYS - 1, True),
            (SPRINKLER_DAYS, False),
            (None, False),
        ],
    )
    def test_static_bed_is_watered_when_recently_worked(self, idle, watered):
        svg = render_plot_svg(_garden(branches=[_branch(idle_days=idle)]))
        assert ('class="sprinkler"' in _garden_part(svg)) is watered

    def test_spray_shrinks_as_the_work_goes_stale(self):
        def reach(idle: int) -> float:
            svg = render_plot_svg(_garden(branches=[_branch(idle_days=idle)]))
            m = re.search(
                r'class="sprinkler-reach"[^>]*\br="([\d.]+)"',
                _garden_part(svg),
            )
            assert m
            return float(m.group(1))

        assert (
            reach(0) > reach(SPRINKLER_DAYS // 2) > reach(SPRINKLER_DAYS - 1)
        )

    def test_spray_turns_on_its_own_clock(self):
        svg = render_plot_svg(_garden(branches=[_branch(idle_days=0)]))
        assert '@keyframes ccp-spin' in svg
        assert 'class="ccp-spin"' in _garden_part(svg)

    def test_legend_sprinkler_holds_still(self):
        legend = _legend(render_plot_svg(_garden()))
        assert 'class="ccp-spin"' not in legend

    def test_replay_turns_on_when_worked_and_off_after_the_window(self):
        tl = replace(
            _timeline(n_days=4),
            branch_idle_days={
                'test-repo': [None, 0, SPRINKLER_DAYS // 2, SPRINKLER_DAYS]
            },
        )
        heads = _grow_scales(render_plot_timeline_svg(tl), 'sprinkler-grow')
        assert heads
        assert all(h == heads[0] for h in heads)
        scales = heads[0]
        assert scales[0] == 0
        assert scales[1] == 1
        assert 0 < scales[2] < 1
        assert scales[3] == 0

    def test_no_replay_sprinkler_without_idle_data(self):
        svg = render_plot_timeline_svg(_timeline())
        assert 'sprinkler-grow' not in svg
        assert 'bed-wet' not in svg

    def test_no_replay_sprinkler_for_a_bed_never_recently_worked(self):
        tl = replace(
            _timeline(n_days=3),
            branch_idle_days={'test-repo': [None, SPRINKLER_DAYS, 40]},
        )
        assert 'sprinkler-grow' not in render_plot_timeline_svg(tl)

    @pytest.mark.parametrize(
        ('idle', 'line'),
        [
            (0, 'worked today'),
            (1, 'last worked yesterday'),
            (5, 'last worked 5 days ago'),
        ],
    )
    def test_tooltip_says_when_the_bed_was_last_worked(self, idle, line):
        assert line in _bed_tooltip(_branch(idle_days=idle)).split('\n')

    def test_tooltip_is_silent_without_idle_data(self):
        assert 'worked' not in _bed_tooltip(_branch())

    def test_replay_tooltip_uses_the_last_frame(self):
        tl = replace(
            _timeline(n_days=3),
            branch_idle_days={'test-repo': [None, 0, 2]},
        )
        assert 'last worked 2 days ago' in render_plot_timeline_svg(tl)

    def test_references_resolve_with_sprinklers(self):
        svg = render_plot_svg(_garden(branches=[_branch(idle_days=0)]))
        assert _dangling_refs(svg) == set()
        ET.fromstring(svg)  # noqa: S314 -- our own output
