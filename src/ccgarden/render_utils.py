"""Shared rendering utilities for ccgarden SVG renderers.

Extracted from ``render.py`` so both the tree renderer and the
plot-garden renderer can share XML, color, shape, animation,
and weather-pacing helpers without duplication.
"""

from __future__ import annotations

import datetime
import itertools
import json
import math
from typing import TYPE_CHECKING

from ccgarden.data import DORMANCY_HALF_LIFE_DAYS

if TYPE_CHECKING:
    import random

# ── Timeline duration constants ──────────────────────────────────────

TIMELINE_PER_DAY_SECONDS = 0.6
TIMELINE_MIN_DURATION_S = 5.0
TIMELINE_MAX_DURATION_S = 18.0
TIMELINE_MIN_DAYS_TO_ANIMATE = 2

# ── Night / weather constants ────────────────────────────────────────

NIGHTNESS_SATURATION = 0.45

EPSILON = 1e-6

RAIN_ONSET_DAYS = 1.0
RAIN_FULL_DAYS = 10.0
RAIN_MIN_INTENSITY = 0.28
SUN_STORM_MIN_OPACITY = 0.15
RAIN_MAX_OPACITY = 0.7

# ── Frame-dwell constants ───────────────────────────────────────────

DORMANT_FRAME_DWELL = 2.5
RECOVERY_FRAME_DWELL = 2.0
WEATHER_SWING_DWELL = 3.5

# ── Spline constant ─────────────────────────────────────────────────

EASE_IN_OUT_SPLINE = '0.42 0 0.58 1'


# ── XML helpers ──────────────────────────────────────────────────────


def _escape_xml(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _title(text: str) -> str:
    """A ``<title>`` child that browsers render as a hover tooltip."""
    return f'<title>{_escape_xml(text)}</title>'


def _tt_attr(day_labels: list[str]) -> str:
    """A ``data-tt`` attribute: one tooltip string per day, JSON-encoded.

    A static ``<title>`` can't track which day the timeline animation
    is currently showing, so the tap-tooltip script reads this instead.
    """
    encoded = _escape_xml(json.dumps(day_labels, ensure_ascii=False)).replace(
        "'", '&apos;'
    )
    return f"data-tt='{encoded}'"


def _format_day(day: str) -> str:
    try:
        return datetime.date.fromisoformat(day).strftime('%b %-d, %Y')
    except ValueError:
        return day


# ── Color helpers ────────────────────────────────────────────────────


def _blend_hex(dormant: str, living: str, vitality: float) -> str:
    """Mix two #rrggbb colours, ``vitality`` 1.0 being fully living."""
    ratio = max(0.0, min(vitality, 1.0))
    channels = []
    for start in (1, 3, 5):
        cold = int(dormant[start : start + 2], 16)
        warm = int(living[start : start + 2], 16)
        channels.append(round(cold + (warm - cold) * ratio))
    return '#{:02x}{:02x}{:02x}'.format(*channels)


def _lerp_hex(start: str, end: str, fraction: float) -> str:
    """Blend two ``#rrggbb`` colors by *fraction* from start to end."""
    start_rgb = (int(start[i : i + 2], 16) for i in (1, 3, 5))
    end_rgb = (int(end[i : i + 2], 16) for i in (1, 3, 5))
    channels = (
        round(s + (e - s) * fraction)
        for s, e in zip(start_rgb, end_rgb, strict=True)
    )
    return '#{:02x}{:02x}{:02x}'.format(*channels)


# ── Shape helpers ────────────────────────────────────────────────────


def _blob_path(
    center_x: float,
    center_y: float,
    radius: float,
    rng: random.Random,
    *,
    points: int = 9,
    jitter: float = 0.32,
) -> str:
    vertices = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        r = radius * (1 + rng.uniform(-jitter, jitter))
        vertices.append(
            (
                center_x + r * math.cos(angle),
                center_y + r * math.sin(angle),
            )
        )
    start_mid = (
        (vertices[0][0] + vertices[-1][0]) / 2,
        (vertices[0][1] + vertices[-1][1]) / 2,
    )
    d = f'M {start_mid[0]},{start_mid[1]} '
    for i in range(points):
        p1 = vertices[i]
        p2 = vertices[(i + 1) % points]
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        d += f'Q {p1[0]},{p1[1]} {mid[0]},{mid[1]} '
    return d + 'Z'


# ── Weather helpers ──────────────────────────────────────────────────


def _saturated_nightness(nightness: float) -> float:
    """Raw night share, curved onto 0..1 by ``NIGHTNESS_SATURATION``."""
    return max(0.0, min(nightness / NIGHTNESS_SATURATION, 1.0))


def _exact_days_away(vitality: float) -> float:
    """Invert ``_daily_vitality``'s decay back into days of silence."""
    if vitality >= 1.0:
        return 0.0
    if vitality <= 0.0:
        return math.inf
    return -math.log2(vitality) * DORMANCY_HALF_LIFE_DAYS


def _rain_intensity(vitality: float) -> float:
    """0 while the garden is being tended, ramping to 1 once gone."""
    days = _exact_days_away(vitality)
    if days < RAIN_ONSET_DAYS - EPSILON:
        return 0.0
    if days >= RAIN_FULL_DAYS:
        return 1.0
    ramp = (days - RAIN_ONSET_DAYS) / (RAIN_FULL_DAYS - RAIN_ONSET_DAYS)
    return RAIN_MIN_INTENSITY + (1.0 - RAIN_MIN_INTENSITY) * ramp


def _rain_opacity(vitality: float) -> float:
    return _rain_intensity(vitality) * RAIN_MAX_OPACITY


def _sun_storm_opacity(vitality: float) -> float:
    """How much of the sun survives the cloud, 1.0 in clear weather."""
    return 1.0 - (1.0 - SUN_STORM_MIN_OPACITY) * _rain_intensity(vitality)


def _weather_load(nightness: float, vitality: float) -> float:
    """Total canvas-wide weather on one frame, for pacing purposes."""
    return (
        _saturated_nightness(nightness)
        + _rain_opacity(vitality)
        + (1.0 - _sun_storm_opacity(vitality))
    )


# ── Animation / timeline helpers ────────────────────────────────────


def _timeline_duration(day_count: float) -> float:
    """Seconds of replay for *day_count* frame-weights of timeline."""
    return min(
        max(day_count * TIMELINE_PER_DAY_SECONDS, TIMELINE_MIN_DURATION_S),
        TIMELINE_MAX_DURATION_S,
    )


def _key_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


def _frame_weights(
    daily_sessions: list[int],
    daily_nightness: list[float] | None = None,
    daily_vitality: list[float] | None = None,
) -> list[float]:
    """Relative time spent arriving at each frame after the first."""
    count = len(daily_sessions)
    nightness = daily_nightness or [0.0] * count
    vitality = daily_vitality or [1.0] * count
    loads = [
        _weather_load(night, life)
        for night, life in zip(nightness, vitality, strict=True)
    ]
    weights = []
    for index, (previous, sessions) in enumerate(
        itertools.pairwise(daily_sessions)
    ):
        if sessions <= 0:
            weight = DORMANT_FRAME_DWELL
        elif previous <= 0:
            weight = RECOVERY_FRAME_DWELL
        else:
            weight = 1.0
        swing = abs(loads[index + 1] - loads[index])
        weights.append(weight + WEATHER_SWING_DWELL * swing)
    return weights


def _weighted_key_times(
    daily_sessions: list[int],
    daily_nightness: list[float] | None = None,
    daily_vitality: list[float] | None = None,
) -> list[float]:
    """Frame times with dormant frames held longer than the rest."""
    if len(daily_sessions) <= 1:
        return [0.0]
    weights = _frame_weights(daily_sessions, daily_nightness, daily_vitality)
    total = sum(weights)
    times = [0.0]
    elapsed = 0.0
    for weight in weights:
        elapsed += weight
        times.append(elapsed / total)
    return times


def _collapse_keyframes(
    values: list[str],
    key_times: list[float],
) -> tuple[list[str], list[float]]:
    """Drop interior frames in runs of identical values."""
    if len(values) <= 2:  # noqa: PLR2004
        return values, key_times
    out_v: list[str] = [values[0]]
    out_t: list[float] = [key_times[0]]
    for i in range(1, len(values)):
        if values[i] == values[i - 1] and i < len(values) - 1:
            if values[i] != values[i + 1]:
                out_v.append(values[i])
                out_t.append(key_times[i])
        else:
            out_v.append(values[i])
            out_t.append(key_times[i])
    return out_v, out_t


def _spline_attrs(key_times: list[float], *, smooth: bool) -> str:
    if not smooth or len(key_times) < TIMELINE_MIN_DAYS_TO_ANIMATE:
        return 'calcMode="linear" '
    splines = ';'.join([EASE_IN_OUT_SPLINE] * (len(key_times) - 1))
    return f'calcMode="spline" keySplines="{splines}" '


def _animate_tag(
    attribute: str,
    values: list[str],
    key_times: list[float],
    duration: float,
    *,
    smooth: bool = False,
    collapse: bool = True,
) -> str:
    if collapse:
        values, key_times = _collapse_keyframes(values, key_times)
    return (
        f'<animate attributeName="{attribute}" dur="{duration:.3f}s" '
        f'begin="0s" fill="freeze" '
        f'{_spline_attrs(key_times, smooth=smooth)}'
        f'keyTimes="{";".join(f"{t:.4f}" for t in key_times)}" '
        f'values="{";".join(values)}" />'
    )


def _animate_transform_tag(
    transform_type: str,
    values: list[str],
    key_times: list[float],
    duration: float,
    *,
    collapse: bool = True,
) -> str:
    if collapse:
        values, key_times = _collapse_keyframes(values, key_times)
    return (
        f'<animateTransform attributeName="transform" '
        f'type="{transform_type}" dur="{duration:.3f}s" '
        f'begin="0s" fill="freeze" calcMode="linear" '
        f'keyTimes="{";".join(f"{t:.4f}" for t in key_times)}" '
        f'values="{";".join(values)}" />'
    )
