"""Top-down plot-garden renderer.

An alternative to ``render.py``'s tree silhouette: raised beds seen
from above. Same ``GardenData`` / ``GardenTimeline`` input contract,
shares XML/color/animation helpers from ``render_utils``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ccgarden.render_utils import (
    _blend_hex,
    _escape_xml,
    _saturated_nightness,
    _title,
)

if TYPE_CHECKING:
    from ccgarden.data import GardenData, GardenTimeline

VIEWBOX_WIDTH = 900
VIEWBOX_HEIGHT = 700

SKY_BAND_HEIGHT = 60
STATS_BAR_HEIGHT = 40

SOIL_DORMANT = '#6b4a35'
SOIL_LIVING = '#4a3524'

SKY_DAY = '#bfe3f7'
SKY_NIGHT = '#152238'


def _render_sky_band(nightness: float) -> str:
    """A thin band across the top, dark in proportion to night share."""
    color = _blend_hex(SKY_DAY, SKY_NIGHT, _saturated_nightness(nightness))
    return (
        f'<rect class="plot-sky" x="0" y="0" '
        f'width="{VIEWBOX_WIDTH}" height="{SKY_BAND_HEIGHT}" '
        f'fill="{color}">{_title("Sky")}</rect>'
    )


def _render_soil(vitality: float) -> str:
    """The bed field, darker and richer the more alive the garden is."""
    color = _blend_hex(SOIL_DORMANT, SOIL_LIVING, vitality)
    return (
        f'<rect class="plot-soil" x="0" y="{SKY_BAND_HEIGHT}" '
        f'width="{VIEWBOX_WIDTH}" '
        f'height="{VIEWBOX_HEIGHT - SKY_BAND_HEIGHT - STATS_BAR_HEIGHT}" '
        f'fill="{color}">{_title("Soil")}</rect>'
    )


def _render_stats_bar(garden: GardenData) -> str:
    """A one-line summary bar along the bottom of the plot."""
    total_sessions = sum(day_ring.sessions for day_ring in garden.rings)
    text = _escape_xml(
        f'{total_sessions} sessions — {garden.total_tokens:,} tokens'
    )
    y = VIEWBOX_HEIGHT - STATS_BAR_HEIGHT
    return (
        f'<g class="plot-stats-bar">'
        f'<rect x="0" y="{y}" width="{VIEWBOX_WIDTH}" '
        f'height="{STATS_BAR_HEIGHT}" fill="#222" />'
        f'<text x="12" y="{y + STATS_BAR_HEIGHT / 2 + 4:.1f}" '
        f'fill="#eee" font-size="14">{text}</text>'
        f'</g>'
    )


def render_plot_svg(garden: GardenData) -> str:
    body = (
        _render_sky_band(garden.nightness)
        + _render_soil(garden.vitality)
        + _render_stats_bar(garden)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {VIEWBOX_HEIGHT}" '
        f'width="{VIEWBOX_WIDTH}" height="{VIEWBOX_HEIGHT}">{body}</svg>'
    )


def render_plot_timeline_svg(timeline: GardenTimeline) -> str:
    raise NotImplementedError
