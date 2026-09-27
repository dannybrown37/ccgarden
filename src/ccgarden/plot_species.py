"""The plot's plant catalog: one species per model/effort combo.

Each model family draws from its own pool -- Opus the big brassicas and
fruiting plants, Sonnet the leafy greens, Haiku the herbs -- so a bed
still reads by family at a glance while every combo is its own plant.
Known combos are pinned in ``PINNED`` so a garden never reshuffles
(and no tomatoes, ever -- the owner hates them); a
combo seen for the first time takes the next free plant in its pool.
Drawings are top-down in a -10..10 box with foliage in ``currentColor``
so the renderer can tint for dormancy and effort.
"""

from __future__ import annotations

import math
import re
import zlib
from typing import NamedTuple


class SpeciesArt(NamedTuple):
    name: str
    color: str
    shadow_r: float
    body: str


def _ring(
    count: int,
    offset: float,
    rx: float,
    ry: float,
    *,
    phase: float = 0.0,
    fill: str = 'currentColor',
    extra: str = '',
) -> str:
    return ''.join(
        f'<ellipse cx="0" cy="{-offset:.1f}" rx="{rx:.1f}" ry="{ry:.1f}"'
        f' transform="rotate({phase + i * 360 / count:.1f})"'
        f' fill="{fill}"{extra}/>'
        for i in range(count)
    )


def _spokes(count: int, inner: float, outer: float, stroke: str) -> str:
    return (
        f'<g stroke="{stroke}" stroke-width="0.7" stroke-linecap="round">'
        + ''.join(
            f'<line x1="0" y1="{-inner:.1f}" x2="0" y2="{-outer:.1f}"'
            f' transform="rotate({i * 360 / count:.1f})"/>'
            for i in range(count)
        )
        + '</g>'
    )


def _dots(
    count: int,
    radius: float,
    r: float,
    fill: str,
    *,
    phase: float = 0.0,
) -> str:
    return ''.join(
        f'<circle cx="{radius * math.cos(a):.1f}"'
        f' cy="{radius * math.sin(a):.1f}" r="{r:.1f}" fill="{fill}"/>'
        for a in (phase + i * math.tau / count for i in range(count))
    )


def _lobes(count: int, radius: float, r: float) -> str:
    return _dots(count, radius, r, 'currentColor')


VEIN = '<g fill="none" stroke="#000" stroke-opacity="0.25" stroke-width="0.5">'
LIGHTEN = ' fill-opacity="0.25"'

SPECIES: dict[str, SpeciesArt] = {
    # ── Opus pool: big brassicas and fruiting plants ──
    'cabbage': SpeciesArt(
        'Cabbage',
        '#7f60b5',
        9.0,
        _lobes(8, 7.0, 2.8)
        + '<circle r="7.2" fill="currentColor"/>'
        + VEIN
        + '<circle r="5.2"/><circle r="3.3"/><circle r="1.6"/></g>'
        + '<circle r="3.3" fill="#fff" fill-opacity="0.12"/>',
    ),
    'kale': SpeciesArt(
        'Kale',
        '#4c7d78',
        9.5,
        _ring(7, 5.2, 2.6, 5.4)
        + _ring(7, 8.4, 1.4, 1.4, phase=10)
        + _ring(7, 8.4, 1.4, 1.4, phase=-10)
        + _spokes(7, 1.0, 8.5, '#c8dcd6')
        + '<circle r="1.6" fill="currentColor"/>',
    ),
    'cauliflower': SpeciesArt(
        'Cauliflower',
        '#6c9a55',
        9.0,
        _ring(6, 5.8, 3.4, 4.2)
        + _spokes(6, 3.0, 8.6, '#d6e6c8')
        + '<circle r="4.2" fill="#f4efdc"/>'
        + _dots(7, 2.4, 1.3, '#e6dfc4')
        + '<circle r="1.2" fill="#e6dfc4"/>'
        + '<circle r="4.2" fill="currentColor" fill-opacity="0.08"/>',
    ),
    'broccoli': SpeciesArt(
        'Broccoli',
        '#3f7d3a',
        8.5,
        _ring(5, 5.8, 2.8, 4.2, fill='currentColor', extra=LIGHTEN)
        + _dots(8, 3.8, 2.2, 'currentColor')
        + _dots(5, 1.6, 1.9, 'currentColor', phase=0.4)
        + _dots(8, 3.8, 0.8, '#1f4a22')
        + '<circle r="1" fill="#1f4a22"/>',
    ),
    'artichoke': SpeciesArt(
        'Artichoke',
        '#8aa39a',
        9.5,
        ''.join(
            f'<path d="M0,0 L-1.6,-8.8 L0,-7 L1.6,-8.8 Z"'
            f' transform="rotate({i * 360 / 9:.0f})" fill="currentColor"/>'
            for i in range(9)
        )
        + _ring(6, 2.6, 1.8, 2.8, fill='#6e4a8a')
        + '<circle r="1.6" fill="#8e62ad"/>',
    ),
    'squash': SpeciesArt(
        'Squash',
        '#5f9a3f',
        9.5,
        _lobes(3, 4.6, 4.8)
        + VEIN
        + _spokes(3, 0.5, 8, '#000').replace('<g ', '<g opacity="0.3" ')
        + '</g>'
        + _ring(5, 1.7, 1.2, 1.9, fill='#f2c230')
        + '<circle r="0.9" fill="#d98e1a"/>',
    ),
    'brussels': SpeciesArt(
        'Brussels sprouts',
        '#4f8a45',
        9.0,
        _ring(6, 5.6, 2.6, 4.2)
        + _dots(9, 3.2, 1.3, '#8cc26a')
        + _dots(9, 3.2, 0.5, '#fff', phase=-0.15).replace(
            'fill="#fff"', 'fill="#fff" fill-opacity="0.4"'
        )
        + '<circle r="1.8" fill="currentColor"/>',
    ),
    'pumpkin': SpeciesArt(
        'Pumpkin',
        '#5b8f3c',
        10.0,
        _lobes(4, 5.8, 3.6)
        + '<g transform="translate(1.5 1.5)">'
        + '<ellipse rx="4.4" ry="3.8" fill="#e07b24"/>'
        + '<g fill="none" stroke="#a24d0e" stroke-width="0.5">'
        + '<ellipse rx="2.2" ry="3.8"/><ellipse rx="0.8" ry="3.8"/></g>'
        + '<rect x="-0.5" y="-4.6" width="1" height="1.6" fill="#4a3a1a"/>'
        + '</g>',
    ),
    'eggplant': SpeciesArt(
        'Eggplant',
        '#5c8a4a',
        9.0,
        _ring(5, 4.8, 3.0, 4.6)
        + _spokes(5, 1.0, 8.0, '#7a5a8a')
        + '<ellipse cx="2.4" cy="2.6" rx="1.7" ry="3.3"'
        ' transform="rotate(-30 2.4 2.6)" fill="#4b2a5e"/>'
        + '<ellipse cx="-2.8" cy="1.6" rx="1.5" ry="3"'
        ' transform="rotate(35 -2.8 1.6)" fill="#4b2a5e"/>'
        + '<circle r="1.2" fill="#3a5a2a"/>',
    ),
    'pepper': SpeciesArt(
        'Pepper',
        '#4a8a40',
        8.5,
        _ring(8, 4.6, 2.0, 3.8)
        + '<path d="M-3,1 q-1.5,3 0.5,5 q1.8,-1.5 1.5,-4.6 z" fill="#e8b623"/>'
        + '<path d="M3,-1 q2.8,1.6 2.2,4.6 q-2.4,-0.2 -3.4,-3.6 z"'
        ' fill="#d13a2a"/>' + '<circle r="1.1" fill="#2f5a22"/>',
    ),
    # ── Sonnet pool: leafy greens ──
    'lettuce': SpeciesArt(
        'Lettuce',
        '#3fae5f',
        8.5,
        _ring(9, 4.6, 3.4, 4.6)
        + _ring(6, 2.6, 2.6, 3.4, phase=30)
        + _ring(6, 2.6, 2.6, 3.4, phase=30, fill='#fff', extra=LIGHTEN)
        + '<circle r="1.8" fill="currentColor"/>'
        + '<circle r="1.8" fill="#fff" fill-opacity="0.35"/>',
    ),
    'red-lettuce': SpeciesArt(
        'Red lettuce',
        '#a0445c',
        8.5,
        _ring(10, 4.8, 3.2, 4.4)
        + _ring(10, 7.6, 1.6, 1.4, phase=18)
        + _ring(6, 2.4, 2.4, 3.2, phase=30, fill='#7cbf5a')
        + '<circle r="1.6" fill="#b6de8a"/>',
    ),
    'chard': SpeciesArt(
        'Rainbow chard',
        '#3d7f3d',
        9.0,
        _ring(6, 4.8, 2.8, 4.8)
        + ''.join(
            f'<line x1="0" y1="0" x2="0" y2="-8.4" stroke="{c}"'
            f' stroke-width="1" stroke-linecap="round"'
            f' transform="rotate({i * 60})"/>'
            for i, c in enumerate(
                (
                    '#d23c5a',
                    '#f0c02c',
                    '#e8773a',
                    '#d23c5a',
                    '#f7f0d8',
                    '#f0c02c',
                )
            )
        ),
    ),
    'bok-choy': SpeciesArt(
        'Bok choy',
        '#4e9a45',
        8.0,
        _ring(6, 4.6, 2.6, 4.2)
        + _spokes(6, 0.5, 6.2, '#eef3dc').replace(
            'stroke-width="0.7"', 'stroke-width="1.6"'
        )
        + '<circle r="1.8" fill="#eef3dc"/>',
    ),
    'spinach': SpeciesArt(
        'Spinach',
        '#2f7a3a',
        8.0,
        _ring(7, 4.4, 2.8, 3.6)
        + _ring(4, 2.0, 1.8, 2.4, phase=45)
        + VEIN
        + _spokes(7, 1.0, 7.0, '#000').replace('<g ', '<g opacity="0.3" ')
        + '</g>',
    ),
    'beet': SpeciesArt(
        'Beet',
        '#3c7a3c',
        8.5,
        _ring(6, 4.8, 2.4, 4.2)
        + _spokes(6, 1.0, 8.2, '#9e2446')
        + '<circle r="2.6" fill="#8e1f3e"/>'
        + '<circle cx="-0.8" cy="-0.8" r="0.9" fill="#fff"'
        ' fill-opacity="0.3"/>',
    ),
    # ── Haiku pool: herbs ──
    'basil': SpeciesArt(
        'Basil',
        '#a9d153',
        7.5,
        _ring(5, 4.2, 2.4, 4.0)
        + _spokes(5, 1.0, 7.4, '#5a7a2a')
        + '<circle r="1.4" fill="currentColor"/>',
    ),
    'mint': SpeciesArt(
        'Mint',
        '#6fbf7a',
        7.5,
        ''.join(
            f'<g transform="rotate({i * 90 + 45})">'
            f'<ellipse cx="-1.6" cy="-4.2" rx="1.6" ry="2.2"'
            f' fill="currentColor"/>'
            f'<ellipse cx="1.6" cy="-4.2" rx="1.6" ry="2.2"'
            f' fill="currentColor"/>'
            f'<ellipse cx="0" cy="-6.8" rx="1.3" ry="1.7"'
            f' fill="currentColor"/></g>'
            for i in range(4)
        )
        + '<circle r="1.6" fill="currentColor"/>',
    ),
    'parsley': SpeciesArt(
        'Parsley',
        '#4a9a3a',
        7.5,
        _dots(9, 5.6, 1.7, 'currentColor')
        + _dots(7, 3.4, 1.6, 'currentColor', phase=0.4)
        + _dots(4, 1.4, 1.4, 'currentColor', phase=0.8)
        + _dots(9, 5.6, 0.6, '#fff', phase=0.1).replace(
            'fill="#fff"', 'fill="#fff" fill-opacity="0.35"'
        ),
    ),
    'chives': SpeciesArt(
        'Chives',
        '#5a9a45',
        6.5,
        '<g stroke="currentColor" stroke-width="1" stroke-linecap="round">'
        + ''.join(
            f'<line x1="0" y1="0" x2="0" y2="-7"'
            f' transform="rotate({i * 360 / 11:.0f})"/>'
            for i in range(11)
        )
        + '</g>'
        + _dots(3, 5.8, 1.6, '#b98ad6', phase=0.3)
        + '<circle r="1" fill="currentColor"/>',
    ),
    # ── Anything else ──
    'sprout': SpeciesArt(
        'Sprout',
        '#5fa8a0',
        5.0,
        '<ellipse cx="-2.6" cy="0" rx="3" ry="1.8" transform="rotate(-20)"'
        ' fill="currentColor"/>'
        '<ellipse cx="2.6" cy="0" rx="3" ry="1.8" transform="rotate(-20)"'
        ' fill="currentColor"/>'
        '<circle r="0.9" fill="currentColor"/>',
    ),
}

FAMILY_POOLS: dict[str, tuple[str, ...]] = {
    'opus': (
        'cabbage',
        'kale',
        'cauliflower',
        'broccoli',
        'artichoke',
        'squash',
        'brussels',
        'pumpkin',
        'eggplant',
        'pepper',
    ),
    'sonnet': (
        'lettuce',
        'red-lettuce',
        'chard',
        'bok-choy',
        'spinach',
        'beet',
    ),
    'haiku': ('basil', 'mint', 'parsley', 'chives'),
    'unknown': ('sprout',),
}

# Hand-placed so the gardens already out there keep their plants.
PINNED: dict[str, str] = {
    'claude-opus-4-6 (low)': 'cabbage',
    'claude-opus-4-6 (medium)': 'kale',
    'claude-opus-4-6 (high)': 'cauliflower',
    'claude-opus-4-7 (low)': 'broccoli',
    'claude-opus-4-7 (high)': 'artichoke',
    'claude-opus-5 (low)': 'squash',
    'claude-opus-5 (medium)': 'pepper',
    'claude-opus-5 (xhigh)': 'pumpkin',
    'claude-opus-5-5 (medium)': 'eggplant',
    'claude-sonnet-5 (low)': 'lettuce',
    'claude-sonnet-5 (medium)': 'red-lettuce',
    'claude-sonnet-5 (high)': 'chard',
    'claude-sonnet-5 (xhigh)': 'bok-choy',
    'claude-haiku-4-5-20251001': 'basil',
}


def model_family(label: str) -> str:
    lower = label.lower()
    for family in ('haiku', 'sonnet', 'opus'):
        if family in lower:
            return family
    return 'unknown'


def assign_species(labels: list[str]) -> dict[str, str]:
    """Give every combo in this garden its own plant from its pool.

    Pinned combos keep their plant; the rest, in label order so input
    order can't matter, probe their family pool from a hashed start for
    the first plant nobody here has. A pool smaller than its combos
    wraps around rather than fail -- two combos share a plant before
    one goes unplanted.
    """
    mapping = {label: PINNED[label] for label in labels if label in PINNED}
    taken = set(mapping.values())
    for label in sorted(set(labels) - set(mapping)):
        pool = FAMILY_POOLS[model_family(label)]
        start = zlib.crc32(label.encode()) % len(pool)
        order = pool[start:] + pool[:start]
        species = next((s for s in order if s not in taken), order[0])
        mapping[label] = species
        taken.add(species)
    return mapping


def combo_name(label: str) -> str:
    """'claude-opus-4-6 (low)' → 'Opus 4.6 · low'."""
    effort = ''
    match = re.fullmatch(r'(.*?)\s*\((\w+)\)', label)
    model = label
    if match:
        model, effort = match.groups()
    model = model.strip('<>').removeprefix('claude-')
    parts = [p for p in model.split('-') if not re.fullmatch(r'\d{8}', p)]
    if parts and parts[0] in {'opus', 'sonnet', 'haiku'}:
        name = parts[0].capitalize()
        version = '.'.join(parts[1:])
        model = f'{name} {version}' if version else name
    return f'{model} · {effort}' if effort else model
