from __future__ import annotations

import math
import random

import pytest

from ccgarden.render_utils import (
    DORMANT_FRAME_DWELL,
    EASE_IN_OUT_SPLINE,
    NIGHTNESS_SATURATION,
    RECOVERY_FRAME_DWELL,
    TIMELINE_MAX_DURATION_S,
    TIMELINE_MIN_DURATION_S,
    TIMELINE_PER_DAY_SECONDS,
    _animate_tag,
    _animate_transform_tag,
    _blend_hex,
    _blob_path,
    _collapse_keyframes,
    _escape_xml,
    _exact_days_away,
    _format_day,
    _frame_weights,
    _key_times,
    _lerp_hex,
    _rain_intensity,
    _rain_opacity,
    _saturated_nightness,
    _spline_attrs,
    _sun_storm_opacity,
    _timeline_duration,
    _title,
    _tt_attr,
    _weather_load,
    _weighted_key_times,
)


# ── XML helpers ──────────────────────────────────────────────────────


class TestEscapeXml:
    @pytest.mark.parametrize(
        ('inp', 'expected'),
        [
            ('hello', 'hello'),
            ('<b>', '&lt;b&gt;'),
            ('a & b', 'a &amp; b'),
            ('<&>', '&lt;&amp;&gt;'),
        ],
    )
    def test_escapes(self, inp, expected):
        assert _escape_xml(inp) == expected


class TestTitle:
    def test_wraps_in_title_tag(self):
        assert _title('foo') == '<title>foo</title>'

    def test_escapes_special_chars(self):
        result = _title('<script>')
        assert '&lt;' in result
        assert '<script>' not in result


class TestTtAttr:
    def test_returns_data_tt_attribute(self):
        result = _tt_attr(['Day 1', 'Day 2'])
        assert result.startswith("data-tt='")
        assert result.endswith("'")

    def test_escapes_special_chars(self):
        result = _tt_attr(["it's <hot>"])
        assert '&lt;' in result
        assert '&apos;' in result


class TestFormatDay:
    def test_formats_iso_date(self):
        assert _format_day('2026-01-15') == 'Jan 15, 2026'

    def test_returns_input_on_bad_date(self):
        assert _format_day('not-a-date') == 'not-a-date'


# ── Color helpers ────────────────────────────────────────────────────


class TestBlendHex:
    def test_full_vitality_returns_living(self):
        assert _blend_hex('#000000', '#ffffff', 1.0) == '#ffffff'

    def test_zero_vitality_returns_dormant(self):
        assert _blend_hex('#000000', '#ffffff', 0.0) == '#000000'

    def test_midpoint(self):
        result = _blend_hex('#000000', '#ffffff', 0.5)
        r = int(result[1:3], 16)
        assert 126 <= r <= 128

    def test_clamps_above_one(self):
        assert _blend_hex('#000000', '#ffffff', 1.5) == '#ffffff'


class TestLerpHex:
    def test_fraction_zero_returns_start(self):
        assert _lerp_hex('#ff0000', '#0000ff', 0.0) == '#ff0000'

    def test_fraction_one_returns_end(self):
        assert _lerp_hex('#ff0000', '#0000ff', 1.0) == '#0000ff'

    def test_midpoint(self):
        result = _lerp_hex('#000000', '#ffffff', 0.5)
        r = int(result[1:3], 16)
        assert 126 <= r <= 128


# ── Shape helpers ────────────────────────────────────────────────────


class TestBlobPath:
    def test_returns_closed_path(self):
        rng = random.Random(42)
        path = _blob_path(100, 100, 50, rng)
        assert path.startswith('M ')
        assert path.endswith('Z')

    def test_contains_quadratic_curves(self):
        rng = random.Random(42)
        path = _blob_path(100, 100, 50, rng)
        assert 'Q ' in path

    def test_deterministic(self):
        p1 = _blob_path(100, 100, 50, random.Random(42))
        p2 = _blob_path(100, 100, 50, random.Random(42))
        assert p1 == p2

    def test_custom_points(self):
        rng = random.Random(42)
        path = _blob_path(100, 100, 50, rng, points=5)
        assert path.count('Q ') == 5


# ── Weather / rain helpers ───────────────────────────────────────────


class TestSaturatedNightness:
    def test_zero(self):
        assert _saturated_nightness(0.0) == 0.0

    def test_at_saturation(self):
        assert _saturated_nightness(NIGHTNESS_SATURATION) == 1.0

    def test_above_saturation_clamps(self):
        assert _saturated_nightness(1.0) == 1.0


class TestExactDaysAway:
    def test_full_vitality(self):
        assert _exact_days_away(1.0) == 0.0

    def test_zero_vitality(self):
        assert _exact_days_away(0.0) == math.inf


class TestRainIntensity:
    def test_full_vitality_no_rain(self):
        assert _rain_intensity(1.0) == 0.0

    def test_zero_vitality_full_rain(self):
        assert _rain_intensity(0.0) == 1.0


class TestRainOpacity:
    def test_full_vitality_zero_opacity(self):
        assert _rain_opacity(1.0) == 0.0

    def test_proportional_to_intensity(self):
        assert _rain_opacity(0.0) > 0.0


class TestSunStormOpacity:
    def test_clear_weather(self):
        assert _sun_storm_opacity(1.0) == 1.0

    def test_full_storm(self):
        assert _sun_storm_opacity(0.0) < 1.0


class TestWeatherLoad:
    def test_clear_day(self):
        assert _weather_load(0.0, 1.0) == 0.0

    def test_increases_with_night(self):
        assert _weather_load(0.3, 1.0) > _weather_load(0.0, 1.0)

    def test_increases_with_dormancy(self):
        assert _weather_load(0.0, 0.1) > _weather_load(0.0, 1.0)


# ── Animation / timeline helpers ────────────────────────────────────


class TestTimelineDuration:
    def test_minimum(self):
        assert _timeline_duration(1.0) == TIMELINE_MIN_DURATION_S

    def test_maximum(self):
        assert _timeline_duration(1000.0) == TIMELINE_MAX_DURATION_S

    def test_proportional_in_range(self):
        days = 10.0
        result = _timeline_duration(days)
        assert result == days * TIMELINE_PER_DAY_SECONDS


class TestKeyTimes:
    def test_single(self):
        assert _key_times(1) == [0.0]

    def test_two(self):
        assert _key_times(2) == [0.0, 1.0]

    def test_three(self):
        result = _key_times(3)
        assert result[0] == 0.0
        assert result[-1] == 1.0
        assert abs(result[1] - 0.5) < 1e-9


class TestFrameWeights:
    def test_all_active_weight_one(self):
        weights = _frame_weights([1, 2, 3])
        assert all(w >= 1.0 for w in weights)

    def test_dormant_frame_weighted(self):
        weights = _frame_weights([1, 0, 1])
        assert weights[0] >= DORMANT_FRAME_DWELL

    def test_recovery_frame_weighted(self):
        weights = _frame_weights([0, 1])
        assert weights[0] >= RECOVERY_FRAME_DWELL


class TestWeightedKeyTimes:
    def test_single_day(self):
        assert _weighted_key_times([5]) == [0.0]

    def test_starts_zero_ends_one(self):
        result = _weighted_key_times([1, 2, 3, 4])
        assert result[0] == 0.0
        assert abs(result[-1] - 1.0) < 1e-9


class TestCollapseKeyframes:
    def test_no_collapse_different_values(self):
        vals = ['a', 'b', 'c']
        times = [0.0, 0.5, 1.0]
        out_v, out_t = _collapse_keyframes(vals, times)
        assert out_v == vals
        assert out_t == times

    def test_collapses_run(self):
        vals = ['a', 'a', 'a', 'b']
        times = [0.0, 0.25, 0.5, 1.0]
        out_v, out_t = _collapse_keyframes(vals, times)
        assert out_v == ['a', 'a', 'b']
        assert out_t == [0.0, 0.5, 1.0]

    def test_short_list_unchanged(self):
        vals = ['a', 'b']
        times = [0.0, 1.0]
        out_v, _out_t = _collapse_keyframes(vals, times)
        assert out_v == vals


class TestSplineAttrs:
    def test_linear_when_not_smooth(self):
        result = _spline_attrs([0.0, 0.5, 1.0], smooth=False)
        assert 'linear' in result

    def test_spline_when_smooth(self):
        result = _spline_attrs([0.0, 0.5, 1.0], smooth=True)
        assert 'spline' in result
        assert EASE_IN_OUT_SPLINE in result


class TestAnimateTag:
    def test_produces_animate_element(self):
        result = _animate_tag('opacity', ['0', '1'], [0.0, 1.0], 5.0)
        assert '<animate ' in result
        assert 'attributeName="opacity"' in result
        assert 'dur="5.000s"' in result

    def test_smooth_flag(self):
        result = _animate_tag(
            'opacity',
            ['0', '0.5', '1'],
            [0.0, 0.5, 1.0],
            5.0,
            smooth=True,
        )
        assert 'spline' in result


class TestAnimateTransformTag:
    def test_produces_animate_transform(self):
        result = _animate_transform_tag(
            'scale',
            ['1', '2'],
            [0.0, 1.0],
            5.0,
        )
        assert '<animateTransform ' in result
        assert 'type="scale"' in result
