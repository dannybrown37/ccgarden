"""Tests for the top-down garden plot renderer."""

from __future__ import annotations

import pytest

from ccgarden.data import (
    GardenData,
    RepoBranch,
    SkillFruit,
    ToolBush,
)
from ccgarden.render_plot import (
    _bed_area_metric,
    _bed_tooltip,
    _furrow_count,
    _layout_beds,
    _model_family,
    _plant_specs,
    _point_in_any_bed,
    _squarify,
    _weed_count,
    render_plot_svg,
)


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
        assert _model_family(label) == expected


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

    def test_tokens_and_cost(self):
        branch = _branch(
            input_tokens=50000,
            output_tokens=10000,
            cost=3.50,
        )
        tt = _bed_tooltip(branch)
        assert '60k tokens' in tt
        assert '$3.50' in tt

    def test_model_breakdown(self):
        branch = _branch(
            model_effort_counts={
                'claude-sonnet-5 (high)': 80,
                'claude-opus-5 (low)': 20,
            }
        )
        tt = _bed_tooltip(branch)
        assert 'sonnet-5' in tt
        assert '80%' in tt


# ── Furrows ───────────────────────────────────────────────────


class TestFurrowCount:
    @pytest.mark.parametrize(
        ('lines', 'expected_range'),
        [
            (0, (0, 0)),
            (100, (1, 3)),
            (5000, (7, 8)),
        ],
    )
    def test_furrow_scaling(self, lines, expected_range):
        lo, hi = expected_range
        assert lo <= _furrow_count(lines) <= hi


# ── Weeds (dormancy) ─────────────────────────────────────────


class TestWeedCount:
    @pytest.mark.parametrize(
        ('vitality', 'expected_range'),
        [
            (1.0, (0, 0)),
            (0.9, (0, 0)),
            (0.6, (1, 3)),
            (0.3, (3, 6)),
            (0.0, (5, 8)),
        ],
    )
    def test_weed_scaling(self, vitality, expected_range):
        lo, hi = expected_range
        assert lo <= _weed_count(vitality) <= hi


class TestWeedsInSvg:
    def test_no_weeds_at_full_vitality(self):
        garden = _garden(vitality=1.0)
        svg = render_plot_svg(garden)
        assert 'href="#plant-weed"' not in svg

    def test_weeds_appear_at_low_vitality(self):
        garden = _garden(vitality=0.3)
        svg = render_plot_svg(garden)
        assert 'plant-weed' in svg

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


# ── SVG output ──────────────────────────────────────────────────


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
        assert 'ellipse' in svg

    def test_bed_tooltip_in_svg(self):
        garden = _garden(
            branches=[
                _branch('my-repo', sessions=42, lines_added=500),
            ]
        )
        svg = render_plot_svg(garden)
        assert '42 sessions' in svg


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
