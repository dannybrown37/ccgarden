from __future__ import annotations

import datetime
import itertools
import json
import math
import random
import zlib
from dataclasses import replace
from typing import TYPE_CHECKING, NamedTuple

from ccgarden.data import (
    DORMANCY_HALF_LIFE_DAYS,
    CartoonBird,
    DayRing,
    GardenData,
    ModelCloud,
    RepoBranch,
    SkillFruit,
    ToolBush,
)

if TYPE_CHECKING:
    from ccgarden.data import (
        GardenTimeline,
        RepoBranchDay,
        ToolUsageDay,
    )

VIEWBOX_WIDTH = 800
VIEWBOX_HEIGHT = 800
GROUND_Y = 728
# The legend gets its own band below the garden rather than sharing the thin
# strip of grass under GROUND_Y -- eight entries squeezed into 64px of height
# left each column too narrow, so the descriptions ran into their neighbours.
LEGEND_BAND_HEIGHT = 118.0
LEGEND_BAND_BOTTOM = VIEWBOX_HEIGHT + LEGEND_BAND_HEIGHT
TRUNK_HEIGHT = 300
TRUNK_TOP_Y = GROUND_Y - TRUNK_HEIGHT
TRUNK_CENTER_X = VIEWBOX_WIDTH / 2
TRUNK_BASE_HALF_WIDTH_MIN = 9.0
TRUNK_BASE_HALF_WIDTH_MAX = 30.0
TRUNK_SESSIONS_SATURATION = 400
TRUNK_TOP_TAPER = 0.72
TREE_GROWTH_SCALE_MIN = 0.12
BRANCH_ZONE_HEIGHT = 220
BRANCH_LENGTH_MIN = 30.0
BRANCH_LENGTH_MAX = 230.0
BRANCH_LINES_SATURATION = 6000
# Lines added below which `_branch_length` grows quickly, and above which it
# compresses. Tune this rather than the min/max pair to rebalance the crown.
BRANCH_LENGTH_LOG_KNEE = 400.0
BRANCH_SPREAD_DEGREES = 55.0
# Strictly alternating branches at evenly interpolated angles read as a
# ladder rather than a tree, so each branch gets a seeded nudge to both its
# height on the trunk and its exit angle. Both are derived from the repo
# name, so the same db still renders the same garden.
BRANCH_ANGLE_JITTER_DEGREES = 8.0
# As a fraction of the gap between two neighbouring branch origins -- kept
# under half a gap so jitter can never reorder branches up the trunk.
BRANCH_Y_JITTER_FRACTION = 0.4
# A long branch carries more foliage, so it sags. Most of that sag lives in
# the belly of the branch (BRANCH_BOW_*, below) rather than the exit angle,
# which only tips this far towards horizontal at BRANCH_LENGTH_MAX -- a
# branch that leaves the trunk low and still lifts its tip is the vase
# shape real trees make as they grow back towards the light. Putting all the
# sag in the angle instead just flattened everything.
BRANCH_DROOP_DEGREES = 9.0
# Lateral belly of a branch as a fraction of its length, ramping from short
# (nearly straight) to BRANCH_LENGTH_MAX (a pronounced sag).
BRANCH_BOW_FRACTION_MIN = 0.07
BRANCH_BOW_FRACTION_MAX = 0.2
BRANCH_TIP_WIDTH = 1.6
BRANCH_WIDTH_MIN = 2.2
BRANCH_WIDTH_MAX = 7.0
BRANCH_TOKENS_SATURATION = 2_500_000
# A skeleton of one branch per repo is a telephone pole for anyone who does
# all their work in a single repo. A real crown is carried on a handful of
# primary limbs however many repos feed it, so the busiest repos are split
# across several limbs until the tree has at least this many. Volume still
# decides everything *about* a limb -- its length, thickness and foliage --
# so more work is still a bigger tree; it just always reads as a tree.
MIN_LIMBS = 6
# A limb count alone doesn't buy a tree. Someone whose work is one real repo
# plus five repos they ran two prompts against already clears MIN_LIMBS, and
# gets a garden with one limb of substance and five twigs -- the pole
# problem wearing a disguise. So the busiest repos keep splitting past the
# minimum until no single limb carries more than this share of the tree's
# weight, which is what makes a lopsided garden read as a crown.
LIMB_MAX_SHARE = 0.3
# Ceiling on how far one repo can be split, so a garden with a truly
# runaway repo terminates instead of shaving it into filaments.
MAX_LIMBS_PER_REPO = 8
# Each successive limb cut from the same repo carries this much of the
# previous one's share, so a split repo gets one dominant leader and
# progressively smaller siblings instead of a fan of identical twins. Kept
# close to 1: a steeper falloff hands the first limb so much of the repo
# that its canopy reads as the whole tree with four wisps stuck on beside
# it, which is the pole problem again in a different shape.
LIMB_SHARE_FALLOFF = 0.78
LEAVES_PER_SESSION = 5
LEAF_SATURATION_COUNT = 2000
LEAF_TURNS_FLOOR = 0.0
LEAF_TURNS_CEILING = 6.9
LEAF_SIZE_MULTIPLIER_MIN = 0.75
LEAF_SIZE_MULTIPLIER_MAX = 1.5
CANOPY_MIN_LEAVES = 3
CANOPY_RADIUS_MIN = 20.0
CANOPY_RADIUS_MAX = 130.0
LEAF_SCATTER_RADIUS = 45.0
LEAF_RADIUS = 7.0
LEAF_COLORS = ('#3f7a3f', '#4f8f4f', '#5a9e5a', '#6bb26b', '#7dc47d')
LEAF_SHAPE_D = 'M0,-1 C0.55,-0.75 0.55,0.75 0,1 C-0.55,0.75 -0.55,-0.75 0,-1 Z'
LEAF_VEIN_D = 'M0,-0.85 L0,0.85'
# Greenery covers the outer FOLIAGE_START_FRACTION..FOLIAGE_TIP_OVERHANG span
# of each branch's length (as a fraction from origin to tip), so long
# branches get proportionally more covered length instead of a single leaf
# ball stuck at the very tip.
FOLIAGE_START_FRACTION = 0.4
FOLIAGE_TIP_OVERHANG = 1.08
FOLIAGE_BLOB_SPACING = 55.0
MAX_FOLIAGE_BLOBS = 6
RING_STROKE_WIDTH_MIN = 0.75
RING_STROKE_WIDTH_MAX = 3.5
RING_SESSIONS_SATURATION = 60

FLOWER_COLORS = ('#f4c95d', '#f27ab0', '#fdfdf6', '#c98bdb', '#f2896d')
FLOWER_CENTER_COLOR = '#5a3d1a'
FLOWER_RADIUS = 5.0

FRUIT_COLORS = (
    '#e74c3c',
    '#e67e22',
    '#f1c40f',
    '#9b59b6',
    '#e91e63',
    '#27ae60',
    '#3498db',
    '#d35400',
)
# Nominal fruit size, used by the legend icon; a real fruit is sized from
# its skill's call count by `_fruit_radius`.
FRUIT_RADIUS = 4.5
FRUIT_STEM_LENGTH = 6.0
FRUIT_RADIUS_MIN = 3.2
FRUIT_RADIUS_MAX = 7.5
FRUIT_RADIUS_SATURATION = 60
# Fruit is per-skill, not per-call: a skill you lean on daily should read as
# a heavier bough than one you tried once, without a 300-call skill burying
# the tree. A root curve gives 1 fruit at 1 call and ~11 at 100.
FRUIT_ROOT_SATURATION = 1.1
FRUIT_MIN_CALLS = 5
FRUIT_MIN_PER_SKILL = 1
FRUIT_MAX_PER_SKILL = 14
FRUIT_TOTAL_MAX = 120
# Fruit hangs in the same foliage blobs the leaves fill, pulled in from the
# rim so it reads as sitting *in* the green rather than stuck on its edge.
FRUIT_CANOPY_INSET = 0.72
# Fruit comes at the end: the crop fades in over the last slice of the
# replay rather than ripening piece by piece across the days.
FRUIT_RIPEN_FRACTION = 0.08
# Fruit is drawn in unit space and scaled, so one box bounds every shape:
# half-width and the body's top and bottom, in radius multiples, plus the
# stem tip above it. Placement keeps all of that in the green.
FRUIT_EXTENT_HALF_WIDTH = 1.25
FRUIT_EXTENT_TOP = -1.05
FRUIT_EXTENT_BOTTOM = 1.2
FRUIT_STEM_TIP = -1.95
# The far corner of that body box, in radius multiples: a fruit centred in
# a disk needs this much room, and a small canopy shrinks its fruit to fit
# rather than dropping it.
FRUIT_EXTENT_REACH = math.hypot(FRUIT_EXTENT_HALF_WIDTH, FRUIT_EXTENT_BOTTOM)
FRUIT_PLACEMENT_TRIES = 24
# Centre-to-centre spacing as a multiple of the two radii summed: just
# clear of touching, so a crop reads as scattered rather than as clumps.
FRUIT_MIN_GAP = 1.05
MAX_FRUIT_PER_LIMB = 12

# One cloud per model used, sized by how many tokens that model produced.
CLOUD_MARGIN = 24.0
CLOUD_Y_MIN = 40.0
# The tallest branch plus its canopy reaches into the top of the sky right
# above the trunk, so clouds are laid out in two bands either side of a
# keep-out column centered on the trunk rather than straight across the
# width. Half-width covers the trunk plus the reach of a near-vertical
# max-length branch's canopy, so even the biggest tree only clips the
# inside edge of a cloud instead of swallowing it whole.
CLOUD_TREE_KEEPOUT_HALF_WIDTH = 170.0
# How far down a cloud may drift, as a function of how far its slot sits
# from the trunk. Right beside the keep-out column the tree's outer
# branches are still climbing, so clouds stay high; out at the frame edges
# the sky is clear all the way down and small clouds can use it.
CLOUD_Y_MAX_NEAR_TREE = 150.0
CLOUD_Y_MAX_AT_EDGE = 330.0
CLOUD_RADIUS_MIN = 16.0
CLOUD_RADIUS_MAX = 60.0
CLOUD_TOKENS_SATURATION = 6_000_000
CLOUD_PUFFS = (
    (0.0, -0.18, 1.0),
    (-0.55, 0.12, 0.68),
    (0.55, 0.12, 0.68),
    (-0.18, 0.3, 0.55),
    (0.22, 0.3, 0.5),
)
# Each puff is scaled by a random size jitter, then `_blob_path` wobbles each
# of its vertices by up to a further shape jitter. A cloud therefore reaches
# well past its nominal radius -- roughly 1.4x -- which is what
# `_cloud_extent` turns into the margins that keep it inside the viewBox.
CLOUD_PUFF_SIZE_JITTER = (0.92, 1.08)
CLOUD_PUFF_SHAPE_JITTER = 0.16

# A cloud's reasoning-effort level darkens it toward a storm-cloud grey, so
# heavier-thinking model/effort combos read visually "heavier" in the sky.
# Unrecognized or absent effort falls back to 0.0 -- the original pale cloud.
CLOUD_EFFORT_DARKNESS = {
    'low': 0.15,
    'medium': 0.4,
    'high': 0.65,
    'xhigh': 0.85,
    'max': 1.0,
}
CLOUD_GRADIENT_STOPS = ('#ffffff', '#eef3f8', '#c7d5e4')
CLOUD_STORM_STOPS = ('#4d5566', '#333c4d', '#1c222e')

# The single sun, sized and positioned by the garden's all-in token total
# (every output/input/cache-read/cache-write token counted anywhere) --
# the one shape standing in for the whole garden's total "energy" rather
# than any one branch/model/tool's share of it. It rises from a low,
# barely-there position near the horizon at zero tokens up to its full
# height and brightness at the saturation point, echoing an actual
# sunrise into the dusk-blue sky gradient in `_render_defs`. Drawn first
# so clouds float in front of it, as they would in front of a real sun.
SUN_RADIUS_MIN = 26.0
SUN_RADIUS_MAX = 68.0
SUN_TOKENS_SATURATION = 200_000_000
# The sun crosses the sky with the *replay*, not with your token total:
# height still tells you how far the totals have come, but a lapse
# freezes every cumulative channel, and a sun frozen mid-sky while rain
# hammers the garden is the one thing that always read as a broken
# animation. Time always passes, so the sweep always moves.
SUN_X_START = 96.0
SUN_X_END = 704.0
SUN_Y_START = 640.0
SUN_Y_END = 95.0
SUN_RAY_COUNT = 12
# The moon is the same body seen on a night shift -- same sweep, same
# size, cross-faded on the day's nightness -- rather than a second thing
# to place, which would need its own keepout from everything the sun
# already avoids.
MOON_GRADIENT_STOPS = ('#fdfdf7', '#dee4f3', '#aeb8d2')
MOON_HALO_COLOR = '#cdd8f2'
MOON_CRATER_COLOR = '#c3cbe0'
MOON_CRATERS = ((-0.30, -0.22, 0.20), (0.26, 0.10, 0.26), (-0.10, 0.36, 0.15))
# The halo is the sun's widest part -- wider than the rays -- so it sets how
# much clearance `_sun_position` has to keep from the top and sides.
SUN_HALO_RADIUS_FACTOR = 1.9
SUN_GRADIENT_STOPS = ('#fffbe6', '#ffd76a', '#ff9f45')
SUN_HALO_COLOR = '#fff3c4'
SUN_RAY_COLOR = '#ffdb8a'

# One bush per tool used, sized by how many times that tool was called.
# Puffs are laid out relative to a (0, 0) ground-contact point (see
# `_render_bush`), unlike clouds which are centered on their own midpoint.
# Capped at MAX_BUSHES (mirroring claude_stats.TOP_TOOLS_SHOWN) since a
# repo can easily touch a dozen-plus distinct tools -- more than that many
# max-size bushes wouldn't fit the ground strip without wall-to-wall overlap.
MAX_BUSHES = 10
BUSH_MARGIN = 40.0
BUSH_RADIUS_MIN = 12.0
BUSH_RADIUS_MAX = 34.0
BUSH_TOOL_COUNT_SATURATION = 3000
BUSH_GROWTH_EXPONENT = 0.65
BUSH_PUFFS = (
    (0.0, -0.55, 0.85),
    (-0.62, -0.3, 0.62),
    (0.62, -0.3, 0.62),
    (-0.25, -0.55, 0.5),
    (0.28, -0.55, 0.5),
)

# One sunflower per repo, standing as tall as that repo's prompt count.
# Prompts are the one thing *you* contribute rather than the tree, so they
# get a plant of their own instead of another dimension on the branches.
# Sunflowers are planted in the two flank bands either side of the tree --
# the widest stretch of empty ground in the frame, and far enough from the
# trunk that a tall stalk rises into open sky rather than into the canopy.
MAX_SUNFLOWERS = 8
SUNFLOWER_MARGIN = 20.0
SUNFLOWER_BAND_WIDTH = 150.0
SUNFLOWER_HEIGHT_MIN = 70.0
SUNFLOWER_HEIGHT_MAX = 200.0
SUNFLOWER_PROMPTS_SATURATION = 1500
SUNFLOWER_GROWTH_EXPONENT = 0.6
SUNFLOWER_PETAL_COUNT = 12
SUNFLOWER_PETAL_COLORS = ('#f5b731', '#f0a92a', '#ffc94d')
SUNFLOWER_STALK_COLOR = '#4f8f4f'

# One bird per cartoon adapter that saved tokens, sized by how many it
# saved. Cartoon is an optional external tool the garden plugs into, so
# unlike every other shape here the birds are simply absent -- along with
# their legend entry -- on a machine that doesn't have it. Tokens cartoon
# saves are tokens that never had to be sent, which is the one quantity in
# the garden that's about what *didn't* happen, so it gets the one shape
# that isn't rooted to the ground.
BIRD_MARGIN = 55.0
# Birds share the sky with the canopy, so like the clouds they skip the
# column of sky the tree grows into and spread across the two bands either
# side of it -- otherwise a small flock anchors near the middle of the
# frame and reads as hugging the tree.
BIRD_TREE_KEEPOUT_HALF_WIDTH = 150.0
# Deliberately lower than the clouds' band: the open mid-sky either side
# of the canopy is the emptiest part of the frame, and a bird is small
# enough to sit there without competing with anything.
BIRD_Y_MIN = 120.0
BIRD_Y_MAX = 430.0
MAX_BIRDS = 12
BIRD_SIZE_MIN = 6.0
BIRD_SIZE_MAX = 16.0
BIRD_TOKENS_SATURATION = 250_000
# The reference size the stroke width is scaled against.
BIRD_SIZE = 9.0
# Birds cluster into small skeins rather than scattering evenly: a handful
# of loose Vs reads as wildlife, an even spread reads as a dot grid.
BIRD_FLOCK_SIZE = 4
BIRD_FLOCK_SPACING_X = 15.0
BIRD_FLOCK_SPACING_Y = 8.0
# A dark silhouette is what a bird actually looks like, but the sky here is
# a dark dusk blue -- so they're drawn as a pale, near-white stroke, the
# only value that reads at this size against that gradient.
BIRD_COLOR = '#dce7f4'
EPSILON = 1e-6
BIRD_LEGEND_COLOR = '#3f4b5c'
BIRD_STROKE_WIDTH = 1.8
# In the timeline the flock drifts on its own slow loop, out from the tree
# and back. It is the one motion in the garden that isn't tied to the day
# frames -- cartoon reports a single snapshot, so there is no history to
# replay -- but birds in a still sky read as dead, and drifting invents no
# numbers, only movement.
BIRD_DRIFT_X = 26.0
BIRD_DRIFT_Y = 9.0
BIRD_DRIFT_SECONDS = 11.0

# Wind. Every other motion in the garden is tied to the day frames, so a
# lapse -- when nothing grows -- used to leave the whole picture standing
# still, and the frozen final frame with it. This is the garden's idle
# breath: a slow sway on anything rooted, a drift on anything in the sky,
# running on its own clock so a paused, finished or scrubbed replay is
# still alive.
#
# CSS keyframes rather than SMIL, for the same compositor reason as the
# birds' drift (see `_bird_drift_rule`) -- a permanent SMIL transform on a
# limb holding thousands of leaves would repaint the document forever on
# the main thread. Each sway pivots at its own root, so a limb hinges
# where it meets the trunk and a sunflower at the soil, never about the
# middle of its own bounding box: hence `transform-box: view-box` plus an
# explicit `transform-origin` on every wind group.
# Each tier is (degrees of swing, seconds per full sway).
WIND_SWAY_TIERS = {
    'limb': (0.85, 7.4),
    'stalk': (2.4, 4.3),
    'bush': (1.1, 5.6),
    'fruit': (2.8, 3.2),
}
# Sky motion is a slide, not a hinge: clouds cross, the sun breathes.
WIND_CLOUD_DRIFT_X = 13.0
WIND_CLOUD_DRIFT_SECONDS = 24.0
# The sun climbs with your token total and then, at the end of the
# replay, has nowhere left to go -- so it needs an idle of its own or it
# reads as a sticker. A bob alone is too small to notice at this scale:
# it wanders a little, its rays turn, and its halo breathes.
WIND_SUN_WANDER_X = 9.0
WIND_SUN_WANDER_Y = 6.0
WIND_SUN_BOB_SECONDS = 19.0
WIND_SUN_SPIN_SECONDS = 64.0
WIND_SUN_PULSE_SECONDS = 7.5
WIND_SUN_PULSE_SCALE = 1.07
WIND_BIRD_FLAP_Y = 2.6
WIND_BIRD_FLAP_SECONDS = 0.62
# Storm motion lives *inside* the rain group, so it inherits the rain's
# own per-day opacity for free: no second animation has to be gated to
# the lapse, and when the garden is being tended it costs nothing but a
# handful of invisible paths.
STORM_GUST_COUNT = 12
STORM_GUST_SECONDS = 2.4
STORM_LEAF_COUNT = 14
STORM_LEAF_SECONDS = 3.6
# Torn cloud running ahead of the weather. The garden's own clouds are
# per-model shapes pinned to their slots -- these are scenery, and their
# job is to cross the sky fast enough that a lapse never looks paused.
STORM_SCUD_COUNT = 7
STORM_SCUD_SECONDS = 9.0
# Lightning. A lapse is the one stretch where every cumulative shape is
# frozen by definition, so without something large and fast the picture
# reads as a stall no matter how the frames are paced. This is the
# storm's own heartbeat -- and because it lives inside the rain group its
# peak is multiplied by the rain's opacity, so a four-day gap only
# flickers while a month away really does flash.
STORM_FLASH_SECONDS = 6.0
STORM_FLASH_PEAK = 0.34

TOOLTIP_PAD = 8.0
TOOLTIP_FONT_SIZE = 13.0
TOOLTIP_HEIGHT = TOOLTIP_FONT_SIZE + TOOLTIP_PAD * 2

TIMELINE_PER_DAY_SECONDS = 0.6
TIMELINE_MIN_DURATION_S = 5.0
TIMELINE_MAX_DURATION_S = 18.0
TIMELINE_MIN_DAYS_TO_ANIMATE = 2

# Extra strip below the legend, holding the scrubber that appears once the
# initial timelapse finishes playing.
SCRUBBER_HEIGHT = 40.0
SCRUBBER_MARGIN = 4.0
SCRUBBER_TOTAL_HEIGHT = SCRUBBER_HEIGHT + SCRUBBER_MARGIN * 2
SCRUBBER_Y = LEGEND_BAND_BOTTOM + SCRUBBER_MARGIN
TIMELINE_VIEWBOX_HEIGHT = LEGEND_BAND_BOTTOM + SCRUBBER_TOTAL_HEIGHT


def _escape_xml(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _title(text: str) -> str:
    """A `<title>` child that browsers render as a native hover tooltip."""
    return f'<title>{_escape_xml(text)}</title>'


def _tt_attr(day_labels: list[str]) -> str:
    """A `data-tt` attribute: one tooltip string per day, JSON-encoded.

    A static `<title>` can't track which day the timeline animation is
    currently showing, so `_render_tap_tooltip` reads this instead for any
    element whose stats grow over the timeline -- picking the entry that
    matches the SMIL clock's current position rather than always the last.
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


def _trunk_half_width(total_sessions: int) -> float:
    """Base half-width of the trunk, growing with cumulative sessions.

    A plain linear formula saturates at its cap within the first ~26
    sessions, which made the trunk (and its day-by-day growth animation)
    jump straight to full width on day one for anyone with a normal daily
    session count, instead of visibly widening across days/months like the
    canopy already does (see `_canopy_radius`).
    """
    growth = math.sqrt(
        min(total_sessions, TRUNK_SESSIONS_SATURATION)
        / TRUNK_SESSIONS_SATURATION
    )
    return (
        TRUNK_BASE_HALF_WIDTH_MIN
        + (TRUNK_BASE_HALF_WIDTH_MAX - TRUNK_BASE_HALF_WIDTH_MIN) * growth
    )


def _grown_size(
    value: float,
    final_value: float,
    minimum: float,
    final_size: float,
) -> float:
    """A shape's size on a day it has `value` of its eventual `final_value`.

    Interpolates from the shape's minimum up to its final size -- but a
    shape with nothing behind it yet has size zero, not the minimum. The
    minimum is what a shape looks like once it exists; before its first
    day of data (notably the timeline's empty day 0) it hasn't sprouted,
    so the whole garden grows out of bare ground rather than fading up
    from a pre-arranged set of seedlings.
    """
    # A shape that never accumulates anything (final_value of zero) is
    # still a shape -- it just sits at its minimum the whole way, as it
    # always has. Only a shape that *will* grow is held back to nothing.
    if not final_value:
        return final_size
    if value <= 0:
        return 0.0
    return minimum + (final_size - minimum) * min(value / final_value, 1.0)


def _trunk_half_widths_for_timeline(
    cumulative_sessions: list[int],
) -> list[float]:
    """Per-day trunk half-widths for the growth timelapse.

    Evaluating `_trunk_half_width` independently on each day's raw
    cumulative total (as `render_svg`'s static render does) makes the
    trunk start already partway up the saturation curve on day one --
    with a normal amount of prior history, there's almost no headroom left
    to visibly grow into over the remaining days. Branches sidestep this
    by interpolating as a fraction of *their own* final size instead of
    re-deriving an absolute value per day; do the same here so the trunk
    always starts near the minimum and grows into the real final width.

    Width only: the tree's *height* is not in this curve at all, it comes
    from the whole-tree scale in `_tree_growth_scales` — so the widths
    here are the widths of a full-grown trunk, which that scale then
    shrinks back down to a sapling's on early days.
    """
    final_width = _trunk_half_width(cumulative_sessions[-1])
    return [
        max(
            _grown_size(
                sessions,
                cumulative_sessions[-1],
                TRUNK_BASE_HALF_WIDTH_MIN,
                final_width,
            ),
            TRUNK_BASE_HALF_WIDTH_MIN,
        )
        for sessions in cumulative_sessions
    ]


def _tree_growth_scales(cumulative_sessions: list[int]) -> list[float]:
    """Per-day uniform scale for the whole tree, hinged on the ground.

    The tree used to stand at its final height from frame one and only
    widen, which read as a full-grown trunk being *filled in* rather than
    a tree growing. One scale about (`TRUNK_CENTER_X`, `GROUND_Y`) on the
    group carrying trunk, rings, branches and leaves lifts all of it out
    of the soil together, and costs O(days) of animation values instead
    of re-emitting every path per day at a new height.

    It is uniform, not vertical-only: a trunk stretched in y alone is a
    stubby full-width stump, and the leaves on it would be ellipses.
    Because it multiplies the width curve above, the two compose --
    early days are a thin short sapling, the last frame is exactly the
    static garden.
    """
    final = cumulative_sessions[-1] if cumulative_sessions else 0
    return [
        _grown_size(sessions, final, TREE_GROWTH_SCALE_MIN, 1.0)
        for sessions in cumulative_sessions
    ]


def _render_tree_growth(
    body: str,
    scales: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    """Wrap the tree in the ground-hinged growth scale.

    translate out, scale, translate back -- `animateTransform` replaces
    the whole transform of the element it sits on, so the pivot needs
    groups of its own (same shape as `_render_timeline_rings`).
    """
    cx = TRUNK_CENTER_X
    scale = _animate_transform_tag(
        'scale',
        [f'{value:.4f} {value:.4f}' for value in scales],
        key_times,
        duration,
    )
    return (
        f'<g class="tree-growth" '
        f'transform="translate({cx:.2f},{GROUND_Y:.2f})"><g>{scale}'
        f'<g transform="translate({-cx:.2f},{-GROUND_Y:.2f})">'
        f'{body}</g></g></g>'
    )


def _ring_stroke_width(sessions: int) -> float:
    """A ring's boldness for a day with this many sessions.

    Same saturation problem as the trunk: a linear formula capped out by
    ~9 sessions/day, so any normal work day maxed out the stroke and every
    ring looked identically bold regardless of how busy the day actually
    was.
    """
    growth = math.sqrt(
        min(sessions, RING_SESSIONS_SATURATION) / RING_SESSIONS_SATURATION
    )
    return (
        RING_STROKE_WIDTH_MIN
        + (RING_STROKE_WIDTH_MAX - RING_STROKE_WIDTH_MIN) * growth
    )


def _branch_length(lines_added: int) -> float:
    """A branch's length for a repo with this many cumulative lines added.

    Lines added are distributed like most repo metrics: one or two repos
    carry an order of magnitude more than the rest. A linear mapping leaves
    every branch stubby, and a power curve (this used to be
    fraction ** 0.7) still hands the dominant repo most of the available
    length, which is what left the crown lopsided -- one branch at the cap
    and a fan of short ones under it.

    A log curve balances that: it climbs steeply below
    BRANCH_LENGTH_LOG_KNEE, so a modest repo still gets a branch with real
    presence, then compresses hard above it, so a 10x bigger repo reads as
    clearly bigger without running away with the frame. Relative ratios
    shrink -- that is the point. Absolute proportionality lives in the
    tooltip; the silhouette is for balance.
    """
    lines = min(lines_added, BRANCH_LINES_SATURATION)
    growth = math.log1p(lines / BRANCH_LENGTH_LOG_KNEE) / math.log1p(
        BRANCH_LINES_SATURATION / BRANCH_LENGTH_LOG_KNEE
    )
    return BRANCH_LENGTH_MIN + (BRANCH_LENGTH_MAX - BRANCH_LENGTH_MIN) * growth


def _branch_width(total_tokens: int) -> float:
    """A branch's thickness for a repo with this many cumulative tokens.

    Length already tracks lines added and leaf count already tracks
    sessions, so thickness is free to carry a third signal: how much
    Claude actually read and wrote on that repo (input + output tokens),
    which can diverge a lot from lines-added for repos with long research
    or review sessions that touch little code. Same sqrt-saturation shape
    as the other size formulas so small totals still get lifted off the
    floor instead of staying visually flat.
    """
    growth = math.sqrt(
        min(total_tokens, BRANCH_TOKENS_SATURATION) / BRANCH_TOKENS_SATURATION
    )
    return BRANCH_WIDTH_MIN + (BRANCH_WIDTH_MAX - BRANCH_WIDTH_MIN) * growth


def _half_width_at(y: float, base_half_width: float) -> float:
    trunk_fraction = (GROUND_Y - y) / TRUNK_HEIGHT
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    return (
        base_half_width - (base_half_width - top_half_width) * trunk_fraction
    )


# Seasons. Vitality (see `_daily_vitality`) runs 1.0 for "worked today"
# down toward 0 for "long gone", and every seasonal colour is a blend
# between the living value and its dormant counterpart. One shared paint
# per leaf colour means the whole canopy turns with five <animate> tags
# instead of one per leaf, which matters when a big garden has thousands.
LEAF_PAINT_ID = 'leafPaint'
AUTUMN_COLORS = ('#8a4b1e', '#a35c1f', '#b8792a', '#c98f36', '#d8a441')
DORMANT_GROUND_STOPS = ('#8d8a5a', '#6b6942')
LIVING_GROUND_STOPS = ('#74b25e', '#3f7a3f')
# The canopy blobs sit behind the individual leaves, so they have to turn
# with them -- a gold canopy over green undergrowth reads as a rendering
# bug rather than as autumn.
DORMANT_CANOPY_STOPS = ('#c9a05a', '#a37438', '#6b4a20')
LIVING_CANOPY_STOPS = ('#8fcf6f', '#5a9e5a', '#2f5f2f')
# Leaves thin out as well as turn -- a bare-branch winter needs both.
LEAF_OPACITY_LIVING = 0.92
LEAF_OPACITY_DORMANT = 0.12


def _blend_hex(dormant: str, living: str, vitality: float) -> str:
    """Mix two #rrggbb colours, `vitality` 1.0 being fully living."""
    ratio = max(0.0, min(vitality, 1.0))
    channels = []
    for start in (1, 3, 5):
        cold = int(dormant[start : start + 2], 16)
        warm = int(living[start : start + 2], 16)
        channels.append(round(cold + (warm - cold) * ratio))
    return '#{:02x}{:02x}{:02x}'.format(*channels)


def _leaf_color(index: int, vitality: float) -> str:
    return _blend_hex(AUTUMN_COLORS[index], LEAF_COLORS[index], vitality)


def _leaf_opacity(vitality: float) -> float:
    ratio = max(0.0, min(vitality, 1.0))
    return (
        LEAF_OPACITY_DORMANT
        + (LEAF_OPACITY_LIVING - LEAF_OPACITY_DORMANT) * ratio
    )


def _season_animations(
    vitality: list[float],
    key_times: list[float],
    duration: float,
) -> tuple[list[str], list[str], list[str]]:
    """Leaf-paint, ground-stop and canopy-stop colour animations, one per stop.

    Returned rather than emitted inline because the paints they drive
    live in `<defs>`, which is rendered before any of the shapes that
    reference them.
    """
    leaf_animations = [
        _animate_tag(
            'stop-color',
            [_leaf_color(index, value) for value in vitality],
            key_times,
            duration,
            smooth=True,
        )
        for index in range(len(LEAF_COLORS))
    ]
    ground_animations = [
        _animate_tag(
            'stop-color',
            [_blend_hex(dormant, living, value) for value in vitality],
            key_times,
            duration,
            smooth=True,
        )
        for dormant, living in zip(
            DORMANT_GROUND_STOPS, LIVING_GROUND_STOPS, strict=True
        )
    ]
    canopy_animations = [
        _animate_tag(
            'stop-color',
            [_blend_hex(dormant, living, value) for value in vitality],
            key_times,
            duration,
            smooth=True,
        )
        for dormant, living in zip(
            DORMANT_CANOPY_STOPS, LIVING_CANOPY_STOPS, strict=True
        )
    ]
    return leaf_animations, ground_animations, canopy_animations


def _render_leaf_paints(
    animations: list[str] | None = None, vitality: float = 1.0
) -> str:
    """One single-stop gradient per leaf colour, so leaves share a paint."""
    paints = []
    for index in range(len(LEAF_COLORS)):
        animate = animations[index] if animations else ''
        paints.append(
            f'<linearGradient id="{LEAF_PAINT_ID}{index}">'
            f'<stop offset="0%" '
            f'stop-color="{_leaf_color(index, vitality)}">{animate}</stop>'
            f'</linearGradient>'
        )
    return ''.join(paints)


def _render_defs(
    leaf_animations: list[str] | None = None,
    ground_animations: list[str] | None = None,
    canopy_animations: list[str] | None = None,
    vitality: float = 1.0,
) -> str:
    ground = ground_animations or ['', '']
    canopy = canopy_animations or ['', '', '']
    canopy_stops = [
        _blend_hex(dormant, living, vitality)
        for dormant, living in zip(
            DORMANT_CANOPY_STOPS, LIVING_CANOPY_STOPS, strict=True
        )
    ]
    ground_stops = [
        _blend_hex(dormant, living, vitality)
        for dormant, living in zip(
            DORMANT_GROUND_STOPS, LIVING_GROUND_STOPS, strict=True
        )
    ]
    return (
        '<defs>'
        + _render_leaf_paints(leaf_animations, vitality)
        + '<linearGradient id="skyGradient" x1="0%" y1="0%" x2="0%" y2="100%">'
        '<stop offset="0%" stop-color="#1c3d5a" />'
        '<stop offset="55%" stop-color="#2f5c82" />'
        '<stop offset="100%" stop-color="#4a7fa5" />'
        '</linearGradient>'
        '<linearGradient id="groundGradient" '
        'x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="{ground_stops[0]}">'
        f'{ground[0]}</stop>'
        f'<stop offset="100%" stop-color="{ground_stops[1]}">'
        f'{ground[1]}</stop>'
        '</linearGradient>'
        '<linearGradient id="trunkGradient" gradientUnits="userSpaceOnUse" '
        f'x1="{TRUNK_CENTER_X - TRUNK_BASE_HALF_WIDTH_MAX}" y1="0" '
        f'x2="{TRUNK_CENTER_X + TRUNK_BASE_HALF_WIDTH_MAX}" y2="0">'
        '<stop offset="0%" stop-color="#4a2e1a" />'
        '<stop offset="45%" stop-color="#7a4a26" />'
        '<stop offset="70%" stop-color="#6b4226" />'
        '<stop offset="100%" stop-color="#3a2412" />'
        '</linearGradient>'
        '<radialGradient id="canopyGradient" cx="35%" cy="30%" r="75%">'
        f'<stop offset="0%" stop-color="{canopy_stops[0]}">{canopy[0]}</stop>'
        f'<stop offset="55%" stop-color="{canopy_stops[1]}">{canopy[1]}</stop>'
        f'<stop offset="100%" stop-color="{canopy_stops[2]}">'
        f'{canopy[2]}</stop>'
        '</radialGradient>'
        f'{_cloud_gradient_defs()}'
        '<radialGradient id="sunGradient" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{SUN_GRADIENT_STOPS[0]}" />'
        f'<stop offset="55%" stop-color="{SUN_GRADIENT_STOPS[1]}" />'
        f'<stop offset="100%" stop-color="{SUN_GRADIENT_STOPS[2]}" />'
        '</radialGradient>'
        '<radialGradient id="sunHaloGradient" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{SUN_HALO_COLOR}" '
        'stop-opacity="0.55" />'
        f'<stop offset="100%" stop-color="{SUN_HALO_COLOR}" '
        'stop-opacity="0" />'
        '</radialGradient>'
        '<radialGradient id="moonGradient" cx="38%" cy="34%" r="62%">'
        f'<stop offset="0%" stop-color="{MOON_GRADIENT_STOPS[0]}" />'
        f'<stop offset="58%" stop-color="{MOON_GRADIENT_STOPS[1]}" />'
        f'<stop offset="100%" stop-color="{MOON_GRADIENT_STOPS[2]}" />'
        '</radialGradient>'
        '<radialGradient id="moonHaloGradient" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{MOON_HALO_COLOR}" '
        'stop-opacity="0.45" />'
        f'<stop offset="100%" stop-color="{MOON_HALO_COLOR}" '
        'stop-opacity="0" />'
        '</radialGradient>'
        '<radialGradient id="bushGradient" cx="35%" cy="25%" r="75%">'
        '<stop offset="0%" stop-color="#a9c95a" />'
        '<stop offset="55%" stop-color="#6f8f3a" />'
        '<stop offset="100%" stop-color="#3f5620" />'
        '</radialGradient>'
        '<filter id="softBlur" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="3" />'
        '</filter>'
        '</defs>'
    )


def _render_background() -> str:
    wave = 6
    mid_x = VIEWBOX_WIDTH * 0.5
    quarter_x = VIEWBOX_WIDTH * 0.25
    three_quarter_x = VIEWBOX_WIDTH * 0.75
    ground_edge = (
        f'M0,{GROUND_Y} '
        f'Q {quarter_x},{GROUND_Y - wave} {mid_x},{GROUND_Y} '
        f'Q {three_quarter_x},{GROUND_Y + wave} {VIEWBOX_WIDTH},{GROUND_Y}'
    )
    ground_fill = (
        f'{ground_edge} L {VIEWBOX_WIDTH},{VIEWBOX_HEIGHT} '
        f'L0,{VIEWBOX_HEIGHT} Z'
    )
    return (
        f'<rect x="0" y="0" width="{VIEWBOX_WIDTH}" height="{VIEWBOX_HEIGHT}" '
        f'fill="url(#skyGradient)" />'
        f'<path d="{ground_fill}" fill="url(#groundGradient)" />'
        f'<path d="{ground_edge}" fill="none" stroke="#2f5f2f" '
        f'stroke-width="2" opacity="0.5" />'
        f'{_render_grass()}'
    )


def _wind_style() -> str:
    """Every idle-motion keyframe in the document, emitted once.

    One rule per tier rather than one per element: the phase offset that
    stops the garden swaying in lockstep is a per-element
    `animation-delay`, which needs no keyframes of its own.
    """
    rules = []
    for tier, (degrees, seconds) in WIND_SWAY_TIERS.items():
        rules.append(
            f'@keyframes ccg-sway-{tier}{{'
            f'0%,100%{{transform:rotate({-degrees:.2f}deg)}}'
            f'50%{{transform:rotate({degrees:.2f}deg)}}}}'
            f'.ccg-sway-{tier}{{animation:ccg-sway-{tier} {seconds:.2f}s '
            f'ease-in-out infinite}}'
        )
    rules.append(
        f'@keyframes ccg-drift{{'
        f'0%,100%{{transform:translateX({-WIND_CLOUD_DRIFT_X:.1f}px)}}'
        f'50%{{transform:translateX({WIND_CLOUD_DRIFT_X:.1f}px)}}}}'
        f'.ccg-drift{{animation:ccg-drift '
        f'{WIND_CLOUD_DRIFT_SECONDS:.1f}s ease-in-out infinite}}'
    )
    rules.append(
        f'@keyframes ccg-bob{{'
        f'0%,100%{{transform:translate({-WIND_SUN_WANDER_X:.1f}px,'
        f'{WIND_SUN_WANDER_Y:.1f}px)}}'
        f'25%{{transform:translate(0px,{-WIND_SUN_WANDER_Y:.1f}px)}}'
        f'50%{{transform:translate({WIND_SUN_WANDER_X:.1f}px,'
        f'{WIND_SUN_WANDER_Y * 0.4:.1f}px)}}'
        f'75%{{transform:translate(0px,{-WIND_SUN_WANDER_Y * 0.6:.1f}px)}}}}'
        f'.ccg-bob{{animation:ccg-bob '
        f'{WIND_SUN_BOB_SECONDS:.1f}s ease-in-out infinite}}'
    )
    rules.append(
        f'@keyframes ccg-spin{{'
        f'0%{{transform:rotate(0deg)}}100%{{transform:rotate(360deg)}}}}'
        f'.ccg-spin{{animation:ccg-spin '
        f'{WIND_SUN_SPIN_SECONDS:.1f}s linear infinite}}'
    )
    rules.append(
        f'@keyframes ccg-pulse{{'
        f'0%,100%{{transform:scale(1)}}'
        f'50%{{transform:scale({WIND_SUN_PULSE_SCALE:.2f})}}}}'
        f'.ccg-pulse{{animation:ccg-pulse '
        f'{WIND_SUN_PULSE_SECONDS:.1f}s ease-in-out infinite}}'
    )
    rules.append(
        f'@keyframes ccg-flap{{'
        f'0%,100%{{transform:translateY(0)}}'
        f'50%{{transform:translateY({-WIND_BIRD_FLAP_Y:.1f}px)}}}}'
        f'.ccg-flap{{animation:ccg-flap '
        f'{WIND_BIRD_FLAP_SECONDS:.2f}s ease-in-out infinite}}'
    )
    rules.append(
        # Two quick strikes, then a long dark wait: infrequent and brief
        # on purpose -- a full-canvas flicker is exactly the pattern
        # photosensitive viewers need protecting from, and it is disabled
        # outright under prefers-reduced-motion below.
        f'@keyframes ccg-flash{{'
        f'0%,3%{{opacity:0}}'
        f'4%{{opacity:{STORM_FLASH_PEAK:.2f}}}'
        f'6%{{opacity:0.06}}'
        f'8%{{opacity:{STORM_FLASH_PEAK * 0.7:.2f}}}'
        f'13%,100%{{opacity:0}}}}'
        f'.ccg-flash{{animation:ccg-flash {STORM_FLASH_SECONDS:.1f}s '
        f'linear infinite}}'
    )
    rules.append(
        f'@keyframes ccg-scud{{'
        f'0%{{transform:translateX(-320px)}}'
        f'100%{{transform:translateX({VIEWBOX_WIDTH + 320:.0f}px)}}}}'
        f'.ccg-scud{{animation:ccg-scud {STORM_SCUD_SECONDS:.1f}s '
        f'linear infinite}}'
    )
    rules.append(
        f'@keyframes ccg-gust{{'
        f'0%{{transform:translateX(-140px);opacity:0}}'
        f'25%{{opacity:0.9}}'
        f'100%{{transform:translateX({VIEWBOX_WIDTH + 160:.0f}px);'
        f'opacity:0}}}}'
        f'.ccg-gust{{animation:ccg-gust {STORM_GUST_SECONDS:.2f}s '
        f'linear infinite}}'
    )
    rules.append(
        f'@keyframes ccg-tumble{{'
        f'0%{{transform:translate(-60px,0) rotate(0deg);opacity:0}}'
        f'20%{{opacity:1}}'
        f'100%{{transform:translate({VIEWBOX_WIDTH + 90:.0f}px,-40px) '
        f'rotate(900deg);opacity:0}}}}'
        f'.ccg-tumble{{animation:ccg-tumble {STORM_LEAF_SECONDS:.2f}s '
        f'linear infinite}}'
    )
    # Every drop falls the same distance, so the travel lives in the one
    # keyframe rule and only speed and phase vary per drop.
    fall_travel = VIEWBOX_HEIGHT + RAIN_STREAK_MAX * 2
    rules.append(
        f'@keyframes ccg-fall{{'
        f'from{{transform:translate(0,0)}}'
        f'to{{transform:translate({fall_travel * RAIN_SLANT:.1f}px,'
        f'{fall_travel:.1f}px)}}}}'
        f'.ccg-fall{{animation:ccg-fall 1s linear infinite}}'
    )
    # Opacity, not transform, so it stays out of `wind_classes` below --
    # `will-change: transform` on 70 stars buys nothing and asks the
    # compositor for 70 layers. Duration and phase ride inline per star.
    rules.append(
        f'@keyframes ccg-twinkle{{'
        f'0%,100%{{opacity:{STAR_TWINKLE_MIN_OPACITY}}}'
        f'50%{{opacity:1}}}}'
        f'.ccg-twinkle{{animation:ccg-twinkle 4s ease-in-out infinite}}'
    )
    wind_classes = (
        '.ccg-sway-'
        + ',.ccg-sway-'.join(WIND_SWAY_TIERS)
        + ',.ccg-drift,.ccg-bob,.ccg-spin,.ccg-pulse'
        + ',.ccg-flap,.ccg-gust,.ccg-tumble,.ccg-scud,.ccg-flash'
    )
    return (
        '<style>'
        + ''.join(rules)
        + f'{wind_classes}{{transform-box:view-box;will-change:transform}}'
        # The legend reuses the garden's own shape renderers for its icons,
        # which brings their idle motion along with them. A key is a table,
        # not a scene: kill every animation inside it, by descendant
        # selector so a new icon can't reintroduce one. The extra class
        # selector outranks the `.ccg-*` rules above without !important.
        + '.legend [class*="ccg-"]{animation:none}'
        + '@media (prefers-reduced-motion:reduce)'
        + f'{{{wind_classes},.ccg-twinkle,.ccg-fall{{animation:none}}}}'
        + '</style>'
    )


WIND_PERIODS = {
    **{
        f'ccg-sway-{tier}': seconds
        for tier, (_, seconds) in WIND_SWAY_TIERS.items()
    },
    'ccg-drift': WIND_CLOUD_DRIFT_SECONDS,
    'ccg-bob': WIND_SUN_BOB_SECONDS,
    'ccg-spin': WIND_SUN_SPIN_SECONDS,
    'ccg-pulse': WIND_SUN_PULSE_SECONDS,
    'ccg-flap': WIND_BIRD_FLAP_SECONDS,
}


def _wind_group(
    css_class: str,
    seed: str,
    pivot: tuple[float, float] = (0.0, 0.0),
) -> str:
    """Open a wind group hinged at `pivot`, phase-shifted by `seed`.

    The negative delay starts each element part-way into the shared loop,
    so a hedge of bushes ripples instead of pulsing as one.
    """
    phase = random.Random(f'ccgarden-wind:{seed}').uniform(
        0.0, WIND_PERIODS[css_class]
    )
    x, y = pivot
    return (
        f'<g class="{css_class}" '
        f'style="transform-origin:{x:.1f}px {y:.1f}px;'
        f'animation-delay:-{phase:.2f}s">'
    )


def _render_grass() -> str:
    rng = random.Random('ccgarden-grass')
    elements = []
    for _ in range(46):
        x = rng.uniform(4, VIEWBOX_WIDTH - 4)
        y = GROUND_Y + rng.uniform(4, VIEWBOX_HEIGHT - GROUND_Y - 8)
        height = rng.uniform(6, 13)
        lean = rng.uniform(-4, 4)
        elements.append(
            f'<path d="M{x},{y} Q{x + lean},{y - height * 0.6} '
            f'{x + lean * 1.6},{y - height}" fill="none" '
            f'stroke="#2f5f2f" stroke-width="1.4" stroke-linecap="round" '
            f'opacity="0.4" />'
        )
    return ''.join(elements)


# The sky darkens with the share of that day's prompts typed between
# 21:00 and 06:00 local. Unlike every other dimension this one isn't a
# saturating growth curve -- it's already a 0..1 ratio -- so it only needs
# a ceiling, to keep even an all-night garden readable rather than black.
NIGHT_VEIL_MAX_OPACITY = 0.62
# Almost nobody types a majority of their prompts after 21:00, so a raw
# ratio would leave every garden in permanent daylight. Saturating at 45%
# means a genuine night owl gets a genuinely dark sky, while an ordinary
# evening habit still shows as dusk rather than noon.
NIGHTNESS_SATURATION = 0.45
NIGHT_VEIL_COLOR = '#0b1636'
STAR_COUNT = 70
STAR_FIELD_BOTTOM = 420.0
STAR_RADIUS_MIN = 0.6
STAR_RADIUS_MAX = 1.9
STAR_COLOR = '#fdfbf0'
# Stars sit behind the tree and clouds but in front of the sky, so a
# night garden reads as "lit from behind" rather than as speckled foliage.
STAR_TWINKLE_MIN_S = 2.4
STAR_TWINKLE_MAX_S = 6.5
STAR_TWINKLE_MIN_OPACITY = 0.35


def _star_field() -> list[tuple[float, float, float, float, float]]:
    """Deterministic (x, y, radius, twinkle duration, phase) per star.

    Seeded like the grass so the same db always renders the same sky.
    Stars thin out toward the horizon, which is where the tree and the
    ground would hide them anyway.
    """
    rng = random.Random('ccgarden-stars')
    stars = []
    for _ in range(STAR_COUNT):
        depth = rng.random() ** 0.6
        stars.append(
            (
                rng.uniform(4, VIEWBOX_WIDTH - 4),
                depth * STAR_FIELD_BOTTOM,
                rng.uniform(STAR_RADIUS_MIN, STAR_RADIUS_MAX),
                rng.uniform(STAR_TWINKLE_MIN_S, STAR_TWINKLE_MAX_S),
                rng.uniform(0.0, 1.0),
            )
        )
    return stars


def _render_stars(
    opacity: float,
    animate: str = '',
    title: str = '',
    group_attrs: str = '',
) -> str:
    """The star field, faded in as a whole by `opacity`.

    `animate` carries the group's per-day opacity <animate> in the
    timeline render; the static render just bakes the value in.

    The stars carry the sky's tooltip, because they're the only part of
    the night that can take a hover: the veil has to stay
    `pointer-events="none"` or it would swallow every shape's tooltip
    underneath it, and a fully-daylit garden has no stars to hover --
    which is the right answer, since it has no night to describe.
    """
    stars = []
    for x, y, radius, twinkle, phase in _star_field():
        stars.append(
            f'<circle class="ccg-twinkle" '
            f'cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}" '
            f'fill="{STAR_COLOR}" '
            f'style="animation-duration:{twinkle:.2f}s;'
            f'animation-delay:-{phase * twinkle:.2f}s" />'
        )
    return (
        f'<g class="stars" opacity="{opacity:.3f}" {group_attrs}>'
        f'{title}{animate}{"".join(stars)}</g>'
    )


def _saturated_nightness(nightness: float) -> float:
    """Raw night share, curved onto 0..1 by `NIGHTNESS_SATURATION`."""
    return max(0.0, min(nightness / NIGHTNESS_SATURATION, 1.0))


def _night_veil_opacity(nightness: float) -> float:
    return _saturated_nightness(nightness) * NIGHT_VEIL_MAX_OPACITY


def _render_night_veil(nightness: float, animate: str = '') -> str:
    """A deep-blue wash over the whole garden, scaled by `nightness`.

    Drawn over the scene rather than under it so the ground and foliage
    go dusky too -- a night sky above brightly lit grass reads as wrong.
    Never over the legend, which has to stay readable.
    """
    return (
        f'<rect class="night" x="0" y="0" width="{VIEWBOX_WIDTH}" '
        f'height="{VIEWBOX_HEIGHT}" fill="{NIGHT_VEIL_COLOR}" '
        f'opacity="{_night_veil_opacity(nightness):.3f}" '
        f'pointer-events="none">{animate}</rect>'
    )


def _night_title(nightness: float, hour_counts: dict[int, int]) -> str:
    total = sum(hour_counts.values())
    if total <= 0:
        return ''
    peak = max(hour_counts.items(), key=lambda item: (item[1], -item[0]))[0]
    return _title(
        f'Sky — {nightness:.0%} of {total:,} prompts typed at night; '
        f'busiest hour {peak:02d}:00'
    )


def _render_timeline_night(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
    *,
    veil: bool,
) -> str:
    """The star field (`veil=False`) or the night wash (`veil=True`).

    Both are the same signal animated over the same per-day values, but
    they sit at opposite ends of the drawing order -- stars behind the
    garden, veil in front of it -- so they're rendered in two passes.

    A db recorded before `daily_hour_usage` existed has no nightness at
    all, in which case there's nothing to draw and no animation to emit.
    """
    nightness = timeline.daily_nightness
    if not nightness or not any(nightness):
        return ''

    if veil:
        values = [f'{_night_veil_opacity(value):.3f}' for value in nightness]
        animate = _animate_tag(
            'opacity', values, key_times, duration, smooth=True
        )
        return _render_night_veil(nightness[-1], animate)

    values = [f'{_saturated_nightness(value):.3f}' for value in nightness]
    animate = _animate_tag('opacity', values, key_times, duration, smooth=True)
    day_labels = [
        f'Sky — {_format_day(day)}: {value:.0%} of prompts typed at night'
        for day, value in zip(timeline.days, nightness, strict=True)
    ]
    return _render_stars(
        _saturated_nightness(nightness[-1]),
        animate,
        _title(day_labels[-1]),
        _tt_attr(day_labels),
    )


# Rain. The cumulative shapes hold their value across a gap, so a lapse
# would otherwise read as the animation stalling rather than as time
# passing. Rain rides the same vitality signal as the season, but it is
# the part a viewer notices *immediately*: colour drifts, weather starts.
# Thresholds are in days away rather than in raw vitality, because
# that's the unit the gap is actually in -- `data.py` spends several
# frames crossing a gap, so the renderer sees a lapse deepen day by day
# and the onset has to land on a day count, not on a raw vitality number
# it would straddle by accident.
#
# One day, not two: the renderer only ever sees a dormant frame at all
# when the gap was long enough to count as a lapse, and the first of
# those frames is the one held longest (`DORMANT_FRAME_DWELL`). With the
# onset at two days that frame had no rain, no dimmed sun and a season
# tint too faint to see -- the single longest interval in the replay was
# also the only one in which nothing whatsoever happened.
RAIN_ONSET_DAYS = 1.0
RAIN_FULL_DAYS = 10.0
# Rain that fades in from nothing spends its first frames looking like a
# compression artefact, so the first rainy day already gets a real
# drizzle and the ramp thickens it from there.
RAIN_MIN_INTENSITY = 0.28
# What's left of the sun at the height of a downpour.
SUN_STORM_MIN_OPACITY = 0.15
RAIN_MAX_OPACITY = 0.7
RAIN_DROP_COUNT = 150
RAIN_COLOR = '#cfe0ef'
RAIN_OVERCAST_COLOR = '#5d707e'
RAIN_OVERCAST_OPACITY = 0.34
RAIN_STREAK_MIN = 10.0
RAIN_STREAK_MAX = 26.0
# Wind blows the streaks rightward; the same ratio drives both the line's
# slant and its fall vector, or the drops would slide sideways.
RAIN_SLANT = 0.22
RAIN_FALL_MIN_S = 0.55
RAIN_FALL_MAX_S = 1.15


def _exact_days_away(vitality: float) -> float:
    """Invert `_daily_vitality`'s decay back into days of silence."""
    if vitality >= 1.0:
        return 0.0
    if vitality <= 0.0:
        return math.inf
    return -math.log2(vitality) * DORMANCY_HALF_LIFE_DAYS


def _days_away(vitality: float) -> int | None:
    """Whole days of silence, or None for a garden gone past measuring."""
    days = _exact_days_away(vitality)
    return round(days) if math.isfinite(days) else None


def _rain_intensity(vitality: float) -> float:
    """0 while the garden is being tended, ramping to 1 once it's gone."""
    days = _exact_days_away(vitality)
    # Tolerantly: a day's vitality round-trips through a log and lands a
    # hair under its own day count, which at the onset is the difference
    # between a drizzle and a frame where nothing happens at all.
    if days < RAIN_ONSET_DAYS - EPSILON:
        return 0.0
    if days >= RAIN_FULL_DAYS:
        return 1.0
    ramp = (days - RAIN_ONSET_DAYS) / (RAIN_FULL_DAYS - RAIN_ONSET_DAYS)
    return RAIN_MIN_INTENSITY + (1.0 - RAIN_MIN_INTENSITY) * ramp


def _rain_opacity(vitality: float) -> float:
    return _rain_intensity(vitality) * RAIN_MAX_OPACITY


def _sun_storm_opacity(vitality: float) -> float:
    """How much of the sun survives the cloud, 1.0 in clear weather.

    The sun's height is driven by your token total, which -- like every
    cumulative shape -- holds still through a lapse. Everything else on
    screen is moving by then (rain, scud, the wind), so a sun that just
    stops mid-sky reads as a broken animation rather than as weather.
    Fading it out is what a storm actually does to a sun, and it is a
    change the sun can go on making while its position is frozen.
    """
    return 1.0 - (1.0 - SUN_STORM_MIN_OPACITY) * _rain_intensity(vitality)


def _rain_field() -> list[tuple[float, float, float, float, float]]:
    """Deterministic (x, length, width, fall duration, phase) per drop.

    Seeded like the grass and the stars, so the same db always renders
    the same downpour. Every drop starts above the top edge and falls
    clear past the bottom one, so nothing pops in or out mid-frame --
    the spread comes from the phase offsets, not from staggered starts.
    """
    rng = random.Random('ccgarden-rain')
    drops = []
    for _ in range(RAIN_DROP_COUNT):
        drops.append(
            (
                rng.uniform(-VIEWBOX_WIDTH * RAIN_SLANT, VIEWBOX_WIDTH),
                rng.uniform(RAIN_STREAK_MIN, RAIN_STREAK_MAX),
                rng.uniform(0.7, 1.4),
                rng.uniform(RAIN_FALL_MIN_S, RAIN_FALL_MAX_S),
                rng.uniform(0.0, 1.0),
            )
        )
    return drops


def _render_rain(
    opacity: float,
    animate: str = '',
    title: str = '',
    group_attrs: str = '',
) -> str:
    """Falling streaks plus an overcast wash, faded in as a whole.

    `animate` carries the group's per-day opacity <animate> in the
    timeline render; the static render bakes the value in. The wash is
    `pointer-events="none"` -- it covers the entire garden, and would
    otherwise swallow every shape's tooltip -- while the streaks
    themselves stay hoverable, which is what carries the rain's own
    tooltip.
    """
    drops = []
    for x, length, width, fall, phase in _rain_field():
        top_y = -RAIN_STREAK_MAX - length
        drops.append(
            f'<line x1="{x:.1f}" y1="{top_y:.1f}" '
            f'x2="{x + length * RAIN_SLANT:.1f}" '
            f'y2="{top_y + length:.1f}" '
            f'stroke="{RAIN_COLOR}" stroke-width="{width:.2f}" '
            f'stroke-linecap="round" class="ccg-fall" '
            f'style="animation-duration:{fall:.2f}s;'
            f'animation-delay:-{phase * fall:.2f}s" />'
        )
    return (
        f'<g class="rain" opacity="{opacity:.3f}" {group_attrs}>'
        f'{title}'
        f'{animate}'
        f'<rect x="0" y="0" width="{VIEWBOX_WIDTH}" '
        f'height="{VIEWBOX_HEIGHT}" fill="{RAIN_OVERCAST_COLOR}" '
        f'opacity="{RAIN_OVERCAST_OPACITY}" pointer-events="none" />'
        f'{"".join(drops)}</g>'
    )


def _storm_opacity(vitality: float) -> float:
    """How present the blowing weather is, on the rain's own signal.

    Deliberately *not* the rain's opacity. A lapse freezes every
    cumulative shape, so the storm is all the motion those frames have --
    and at a short gap the rain is only a quarter opaque, which left the
    gusts and the scud so faint that the replay still read as paused
    (measured: 5% of pixels changing per quarter-second against 19%
    during growth). Square-rooting the intensity brings a drizzle's
    wind up to something you can see without touching how wet it looks.
    """
    return math.sqrt(_rain_intensity(vitality))


def _render_storm(opacity: float, animate: str = '') -> str:
    """Gust streaks, torn-off leaves, scud and lightning.

    Rain alone falls straight through a still garden, which reads as
    weather happening *to* a photograph. These blow across it.
    """
    rng = random.Random('ccgarden-storm')
    lightning = (
        f'<rect class="ccg-flash" x="0" y="0" width="{VIEWBOX_WIDTH}" '
        f'height="{VIEWBOX_HEIGHT}" fill="#f2f7ff" opacity="0" '
        f'style="transform-origin:0px 0px" />'
    )
    parts = [lightning]
    for index in range(STORM_SCUD_COUNT):
        cy = rng.uniform(50.0, 250.0)
        radius = rng.uniform(46.0, 88.0)
        speed = STORM_SCUD_SECONDS * rng.uniform(0.7, 1.5)
        delay = rng.uniform(0.0, speed)
        puffs = ''.join(
            f'<path d="{d}" fill="{RAIN_OVERCAST_COLOR}" opacity="0.72" />'
            for d in _cloud_puffs_d(radius, f'ccgarden-scud:{index}')
        )
        parts.append(
            f'<g class="ccg-scud" '
            f'style="transform-origin:0px 0px;'
            f'animation-duration:{speed:.2f}s;'
            f'animation-delay:-{delay:.2f}s">'
            f'<g transform="translate(0,{cy:.1f})">{puffs}</g></g>'
        )
    for _index in range(STORM_GUST_COUNT):
        y = rng.uniform(40.0, GROUND_Y - 20.0)
        length = rng.uniform(70.0, 190.0)
        dip = rng.uniform(-14.0, 14.0)
        delay = rng.uniform(0.0, STORM_GUST_SECONDS)
        speed = STORM_GUST_SECONDS * rng.uniform(0.8, 1.35)
        parts.append(
            f'<path class="ccg-gust" d="M0,{y:.1f} '
            f'q{length / 2:.1f},{dip:.1f} {length:.1f},0" fill="none" '
            f'stroke="{RAIN_COLOR}" stroke-width="{rng.uniform(1.0, 2.2):.2f}"'
            f' stroke-linecap="round" opacity="0.85" '
            f'style="transform-origin:0px 0px;'
            f'animation-duration:{speed:.2f}s;'
            f'animation-delay:-{delay:.2f}s" />'
        )
    for index in range(STORM_LEAF_COUNT):
        y = rng.uniform(GROUND_Y * 0.35, GROUND_Y - 10.0)
        size = rng.uniform(3.0, 6.0)
        color = LEAF_COLORS[index % len(LEAF_COLORS)]
        delay = rng.uniform(0.0, STORM_LEAF_SECONDS)
        speed = STORM_LEAF_SECONDS * rng.uniform(0.75, 1.4)
        parts.append(
            f'<ellipse class="ccg-tumble" cx="0" cy="{y:.1f}" '
            f'rx="{size:.1f}" ry="{size * 0.45:.1f}" fill="{color}" '
            f'opacity="0.9" '
            f'style="transform-origin:0px {y:.1f}px;'
            f'animation-duration:{speed:.2f}s;'
            f'animation-delay:-{delay:.2f}s" />'
        )
    return (
        f'<g class="storm" opacity="{opacity:.3f}" pointer-events="none">'
        f'{animate}{"".join(parts)}</g>'
    )


def _lapse_phrase(vitality: float) -> str:
    days = _days_away(vitality)
    if days is None:
        return 'a very long time'
    return f'{days} {"day" if days == 1 else "days"}'


def _rain_title(vitality: float) -> str:
    return _title(
        f'Rain — no sessions for {_lapse_phrase(vitality)}; '
        f'the garden is going thirsty'
    )


def _render_timeline_rain(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    """The downpour, animated over the same vitality the season rides.

    A garden that has never been left alone never rains, and emits no
    rain layer at all rather than a permanently invisible one.
    """
    vitality = timeline.daily_vitality
    if not vitality or not any(
        _rain_intensity(value) > 0 for value in vitality
    ):
        return ''

    values = [f'{_rain_opacity(value):.3f}' for value in vitality]
    animate = _animate_tag('opacity', values, key_times, duration, smooth=True)
    day_labels = [
        f'Rain — {_format_day(day)}: {_lapse_phrase(value)} since a session'
        for day, value in zip(timeline.days, vitality, strict=True)
    ]
    return _render_rain(
        _rain_opacity(vitality[-1]),
        animate,
        _title(day_labels[-1]),
        _tt_attr(day_labels),
    )


def _render_timeline_storm(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    """The blowing half of the weather, on its own opacity curve.

    Split from `_render_timeline_rain` rather than nested inside it so
    the wind can come up faster than the wet does -- see `_storm_opacity`.
    """
    vitality = timeline.daily_vitality
    if not vitality or not any(
        _rain_intensity(value) > 0 for value in vitality
    ):
        return ''

    values = [f'{_storm_opacity(value):.3f}' for value in vitality]
    animate = _animate_tag('opacity', values, key_times, duration, smooth=True)
    return _render_storm(_storm_opacity(vitality[-1]), animate)


def _cache_efficiency_flower_count(
    cache_read_tokens: int, cache_write_tokens: int
) -> int:
    """Nearest whole multiple of cache reads per write -- one flower per x.

    Cache efficiency (reads/write) is otherwise invisible anywhere in the
    tree, unlike every other tracked stat; a garden-wide flower count gives
    it a home without tying it to any single repo's branch or bush.
    """
    if cache_write_tokens <= 0:
        return 0
    return max(0, round(cache_read_tokens / cache_write_tokens))


def _render_flower(
    cx: float, cy: float, size: float, petal_color: str, rng: random.Random
) -> str:
    orbit = size * 0.55
    petal_radius = size * 0.42
    angle_offset = rng.uniform(0, 72)
    petals = []
    for i in range(5):
        angle = math.radians(angle_offset + i * 72)
        petal_x = cx + orbit * math.cos(angle)
        petal_y = cy + orbit * math.sin(angle)
        petals.append(
            f'<circle cx="{petal_x:.1f}" cy="{petal_y:.1f}" '
            f'r="{petal_radius:.2f}" fill="{petal_color}" opacity="0.92" />'
        )
    petal_markup = ''.join(petals)
    center = (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{size * 0.28:.2f}" '
        f'fill="{FLOWER_CENTER_COLOR}" opacity="0.95" />'
    )
    return petal_markup + center


def _render_flowers_on_bushes(
    count: int,
    bush_footprints: list[tuple[float, float]],
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> str:
    """`count` flowers scattered across the given bush footprints.

    Cache efficiency has no bush or branch of its own to live on, so its
    flowers ride along on the tool bushes instead -- round-robining
    through them so they spread across every bush rather than piling onto
    one. With no bushes there's nowhere to plant them, so nothing renders.
    """
    if count <= 0 or not bush_footprints:
        return ''
    title = _title(
        f'Cache efficiency — {cache_read_tokens:,} cache reads per '
        f'{cache_write_tokens:,} cache writes'
    )
    rng = random.Random('ccgarden-flowers')
    elements = []
    for index in range(count):
        bush_x, bush_radius = bush_footprints[index % len(bush_footprints)]
        angle = rng.uniform(0, 2 * math.pi)
        dist = bush_radius * rng.uniform(0.0, 0.7)
        x = bush_x + dist * math.cos(angle)
        y = GROUND_Y - bush_radius * 0.6 + dist * math.sin(angle) * 0.6
        size = FLOWER_RADIUS * rng.uniform(0.6, 0.9)
        color = rng.choice(FLOWER_COLORS)
        elements.append(
            f'<g class="flower">{title}'
            f'{_render_flower(x, y, size, color, rng)}</g>'
        )
    return ''.join(elements)


def _lerp_hex(start: str, end: str, fraction: float) -> str:
    """Blend two `#rrggbb` colors, `fraction` of the way from start to end."""
    start_rgb = (int(start[i : i + 2], 16) for i in (1, 3, 5))
    end_rgb = (int(end[i : i + 2], 16) for i in (1, 3, 5))
    channels = (
        round(s + (e - s) * fraction)
        for s, e in zip(start_rgb, end_rgb, strict=True)
    )
    return '#{:02x}{:02x}{:02x}'.format(*channels)


def _cloud_gradient_id(effort: str | None) -> str:
    """Gradient id for a cloud at this reasoning-effort level.

    Unrecognized or absent effort maps to the original pale `cloudGradient`.
    """
    if effort not in CLOUD_EFFORT_DARKNESS:
        return 'cloudGradient'
    return f'cloudGradient-{effort}'


def _cloud_gradient_defs() -> str:
    """One radial gradient per effort darkness level, plus the base cloud."""
    defs = []
    for gradient_id, darkness in (
        ('cloudGradient', 0.0),
        *(
            (f'cloudGradient-{effort}', darkness)
            for effort, darkness in CLOUD_EFFORT_DARKNESS.items()
        ),
    ):
        stops = tuple(
            _lerp_hex(pale, storm, darkness)
            for pale, storm in zip(
                CLOUD_GRADIENT_STOPS, CLOUD_STORM_STOPS, strict=True
            )
        )
        defs.append(
            f'<radialGradient id="{gradient_id}" cx="35%" cy="30%" r="75%">'
            f'<stop offset="0%" stop-color="{stops[0]}" />'
            f'<stop offset="60%" stop-color="{stops[1]}" />'
            f'<stop offset="100%" stop-color="{stops[2]}" />'
            '</radialGradient>'
        )
    return ''.join(defs)


def _effort_from_cloud_label(label: str) -> str | None:
    """Pull the effort out of a `model_effort_label` combo.

    E.g. `sonnet (high)` -> `high`; returns None for a bare model name.
    """
    if label.endswith(')') and '(' in label:
        return label.rsplit('(', 1)[1][:-1]
    return None


def _cloud_radius(total_tokens: int) -> float:
    """A model's cloud radius, growing quickly then leveling off.

    Same sqrt-saturation shape as the other size formulas (see
    `_canopy_radius`, `_branch_width`) so a lightly-used model's cloud is
    still visible off the floor instead of vanishing, while a heavily-used
    model doesn't need an unbounded amount of sky to read as "the big one".
    """
    growth = math.sqrt(
        min(total_tokens, CLOUD_TOKENS_SATURATION) / CLOUD_TOKENS_SATURATION
    )
    return CLOUD_RADIUS_MIN + (CLOUD_RADIUS_MAX - CLOUD_RADIUS_MIN) * growth


def _cloud_puffs_d(radius: float, seed: str) -> list[str]:
    """`d` values for each lumpy puff making up one cloud, at this radius."""
    rng = random.Random(seed)
    d_values = []
    for index, (dx_frac, dy_frac, r_frac) in enumerate(CLOUD_PUFFS):
        jitter = rng.uniform(*CLOUD_PUFF_SIZE_JITTER)
        puff_radius = radius * r_frac * jitter
        d_values.append(
            _blob_path(
                dx_frac * radius,
                dy_frac * radius,
                puff_radius,
                random.Random(f'{seed}:{index}'),
                points=8,
                jitter=CLOUD_PUFF_SHAPE_JITTER,
            )
        )
    return d_values


def _cloud_extent() -> tuple[float, float, float]:
    """How far a radius-1 cloud reaches (left/right, up, down) from center.

    Derived from `CLOUD_PUFFS` and the two jitters rather than hardcoded, so
    retuning the puff layout can't silently reintroduce clouds that hang off
    the edge of the sky. Both jitters are taken at their worst case: a
    `_blob_path` curve stays inside the hull of its jittered vertices, so
    these are upper bounds on the drawn shape.
    """
    max_puff_scale = CLOUD_PUFF_SIZE_JITTER[1] * (1 + CLOUD_PUFF_SHAPE_JITTER)
    half_width = up = down = 0.0
    for dx_frac, dy_frac, r_frac in CLOUD_PUFFS:
        reach = r_frac * max_puff_scale
        half_width = max(half_width, abs(dx_frac) + reach)
        up = max(up, reach - dy_frac)
        down = max(down, reach + dy_frac)
    return half_width, up, down


def _clamp_cloud_position(
    x: float, y: float, radius: float
) -> tuple[float, float]:
    """Nudge a cloud's slot inward just enough to keep it fully in frame.

    Only clouds that would actually overflow move -- a small cloud clears
    every edge by a wide margin and keeps the scattered slot
    `_cloud_positions` gave it.
    """
    half_width, up, down = _cloud_extent()
    x = min(max(x, half_width * radius), VIEWBOX_WIDTH - half_width * radius)
    y = min(max(y, up * radius), VIEWBOX_HEIGHT - down * radius)
    return x, y


def _render_cloud(
    cx: float, cy: float, radius: float, seed: str, effort: str | None = None
) -> str:
    gradient_id = _cloud_gradient_id(effort)
    puffs = ''.join(
        f'<path d="{d}" fill="url(#{gradient_id})" opacity="0.88" />'
        for d in _cloud_puffs_d(radius, seed)
    )
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f})">'
        + _wind_group('ccg-drift', seed)
        + f'{puffs}</g></g>'
    )


def _cloud_bands() -> tuple[tuple[float, float], tuple[float, float]]:
    """The (start, end) x spans of the sky left and right of the tree."""
    left = (CLOUD_MARGIN, TRUNK_CENTER_X - CLOUD_TREE_KEEPOUT_HALF_WIDTH)
    right = (
        TRUNK_CENTER_X + CLOUD_TREE_KEEPOUT_HALF_WIDTH,
        VIEWBOX_WIDTH - CLOUD_MARGIN,
    )
    return left, right


def _cloud_slot_x(fraction: float) -> float:
    """The x for a slot `fraction` of the way through the usable sky.

    The two bands are treated as one continuous run so slots stay evenly
    spread overall, they just skip the column of sky the tree grows into.
    """
    (left_start, left_end), (right_start, right_end) = _cloud_bands()
    left_width = max(left_end - left_start, 0.0)
    right_width = max(right_end - right_start, 0.0)
    offset = fraction * (left_width + right_width)
    if offset <= left_width:
        return left_start + offset
    return right_start + (offset - left_width)


def _cloud_y_max(x: float) -> float:
    """How far down the sky a cloud at this x may drift.

    Ramps from `CLOUD_Y_MAX_NEAR_TREE` at the edge of the keep-out column
    out to `CLOUD_Y_MAX_AT_EDGE` at the frame's sides, following the way
    the tree's outer branches slope down away from the trunk.
    """
    distance = abs(x - TRUNK_CENTER_X)
    span = TRUNK_CENTER_X - CLOUD_MARGIN - CLOUD_TREE_KEEPOUT_HALF_WIDTH
    if span <= 0:
        return CLOUD_Y_MAX_NEAR_TREE
    fraction = min(
        max((distance - CLOUD_TREE_KEEPOUT_HALF_WIDTH) / span, 0.0), 1.0
    )
    return (
        CLOUD_Y_MAX_NEAR_TREE
        + (CLOUD_Y_MAX_AT_EDGE - CLOUD_Y_MAX_NEAR_TREE) * fraction
    )


def _cloud_positions(count: int) -> list[tuple[float, float]]:
    """Deterministic (x, y) sky slot for each of `count` clouds.

    Spread evenly across the two sky bands either side of the trunk's
    keep-out column (see `_cloud_slot_x`), with per-slot jitter so a full
    sky of models doesn't read as a mechanical grid, and a per-slot depth
    that opens up toward the frame edges (see `_cloud_y_max`). Shuffled
    before returning so slot order doesn't line up with the caller's
    (biggest-model-first) list order -- otherwise every render reads as a
    strict big-to-small gradient across the sky instead of a scattered
    distribution of sizes.
    """
    positions = []
    for index in range(count):
        rng = random.Random(f'ccgarden-cloud-slot:{index}')
        x = _cloud_slot_x((index + rng.uniform(0.25, 0.75)) / count)
        y_max = _cloud_y_max(x)
        y = CLOUD_Y_MIN + rng.uniform(0.0, y_max - CLOUD_Y_MIN)
        positions.append((x, y))
    random.Random('ccgarden-cloud-order').shuffle(positions)
    return positions


def _render_clouds(models: list[ModelCloud]) -> str:
    if not models:
        return ''
    positions = _cloud_positions(len(models))
    elements = []
    for (x, y), model_cloud in zip(positions, models, strict=True):
        total_tokens = model_cloud.output_tokens + model_cloud.input_tokens
        radius = _cloud_radius(total_tokens)
        cx, cy = _clamp_cloud_position(x, y, radius)
        effort = _effort_from_cloud_label(model_cloud.model)
        title = _title(f'{model_cloud.model} — {total_tokens:,} tokens')
        elements.append(
            f'<g class="cloud">{title}'
            f'{_render_cloud(cx, cy, radius, model_cloud.model, effort)}</g>'
        )
    return ''.join(elements)


def _bird_size(tokens_saved: int) -> float:
    """A bird's wingspan for an adapter that saved this many tokens.

    Same sqrt-saturation shape as the other size formulas (see
    `_cloud_radius`, `_bush_radius`), so an adapter with modest savings is
    still a visible bird rather than a speck.
    """
    growth = math.sqrt(
        min(max(tokens_saved, 0), BIRD_TOKENS_SATURATION)
        / BIRD_TOKENS_SATURATION
    )
    return BIRD_SIZE_MIN + (BIRD_SIZE_MAX - BIRD_SIZE_MIN) * growth


def _bird_bands() -> tuple[tuple[float, float], tuple[float, float]]:
    """The (start, end) x spans of the sky left and right of the tree."""
    left = (BIRD_MARGIN, TRUNK_CENTER_X - BIRD_TREE_KEEPOUT_HALF_WIDTH)
    right = (
        TRUNK_CENTER_X + BIRD_TREE_KEEPOUT_HALF_WIDTH,
        VIEWBOX_WIDTH - BIRD_MARGIN,
    )
    return left, right


def _bird_slot_x(fraction: float) -> float:
    """The x for a slot `fraction` of the way through the usable sky.

    The two bands are treated as one continuous run so slots stay evenly
    spread overall, they just skip the column of sky the tree grows into.
    """
    (left_start, left_end), (right_start, right_end) = _bird_bands()
    left_width = max(left_end - left_start, 0.0)
    right_width = max(right_end - right_start, 0.0)
    offset = fraction * (left_width + right_width)
    if offset <= left_width:
        return left_start + offset
    return right_start + (offset - left_width)


def _bird_clamp_x(x: float) -> float:
    """Pull an x back into whichever sky band it is nearest."""
    (left_start, left_end), (right_start, right_end) = _bird_bands()
    if x <= left_end:
        return max(x, left_start)
    if x >= right_start:
        return min(x, right_end)
    # Inside the tree's column: fall out to the closer side of it.
    if x - left_end <= right_start - x:
        return left_end
    return right_start


def _bird_positions(count: int) -> list[tuple[float, float]]:
    """Deterministic (x, y) sky slot for each of `count` birds.

    Birds are dealt into skeins of up to `BIRD_FLOCK_SIZE`, each skein
    anchored at its own slot across the sky either side of the tree and
    laid out as a V trailing up and back from its leader.
    """
    if count <= 0:
        return []
    flock_count = math.ceil(count / BIRD_FLOCK_SIZE)
    positions = []
    for index in range(count):
        flock_index = index // BIRD_FLOCK_SIZE
        rank_in_flock = index % BIRD_FLOCK_SIZE
        anchor_rng = random.Random(f'ccgarden-bird-flock:{flock_index}')
        anchor_x = _bird_slot_x(
            (flock_index + anchor_rng.uniform(0.3, 0.7)) / flock_count
        )
        anchor_y = anchor_rng.uniform(BIRD_Y_MIN, BIRD_Y_MAX)

        # Alternate sides of the V, one step further back with each pair.
        side = -1.0 if rank_in_flock % 2 else 1.0
        rank = (rank_in_flock + 1) // 2
        rng = random.Random(f'ccgarden-bird:{index}')
        offset_x = side * rank * BIRD_FLOCK_SPACING_X * rng.uniform(0.8, 1.2)
        x = _bird_clamp_x(anchor_x + offset_x)
        y = min(
            anchor_y + rank * BIRD_FLOCK_SPACING_Y * rng.uniform(0.7, 1.3),
            BIRD_Y_MAX,
        )
        positions.append((x, y))
    return positions


def _bird_d(cx: float, cy: float, size: float) -> str:
    """A bird as the classic pair of wing strokes meeting at the body."""
    half = size / 2
    lift = size * 0.55
    return (
        f'M{cx - size:.1f},{cy:.1f} '
        f'Q{cx - half:.1f},{cy - lift:.1f} {cx:.1f},{cy:.1f} '
        f'Q{cx + half:.1f},{cy - lift:.1f} {cx + size:.1f},{cy:.1f}'
    )


def _render_bird(
    cx: float, cy: float, size: float, color: str = BIRD_COLOR
) -> str:
    return (
        f'<path d="{_bird_d(cx, cy, size)}" fill="none" '
        f'stroke="{color}" '
        f'stroke-width="{BIRD_STROKE_WIDTH * size / BIRD_SIZE:.2f}" '
        f'stroke-linecap="round" opacity="0.85" />'
    )


def _clear_of_sun(
    x: float, y: float, size: float, sun: tuple[float, float, float]
) -> tuple[float, float]:
    """Push a bird radially out of the sun's halo, if it landed inside it.

    A pale bird washes out completely against the halo, so the one thing
    a flock has to dodge is the sun -- clouds it may cross freely, which
    is what birds do anyway.
    """
    sun_x, sun_y, sun_radius = sun
    keepout = sun_radius * SUN_HALO_RADIUS_FACTOR + size * 2
    dx, dy = x - sun_x, y - sun_y
    distance = math.hypot(dx, dy)
    if distance >= keepout:
        return x, y
    if distance < EPSILON:
        # Dead center on the sun: no direction to push, so pick one.
        dx, dy, distance = 0.0, 1.0, 1.0
    scale = keepout / distance
    pushed_x = sun_x + dx * scale
    pushed_y = sun_y + dy * scale
    return (
        min(max(pushed_x, BIRD_MARGIN), VIEWBOX_WIDTH - BIRD_MARGIN),
        min(max(pushed_y, BIRD_Y_MIN), BIRD_Y_MAX),
    )


def _bird_slots(
    birds: list[CartoonBird], sun: tuple[float, float, float]
) -> list[tuple[float, float, float]]:
    """(x, y, size) for each bird, placed in the sky and clear of the sun."""
    sizes = [_bird_size(bird.tokens_saved) for bird in birds]
    return [
        (*_clear_of_sun(x, y, size, sun), size)
        for (x, y), size in zip(
            _bird_positions(len(birds)), sizes, strict=True
        )
    ]


def _bird_drift(
    index: int,
    x: float,
    y: float,
    size: float,
    sun: tuple[float, float, float],
) -> tuple[float, float]:
    """How far a bird drifts from its slot at the far end of its loop.

    Outward, away from the trunk, so the drift can never carry a bird into
    the canopy; the far end is put through the same band clamp and sun
    push-out as the slot itself, so both ends of the loop are legal
    positions and everything between them is too.
    """
    rng = random.Random(f'ccgarden-bird-drift:{index}')
    direction = 1.0 if x >= TRUNK_CENTER_X else -1.0
    far_x = _bird_clamp_x(x + direction * BIRD_DRIFT_X * rng.uniform(0.7, 1.3))
    far_y = min(
        max(y - BIRD_DRIFT_Y * rng.uniform(0.5, 1.3), BIRD_Y_MIN), BIRD_Y_MAX
    )
    far_x, far_y = _clear_of_sun(far_x, far_y, size, sun)
    return far_x - x, far_y - y


def _bird_drift_rule(index: int, dx: float, dy: float) -> str:
    """A slow there-and-back drift, looping for as long as the SVG is open.

    Deliberately not keyed to the timeline's day frames: it runs on its own
    clock so a paused or scrubbed replay still has a living sky.

    CSS rather than the `animateTransform` this used to be. SMIL transforms
    are never handed to the compositor, so a flock that drifts forever kept
    the whole document -- thousands of branch and leaf paths -- repainting on
    the main thread every frame, which visibly janked scrolling on any page
    embedding the garden. An equivalent CSS keyframe animation can be
    composited, and costs nothing once the layer is up.
    """
    rng = random.Random(f'ccgarden-bird-drift-time:{index}')
    duration = BIRD_DRIFT_SECONDS * rng.uniform(0.85, 1.15)
    return (
        f'@keyframes bird-drift-{index}{{'
        f'50%{{transform:translate({dx:.2f}px,{dy:.2f}px)}}}}'
        f'.bird-drift-{index}{{'
        f'animation:bird-drift-{index} {duration:.3f}s '
        f'ease-in-out infinite}}'
    )


def _bird_drift_style(rules: list[str]) -> str:
    """The flock's drift keyframes, plus the two rules they all share.

    `will-change` is what actually buys the compositor layer; without it a
    browser is free to keep animating the transform on the main thread and
    the SMIL problem comes straight back.
    """
    return (
        '<style>'
        + ''.join(rules)
        + '.bird-drift{will-change:transform}'
        + '@media (prefers-reduced-motion:reduce)'
        + '{.bird-drift{animation:none}}'
        + '</style>'
    )


def _bird_label(bird: CartoonBird, since: str) -> str:
    window = f' (last {since})' if since else ''
    return (
        f'{bird.adapter} — {bird.tokens_saved:,} tokens saved '
        f'over {bird.calls:,} calls{window}'
    )


def _render_birds(
    birds: list[CartoonBird],
    since: str,
    sun: tuple[float, float, float],
) -> str:
    """One bird per cartoon adapter -- nothing at all when cartoon is absent.

    Every caller passes whatever `load_cartoon_birds` came back with, so
    a machine without cartoon just renders a garden with an empty sky.
    """
    flock = birds[:MAX_BIRDS]
    if not flock:
        return ''
    slots = _bird_slots(flock, sun)
    elements = [
        f'<g class="bird">{_title(_bird_label(bird, since))}'
        + _wind_group('ccg-flap', f'bird:{index}')
        + f'{_render_bird(x, y, size)}</g></g>'
        for index, (bird, (x, y, size)) in enumerate(
            zip(flock, slots, strict=True)
        )
    ]
    return f'<g class="birds">{"".join(elements)}</g>'


def _sun_growth(total_tokens: int) -> float:
    """0..1 share of the way to `SUN_TOKENS_SATURATION`, sqrt-eased.

    Same sqrt-saturation shape as the other size formulas (see
    `_cloud_radius`, `_bush_radius`) -- there's only ever one sun, so
    unlike those per-category shapes there's no risk of it flattening
    several entries together, just the usual "small totals still read as
    something" floor.
    """
    return math.sqrt(
        min(total_tokens, SUN_TOKENS_SATURATION) / SUN_TOKENS_SATURATION
    )


def _sun_radius(total_tokens: int) -> float:
    growth = _sun_growth(total_tokens)
    return SUN_RADIUS_MIN + (SUN_RADIUS_MAX - SUN_RADIUS_MIN) * growth


def _sun_sweep_x(progress: float, radius: float) -> float:
    """How far across the sky the sun has got, `progress` 0..1 of the replay.

    Keyed to elapsed replay time rather than to any statistic, so it is
    the one thing on screen that keeps moving through a lapse, when every
    cumulative shape is frozen and only the weather is left.

    `radius` shortens the *path*, not the individual frame -- clamping
    each frame separately would leave the sun crawling through whichever
    end of the sweep the halo overhangs, and an even pace is the whole
    point. Callers pass the sun's final radius for every frame.
    """
    span = min(max(progress, 0.0), 1.0)
    halo_radius = radius * SUN_HALO_RADIUS_FACTOR
    start = max(SUN_X_START, halo_radius)
    end = min(SUN_X_END, VIEWBOX_WIDTH - halo_radius)
    return start + (max(end, start) - start) * span


def _sun_height(total_tokens: int, radius: float) -> float:
    """How high the sun has climbed, on the garden's total token count.

    Still the token channel: only the horizontal sweep was taken off it.
    Clamped at the top so the halo never leaves the viewBox, and
    deliberately *not* at the bottom -- a garden with few tokens gets a
    sun half-buried below the horizon, which is the intended sunrise.
    """
    growth = _sun_growth(total_tokens)
    y = SUN_Y_START + (SUN_Y_END - SUN_Y_START) * growth
    return max(y, radius * SUN_HALO_RADIUS_FACTOR)


def _sun_position(total_tokens: int) -> tuple[float, float]:
    """Where the sun ends up: the far end of the sweep, at its final height."""
    radius = _sun_radius(total_tokens)
    return _sun_sweep_x(1.0, radius), _sun_height(total_tokens, radius)


def _render_moon(cx: float, cy: float, radius: float) -> str:
    """The night shift's sun: same place, same size, no rays.

    Craters are fixed offsets rather than seeded jitter -- there is only
    ever one moon, and a face that changed between renders would read as
    a different moon rather than as the same garden.
    """
    craters = ''.join(
        f'<circle cx="{radius * dx:.2f}" cy="{radius * dy:.2f}" '
        f'r="{radius * dr:.2f}" fill="{MOON_CRATER_COLOR}" opacity="0.55" />'
        for dx, dy, dr in MOON_CRATERS
    )
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f})">'
        + _wind_group('ccg-pulse', 'moon-halo')
        + f'<circle r="{radius * SUN_HALO_RADIUS_FACTOR * 0.8:.2f}" '
        f'fill="url(#moonHaloGradient)" />'
        f'</g>'
        f'<circle r="{radius:.2f}" fill="url(#moonGradient)" />'
        f'{craters}'
        f'</g>'
    )


def _sky_body_opacities(
    nightness: float, vitality: float
) -> tuple[float, float]:
    """(sun, moon) opacity for one frame -- they cross-fade on nightness.

    Both are then dimmed by the same storm factor: cloud thick enough to
    swallow a sun swallows a moon too.
    """
    night = _saturated_nightness(nightness)
    storm = _sun_storm_opacity(vitality)
    return storm * (1.0 - night), storm * night


def _render_sky_body(
    cx: float,
    cy: float,
    radius: float,
    nightness: float,
    vitality: float,
    *,
    sun_animate: str = '',
    moon_animate: str = '',
) -> str:
    """The sun and the moon at the same point, cross-faded on nightness."""
    sun_opacity, moon_opacity = _sky_body_opacities(nightness, vitality)
    return (
        f'<g class="sun-disc" opacity="{sun_opacity:.3f}">'
        f'{sun_animate}{_render_sun(cx, cy, radius)}</g>'
        f'<g class="moon-disc" opacity="{moon_opacity:.3f}">'
        f'{moon_animate}{_render_moon(cx, cy, radius)}</g>'
    )


def _sun_rays_d(radius: float) -> list[str]:
    """`d` values for each ray line radiating out from the sun's center."""
    inner = radius * 1.12
    outer = inner + radius * 0.55
    d_values = []
    for index in range(SUN_RAY_COUNT):
        angle = 2 * math.pi * index / SUN_RAY_COUNT
        x1 = inner * math.cos(angle)
        y1 = inner * math.sin(angle)
        x2 = outer * math.cos(angle)
        y2 = outer * math.sin(angle)
        d_values.append(f'M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}')
    return d_values


def _render_sun(cx: float, cy: float, radius: float) -> str:
    halo_radius = radius * SUN_HALO_RADIUS_FACTOR
    rays = ''.join(
        f'<path d="{d}" stroke="{SUN_RAY_COLOR}" '
        f'stroke-width="{max(radius * 0.12, 2.5):.2f}" '
        f'stroke-linecap="round" opacity="0.7" />'
        for d in _sun_rays_d(radius)
    )
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f})">'
        + _wind_group('ccg-pulse', 'sun-halo')
        + f'<circle r="{halo_radius:.2f}" fill="url(#sunHaloGradient)" />'
        f'</g>'
        + _wind_group('ccg-spin', 'sun-rays')
        + f'{rays}</g>'
        + f'<circle r="{radius:.2f}" fill="url(#sunGradient)" />'
        f'</g>'
    )


def _bush_radius(tool_count: int) -> float:
    """A tool's bush radius, growing toward a cap without fully flattening.

    Tool call counts are far more top-heavy than day-level totals (one
    tool -- typically Bash -- often outnumbers the next-most-used tool by
    3x or more), so this uses a gentler, more-linear curve than the plain
    sqrt-saturation shape in `_cloud_radius`/`_canopy_radius`: a fractional
    exponent above 0.5 lets the heaviest hitters actually look heavier,
    while still giving a rarely-used tool a visible bush instead of
    vanishing.
    """
    growth = (
        min(tool_count, BUSH_TOOL_COUNT_SATURATION)
        / BUSH_TOOL_COUNT_SATURATION
    ) ** BUSH_GROWTH_EXPONENT
    return BUSH_RADIUS_MIN + (BUSH_RADIUS_MAX - BUSH_RADIUS_MIN) * growth


def _bush_puffs_d(radius: float, seed: str) -> list[str]:
    """`d` values for each lumpy puff making up one bush, at this radius.

    Puffs are laid out relative to (0, 0) sitting at the bush's ground
    contact point, with every puff's lower edge at or below that line --
    so a caller translating to (x, GROUND_Y) gets a shrub resting on the
    grass, and scaling the whole group grows it up out of that same root
    point instead of expanding symmetrically the way a floating cloud does.
    """
    rng = random.Random(seed)
    d_values = []
    for index, (dx_frac, dy_frac, r_frac) in enumerate(BUSH_PUFFS):
        jitter = rng.uniform(0.92, 1.08)
        puff_radius = radius * r_frac * jitter
        d_values.append(
            _blob_path(
                dx_frac * radius,
                dy_frac * radius,
                puff_radius,
                random.Random(f'{seed}:{index}'),
                points=9,
                jitter=0.22,
            )
        )
    return d_values


def _render_bush(cx: float, base_y: float, radius: float, seed: str) -> str:
    puffs = ''.join(
        f'<path d="{d}" fill="url(#bushGradient)" opacity="0.94" />'
        for d in _bush_puffs_d(radius, seed)
    )
    return f'<g transform="translate({cx:.1f},{base_y:.1f})">{puffs}</g>'


def _bush_x_positions(count: int) -> list[float]:
    """Deterministic ground-line x slot for each of `count` bushes.

    Spread evenly across the width like the flower floor and cloud slots,
    with per-slot jitter so a full row of tools doesn't read as a
    mechanical grid. Shuffled before returning for the same reason as
    `_cloud_positions` -- the caller's list is sorted biggest-tool-first,
    and zipping it straight against slots in order would always put the
    biggest bush leftmost and the smallest rightmost.
    """
    usable_width = VIEWBOX_WIDTH - BUSH_MARGIN * 2
    positions = []
    for index in range(count):
        rng = random.Random(f'ccgarden-bush-slot:{index}')
        x = BUSH_MARGIN + usable_width * (
            (index + rng.uniform(0.2, 0.8)) / count
        )
        positions.append(x)
    random.Random('ccgarden-bush-order').shuffle(positions)
    return positions


def _bush_footprints(tools: list[ToolBush]) -> list[tuple[float, float]]:
    """(x, radius) ground-line footprint for each bush that will be drawn.

    Shared with the flower placement in `render_svg`/`render_timeline_svg`
    so flowers only ever land inside a bush that's actually rendered.
    """
    tools = tools[:MAX_BUSHES]
    if not tools:
        return []
    xs = _bush_x_positions(len(tools))
    return [
        (x, _bush_radius(tool_bush.count))
        for x, tool_bush in zip(xs, tools, strict=True)
    ]


def _render_bushes(tools: list[ToolBush]) -> str:
    tools = tools[:MAX_BUSHES]
    footprints = _bush_footprints(tools)
    return ''.join(
        (
            '<g class="bush">'
            f'{_title(f"{tool_bush.tool} — used {tool_bush.count:,} times")}'
            + _wind_group('ccg-sway-bush', tool_bush.tool, (x, GROUND_Y))
            + f'{_render_bush(x, GROUND_Y, radius, tool_bush.tool)}</g></g>'
        )
        for (x, radius), tool_bush in zip(footprints, tools, strict=True)
    )


def _sunflower_height(prompts: int) -> float:
    """A repo's sunflower height, growing toward a cap without flattening.

    Same shape as `_bush_radius` and for the same reason: prompt counts
    are top-heavy across repos (one main project usually dwarfs the rest),
    so a fractional exponent above 0.5 keeps the busiest repo visibly the
    tallest while a barely-touched repo still gets a stalk you can see.
    """
    growth = (
        min(prompts, SUNFLOWER_PROMPTS_SATURATION)
        / SUNFLOWER_PROMPTS_SATURATION
    ) ** SUNFLOWER_GROWTH_EXPONENT
    return (
        SUNFLOWER_HEIGHT_MIN
        + (SUNFLOWER_HEIGHT_MAX - SUNFLOWER_HEIGHT_MIN) * growth
    )


def _sunflower_x_positions(count: int) -> list[float]:
    """Ground-line x slot for each of `count` sunflowers, alternating sides.

    Two bands, one per flank, filled alternately so the sunflowers stay
    balanced either side of the trunk however many repos there are --
    filling one band before starting the other would leave a lone
    left-hand thicket for anyone with five repos.
    """
    left_count = math.ceil(count / 2)
    right_count = count - left_count
    positions: list[float] = []
    for side_index, side_count in ((0, left_count), (1, right_count)):
        band_start = (
            SUNFLOWER_MARGIN
            if side_index == 0
            else VIEWBOX_WIDTH - SUNFLOWER_MARGIN - SUNFLOWER_BAND_WIDTH
        )
        for index in range(side_count):
            rng = random.Random(
                f'ccgarden-sunflower-slot:{side_index}:{index}'
            )
            positions.append(
                band_start
                + SUNFLOWER_BAND_WIDTH
                * ((index + rng.uniform(0.25, 0.75)) / side_count)
            )
    # Interleave the two bands back into the caller's (prompts-descending)
    # order, so the tallest sunflowers don't all end up on one side.
    interleaved: list[float] = []
    for index in range(count):
        side, slot = index % 2, index // 2
        interleaved.append(
            positions[slot] if side == 0 else positions[left_count + slot]
        )
    return interleaved


def _render_sunflower(
    cx: float, base_y: float, height: float, seed: str
) -> str:
    """One sunflower, rooted at (cx, base_y) and growing upward.

    Laid out relative to a (0, 0) ground-contact point like `_render_bush`,
    so a caller can scale the whole group to grow it up out of the soil
    instead of expanding it symmetrically about its middle.
    """
    rng = random.Random(seed)
    lean = rng.uniform(-0.16, 0.16) * height
    head_x = lean
    head_y = -height
    head_radius = height * 0.115
    stalk_width = max(2.0, height * 0.035)

    parts = [
        (
            f'<path d="M0,0 Q{lean * 0.3:.1f},{-height * 0.55:.1f} '
            f'{head_x:.1f},{head_y:.1f}" fill="none" '
            f'stroke="{SUNFLOWER_STALK_COLOR}" '
            f'stroke-width="{stalk_width:.2f}" stroke-linecap="round" />'
        )
    ]
    for leaf_index, frac in enumerate((0.36, 0.6)):
        side = 1 if leaf_index % 2 == 0 else -1
        leaf_x = lean * frac * 0.4 + side * height * 0.07
        leaf_y = -height * frac
        leaf_scale = height * 0.1
        parts.append(
            f'<g transform="translate({leaf_x:.1f},{leaf_y:.1f}) '
            f'rotate({side * 68}) scale({leaf_scale:.2f})">'
            f'<path d="{LEAF_SHAPE_D}" fill="{SUNFLOWER_STALK_COLOR}" '
            f'opacity="0.9" />'
            f'</g>'
        )

    angle_offset = rng.uniform(0, 360 / SUNFLOWER_PETAL_COUNT)
    for petal_index in range(SUNFLOWER_PETAL_COUNT):
        angle = angle_offset + petal_index * (360 / SUNFLOWER_PETAL_COUNT)
        color = SUNFLOWER_PETAL_COLORS[
            petal_index % len(SUNFLOWER_PETAL_COLORS)
        ]
        parts.append(
            f'<ellipse cx="{head_x:.1f}" cy="{head_y:.1f}" '
            f'rx="{head_radius * 0.95:.2f}" ry="{head_radius * 0.36:.2f}" '
            f'fill="{color}" opacity="0.94" '
            f'transform="rotate({angle:.1f} {head_x:.1f} {head_y:.1f})" />'
        )
    parts.append(
        f'<circle cx="{head_x:.1f}" cy="{head_y:.1f}" '
        f'r="{head_radius * 0.52:.2f}" fill="{FLOWER_CENTER_COLOR}" />'
    )
    return (
        f'<g transform="translate({cx:.1f},{base_y:.1f})">{"".join(parts)}</g>'
    )


def _sunflower_repos(branches: list[RepoBranch]) -> list[RepoBranch]:
    """The repos that get a sunflower, tallest (most prompts) first."""
    with_prompts = [branch for branch in branches if branch.prompts > 0]
    with_prompts.sort(key=lambda branch: branch.prompts, reverse=True)
    return with_prompts[:MAX_SUNFLOWERS]


def _render_sunflowers(branches: list[RepoBranch]) -> str:
    repos = _sunflower_repos(branches)
    if not repos:
        return ''
    xs = _sunflower_x_positions(len(repos))
    parts = []
    for x, branch in zip(xs, repos, strict=True):
        plant = _render_sunflower(
            x, GROUND_Y, _sunflower_height(branch.prompts), branch.repo
        )
        parts.append(
            '<g class="sunflower">'
            f'{_title(f"{branch.repo} — {branch.prompts:,} prompts")}'
            + _wind_group('ccg-sway-stalk', branch.repo, (x, GROUND_Y))
            + f'{plant}</g></g>'
        )
    return ''.join(parts)


def _render_trunk(base_half_width: float) -> str:
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    cx = TRUNK_CENTER_X
    lean = base_half_width * 0.1
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    top_shoulder_y = TRUNK_TOP_Y + top_half_width * 0.5
    dome_y = TRUNK_TOP_Y - top_half_width * 0.35
    left_ctrl_x = cx - (base_half_width + top_half_width) / 2 - lean
    right_ctrl_x = cx + (base_half_width + top_half_width) / 2 + lean

    d = (
        f'M {cx - base_half_width},{GROUND_Y} '
        f'Q {left_ctrl_x},{mid_y} {cx - top_half_width},{top_shoulder_y} '
        f'Q {cx},{dome_y} {cx + top_half_width},{top_shoulder_y} '
        f'Q {right_ctrl_x},{mid_y} {cx + base_half_width},{GROUND_Y} '
        f'Z'
    )
    trunk = (
        f'<path class="trunk" d="{d}" fill="url(#trunkGradient)" '
        f'stroke="#3a2412" stroke-width="1.5" stroke-linejoin="round" />'
    )
    return trunk + _render_bark_texture(base_half_width, top_half_width)


def _render_bark_texture(base_half_width: float, top_half_width: float) -> str:
    rng = random.Random('ccgarden-bark')
    cx = TRUNK_CENTER_X
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    elements = []
    for x_offset in (-0.32, 0.4):
        top_x = cx + x_offset * top_half_width
        base_x = cx + x_offset * base_half_width
        jitter = rng.uniform(-2, 2)
        elements.append(
            f'<path d="M{base_x},{GROUND_Y - 8} '
            f'Q{(base_x + top_x) / 2 + jitter},{mid_y} '
            f'{top_x},{TRUNK_TOP_Y + 10}" '
            f'fill="none" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.22" />'
        )
    return ''.join(elements)


def _render_rings(rings: list[DayRing], base_half_width: float) -> str:
    if not rings:
        return ''
    elements = []
    count = len(rings)
    for index, day_ring in enumerate(rings):
        y = GROUND_Y - (index + 1) / (count + 1) * TRUNK_HEIGHT
        half_width = _half_width_at(y, base_half_width) * 0.85
        cx = TRUNK_CENTER_X
        bow = half_width * 0.1
        stroke_width = _ring_stroke_width(day_ring.sessions)
        d = f'M {cx - half_width},{y} Q {cx},{y - bow} {cx + half_width},{y}'
        title = _title(
            f'{_format_day(day_ring.day)} — {day_ring.sessions} sessions, '
            f'+{day_ring.lines_added:,}/-{day_ring.lines_removed:,} lines'
        )
        elements.append(
            f'<path class="ring" d="{d}" fill="none" stroke="#3a2412" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" '
            f'opacity="0.22">{title}</path>'
        )
    return ''.join(elements)


class _Limb(NamedTuple):
    """One primary limb of the tree, and the slice of a repo it carries.

    `key` seeds every piece of derived randomness for the limb (placement,
    bow, collar, foliage), so two limbs cut from the same repo don't come
    out as identical twins. It stays equal to `repo` for a repo that isn't
    split, which keeps a wide garden rendering exactly as it did before
    limbs existed.
    """

    key: str
    repo: str
    share: float
    # Where this limb's share sits in its repo's 0..1 run. `_limb_share_of`
    # splits on the *boundaries* rather than rounding each share on its own,
    # so a repo's limbs add back up to exactly the repo -- five limbs still
    # carry exactly `sessions * LEAVES_PER_SESSION` leaves between them.
    start: float = 0.0


def _limb_lead_weight(weight: float, count: int) -> float:
    """What the *largest* of `count` limbs cut from a repo carries.

    The shares fall off geometrically, so the leader takes
    `1 / sum(falloff)` of the repo however many ways it is cut. This is the
    number that decides whether a tree looks balanced -- the leader is the
    limb everything else is compared against.
    """
    return weight / sum(LIMB_SHARE_FALLOFF**rank for rank in range(count))


def _limb_counts(weights: list[float], minimum: int) -> list[int]:
    """How many limbs each repo is split across, biggest repo first.

    Each extra limb goes to whichever repo currently carries the heaviest
    single limb, which is both the highest-averages answer to "who is owed
    the next seat" and, literally, the limb unbalancing the tree. Splitting
    stops once *both* rules are met: at least `minimum` limbs, and no limb
    over `LIMB_MAX_SHARE` of the whole tree.
    """
    counts = [1] * len(weights)
    cap = LIMB_MAX_SHARE * sum(weights)
    while True:
        splittable = [
            index
            for index in range(len(weights))
            if counts[index] < MAX_LIMBS_PER_REPO
        ]
        if not splittable:
            return counts
        leader = max(
            splittable,
            key=lambda index: _limb_lead_weight(weights[index], counts[index]),
        )
        lopsided = _limb_lead_weight(weights[leader], counts[leader]) > cap
        if sum(counts) >= minimum and not lopsided:
            return counts
        counts[leader] += 1


def _plan_limbs(repos: list[tuple[str, float]]) -> list[_Limb]:
    """Lay out the tree's primary limbs, biggest first.

    `repos` is (name, weight) ordered by weight descending, and the limbs
    come back in the same order, which `_branch_placement` reads as
    "longest lowest on the trunk".
    """
    if not repos:
        return []
    counts = _limb_counts([weight for _, weight in repos], MIN_LIMBS)
    weighted: list[tuple[float, _Limb]] = []
    for (repo, weight), count in zip(repos, counts, strict=True):
        falloff = [LIMB_SHARE_FALLOFF**rank for rank in range(count)]
        total = sum(falloff)
        start = 0.0
        for rank, term in enumerate(falloff):
            share = term / total
            key = repo if count == 1 else f'{repo}#{rank}'
            weighted.append((weight * share, _Limb(key, repo, share, start)))
            start += share
    weighted.sort(key=lambda item: -item[0])
    return [limb for _, limb in weighted]


def _limb_share_of[Stats: (RepoBranch, RepoBranchDay)](
    stats: Stats, limb: _Limb
) -> Stats:
    """The slice of a repo's totals that one of its limbs carries.

    Every integer is cut on the limb's cumulative boundaries, so the cuts
    telescope: a repo's limbs sum back to the repo exactly, however many
    limbs it was split across and however the fractions land.
    """
    if limb.share >= 1.0:
        return stats

    def cut(total: int) -> int:
        return round(total * (limb.start + limb.share)) - round(
            total * limb.start
        )

    return replace(
        stats,
        sessions=cut(stats.sessions),
        lines_added=cut(stats.lines_added),
        lines_removed=cut(stats.lines_removed),
        output_tokens=cut(stats.output_tokens),
        input_tokens=cut(stats.input_tokens),
        cost=stats.cost * limb.share,
        prompts=cut(stats.prompts),
    )


class _BranchPlacement(NamedTuple):
    """Where a repo's branch leaves the trunk, and at what pitch.

    Shared by the static and timeline renderers so both trees put the same
    repo in the same place -- the timeline is the same tree, grown.
    """

    origin_x: float
    origin_y: float
    side: int
    spread_index: float
    angle_jitter: float


def _branch_side(index: int) -> int:
    """Which flank of the trunk the index-th largest branch leaves on.

    Strict left/right alternation puts every odd-ranked branch on one side,
    and since branches arrive largest-first that hands the left flank the
    1st, 3rd and 5th biggest every time -- a reliably lopsided tree. The
    Thue-Morse parity (L R R L R L L R ...) is the standard fair-division
    answer to exactly that: it keeps the running weight on the two flanks
    as close as possible for any decreasing series, and its runs of two
    also break up the ladder that clean alternation draws.
    """
    return -1 if bin(index).count('1') % 2 == 0 else 1


def _branch_placement(
    index: int, count: int, repo: str, base_half_width: float
) -> _BranchPlacement:
    side = _branch_side(index)
    rng = random.Random(f'{repo}:place')
    spacing = 1.0 / max(count, 2)
    # Branches arrive ordered by lines added, descending -- so index 0 is the
    # longest, and it belongs at the *bottom* of the zone. Reading the order
    # straight through put the longest branches at the top and the stubs at
    # the base, which is an upside-down cone: the tips traced two rays
    # diverging upwards and the whole tree read as a V. Longest-lowest gives
    # the broad-at-the-bottom silhouette a real crown has.
    y_fraction = (
        1.0
        - index / max(count - 1, 1)
        + rng.uniform(-BRANCH_Y_JITTER_FRACTION, BRANCH_Y_JITTER_FRACTION)
        * spacing
    )
    y_fraction = min(max(y_fraction, 0.0), 1.0)
    origin_y = TRUNK_TOP_Y + y_fraction * BRANCH_ZONE_HEIGHT
    origin_half_width = _half_width_at(origin_y, base_half_width)
    return _BranchPlacement(
        origin_x=TRUNK_CENTER_X + origin_half_width * side * 0.5,
        origin_y=origin_y,
        side=side,
        spread_index=y_fraction,
        angle_jitter=rng.uniform(
            -BRANCH_ANGLE_JITTER_DEGREES, BRANCH_ANGLE_JITTER_DEGREES
        ),
    )


def _branch_bow(length: float, side: int, bow_factor: float) -> float:
    """How far a branch's midpoint sags off the straight origin-tip line.

    Signed by `side` because the perpendicular that `_branch_shape_points`
    offsets along points downwards on the right flank and upwards on the
    left, so `* side` is what makes both flanks sag rather than one of them
    arching over.
    """
    load = min(length / BRANCH_LENGTH_MAX, 1.0)
    fraction = (
        BRANCH_BOW_FRACTION_MIN
        + (BRANCH_BOW_FRACTION_MAX - BRANCH_BOW_FRACTION_MIN) * load
    )
    return length * fraction * side * (0.7 + 0.6 * bow_factor)


def _branch_endpoint(
    origin_x: float,
    origin_y: float,
    length: float,
    side: int,
    spread_index: float,
    *,
    angle_jitter: float = 0.0,
) -> tuple[float, float]:
    # One side-relative spread term carries all three contributions, so a
    # bigger number always means "further from vertical" on either flank.
    droop = BRANCH_DROOP_DEGREES * min(length / BRANCH_LENGTH_MAX, 1.0)
    spread = (
        BRANCH_SPREAD_DEGREES * (0.4 + 0.6 * spread_index)
        + angle_jitter
        + droop
    )
    angle_deg = 90 - side * spread
    angle_rad = math.radians(angle_deg)
    end_x = origin_x + length * (1 if side > 0 else -1) * abs(
        math.cos(angle_rad)
    )
    end_y = origin_y - length * math.sin(angle_rad)
    return end_x, end_y


def _branch_shape_points(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
    root_overlap: float = 0.0,
) -> dict[str, tuple[float, float]]:
    """The six control/corner points of a tapered branch quad.

    `root_overlap` pulls the base back past `origin` along the branch's
    own axis, burying it a little deeper in whatever it grows out of
    (the trunk) so there's no sliver of background visible at the seam.
    """
    dx = end_x - origin_x
    dy = end_y - origin_y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    root_x = origin_x - ux * root_overlap
    root_y = origin_y - uy * root_overlap

    mid_x = (origin_x + end_x) / 2 + px * bow
    mid_y = (origin_y + end_y) / 2 + py * bow
    avg_width = (base_width + tip_width) / 2

    return {
        'base_left': (root_x + px * base_width, root_y + py * base_width),
        'base_right': (root_x - px * base_width, root_y - py * base_width),
        'tip_left': (end_x + px * tip_width, end_y + py * tip_width),
        'tip_right': (end_x - px * tip_width, end_y - py * tip_width),
        'ctrl_left': (mid_x + px * avg_width, mid_y + py * avg_width),
        'ctrl_right': (mid_x - px * avg_width, mid_y - py * avg_width),
    }


def _render_branch_shape(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
    root_overlap: float = 0.0,
) -> str:
    p = _branch_shape_points(
        origin_x,
        origin_y,
        end_x,
        end_y,
        base_width=base_width,
        tip_width=tip_width,
        bow=bow,
        root_overlap=root_overlap,
    )
    return (
        f'M {p["base_left"][0]},{p["base_left"][1]} '
        f'Q {p["ctrl_left"][0]},{p["ctrl_left"][1]} '
        f'{p["tip_left"][0]},{p["tip_left"][1]} '
        f'L {p["tip_right"][0]},{p["tip_right"][1]} '
        f'Q {p["ctrl_right"][0]},{p["ctrl_right"][1]} '
        f'{p["base_right"][0]},{p["base_right"][1]} '
        f'Z'
    )


def _render_branch_outline(
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    base_width: float,
    tip_width: float,
    bow: float,
    root_overlap: float = 0.0,
) -> str:
    """The branch's outer edge only, open at the base.

    Used for stroking: closing the path across the base would draw a
    hard straight line right where the branch is meant to melt into the
    trunk, which is exactly the seam we're trying to hide.
    """
    p = _branch_shape_points(
        origin_x,
        origin_y,
        end_x,
        end_y,
        base_width=base_width,
        tip_width=tip_width,
        bow=bow,
        root_overlap=root_overlap,
    )
    return (
        f'M {p["base_left"][0]},{p["base_left"][1]} '
        f'Q {p["ctrl_left"][0]},{p["ctrl_left"][1]} '
        f'{p["tip_left"][0]},{p["tip_left"][1]} '
        f'L {p["tip_right"][0]},{p["tip_right"][1]} '
        f'Q {p["ctrl_right"][0]},{p["ctrl_right"][1]} '
        f'{p["base_right"][0]},{p["base_right"][1]}'
    )


def _render_branch_collar(
    origin_x: float, origin_y: float, base_width: float, seed: str
) -> str:
    """A soft, blurred bark knuckle where a branch meets the trunk.

    Real branch unions bulge outward and blend gradually into the trunk's
    bark rather than butting up against it at a hard edge. A blurred,
    irregular blob roughly the branch's own width -- drawn under the
    branch fill -- fakes that transition cheaply.
    """
    radius = max(base_width * 2.2, 6.0)
    rng = random.Random(f'{seed}:collar')
    blob_d = _blob_path(origin_x, origin_y, radius, rng, points=7, jitter=0.3)
    return (
        f'<path class="branch-collar" d="{blob_d}" '
        f'fill="url(#trunkGradient)" opacity="0.9" filter="url(#softBlur)" />'
    )


def _render_crown(base_half_width: float, top_half_width: float) -> str:
    rng = random.Random('ccgarden-crown')
    cx = TRUNK_CENTER_X
    cy = TRUNK_TOP_Y - top_half_width * 0.2
    radius = max(base_half_width * 1.15, 22.0)
    blob_d = _blob_path(cx, cy, radius, rng)
    return (
        f'<path class="canopy" d="{blob_d}" fill="url(#canopyGradient)" '
        f'opacity="0.9" />'
    )


def _render_branches_and_leaves(
    branches: list[RepoBranch], base_half_width: float
) -> str:
    if not branches:
        return ''
    elements = [
        _render_crown(base_half_width, base_half_width * TRUNK_TOP_TAPER)
    ]
    by_repo = {branch.repo: branch for branch in branches}
    limbs = _plan_limbs(
        [(branch.repo, float(branch.lines_added)) for branch in branches]
    )
    count = len(limbs)
    for index, limb in enumerate(limbs):
        whole_repo = by_repo[limb.repo]
        repo_branch = _limb_share_of(whole_repo, limb)
        placement = _branch_placement(index, count, limb.key, base_half_width)
        origin_x, origin_y, side = (
            placement.origin_x,
            placement.origin_y,
            placement.side,
        )

        length = _branch_length(repo_branch.lines_added)
        end_x, end_y = _branch_endpoint(
            origin_x,
            origin_y,
            length,
            side,
            placement.spread_index,
            angle_jitter=placement.angle_jitter,
        )
        base_width = _branch_width(
            repo_branch.output_tokens + repo_branch.input_tokens
        )
        curve_rng = random.Random(f'{limb.key}:curve')
        bow = _branch_bow(length, side, curve_rng.random())
        root_overlap = base_width * 0.9

        shape_d = _render_branch_shape(
            origin_x,
            origin_y,
            end_x,
            end_y,
            base_width=base_width,
            tip_width=BRANCH_TIP_WIDTH,
            bow=bow,
            root_overlap=root_overlap,
        )
        outline_d = _render_branch_outline(
            origin_x,
            origin_y,
            end_x,
            end_y,
            base_width=base_width,
            tip_width=BRANCH_TIP_WIDTH,
            bow=bow,
            root_overlap=root_overlap,
        )
        # Hovering any limb reports the repo it was cut from in full -- the
        # limb's own share is a rendering detail, not a statistic.
        total_tokens = whole_repo.output_tokens + whole_repo.input_tokens
        avg_turns = (
            whole_repo.prompts / whole_repo.sessions
            if whole_repo.sessions
            else 0.0
        )
        title = _title(
            f'{whole_repo.repo} — {whole_repo.sessions} sessions, '
            f'+{whole_repo.lines_added:,}/-{whole_repo.lines_removed:,} '
            f'lines, {total_tokens:,} tokens, '
            f'{avg_turns:.1f} turns/session'
        )
        collar = _render_branch_collar(
            origin_x, origin_y, base_width, limb.key
        )
        branch_path = (
            f'<path class="branch" data-repo="{repo_branch.repo}" '
            f'd="{shape_d}" fill="url(#trunkGradient)" opacity="0.95" />'
            f'<path d="{outline_d}" fill="none" stroke="#3a2412" '
            f'stroke-width="0.75" stroke-linecap="round" opacity="0.95" />'
        )
        leaves = _render_leaves(
            repo_branch, origin_x, origin_y, end_x, end_y, seed=limb.key
        )
        elements.append(
            f'<g class="repo-group">{title}'
            + _wind_group('ccg-sway-limb', limb.key, (origin_x, origin_y))
            + f'{collar}{branch_path}{leaves}</g></g>'
        )
    return ''.join(elements)


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
            (center_x + r * math.cos(angle), center_y + r * math.sin(angle))
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


def _canopy_radius(leaf_count: int) -> float:
    """Leaf-cluster radius, growing quickly at first then leveling off.

    A plain linear formula saturates at its cap almost immediately once a
    repo has more than ~45 sessions, which made a bursty repo's canopy
    (and every leaf scattered around it) jump to its final size on its
    first active day instead of visibly growing across days after.
    """
    saturation = min(leaf_count, LEAF_SATURATION_COUNT)
    growth = math.sqrt(saturation / LEAF_SATURATION_COUNT)
    return CANOPY_RADIUS_MIN + (CANOPY_RADIUS_MAX - CANOPY_RADIUS_MIN) * growth


def _leaf_size_multiplier(avg_turns_per_session: float) -> float:
    """Leaf-size scale for a repo with this many turns/session on average.

    Linear rather than the sqrt-saturation curve every other size formula
    here uses, because turns-per-session lives in a narrow, already
    human-scale range (roughly 1-15) instead of spanning the orders of
    magnitude that tokens or session counts do -- a saturating curve would
    flatten the real differences between repos into an almost-flat
    multiplier.
    """
    span = LEAF_TURNS_CEILING - LEAF_TURNS_FLOOR
    fraction = (avg_turns_per_session - LEAF_TURNS_FLOOR) / span
    fraction = max(0.0, min(1.0, fraction))
    return (
        LEAF_SIZE_MULTIPLIER_MIN
        + (LEAF_SIZE_MULTIPLIER_MAX - LEAF_SIZE_MULTIPLIER_MIN) * fraction
    )


def _foliage_girth_fraction(t: float) -> float:
    """0 at the start of the foliage zone, 1 by the tip.

    Leaves and blobs hug close to the branch where the greenery begins and
    billow out wider as they approach the tip.
    """
    span = FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION
    return max(0.0, min(1.0, (t - FOLIAGE_START_FRACTION) / span))


def _foliage_blob_fractions(length: float) -> list[float]:
    """Fractions-along-the-branch at which to anchor filler canopy blobs.

    More, evenly-spaced blobs for a longer branch so the greenery visibly
    bridges more of it instead of staying a single ball at the tip.
    """
    covered = length * (FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION)
    blob_count = max(
        1, min(MAX_FOLIAGE_BLOBS, round(covered / FOLIAGE_BLOB_SPACING) + 1)
    )
    if blob_count == 1:
        return [FOLIAGE_TIP_OVERHANG]
    span = FOLIAGE_TIP_OVERHANG - FOLIAGE_START_FRACTION
    return [
        FOLIAGE_START_FRACTION + span * i / (blob_count - 1)
        for i in range(blob_count)
    ]


def _foliage_blob_relative_radii(length: float) -> list[tuple[float, float]]:
    """(fraction, radius-as-a-fraction-of-canopy_radius) per foliage blob.

    Mirrors the radius `_render_foliage_blob` actually draws at each
    fraction, so leaf placement can be weighted by real blob area instead
    of by raw along-branch position.
    """
    return [
        (
            fraction,
            0.35 + 0.65 * _foliage_girth_fraction(fraction),
        )
        for fraction in _foliage_blob_fractions(length)
    ]


def _leaf_placement(
    rng: random.Random,
    blob_relative_radii: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """A leaf's fixed (t, relative_radius, r_frac, angle) placement.

    Assigns the leaf to one of the branch's actual canopy blobs, weighted
    by that blob's area, then fixes a position inside its disk (radius
    fraction via sqrt for area-uniform density, angle over the full
    circle). Weighting by area -- rather than sampling t directly along
    the branch -- makes leaf density track how much green each blob
    actually covers, instead of piling up wherever the raw along-branch
    position happens to land. `relative_radius` and `r_frac` are kept
    separate (not pre-multiplied) so callers can rescale by a per-day
    canopy_radius during the growth timeline.
    """
    weights = [radius**2 for _, radius in blob_relative_radii]
    fraction, relative_radius = rng.choices(
        blob_relative_radii, weights=weights
    )[0]
    angle = rng.uniform(0.0, 2 * math.pi)
    r_frac = math.sqrt(rng.random())
    return fraction, relative_radius, r_frac, angle


def _leaf_offset(
    relative_radius: float,
    r_frac: float,
    angle: float,
    canopy_radius: float,
) -> tuple[float, float]:
    """A leaf's (perpendicular, along) pixel offset from its blob center."""
    radius = canopy_radius * relative_radius * r_frac
    return radius * math.cos(angle), radius * math.sin(angle)


def _render_foliage_blob(
    origin_x: float,
    origin_y: float,
    dx: float,
    dy: float,
    *,
    fraction: float,
    canopy_radius: float,
    seed: str,
) -> str:
    girth = _foliage_girth_fraction(fraction)
    blob_radius = canopy_radius * (0.35 + 0.65 * girth)
    cx = origin_x + fraction * dx
    cy = origin_y + fraction * dy
    shadow_d = _blob_path(
        cx + blob_radius * 0.18,
        cy + blob_radius * 0.22,
        blob_radius * 0.92,
        random.Random(f'{seed}:shadow'),
    )
    main_d = _blob_path(cx, cy, blob_radius, random.Random(f'{seed}:canopy'))
    return (
        f'<path class="canopy" d="{shadow_d}" fill="#2f5f2f" '
        f'opacity="0.3" filter="url(#softBlur)" />'
        f'<path class="canopy" d="{main_d}" fill="url(#canopyGradient)" '
        f'opacity="0.9" />'
    )


def _render_leaves(
    repo_branch: RepoBranch,
    origin_x: float,
    origin_y: float,
    end_x: float,
    end_y: float,
    *,
    seed: str = '',
) -> str:
    leaf_count = repo_branch.sessions * LEAVES_PER_SESSION
    if leaf_count == 0:
        return ''
    seed = seed or repo_branch.repo
    rng = random.Random(seed)
    elements = []

    avg_turns = (
        repo_branch.prompts / repo_branch.sessions
        if repo_branch.sessions
        else 0.0
    )
    size_multiplier = _leaf_size_multiplier(avg_turns)

    dx, dy = end_x - origin_x, end_y - origin_y
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux

    canopy_radius = _canopy_radius(leaf_count)
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    blob_relative_radii = (
        _foliage_blob_relative_radii(length) if has_canopy else []
    )
    if has_canopy:
        for fraction, _ in blob_relative_radii:
            elements.append(
                _render_foliage_blob(
                    origin_x,
                    origin_y,
                    dx,
                    dy,
                    fraction=fraction,
                    canopy_radius=canopy_radius,
                    seed=f'{seed}:{fraction:.3f}',
                )
            )

    for _ in range(leaf_count):
        if has_canopy:
            t, relative_radius, r_frac, blob_angle = _leaf_placement(
                rng, blob_relative_radii
            )
            perp_offset, along_offset = _leaf_offset(
                relative_radius, r_frac, blob_angle, canopy_radius
            )
        else:
            t = rng.uniform(FOLIAGE_START_FRACTION, FOLIAGE_TIP_OVERHANG)
            blob_angle = rng.uniform(0.0, 2 * math.pi)
            scatter_r = LEAF_SCATTER_RADIUS * 0.4 * math.sqrt(rng.random())
            perp_offset = scatter_r * math.cos(blob_angle)
            along_offset = scatter_r * math.sin(blob_angle)
        cx = origin_x + t * dx
        cy = origin_y + t * dy
        leaf_x = cx + px * perp_offset + ux * along_offset
        leaf_y = cy + py * perp_offset + uy * along_offset
        radius = (
            max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5) * size_multiplier
        )
        angle = rng.uniform(0, 360)
        color_index = rng.randrange(len(LEAF_COLORS))
        elements.append(
            f'<g class="leaf" transform="translate({leaf_x:.1f},{leaf_y:.1f}) '
            f'rotate({angle:.1f}) scale({radius:.2f})">'
            f'<path d="{LEAF_SHAPE_D}" '
            f'fill="url(#{LEAF_PAINT_ID}{color_index})" '
            f'opacity="{LEAF_OPACITY_LIVING}" />'
            f'<path d="{LEAF_VEIN_D}" stroke="#2f5f2f" stroke-width="0.12" '
            f'opacity="0.5" />'
            f'</g>'
        )
    return ''.join(elements)


class _FruitSpot(NamedTuple):
    """A placed fruit: where it hangs and how big it is."""

    x: float
    y: float
    radius: float


class _CanopyDisk(NamedTuple):
    """The reliably-green core of one foliage blob."""

    x: float
    y: float
    radius: float


def _canopy_disks(
    origin_x: float,
    origin_y: float,
    dx: float,
    dy: float,
    leaf_count: int,
) -> list[_CanopyDisk]:
    """The disks a fruit may hang in, per foliage blob on this branch.

    `_blob_path` wobbles each blob's edge by up to 32%, so the drawn
    greenery is only guaranteed to cover `1 - jitter` of the nominal
    radius. `FRUIT_CANOPY_INSET` stays inside that worst case, which is
    what makes "inside this disk" mean "actually on green".
    """
    if leaf_count <= 0:
        return []
    length = math.hypot(dx, dy) or 1.0
    if leaf_count < CANOPY_MIN_LEAVES:
        # Too sparse for blobs: `_render_leaves` scatters this branch's
        # few leaves in a loose band, so hang the fruit in the same band.
        scatter = LEAF_SCATTER_RADIUS * 0.4 * FRUIT_CANOPY_INSET
        return [
            _CanopyDisk(
                x=origin_x + fraction * dx,
                y=origin_y + fraction * dy,
                radius=scatter,
            )
            for fraction, _ in _foliage_blob_relative_radii(length)
        ]
    canopy_radius = _canopy_radius(leaf_count)
    return [
        _CanopyDisk(
            x=origin_x + fraction * dx,
            y=origin_y + fraction * dy,
            radius=canopy_radius * relative * FRUIT_CANOPY_INSET,
        )
        for fraction, relative in _foliage_blob_relative_radii(length)
    ]


def _fruit_fits(
    x: float, y: float, radius: float, disks: list[_CanopyDisk]
) -> bool:
    """True when the fruit *and its stem* sit inside a single blob.

    Testing the centre alone is what let stems poke out above the canopy:
    the stem rises from the top of the fruit, so it clears the greenery
    well before the fruit itself does. The body has to fit the disk's
    guaranteed-green core, while the stem only has to stay within the
    blob's nominal radius -- it is a thin line, and holding it to the same
    conservative core would push every fruit into the middle of the blob.
    """
    half = radius * FRUIT_EXTENT_HALF_WIDTH
    body = [
        (x + sx * half, y + sy * radius)
        for sx in (-1.0, 1.0)
        for sy in (FRUIT_EXTENT_TOP, FRUIT_EXTENT_BOTTOM)
    ]
    stem_x, stem_y = x, y + radius * FRUIT_STEM_TIP
    return any(
        all(
            math.hypot(cx - disk.x, cy - disk.y) <= disk.radius
            for cx, cy in body
        )
        and math.hypot(stem_x - disk.x, stem_y - disk.y)
        <= disk.radius / FRUIT_CANOPY_INSET
        for disk in disks
    )


def _place_fruit(
    rng: random.Random,
    radius: float,
    disks: list[_CanopyDisk],
    placed: list[_FruitSpot],
) -> _FruitSpot | None:
    """A spot inside the canopy that no other fruit is already using.

    Rejection sampling rather than a formula: the canopy is a union of
    overlapping wobbly disks, so there is no closed form for "inside the
    green and clear of the neighbours". Bounded tries keep it O(fruit),
    and the rng is seeded, so a retry is as deterministic as a first hit.
    """
    if not disks:
        return None
    radius = min(radius, max(d.radius for d in disks) / FRUIT_EXTENT_REACH)
    weights = [disk.radius**2 for disk in disks]
    for _ in range(FRUIT_PLACEMENT_TRIES):
        disk = rng.choices(disks, weights=weights)[0]
        angle = rng.uniform(0.0, 2 * math.pi)
        reach = disk.radius * math.sqrt(rng.random())
        x = disk.x + reach * math.cos(angle)
        y = disk.y + reach * math.sin(angle)
        if not _fruit_fits(x, y, radius, disks):
            continue
        if any(
            math.hypot(x - spot.x, y - spot.y)
            < (radius + spot.radius) * FRUIT_MIN_GAP
            for spot in placed
        ):
            continue
        return _FruitSpot(x=x, y=y, radius=radius)
    return None


def _fruit_radius(uses: int) -> float:
    """Fruit size for a skill with `uses` calls.

    A skill you lean on daily hangs heavier than one you tried once.
    """
    saturation = min(max(uses, 0), FRUIT_RADIUS_SATURATION)
    growth = math.sqrt(saturation / FRUIT_RADIUS_SATURATION)
    return FRUIT_RADIUS_MIN + (FRUIT_RADIUS_MAX - FRUIT_RADIUS_MIN) * growth


def _fruit_color(skill: str) -> str:
    # crc32, not hash(): str.__hash__ is salted per process, so hash() would
    # repaint the whole tree on every run.
    return FRUIT_COLORS[zlib.crc32(skill.encode()) % len(FRUIT_COLORS)]


def _fruit_count(uses: int) -> int:
    """How many fruit one skill earns for `uses` calls."""
    raw = round(math.sqrt(max(uses, 0)) * FRUIT_ROOT_SATURATION)
    return min(max(int(raw), FRUIT_MIN_PER_SKILL), FRUIT_MAX_PER_SKILL)


def _fruit_plan(skills: list[SkillFruit]) -> list[tuple[SkillFruit, int]]:
    """Fruit per skill, scaled down together if the tree would overflow."""
    plan = [
        (sf, _fruit_count(sf.count))
        for sf in skills
        if sf.count >= FRUIT_MIN_CALLS
    ]
    total = sum(n for _, n in plan)
    if total <= FRUIT_TOTAL_MAX or total == 0:
        return plan
    scale = FRUIT_TOTAL_MAX / total
    return [(sf, max(FRUIT_MIN_PER_SKILL, int(n * scale))) for sf, n in plan]


def _fruit_label(skill: str, count: int) -> str:
    calls = 'call' if count == 1 else 'calls'
    return f'{skill} — {count:,} {calls}'


# Every shape is drawn at radius 1 about its own centre and scaled into
# place, so sizing a fruit is one number and the shapes stay comparable.
FRUIT_STEM_D = 'M 0,-0.95 L 0,-1.95'
FRUIT_SHAPE_BODIES = {
    'round': '<circle cx="0" cy="0" r="1" fill="{fill}" opacity="0.9" />',
    'pear': (
        '<path d="M 0,-1.05 C 0.42,-0.95 0.40,-0.35 0.55,0.05 '
        'C 0.78,0.60 0.42,1.05 0,1.05 C -0.42,1.05 -0.78,0.60 -0.55,0.05 '
        'C -0.40,-0.35 -0.42,-0.95 0,-1.05 Z" fill="{fill}" opacity="0.9" />'
    ),
    'plum': (
        '<ellipse cx="0" cy="0.05" rx="0.88" ry="1.02" '
        'fill="{fill}" opacity="0.9" />'
        '<path d="M 0,-0.95 Q 0.18,0 0,1.05" stroke="#00000033" '
        'stroke-width="0.12" fill="none" />'
    ),
    'berries': (
        '<circle cx="-0.52" cy="0.28" r="0.58" fill="{fill}" opacity="0.9" />'
        '<circle cx="0.52" cy="0.32" r="0.55" fill="{fill}" opacity="0.9" />'
        '<circle cx="0.02" cy="-0.42" r="0.60" fill="{fill}" opacity="0.9" />'
    ),
    'cherries': (
        '<path d="M -0.45,0.30 Q -0.30,-0.55 0,-0.95" stroke="#5a3d1a" '
        'stroke-width="0.10" fill="none" />'
        '<path d="M 0.48,0.38 Q 0.28,-0.50 0,-0.95" stroke="#5a3d1a" '
        'stroke-width="0.10" fill="none" />'
        '<circle cx="-0.45" cy="0.42" r="0.56" fill="{fill}" opacity="0.9" />'
        '<circle cx="0.48" cy="0.48" r="0.52" fill="{fill}" opacity="0.9" />'
    ),
    'apple': (
        '<path d="M 0,-0.85 C 0.65,-0.90 1.05,-0.25 0.95,0.25 '
        'C 0.85,0.80 0.40,1.10 0,1.10 C -0.40,1.10 -0.85,0.80 -0.95,0.25 '
        'C -1.05,-0.25 -0.65,-0.90 0,-0.85 Z" fill="{fill}" '
        'opacity="0.9" />'
        '<path d="M 0,-0.85 Q -0.08,-0.40 0,0.10" stroke="#00000022" '
        'stroke-width="0.08" fill="none" />'
    ),
    'lemon': (
        '<ellipse cx="0" cy="0" rx="0.60" ry="1.05" fill="{fill}" '
        'opacity="0.9" />'
        '<ellipse cx="-0.10" cy="-0.85" rx="0.18" ry="0.25" '
        'fill="{fill}" opacity="0.9" />'
        '<ellipse cx="0.08" cy="0.88" rx="0.15" ry="0.22" '
        'fill="{fill}" opacity="0.9" />'
    ),
    'star': (
        '<path d="M 0,-1.0 L 0.24,-0.30 L 1.0,-0.30 L 0.38,0.12 '
        'L 0.60,0.90 L 0,0.42 L -0.60,0.90 L -0.38,0.12 '
        'L -1.0,-0.30 L -0.24,-0.30 Z" fill="{fill}" opacity="0.9" />'
    ),
    'acorn': (
        '<path d="M -0.55,-0.50 C -0.55,-0.85 0.55,-0.85 0.55,-0.50 '
        'L 0.55,-0.30 L -0.55,-0.30 Z" fill="#8B6914" opacity="0.9" />'
        '<ellipse cx="0" cy="0.30" rx="0.50" ry="0.70" fill="{fill}" '
        'opacity="0.9" />'
    ),
    'fig': (
        '<path d="M 0,-0.90 C 0.30,-0.80 0.55,-0.45 0.65,-0.05 '
        'C 0.80,0.50 0.60,1.00 0,1.10 C -0.60,1.00 -0.80,0.50 '
        '-0.65,-0.05 C -0.55,-0.45 -0.30,-0.80 0,-0.90 Z" '
        'fill="{fill}" opacity="0.9" />'
    ),
    'heart': (
        '<path d="M 0,-0.30 C 0.25,-0.95 1.05,-0.85 1.0,-0.20 '
        'C 0.95,0.35 0.35,0.80 0,1.10 C -0.35,0.80 -0.95,0.35 '
        '-1.0,-0.20 C -1.05,-0.85 -0.25,-0.95 0,-0.30 Z" '
        'fill="{fill}" opacity="0.9" />'
    ),
    'peach': (
        '<circle cx="0" cy="0.05" r="0.95" fill="{fill}" '
        'opacity="0.9" />'
        '<path d="M 0,-0.90 Q 0.25,0.05 0,0.95" stroke="#00000028" '
        'stroke-width="0.10" fill="none" />'
    ),
}
FRUIT_SHAPE_HIGHLIGHTS = {
    'round': (-0.30, -0.30, 0.28),
    'pear': (-0.22, 0.30, 0.22),
    'plum': (-0.30, -0.25, 0.24),
    'berries': (-0.10, -0.55, 0.18),
    'cherries': (-0.58, 0.28, 0.18),
    'apple': (-0.35, -0.30, 0.25),
    'lemon': (-0.18, -0.35, 0.18),
    'star': (-0.15, -0.45, 0.20),
    'acorn': (-0.15, 0.10, 0.20),
    'fig': (-0.20, -0.30, 0.22),
    'heart': (-0.30, -0.30, 0.22),
    'peach': (-0.30, -0.25, 0.26),
}
FRUIT_SHAPES = tuple(FRUIT_SHAPE_BODIES)


def _fruit_shape(skill: str) -> str:
    """Which shape a skill's fruit takes.

    Salted apart from `_fruit_color` so shape and colour don't move
    together -- keyed off the same name with the same hash, every red
    fruit would share one silhouette.
    """
    digest = zlib.crc32(f'shape:{skill}'.encode())
    return FRUIT_SHAPES[digest % len(FRUIT_SHAPES)]


def _render_single_fruit(
    spot: _FruitSpot,
    color: str,
    shape: str,
    label: str,
) -> str:
    title = _title(_escape_xml(label))
    highlight_x, highlight_y, highlight_r = FRUIT_SHAPE_HIGHLIGHTS[shape]
    body = FRUIT_SHAPE_BODIES[shape].format(fill=color)
    # Cherries draw their own pair of stems.
    stem = (
        ''
        if shape == 'cherries'
        else (
            f'<path d="{FRUIT_STEM_D}" stroke="#5a3d1a" '
            f'stroke-width="0.12" fill="none" />'
        )
    )
    stem_abs_x = spot.x
    stem_abs_y = spot.y + spot.radius * FRUIT_STEM_TIP
    sway_open = _wind_group(
        'ccg-sway-fruit',
        f'{label}:{spot.x:.0f}',
        (stem_abs_x, stem_abs_y),
    )
    return (
        f'{sway_open}'
        f'<g class="fruit" transform="translate({spot.x:.1f},{spot.y:.1f}) '
        f'scale({spot.radius:.2f})">{title}{stem}{body}'
        f'<circle cx="{highlight_x}" cy="{highlight_y}" r="{highlight_r}" '
        f'fill="white" opacity="0.35" />'
        f'</g></g>'
    )


def _fruit_assignments(
    plan: list[tuple[SkillFruit, int]],
) -> list[SkillFruit]:
    """One entry per fruit, with the skills interleaved.

    Emitting a skill's fruit consecutively and then dealing them round
    robin puts every fruit of a skill on the same few limbs, which is
    what made the crop read as coloured clumps. Rotating between skills
    spreads each one over the whole tree and mixes the colours within
    each limb.
    """
    remaining = [(skill, count) for skill, count in plan if count > 0]
    order: list[SkillFruit] = []
    while remaining:
        order.extend(skill for skill, _ in remaining)
        remaining = [
            (skill, count - 1) for skill, count in remaining if count > 1
        ]
    return order


def _limb_canopy(
    limb: _Limb,
    limbs: list[_Limb],
    by_repo: dict[str, RepoBranch],
    base_half_width: float,
) -> list[_CanopyDisk]:
    """The canopy disks hanging off one limb."""
    repo_branch = _limb_share_of(by_repo[limb.repo], limb)
    placement = _branch_placement(
        limbs.index(limb), len(limbs), limb.key, base_half_width
    )
    length = _branch_length(repo_branch.lines_added)
    end_x, end_y = _branch_endpoint(
        placement.origin_x,
        placement.origin_y,
        length,
        placement.side,
        placement.spread_index,
        angle_jitter=placement.angle_jitter,
    )
    return _canopy_disks(
        placement.origin_x,
        placement.origin_y,
        end_x - placement.origin_x,
        end_y - placement.origin_y,
        repo_branch.sessions * LEAVES_PER_SESSION,
    )


def _leafy_canopies(
    limbs: list[_Limb],
    by_repo: dict[str, RepoBranch],
    base_half_width: float,
) -> tuple[list[list[_CanopyDisk]], list[tuple[str, tuple[float, float]]]]:
    """Canopies that carry greenery, with each one's wind seed and pivot.

    A fruit hangs in its limb's canopy, so it has to ride that limb's wind
    group -- same class, same seed, same pivot -- or it floats while the
    greenery around it sways. Limbs whose share rounds down to no leaves
    are dropped: they have nowhere to hang anything.
    """
    canopies: list[list[_CanopyDisk]] = []
    wind: list[tuple[str, tuple[float, float]]] = []
    for index, limb in enumerate(limbs):
        disks = _limb_canopy(limb, limbs, by_repo, base_half_width)
        if not disks:
            continue
        placement = _branch_placement(
            index, len(limbs), limb.key, base_half_width
        )
        canopies.append(disks)
        wind.append((limb.key, (placement.origin_x, placement.origin_y)))
    return canopies, wind


def _render_fruit_on_branches(
    skills: list[SkillFruit],
    branches: list[RepoBranch],
    base_half_width: float,
) -> str:
    if not skills or not branches:
        return ''

    plan = _fruit_plan(skills)
    if not plan:
        return ''

    by_repo = {branch.repo: branch for branch in branches}
    limbs = _plan_limbs([(b.repo, float(b.lines_added)) for b in branches])
    if not limbs:
        return ''

    canopies, canopy_wind = _leafy_canopies(limbs, by_repo, base_half_width)
    if not canopies:
        return ''

    placed: list[list[_FruitSpot]] = [[] for _ in canopies]
    rng = random.Random('ccgarden-fruit')

    buckets: list[list[str]] = [[] for _ in canopies]
    for index, skill in enumerate(_fruit_assignments(plan)):
        radius = _fruit_radius(skill.count)
        # Start at this fruit's turn in the rotation, but walk on if that
        # canopy is already full, so a crowded limb sheds fruit onto its
        # neighbours instead of the crop simply shrinking.
        spot = None
        limb_index = None
        for offset in range(len(canopies)):
            candidate = (index + offset) % len(canopies)
            spot = _place_fruit(
                rng, radius, canopies[candidate], placed[candidate]
            )
            if spot is not None:
                limb_index = candidate
                break
        if spot is None or limb_index is None:
            continue
        placed[limb_index].append(spot)
        buckets[limb_index].append(
            _render_single_fruit(
                spot,
                _fruit_color(skill.skill),
                _fruit_shape(skill.skill),
                _fruit_label(skill.skill, skill.count),
            )
        )

    return ''.join(
        _wind_group('ccg-sway-limb', key, pivot) + ''.join(bucket) + '</g>'
        for (key, pivot), bucket in zip(canopy_wind, buckets, strict=True)
        if bucket
    )


LEGEND_MARGIN = 4.0
LEGEND_Y = VIEWBOX_HEIGHT + LEGEND_MARGIN
LEGEND_HEIGHT = LEGEND_BAND_HEIGHT - LEGEND_MARGIN * 2
LEGEND_X = 14.0
LEGEND_WIDTH = VIEWBOX_WIDTH - LEGEND_X * 2
LEGEND_PADDING = 9.0
# Three shallow rows rather than two deep ones: five columns give a
# description line the ~130px it needs, where seven left every third line
# spilling over its neighbour's divider. Every entry is capped at two
# lines so all three rows fit the band.
LEGEND_GRID_ROWS = 3
LEGEND_ICON_DX = 8.0
LEGEND_TEXT_DX = 20.0
LEGEND_LABEL_DY = 11.0
LEGEND_LINE_HEIGHT = 10.0
LEGEND_LABEL_SIZE = 10.5
LEGEND_DESC_SIZE = 8.6
LEGEND_ROWS = (
    ('Trunk', ('width grows with', 'total sessions'), 'trunk'),
    ('Rings', ('one per day worked;', 'bolder = busier day'), 'ring'),
    (
        'Branches',
        ('grouped by repo; longer =', 'more lines, thicker = tokens'),
        'branch',
    ),
    (
        'Leaves',
        ('one per session; more =', 'busier repo, bigger = turns'),
        'leaf',
    ),
    (
        'Flowers',
        ('one per whole ratio', 'of cache read:write'),
        'flower',
    ),
    (
        'Clouds',
        ('one per model + effort;', 'bigger + darker = more'),
        'cloud',
    ),
    (
        'Bushes',
        ('one per tool used;', 'bigger = used more'),
        'bush',
    ),
    (
        'Sun',
        ('crosses the sky as it replays;', 'ends higher + bigger w/ tokens'),
        'sun',
    ),
    (
        'Season',
        ('turns + thins the', 'longer you are away'),
        'season',
    ),
    (
        'Sky',
        ('darkens with prompts after', '21:00; sun becomes a moon'),
        'sky',
    ),
    (
        'Rain',
        ('falls on the days', 'you never showed up'),
        'rain',
    ),
    (
        'Fruit',
        ('one per skill you ran;', 'more calls, more fruit'),
        'fruit',
    ),
    (
        'Sunflowers',
        ('one per repo;', 'taller = more prompts'),
        'sunflower',
    ),
    (
        'Birds',
        ('one per cartoon call;', 'bigger = more saved'),
        'bird',
    ),
)


def _legend_icon_trunk(cx: float, cy: float) -> str:
    return (
        f'<rect x="{cx - 6:.1f}" y="{cy - 7:.1f}" width="12" height="14" '
        f'rx="3" fill="url(#trunkGradient)" stroke="#3a2412" '
        f'stroke-width="0.6" />'
    )


def _legend_icon_ring(cx: float, cy: float) -> str:
    return (
        f'<path d="M{cx - 7:.1f},{cy + 3:.1f} Q{cx:.1f},{cy - 5:.1f} '
        f'{cx + 7:.1f},{cy + 3:.1f}" fill="none" stroke="#3a2412" '
        f'stroke-width="2.2" stroke-linecap="round" opacity="0.6" />'
    )


def _legend_icon_branch(cx: float, cy: float) -> str:
    return (
        f'<path d="M{cx - 7:.1f},{cy + 7:.1f} Q{cx:.1f},{cy - 2:.1f} '
        f'{cx + 7:.1f},{cy - 7:.1f}" fill="none" '
        f'stroke="url(#trunkGradient)" stroke-width="3" '
        f'stroke-linecap="round" />'
    )


def _legend_icon_leaf(cx: float, cy: float) -> str:
    return (
        f'<g transform="translate({cx:.1f},{cy:.1f}) rotate(-15) scale(6)">'
        f'<path d="{LEAF_SHAPE_D}" fill="#5a9e5a" opacity="0.95" />'
        f'</g>'
    )


def _legend_icon_flower(cx: float, cy: float) -> str:
    return _render_flower(
        cx, cy, 6.0, '#f27ab0', random.Random('legend-flower')
    )


def _legend_icon_cloud(cx: float, cy: float) -> str:
    return _render_cloud(cx, cy, 7.0, 'legend-cloud')


def _legend_icon_bush(cx: float, cy: float) -> str:
    return _render_bush(cx, cy + 5.0, 7.0, 'legend-bush')


def _legend_icon_sun(cx: float, cy: float) -> str:
    return _render_sun(cx, cy, 6.0)


def _legend_icon_sunflower(cx: float, cy: float) -> str:
    return _render_sunflower(cx, cy + 8.0, 16.0, 'legend-sunflower')


def _legend_icon_season(cx: float, cy: float) -> str:
    return (
        f'<path d="{LEAF_SHAPE_D}" fill="{LEAF_COLORS[1]}" '
        f'transform="translate({cx - 3.5:.1f},{cy:.1f}) '
        f'rotate(-20) scale(5)" />'
        f'<path d="{LEAF_SHAPE_D}" fill="{AUTUMN_COLORS[2]}" '
        f'transform="translate({cx + 3.5:.1f},{cy:.1f}) '
        f'rotate(25) scale(5)" />'
    )


def _legend_icon_sky(cx: float, cy: float) -> str:
    return (
        f'<rect x="{cx - 6:.1f}" y="{cy - 5:.1f}" width="12" height="10" '
        f'rx="2" fill="{NIGHT_VEIL_COLOR}" />'
        f'<circle cx="{cx - 3:.1f}" cy="{cy - 2:.1f}" r="0.9" '
        f'fill="{STAR_COLOR}" />'
        f'<circle cx="{cx + 2:.1f}" cy="{cy - 3.4:.1f}" r="0.7" '
        f'fill="{STAR_COLOR}" />'
        f'<circle cx="{cx + 3.4:.1f}" cy="{cy + 1.6:.1f}" r="0.9" '
        f'fill="{STAR_COLOR}" />'
        f'<circle cx="{cx - 1.6:.1f}" cy="{cy + 2.6:.1f}" r="0.6" '
        f'fill="{STAR_COLOR}" />'
    )


def _legend_icon_rain(cx: float, cy: float) -> str:
    cloud = _render_cloud(cx, cy - 3.0, 5.5, 'legend-rain')
    streaks = ''.join(
        f'<line x1="{cx + offset:.1f}" y1="{cy + 2.0:.1f}" '
        f'x2="{cx + offset + 1.4:.1f}" y2="{cy + 7.5:.1f}" '
        f'stroke="#5b86ad" stroke-width="1.2" stroke-linecap="round" />'
        for offset in (-4.0, 0.0, 4.0)
    )
    return cloud + streaks


def _legend_icon_bird(cx: float, cy: float) -> str:
    # Dark, unlike the sky birds: the legend panel is a pale cream card.
    return _render_bird(cx, cy + 2.0, 6.0, BIRD_LEGEND_COLOR)


def _legend_icon_fruit(cx: float, cy: float) -> str:
    return (
        f'<line x1="{cx:.1f}" y1="{cy - 3:.1f}" '
        f'x2="{cx:.1f}" y2="{cy - 8:.1f}" '
        f'stroke="#5a3d1a" stroke-width="1" />'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" '
        f'fill="{FRUIT_COLORS[0]}" />'
        f'<circle cx="{cx - 1.2:.1f}" cy="{cy - 1.2:.1f}" r="1.5" '
        f'fill="white" opacity="0.35" />'
    )


LEGEND_ICON_RENDERERS = {
    'trunk': _legend_icon_trunk,
    'ring': _legend_icon_ring,
    'branch': _legend_icon_branch,
    'leaf': _legend_icon_leaf,
    'flower': _legend_icon_flower,
    'cloud': _legend_icon_cloud,
    'bush': _legend_icon_bush,
    'sun': _legend_icon_sun,
    'sunflower': _legend_icon_sunflower,
    'sky': _legend_icon_sky,
    'season': _legend_icon_season,
    'rain': _legend_icon_rain,
    'bird': _legend_icon_bird,
    'fruit': _legend_icon_fruit,
}


def _render_legend_icon(icon: str, cx: float, cy: float) -> str:
    return LEGEND_ICON_RENDERERS[icon](cx, cy)


def _render_legend(
    *,
    with_birds: bool = False,
    with_night: bool = False,
    with_seasons: bool = False,
    with_rain: bool = False,
    with_fruit: bool = False,
) -> str:
    """A key panel explaining what each part of the tree represents.

    Sits in its own band below the garden viewBox, so it can never overlap
    the tree. Always three rows, with the column count derived from how
    many entries survive the drops below -- a fixed column count leaves the
    last row ragged and half empty as soon as an entry is dropped.

    Columns are left-aligned rather than centred on a short last row: a
    centred row lands its text on the dividers drawn for the rows above,
    and the dividers themselves are drawn per row, only where there's an
    entry to the right of them, so the grid reads as one aligned table.

    The birds, sky, season and rain entries are dropped unless there's
    actually a bird, a night, a turned leaf or a downpour to explain: a
    key to something the garden isn't doing is just a puzzle.
    """
    shown = {
        'bird': with_birds,
        'sky': with_night,
        'season': with_seasons,
        'rain': with_rain,
        'fruit': with_fruit,
    }
    rows = [row for row in LEGEND_ROWS if shown.get(row[2], True)]
    columns = math.ceil(len(rows) / LEGEND_GRID_ROWS)
    column_width = LEGEND_WIDTH / columns
    row_count = math.ceil(len(rows) / columns)
    row_height = LEGEND_HEIGHT / row_count
    parts = [
        (
            f'<g class="legend">'
            f'<rect x="0" y="{VIEWBOX_HEIGHT:.1f}" '
            f'width="{VIEWBOX_WIDTH:.1f}" '
            f'height="{LEGEND_BAND_HEIGHT:.1f}" fill="#3f7a3f" />'
            f'<rect x="{LEGEND_X:.1f}" y="{LEGEND_Y:.1f}" '
            f'width="{LEGEND_WIDTH:.1f}" height="{LEGEND_HEIGHT:.1f}" rx="8" '
            f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.88" />'
        )
    ]
    for row_index in range(row_count):
        row_top = LEGEND_Y + row_height * row_index
        for divider in range(1, columns):
            if row_index * columns + divider >= len(rows):
                break
            divider_x = LEGEND_X + column_width * divider
            parts.append(
                f'<line x1="{divider_x:.1f}" y1="{row_top + 4:.1f}" '
                f'x2="{divider_x:.1f}" '
                f'y2="{row_top + row_height - 4:.1f}" '
                f'stroke="#3a2412" stroke-width="0.4" opacity="0.18" />'
            )
    for index, (label, desc_lines, icon) in enumerate(rows):
        row_index = index // columns
        column_index = index % columns
        col_x = LEGEND_X + column_width * column_index
        row_top = LEGEND_Y + row_height * row_index
        label_y = row_top + LEGEND_LABEL_DY
        icon_cx = col_x + LEGEND_PADDING + LEGEND_ICON_DX
        text_x = col_x + LEGEND_PADDING + LEGEND_TEXT_DX
        parts.append(_render_legend_icon(icon, icon_cx, label_y + 3))
        parts.append(
            f'<text x="{text_x:.1f}" y="{label_y:.1f}" '
            f'font-family="Georgia, serif" font-size="{LEGEND_LABEL_SIZE}" '
            f'font-weight="bold" fill="#2f3b23">{label}</text>'
        )
        for line_index, desc_line in enumerate(desc_lines):
            line_y = (
                label_y + LEGEND_LINE_HEIGHT + line_index * LEGEND_LINE_HEIGHT
            )
            parts.append(
                f'<text x="{text_x:.1f}" y="{line_y:.1f}" '
                f'font-family="Georgia, serif" '
                f'font-size="{LEGEND_DESC_SIZE}" '
                f'fill="#4a4a3a">{desc_line}</text>'
            )
    parts.append('</g>')
    return ''.join(parts)


FRUIT_KEY_ROW_HEIGHT = 22.0
FRUIT_KEY_COLS = 4
FRUIT_KEY_PADDING = 6.0
FRUIT_KEY_ICON_SCALE = 3.5


def _fruit_key_height(skills: list[SkillFruit]) -> float:
    active = [s for s in skills if s.count >= FRUIT_MIN_CALLS]
    if not active:
        return 0.0
    rows = math.ceil(len(active) / FRUIT_KEY_COLS)
    return rows * FRUIT_KEY_ROW_HEIGHT + FRUIT_KEY_PADDING * 2


def _render_fruit_key(
    skills: list[SkillFruit],
    top_y: float,
) -> str:
    active = sorted(
        [s for s in skills if s.count >= FRUIT_MIN_CALLS],
        key=lambda s: s.count,
        reverse=True,
    )
    if not active:
        return ''

    rows = math.ceil(len(active) / FRUIT_KEY_COLS)
    height = rows * FRUIT_KEY_ROW_HEIGHT + FRUIT_KEY_PADDING * 2
    col_width = LEGEND_WIDTH / FRUIT_KEY_COLS

    parts = [
        (
            f'<g class="legend">'
            f'<rect x="0" y="{top_y:.1f}" '
            f'width="{VIEWBOX_WIDTH:.1f}" '
            f'height="{height:.1f}" fill="#3f7a3f" />'
            f'<rect x="{LEGEND_X:.1f}" y="{top_y + 2:.1f}" '
            f'width="{LEGEND_WIDTH:.1f}" '
            f'height="{height - 4:.1f}" rx="6" '
            f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" '
            f'opacity="0.88" />'
        )
    ]

    for i, skill in enumerate(active):
        row = i // FRUIT_KEY_COLS
        col = i % FRUIT_KEY_COLS
        cx = LEGEND_X + col * col_width + 18
        cy = top_y + FRUIT_KEY_PADDING + row * FRUIT_KEY_ROW_HEIGHT + 12
        color = _fruit_color(skill.skill)
        shape = _fruit_shape(skill.skill)
        body = FRUIT_SHAPE_BODIES[shape].format(fill=color)
        hx, hy, hr = FRUIT_SHAPE_HIGHLIGHTS[shape]
        parts.append(
            f'<g class="fruit-key-icon" '
            f'transform="translate({cx:.1f},{cy:.1f}) '
            f'scale({FRUIT_KEY_ICON_SCALE})">'
            f'{body}'
            f'<circle cx="{hx}" cy="{hy}" r="{hr}" '
            f'fill="white" opacity="0.35" />'
            f'</g>'
        )
        text_x = cx + 10
        label = _escape_xml(skill.skill)
        calls = 'call' if skill.count == 1 else 'calls'
        parts.append(
            f'<text x="{text_x:.1f}" y="{cy + 4:.1f}" '
            f'font-family="Georgia, serif" '
            f'font-size="{LEGEND_DESC_SIZE}" '
            f'fill="#2f3b23">'
            f'<tspan font-weight="bold">{label}</tspan>'
            f' ({skill.count} {calls})</text>'
        )

    parts.append('</g>')
    return ''.join(parts)


def render_svg(garden: GardenData) -> str:
    total_sessions = sum(day_ring.sessions for day_ring in garden.rings)
    base_half_width = _trunk_half_width(total_sessions)
    flower_count = _cache_efficiency_flower_count(
        garden.cache_read_tokens, garden.cache_write_tokens
    )

    bush_footprints = _bush_footprints(garden.tools)
    trunk_title = _title(f'Trunk — {total_sessions} total sessions')
    sun_x, sun_y = _sun_position(garden.total_tokens)
    sun_title = _title(f'Sun — {garden.total_tokens:,} tokens (all-in)')

    body = (
        _render_stars(
            _saturated_nightness(garden.nightness),
            title=_night_title(garden.nightness, garden.hour_counts),
        )
        + f'<g class="sun">{sun_title}'
        + _wind_group('ccg-bob', 'sun')
        + _render_sky_body(
            sun_x,
            sun_y,
            _sun_radius(garden.total_tokens),
            garden.nightness,
            garden.vitality,
        )
        + '</g></g>'
        + _render_clouds(garden.model_efforts)
        + _render_birds(
            garden.birds,
            garden.cartoon_since,
            (sun_x, sun_y, _sun_radius(garden.total_tokens)),
        )
        + f'<g class="trunk-group">{trunk_title}'
        f'{_render_trunk(base_half_width)}</g>'
        + _render_rings(garden.rings, base_half_width)
        + _render_branches_and_leaves(garden.branches, base_half_width)
        + _render_fruit_on_branches(
            garden.skills, garden.branches, base_half_width
        )
        # Sunflowers go down before the bushes so their stalks are rooted
        # behind the shrubbery rather than standing in front of it.
        + _render_sunflowers(garden.branches)
        + _render_bushes(garden.tools)
        + _render_flowers_on_bushes(
            flower_count,
            bush_footprints,
            garden.cache_read_tokens,
            garden.cache_write_tokens,
        )
        # Weather goes over the garden but under the legend, and the
        # night veil goes over the rain -- rain lit brighter than the
        # sky it falls out of reads as a rendering bug.
        + (
            _render_rain(
                _rain_opacity(garden.vitality),
                title=_rain_title(garden.vitality),
            )
            + _render_storm(_storm_opacity(garden.vitality))
            if _rain_intensity(garden.vitality) > 0
            else ''
        )
        + _render_night_veil(garden.nightness)
        + _render_legend(
            with_birds=bool(garden.birds),
            with_night=garden.nightness > 0,
            with_seasons=garden.vitality < 1.0,
            with_rain=_rain_intensity(garden.vitality) > 0,
            with_fruit=bool(garden.skills),
        )
        + _render_fruit_key(garden.skills, LEGEND_BAND_BOTTOM)
        + _render_tap_tooltip(
            LEGEND_BAND_BOTTOM + _fruit_key_height(garden.skills)
        )
    )

    total_height = LEGEND_BAND_BOTTOM + _fruit_key_height(garden.skills)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {total_height:.1f}" '
        f'width="{VIEWBOX_WIDTH}" height="{total_height:.1f}">'
        f'{_render_defs(vitality=garden.vitality)}'
        f'{_wind_style()}'
        f'{_render_background()}'
        f'{body}'
        f'</svg>'
    )


# --- timeline (growth-over-time) rendering -----------------------------
#
# Renders the same tree, but with every shape's `d` (or opacity/stroke-
# width) driven by a native SMIL <animate> that replays real day-by-day
# cumulative history from the sqlite db: the trunk widens, branches
# lengthen, and canopy blobs swell exactly in step with the sessions that
# actually happened on each day, while rings and leaves step into view on
# the calendar day they were earned. The base (non-animated) attribute on
# every element is always the final, fully-grown value, so a viewer with
# no SMIL support just sees the finished tree instead of nothing.


def _timeline_duration(day_count: float) -> float:
    """Seconds of replay for a timeline `day_count` frame-weights long.

    Takes a weight rather than a count so the dwell dormant frames get
    (see `_frame_weights`) buys extra runtime instead of being taken out
    of the working days' share.
    """
    return min(
        max(day_count * TIMELINE_PER_DAY_SECONDS, TIMELINE_MIN_DURATION_S),
        TIMELINE_MAX_DURATION_S,
    )


def _key_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


# How much longer a dormant frame is held than a working one. A lapse
# only exists in the timelapse as the frames `data.py` inserts for it, and
# at an even cadence those go by faster than the weather they carry reads
# -- the rain arrives and is gone before the eye finds it. Dwelling on
# them buys the lapse the time it actually took, without spending frames.
DORMANT_FRAME_DWELL = 2.5


# The frame you come back on gets a dwell of its own. Without it the
# garden spends seconds drying out and then snaps green again between two
# ordinary days, which reads as a glitch rather than as a recovery: the
# way out of a lapse has to take about as long as the way in.
RECOVERY_FRAME_DWELL = 2.0
# Extra frame-time per unit of weather change. Sky, rain and sun cover
# the whole canvas, so a day that swings one of them from nothing to full
# repaints the entire picture -- at an ordinary day's pace that lands as a
# slam, however smoothly it is interpolated. Rather than damp the change
# (the day really was a night shift, or really was the day you came back)
# the frame simply gets the time the change needs.
WEATHER_SWING_DWELL = 3.5


def _weather_load(nightness: float, vitality: float) -> float:
    """Total canvas-wide weather on one frame, for pacing purposes.

    Deliberately a sum of the three full-bleed channels rather than any
    one of them: what makes a transition jarring is how much of the
    picture it repaints, and darkness, rain and a smothered sun all
    repaint the same sky.
    """
    return (
        _saturated_nightness(nightness)
        + _rain_opacity(vitality)
        + (1.0 - _sun_storm_opacity(vitality))
    )


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
    """Frame times with the dormant frames held longer than the rest.

    Days you worked all get the same slice; a day with no sessions is a
    day `data.py` inserted to stand for silence, so it gets `DORMANT_
    FRAME_DWELL` of one. The seed day carries no interval of its own, so
    a frame's weight is the time spent *arriving* at it.
    """
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


# Ease-in-out, for the channels that sit still and then swing: weather
# and season hold one value for days and then move, so a linear segment
# starts and stops with a visible corner. Geometry is deliberately left
# linear -- growth moves on nearly every frame, and easing each day
# individually would turn steady growth into a pulse.
EASE_IN_OUT_SPLINE = '0.42 0 0.58 1'


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
) -> str:
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
) -> str:
    return (
        f'<animateTransform attributeName="transform" '
        f'type="{transform_type}" dur="{duration:.3f}s" '
        f'begin="0s" fill="freeze" calcMode="linear" '
        f'keyTimes="{";".join(f"{t:.4f}" for t in key_times)}" '
        f'values="{";".join(values)}" />'
    )


def _trunk_path_d(base_half_width: float) -> str:
    top_half_width = base_half_width * TRUNK_TOP_TAPER
    cx = TRUNK_CENTER_X
    lean = base_half_width * 0.1
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    top_shoulder_y = TRUNK_TOP_Y + top_half_width * 0.5
    dome_y = TRUNK_TOP_Y - top_half_width * 0.35
    left_ctrl_x = cx - (base_half_width + top_half_width) / 2 - lean
    right_ctrl_x = cx + (base_half_width + top_half_width) / 2 + lean
    return (
        f'M {cx - base_half_width:.2f},{GROUND_Y} '
        f'Q {left_ctrl_x:.2f},{mid_y:.2f} '
        f'{cx - top_half_width:.2f},{top_shoulder_y:.2f} '
        f'Q {cx:.2f},{dome_y:.2f} '
        f'{cx + top_half_width:.2f},{top_shoulder_y:.2f} '
        f'Q {right_ctrl_x:.2f},{mid_y:.2f} '
        f'{cx + base_half_width:.2f},{GROUND_Y} '
        f'Z'
    )


def _bark_stripe_d(
    base_half_width: float,
    top_half_width: float,
    x_offset: float,
    jitter: float,
) -> str:
    cx = TRUNK_CENTER_X
    mid_y = (GROUND_Y + TRUNK_TOP_Y) / 2
    top_x = cx + x_offset * top_half_width
    base_x = cx + x_offset * base_half_width
    return (
        f'M{base_x:.2f},{GROUND_Y - 8} '
        f'Q{(base_x + top_x) / 2 + jitter:.2f},{mid_y:.2f} '
        f'{top_x:.2f},{TRUNK_TOP_Y + 10}'
    )


def _outline_widths(
    base_half_width_by_day: list[float], width: float
) -> list[str]:
    """Per-day stroke widths that vanish on days the trunk has no width."""
    return [
        f'{width if half_width > 0 else 0.0:.2f}'
        for half_width in base_half_width_by_day
    ]


def _render_timeline_trunk(
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    d_values = [_trunk_path_d(width) for width in base_half_width_by_day]
    animate = _animate_tag('d', d_values, key_times, duration)
    # The outline has to fade in with the trunk: a zero-width trunk is a
    # degenerate path, and stroking it would draw a hairline the full
    # height of a tree that hasn't sprouted yet. (Blanking the `d` would
    # hide it too, but an empty path can't interpolate, which turns the
    # whole trunk's growth into a discrete step-per-day snap.)
    stroke_animate = _animate_tag(
        'stroke-width',
        _outline_widths(base_half_width_by_day, 1.5),
        key_times,
        duration,
    )
    trunk = (
        f'<path class="trunk" d="{d_values[-1]}" fill="url(#trunkGradient)" '
        f'stroke="#3a2412" stroke-width="1.5" stroke-linejoin="round">'
        f'{animate}{stroke_animate}</path>'
    )
    bark = _render_timeline_bark(base_half_width_by_day, key_times, duration)
    return trunk + bark


def _render_timeline_bark(
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    rng = random.Random('ccgarden-bark')
    elements = []
    for x_offset in (-0.32, 0.4):
        jitter = rng.uniform(-2, 2)
        d_values = [
            _bark_stripe_d(width, width * TRUNK_TOP_TAPER, x_offset, jitter)
            for width in base_half_width_by_day
        ]
        animate = _animate_tag('d', d_values, key_times, duration)
        stroke_animate = _animate_tag(
            'stroke-width',
            _outline_widths(base_half_width_by_day, 1.0),
            key_times,
            duration,
        )
        elements.append(
            f'<path d="{d_values[-1]}" fill="none" stroke="#3a2412" '
            f'stroke-width="1" opacity="0.22">{animate}{stroke_animate}</path>'
        )
    return ''.join(elements)


def _render_timeline_rings(
    timeline: GardenTimeline,
    final_base_half_width: float,
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    """The day rings, drawn at the trunk's final width and scaled down.

    A ring has to be as wide as the trunk it sits in *that day*, or the
    day it first appears it juts out either side of a sapling. Since
    `_half_width_at` is linear in the trunk's base width, every ring's
    width is the same fraction of the trunk on any given day -- so one
    horizontal scale around the trunk's centre, on the group, fits them
    all. That keeps this O(days) rather than the O(days squared) an
    animated `d` per ring would cost, which on a long history is
    megabytes of path data.
    """
    day_count = len(timeline.days)
    if day_count == 0 or final_base_half_width <= 0:
        return ''
    elements = []
    for index, sessions in enumerate(timeline.daily_sessions):
        # A day with no sessions grew no ring -- notably the synthetic
        # day 0 the timeline starts from.
        if sessions <= 0:
            continue
        y = GROUND_Y - (index + 1) / (day_count + 1) * TRUNK_HEIGHT
        half_width = _half_width_at(y, final_base_half_width) * 0.85
        cx = TRUNK_CENTER_X
        bow = half_width * 0.1
        target_width = _ring_stroke_width(sessions)
        d = (
            f'M {cx - half_width:.2f},{y:.2f} '
            f'Q {cx:.2f},{y - bow:.2f} {cx + half_width:.2f},{y:.2f}'
        )
        width_values = [
            f'{target_width:.3f}' if i >= index else '0'
            for i in range(day_count)
        ]
        animate = _animate_tag(
            'stroke-width', width_values, key_times, duration
        )
        title = _title(
            f'{_format_day(timeline.days[index])} — {sessions} sessions'
        )
        elements.append(
            f'<path class="ring" d="{d}" fill="none" stroke="#3a2412" '
            f'stroke-width="{target_width:.3f}" stroke-linecap="round" '
            f'opacity="0.22">{title}{animate}</path>'
        )
    if not elements:
        return ''
    cx = TRUNK_CENTER_X
    scale_values = [
        f'{width / final_base_half_width:.4f} 1'
        for width in base_half_width_by_day
    ]
    scale = _animate_transform_tag('scale', scale_values, key_times, duration)
    # translate out, scale, translate back: `animateTransform` replaces the
    # whole transform of the element it sits on, so the pivot has to live
    # on groups of its own.
    return (
        f'<g transform="translate({cx:.2f},0)"><g>{scale}'
        f'<g transform="translate({-cx:.2f},0)">'
        + ''.join(elements)
        + '</g></g></g>'
    )


def _render_timeline_crown(
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    cx = TRUNK_CENTER_X
    d_values = []
    for width in base_half_width_by_day:
        top_half_width = width * TRUNK_TOP_TAPER
        cy = TRUNK_TOP_Y - top_half_width * 0.2
        # The 22.0 floor is the crown's size once it exists; a trunk that
        # hasn't sprouted yet carries no crown at all.
        radius = max(width * 1.15, 22.0) if width > 0 else 0.0
        d_values.append(
            _blob_path(cx, cy, radius, random.Random('ccgarden-crown'))
        )
    animate = _animate_tag('d', d_values, key_times, duration)
    return (
        f'<path class="canopy" d="{d_values[-1]}" fill="url(#canopyGradient)" '
        f'opacity="0.9">{animate}</path>'
    )


def _render_timeline_branches_and_leaves(
    timeline: GardenTimeline,
    final_base_half_width: float,
    base_half_width_by_day: list[float],
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.branch_order:
        return ''

    vitality = timeline.daily_vitality or [1.0] * len(timeline.days)
    elements = [
        _render_timeline_crown(base_half_width_by_day, key_times, duration)
    ]
    # Limbs are apportioned from the *final* totals, so the timelapse and
    # the static garden build the same skeleton -- the last frame of one is
    # the other.
    limbs = _plan_limbs(
        [
            (repo, float(timeline.branch_days[repo][-1].lines_added))
            for repo in timeline.branch_order
        ]
    )
    count = len(limbs)
    for index, limb in enumerate(limbs):
        repo = limb.repo
        placement = _branch_placement(
            index, count, limb.key, final_base_half_width
        )
        origin_x, origin_y, side = (
            placement.origin_x,
            placement.origin_y,
            placement.side,
        )
        bow_factor = random.Random(f'{limb.key}:curve').random()

        repo_days = timeline.branch_days[repo]
        days = [_limb_share_of(day, limb) for day in repo_days]
        final_lines_added = days[-1].lines_added
        final_tokens = days[-1].output_tokens + days[-1].input_tokens
        final_length = _branch_length(final_lines_added)
        final_width = _branch_width(final_tokens)

        collar_rng_seed = f'{limb.key}:collar'
        d_values = []
        outline_d_values = []
        collar_d_values = []
        day_vectors: list[tuple[float, float]] = []
        for day_stat in days:
            if day_stat.sessions == 0:
                d_values.append(
                    _render_branch_shape(
                        origin_x,
                        origin_y,
                        origin_x,
                        origin_y,
                        base_width=0.0,
                        tip_width=0.0,
                        bow=0.0,
                    )
                )
                outline_d_values.append(
                    _render_branch_outline(
                        origin_x,
                        origin_y,
                        origin_x,
                        origin_y,
                        base_width=0.0,
                        tip_width=0.0,
                        bow=0.0,
                    )
                )
                collar_d_values.append(
                    _blob_path(
                        origin_x,
                        origin_y,
                        0.01,
                        random.Random(collar_rng_seed),
                        points=7,
                        jitter=0.3,
                    )
                )
                day_vectors.append((0.0, 0.0))
                continue
            # Grown as a share of the *final* length/width, not the same
            # absolute-lines_added formula re-evaluated per day -- that
            # formula saturates at BRANCH_LENGTH_MAX almost immediately
            # for a single big-diff day, which made the branch (and every
            # leaf anchored to its tip) jump straight to its final size on
            # day one instead of visibly growing across the days after.
            length_fraction = (
                min(day_stat.lines_added / final_lines_added, 1.0)
                if final_lines_added
                else 1.0
            )
            day_tokens = day_stat.output_tokens + day_stat.input_tokens
            width_fraction = (
                min(day_tokens / final_tokens, 1.0) if final_tokens else 1.0
            )
            length = (
                BRANCH_LENGTH_MIN
                + (final_length - BRANCH_LENGTH_MIN) * length_fraction
            )
            # `length` is the day's grown length, so the droop baked into
            # `_branch_endpoint` deepens over the timelapse: a branch sags
            # as it puts on foliage.
            end_x, end_y = _branch_endpoint(
                origin_x,
                origin_y,
                length,
                side,
                placement.spread_index,
                angle_jitter=placement.angle_jitter,
            )
            base_width = (
                BRANCH_WIDTH_MIN
                + (final_width - BRANCH_WIDTH_MIN) * width_fraction
            )
            bow = _branch_bow(length, side, bow_factor)
            root_overlap = base_width * 0.9
            d_values.append(
                _render_branch_shape(
                    origin_x,
                    origin_y,
                    end_x,
                    end_y,
                    base_width=base_width,
                    tip_width=BRANCH_TIP_WIDTH,
                    bow=bow,
                    root_overlap=root_overlap,
                )
            )
            outline_d_values.append(
                _render_branch_outline(
                    origin_x,
                    origin_y,
                    end_x,
                    end_y,
                    base_width=base_width,
                    tip_width=BRANCH_TIP_WIDTH,
                    bow=bow,
                    root_overlap=root_overlap,
                )
            )
            collar_d_values.append(
                _blob_path(
                    origin_x,
                    origin_y,
                    max(base_width * 2.2, 6.0),
                    random.Random(collar_rng_seed),
                    points=7,
                    jitter=0.3,
                )
            )
            day_vectors.append((end_x - origin_x, end_y - origin_y))

        animate = _animate_tag('d', d_values, key_times, duration)
        outline_animate = _animate_tag(
            'd', outline_d_values, key_times, duration
        )
        collar_animate = _animate_tag(
            'd', collar_d_values, key_times, duration
        )
        day_labels = _branch_day_labels(repo, repo_days)
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        collar = (
            f'<path class="branch-collar" d="{collar_d_values[-1]}" '
            f'fill="url(#trunkGradient)" opacity="0.9" '
            f'filter="url(#softBlur)">{collar_animate}</path>'
        )
        branch_path = (
            f'<path class="branch" data-repo="{repo}" d="{d_values[-1]}" '
            f'fill="url(#trunkGradient)" opacity="0.95">{animate}</path>'
            f'<path d="{outline_d_values[-1]}" fill="none" '
            f'stroke="#3a2412" stroke-width="0.75" stroke-linecap="round" '
            f'opacity="0.95">{outline_animate}</path>'
        )
        leaves = _render_timeline_leaves(
            limb.key,
            days,
            origin_x,
            origin_y,
            day_vectors,
            final_length=final_length,
            key_times=key_times,
            duration=duration,
            vitality=vitality,
        )
        elements.append(
            f'<g class="repo-group" {tt}>{title}'
            + _wind_group('ccg-sway-limb', limb.key, (origin_x, origin_y))
            + f'{collar}{branch_path}{leaves}</g></g>'
        )
    return ''.join(elements)


def _branch_day_labels(repo: str, days: list[RepoBranchDay]) -> list[str]:
    """One tooltip line per day for a repo's branch."""
    labels = []
    for day_stat in days:
        day_tokens = day_stat.output_tokens + day_stat.input_tokens
        avg_turns = (
            day_stat.prompts / day_stat.sessions if day_stat.sessions else 0.0
        )
        labels.append(
            f'{repo} — {day_stat.sessions} sessions, '
            f'+{day_stat.lines_added:,}/-{day_stat.lines_removed:,} '
            f'lines, {day_tokens:,} tokens, '
            f'{avg_turns:.1f} turns/session'
        )
    return labels


def _render_timeline_leaves(  # noqa: PLR0915
    seed: str,
    days: list[RepoBranchDay],
    origin_x: float,
    origin_y: float,
    day_vectors: list[tuple[float, float]],
    *,
    final_length: float,
    key_times: list[float],
    duration: float,
    vitality: list[float],
) -> str:
    # A branch's direction is fixed once chosen (only its length grows day
    # to day), so the unit vectors from the *final* vector describe every
    # day's branch equally well.
    final_dx, final_dy = day_vectors[-1]
    final_length = math.hypot(final_dx, final_dy) or final_length or 1.0
    ux, uy = final_dx / final_length, final_dy / final_length
    px, py = -uy, ux

    day_count = len(days)
    leaf_count = days[-1].sessions * LEAVES_PER_SESSION
    if leaf_count == 0:
        return ''

    final_day = days[-1]
    avg_turns = (
        final_day.prompts / final_day.sessions if final_day.sessions else 0.0
    )
    size_multiplier = _leaf_size_multiplier(avg_turns)

    elements = []
    has_canopy = leaf_count >= CANOPY_MIN_LEAVES
    day_canopy_radius = [
        _canopy_radius(day_stat.sessions * LEAVES_PER_SESSION)
        if day_stat.sessions * LEAVES_PER_SESSION >= CANOPY_MIN_LEAVES
        else 0.0
        for day_stat in days
    ]
    blob_relative_radii = (
        _foliage_blob_relative_radii(final_length) if has_canopy else []
    )

    if has_canopy:
        for fraction in _foliage_blob_fractions(final_length):
            girth = _foliage_girth_fraction(fraction)
            shadow_values = []
            main_values = []
            for day_index, (dx, dy) in enumerate(day_vectors):
                cx = origin_x + fraction * dx
                cy = origin_y + fraction * dy
                blob_radius = day_canopy_radius[day_index] * (
                    0.35 + 0.65 * girth
                )
                shadow_values.append(
                    _blob_path(
                        cx + blob_radius * 0.18,
                        cy + blob_radius * 0.22,
                        blob_radius * 0.92,
                        random.Random(f'{seed}:{fraction:.3f}:shadow'),
                    )
                )
                main_values.append(
                    _blob_path(
                        cx,
                        cy,
                        blob_radius,
                        random.Random(f'{seed}:{fraction:.3f}:canopy'),
                    )
                )
            shadow_animate = _animate_tag(
                'd', shadow_values, key_times, duration
            )
            main_animate = _animate_tag('d', main_values, key_times, duration)
            elements.append(
                f'<path class="canopy" d="{shadow_values[-1]}" '
                f'fill="#2f5f2f" opacity="0.3" '
                f'filter="url(#softBlur)">{shadow_animate}</path>'
            )
            elements.append(
                f'<path class="canopy" d="{main_values[-1]}" '
                f'fill="url(#canopyGradient)" opacity="0.9">'
                f'{main_animate}</path>'
            )

    rng = random.Random(f'{seed}:leaves')
    for leaf_index in range(leaf_count):
        if has_canopy:
            t, relative_radius, r_frac, blob_angle = _leaf_placement(
                rng, blob_relative_radii
            )
        else:
            t = rng.uniform(FOLIAGE_START_FRACTION, FOLIAGE_TIP_OVERHANG)
            blob_angle = rng.uniform(0.0, 2 * math.pi)
        radius = (
            max(LEAF_RADIUS + rng.uniform(-1.5, 2.5), 2.5) * size_multiplier
        )
        angle = rng.uniform(0, 360)
        color_index = rng.randrange(len(LEAF_COLORS))

        # Track the branch's position every day, not just on the day this
        # leaf appears -- otherwise the leaf fades in already sitting at its
        # (eventual) resting spot while the branch under it is still
        # visibly mid-growth, instead of riding the tip out with it.
        positions = []
        for day_index, (dx, dy) in enumerate(day_vectors):
            cx = origin_x + t * dx
            cy = origin_y + t * dy
            if has_canopy:
                perp_offset, along_offset = _leaf_offset(
                    relative_radius,
                    r_frac,
                    blob_angle,
                    day_canopy_radius[day_index],
                )
            else:
                scatter_r = LEAF_SCATTER_RADIUS * 0.4
                perp_offset = scatter_r * math.cos(blob_angle)
                along_offset = scatter_r * math.sin(blob_angle)
            positions.append(
                (
                    cx + px * perp_offset + ux * along_offset,
                    cy + py * perp_offset + uy * along_offset,
                )
            )

        final_x, final_y = positions[-1]
        translate_values = [f'{x:.1f},{y:.1f}' for x, y in positions]
        translate_animate = _animate_transform_tag(
            'translate', translate_values, key_times, duration
        )

        birth_index = next(
            (
                i
                for i, day_stat in enumerate(days)
                if day_stat.sessions * LEAVES_PER_SESSION > leaf_index
            ),
            day_count - 1,
        )
        # Combined with the leaf path's own opacity, this both fades the
        # leaf in on the day it was earned and thins the canopy out as
        # the garden goes dormant.
        opacity_values = [
            f'{_leaf_opacity(vitality[i]) / LEAF_OPACITY_LIVING:.3f}'
            if i >= birth_index
            else '0'
            for i in range(day_count)
        ]
        opacity_animate = _animate_tag(
            'opacity', opacity_values, key_times, duration
        )
        elements.append(
            f'<g class="leaf" '
            f'transform="translate({final_x:.1f},{final_y:.1f})">'
            f'{translate_animate}'
            f'<g transform="rotate({angle:.1f}) scale({radius:.2f})" '
            f'opacity="1">'
            f'<path d="{LEAF_SHAPE_D}" '
            f'fill="url(#{LEAF_PAINT_ID}{color_index})" '
            f'opacity="{LEAF_OPACITY_LIVING}" />'
            f'<path d="{LEAF_VEIN_D}" stroke="#2f5f2f" stroke-width="0.12" '
            f'opacity="0.5" />'
            f'{opacity_animate}'
            f'</g>'
            f'</g>'
        )
    return ''.join(elements)


def _sun_day_values(
    days_tokens: list[int],
    final_tokens: int,
    key_times: list[float],
) -> list[tuple[float, float, float]]:
    """Per-frame (x, y, radius) for the sun.

    Position and size are deliberately on different clocks. *Both* `x` and
    `y` come from `key_times` -- the fraction of the replay elapsed -- so
    the sun travels one straight, constant-speed path from where it rises
    to where it ends up, and a lapse cannot bend or stall it. Only the
    radius is on the data, as a share of the sun's final size (not the
    absolute-tokens formula re-evaluated per day; see the identical
    reasoning in `_render_timeline_branches_and_leaves`).

    Keying the height to tokens instead was the subtler half of the sun
    freezing through a storm: the sweep kept going but the climb stopped,
    so the sun changed direction exactly when everything else stopped.
    Tokens still decide how high it gets -- they set the far end of the
    path, not the pace along it.
    """
    _, final_y = _sun_position(final_tokens)
    final_radius = _sun_radius(final_tokens)
    values = []
    for day_tokens, progress in zip(days_tokens, key_times, strict=True):
        radius = _grown_size(
            day_tokens, final_tokens, SUN_RADIUS_MIN, final_radius
        )
        x = _sun_sweep_x(progress, final_radius)
        y = SUN_Y_START + (final_y - SUN_Y_START) * progress
        values.append((x, y, radius))
    return values


def _render_timeline_sun(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    cumulative = timeline.cumulative_total_tokens
    final_tokens = cumulative[-1] if cumulative else 0
    day_tokens = cumulative or [final_tokens] * len(key_times)
    day_values = _sun_day_values(day_tokens, final_tokens, key_times)
    final_x, final_y, final_radius = day_values[-1]

    translate_values = [f'{x:.2f},{y:.2f}' for x, y, _ in day_values]
    scale_values = [f'{r / final_radius:.4f}' for _, _, r in day_values]
    translate_animate = _animate_transform_tag(
        'translate', translate_values, key_times, duration
    )
    scale_animate = _animate_transform_tag(
        'scale', scale_values, key_times, duration
    )
    day_labels = [f'Sun — {tokens:,} tokens (all-in)' for tokens in day_tokens]
    title = _title(day_labels[-1])
    tt = _tt_attr(day_labels)
    vitality = timeline.daily_vitality or [1.0] * len(day_tokens)
    nightness = timeline.daily_nightness or [0.0] * len(day_tokens)
    opacities = [
        _sky_body_opacities(night, life)
        for night, life in zip(nightness, vitality, strict=True)
    ]
    sun_animate = _animate_tag(
        'opacity',
        [f'{sun:.3f}' for sun, _ in opacities],
        key_times,
        duration,
        smooth=True,
    )
    moon_animate = _animate_tag(
        'opacity',
        [f'{moon:.3f}' for _, moon in opacities],
        key_times,
        duration,
        smooth=True,
    )
    body = _render_sky_body(
        0,
        0,
        final_radius,
        nightness[-1],
        vitality[-1],
        sun_animate=sun_animate,
        moon_animate=moon_animate,
    )
    return (
        f'<g class="sun" {tt}'
        f' transform="translate({final_x:.1f},{final_y:.1f})">'
        f'{title}{translate_animate}'
        + _wind_group('ccg-bob', 'sun')
        + f'<g transform="scale(1)">{scale_animate}{body}</g>'
        f'</g></g>'
    )


def _render_timeline_clouds(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.model_effort_order:
        return ''

    positions = _cloud_positions(len(timeline.model_effort_order))
    elements = []
    for (slot_x, slot_y), model in zip(
        positions, timeline.model_effort_order, strict=True
    ):
        days = timeline.model_effort_days[model]
        final_tokens = days[-1].output_tokens + days[-1].input_tokens
        final_radius = _cloud_radius(final_tokens)
        # Clamped against the *final* radius: the slot is fixed for the whole
        # animation while the cloud scales up into it, so fitting at full size
        # means it fits on every frame.
        cx, cy = _clamp_cloud_position(slot_x, slot_y, final_radius)

        # Grown as a share of the model's *final* radius, not the same
        # absolute-tokens formula re-evaluated per day -- see the identical
        # reasoning in `_render_timeline_branches_and_leaves`.
        scale_values = []
        for day_stat in days:
            day_tokens = day_stat.output_tokens + day_stat.input_tokens
            day_radius = _grown_size(
                day_tokens, final_tokens, CLOUD_RADIUS_MIN, final_radius
            )
            scale_values.append(f'{day_radius / final_radius:.4f}')

        animate = _animate_transform_tag(
            'scale', scale_values, key_times, duration
        )
        gradient_id = _cloud_gradient_id(_effort_from_cloud_label(model))
        puffs = ''.join(
            f'<path d="{d}" fill="url(#{gradient_id})" opacity="0.88" />'
            for d in _cloud_puffs_d(final_radius, model)
        )
        day_labels = [
            f'{model} — {day_stat.output_tokens + day_stat.input_tokens:,} '
            f'tokens'
            for day_stat in days
        ]
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        elements.append(
            f'<g class="cloud" {tt} '
            f'transform="translate({cx:.1f},{cy:.1f})">{title}'
            + _wind_group('ccg-drift', model)
            + f'<g transform="scale(1)">{animate}{puffs}</g>'
            f'</g></g>'
        )
    return ''.join(elements)


def _render_timeline_birds(timeline: GardenTimeline) -> str:
    """The flock, at full size for the whole replay but drifting as it flies.

    Everything else in the timeline replays day by day, but cartoon only
    reports a single since-window snapshot -- there are no per-day frames
    to animate, and faking a growth curve for them would be inventing
    history the tool never recorded. So the birds never grow; they just
    drift on their own loop (see `_bird_drift`), with their window spelled
    out in the tooltip.
    """
    # Keyed to the *final* sun, which climbs during the replay: a flock
    # placed clear of where the sun ends up is clear of it throughout.
    final_tokens = (
        timeline.cumulative_total_tokens[-1]
        if timeline.cumulative_total_tokens
        else 0
    )
    sun_x, sun_y = _sun_position(final_tokens)
    sun = (sun_x, sun_y, _sun_radius(final_tokens))

    flock = timeline.birds[:MAX_BIRDS]
    if not flock:
        return ''
    slots = _bird_slots(flock, sun)
    elements = []
    rules = []
    for index, (bird, (x, y, size)) in enumerate(
        zip(flock, slots, strict=True)
    ):
        dx, dy = _bird_drift(index, x, y, size, sun)
        rules.append(_bird_drift_rule(index, dx, dy))
        elements.append(
            f'<g class="bird">'
            f'{_title(_bird_label(bird, timeline.cartoon_since))}'
            f'<g class="bird-drift bird-drift-{index}">'
            + _wind_group('ccg-flap', f'bird:{index}')
            + f'{_render_bird(x, y, size)}</g></g></g>'
        )
    style = _bird_drift_style(rules)
    return f'<g class="birds">{style}{"".join(elements)}</g>'


def _bush_day_radii(
    days: list[ToolUsageDay], final_radius: float
) -> list[float]:
    """Per-day bush radius, grown as a share of the tool's *final* radius.

    Not the same absolute-count formula re-evaluated per day -- see the
    identical reasoning in `_render_timeline_branches_and_leaves`.
    """
    final_count = days[-1].count
    return [
        _grown_size(day_stat.count, final_count, BUSH_RADIUS_MIN, final_radius)
        for day_stat in days
    ]


def _render_timeline_bushes(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    if not timeline.tool_order:
        return ''

    tool_order = timeline.tool_order[:MAX_BUSHES]
    xs = _bush_x_positions(len(tool_order))
    elements = []
    for x, tool in zip(xs, tool_order, strict=True):
        days = timeline.tool_days[tool]
        final_radius = _bush_radius(days[-1].count)
        day_radii = _bush_day_radii(days, final_radius)

        scale_values = [f'{r / final_radius:.4f}' for r in day_radii]
        animate = _animate_transform_tag(
            'scale', scale_values, key_times, duration
        )
        puffs = ''.join(
            f'<path d="{d}" fill="url(#bushGradient)" opacity="0.94" />'
            for d in _bush_puffs_d(final_radius, tool)
        )
        day_labels = [
            f'{tool} — used {day_stat.count:,} times' for day_stat in days
        ]
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        elements.append(
            f'<g class="bush" {tt} '
            f'transform="translate({x:.1f},{GROUND_Y})">{title}'
            + _wind_group('ccg-sway-bush', tool)
            + f'<g transform="scale(1)">{animate}{puffs}</g>'
            f'</g></g>'
        )
    return ''.join(elements)


def _render_timeline_flowers_on_bushes(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    """Flowers riding each bush's growth, fading in as cache efficiency grows.

    Mirrors `_render_timeline_leaves`: a flower's height above the ground
    tracks its bush's radius *on that day*, not the bush's eventual size,
    so it doesn't start already floating above a bush that hasn't grown
    that tall yet. It also fades in on the day the running cache-read/
    write ratio first reaches its index, the same birth_index approach
    leaves use for a count that grows over the timeline.
    """
    final_flower_count = _cache_efficiency_flower_count(
        timeline.cache_read_tokens, timeline.cache_write_tokens
    )
    tool_order = timeline.tool_order[:MAX_BUSHES]
    day_count = len(timeline.days)
    if (
        final_flower_count <= 0
        or not tool_order
        or len(timeline.cumulative_cache_read) != day_count
        or len(timeline.cumulative_cache_write) != day_count
    ):
        return ''

    xs = _bush_x_positions(len(tool_order))
    bush_day_radii = []
    for tool in tool_order:
        days = timeline.tool_days[tool]
        final_radius = _bush_radius(days[-1].count)
        bush_day_radii.append(_bush_day_radii(days, final_radius))

    day_flower_counts = [
        _cache_efficiency_flower_count(read, write)
        for read, write in zip(
            timeline.cumulative_cache_read,
            timeline.cumulative_cache_write,
            strict=True,
        )
    ]

    day_labels = [
        f'Cache efficiency — {read:,} cache reads per {write:,} cache writes'
        for read, write in zip(
            timeline.cumulative_cache_read,
            timeline.cumulative_cache_write,
            strict=True,
        )
    ]
    title = _title(day_labels[-1])
    tt = _tt_attr(day_labels)
    rng = random.Random('ccgarden-flowers')
    elements = []
    for index in range(final_flower_count):
        bush_index = index % len(tool_order)
        bush_x = xs[bush_index]
        day_radii = bush_day_radii[bush_index]

        angle = rng.uniform(0, 2 * math.pi)
        dist_frac = rng.uniform(0.0, 0.7)
        size = FLOWER_RADIUS * rng.uniform(0.6, 0.9)
        color = rng.choice(FLOWER_COLORS)

        positions = [
            (
                bush_x + day_radius * dist_frac * math.cos(angle),
                GROUND_Y
                - day_radius * 0.6
                + day_radius * dist_frac * math.sin(angle) * 0.6,
            )
            for day_radius in day_radii
        ]

        final_x, final_y = positions[-1]
        translate_values = [f'{x:.1f},{y:.1f}' for x, y in positions]
        translate_animate = _animate_transform_tag(
            'translate', translate_values, key_times, duration
        )

        birth_index = next(
            (i for i, count in enumerate(day_flower_counts) if count > index),
            day_count - 1,
        )
        opacity_values = [
            '1' if i >= birth_index else '0' for i in range(day_count)
        ]
        opacity_animate = _animate_tag(
            'opacity', opacity_values, key_times, duration
        )
        flower = _render_flower(0, 0, size, color, rng)
        elements.append(
            f'<g class="flower" '
            f'transform="translate({final_x:.1f},{final_y:.1f})" '
            f'opacity="1">'
            f'{translate_animate}{opacity_animate}{flower}'
            f'</g>'
        )
    return f'<g class="flowers" {tt}>{title}{"".join(elements)}</g>'


def _render_timeline_fruit(
    timeline: GardenTimeline,
    base_half_width: float,
    duration: float,
) -> str:
    """The whole crop, ripening together at the very end of the replay.

    Skill counts are cumulative like every other shape, but fruit is the
    one worth *not* walking day by day: it reads as the harvest the
    finished garden is carrying rather than as something that grew, and
    day-by-day ripening put full-grown fruit over a tree still rising out
    of the soil. One shared fade also costs a single `<animate>` instead
    of one per fruit.
    """
    if not timeline.skill_order or not timeline.branch_order:
        return ''

    final_skills = [
        SkillFruit(skill=skill, count=timeline.skill_days[skill][-1].count)
        for skill in timeline.skill_order
    ]
    final_branches = [
        RepoBranch(
            repo=repo,
            sessions=days[-1].sessions,
            lines_added=days[-1].lines_added,
            lines_removed=days[-1].lines_removed,
            output_tokens=days[-1].output_tokens,
            input_tokens=days[-1].input_tokens,
            cost=days[-1].cost,
            prompts=days[-1].prompts,
        )
        for repo, days in (
            (repo, timeline.branch_days[repo])
            for repo in timeline.branch_order
        )
    ]

    crop = _render_fruit_on_branches(
        final_skills, final_branches, base_half_width
    )
    if not crop:
        return ''

    ripen = _animate_tag(
        'opacity',
        ['0', '0', '1'],
        [0.0, 1.0 - FRUIT_RIPEN_FRACTION, 1.0],
        duration,
        smooth=True,
    )
    return f'<g class="fruit-crop" opacity="0">{ripen}{crop}</g>'


def _render_timeline_sunflowers(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
) -> str:
    """Sunflowers growing out of the soil as each repo's prompts accumulate.

    Scaled from the ground-contact point like `_render_timeline_bushes`,
    so a stalk rises out of the earth rather than inflating in place, and
    keyed to each day's share of the repo's *final* prompt count for the
    same reason as `_bush_day_radii`.
    """
    repos = _sunflower_repos(
        [
            RepoBranch(
                repo=repo,
                sessions=0,
                lines_added=0,
                lines_removed=0,
                output_tokens=0,
                input_tokens=0,
                cost=0.0,
                prompts=timeline.branch_days[repo][-1].prompts,
            )
            for repo in timeline.branch_order
        ]
    )
    if not repos:
        return ''

    xs = _sunflower_x_positions(len(repos))
    elements = []
    for x, branch in zip(xs, repos, strict=True):
        days = timeline.branch_days[branch.repo]
        final_height = _sunflower_height(branch.prompts)
        final_prompts = days[-1].prompts
        scale_values = []
        for day_stat in days:
            day_height = _grown_size(
                day_stat.prompts,
                final_prompts,
                SUNFLOWER_HEIGHT_MIN,
                final_height,
            )
            scale_values.append(f'{day_height / final_height:.4f}')
        animate = _animate_transform_tag(
            'scale', scale_values, key_times, duration
        )
        plant = _render_sunflower(0, 0, final_height, branch.repo)
        day_labels = [
            f'{branch.repo} — {day_stat.prompts:,} prompts'
            for day_stat in days
        ]
        title = _title(day_labels[-1])
        tt = _tt_attr(day_labels)
        elements.append(
            f'<g class="sunflower" {tt} '
            f'transform="translate({x:.1f},{GROUND_Y})">{title}'
            + _wind_group('ccg-sway-stalk', branch.repo)
            + f'<g transform="scale(1)">{animate}{plant}</g>'
            f'</g></g>'
        )
    return ''.join(elements)


def _timeline_final_garden(timeline: GardenTimeline) -> GardenData:
    """The tree's final state, for the fallback when there's <2 days."""
    rings = [
        DayRing(day=day, sessions=sessions, lines_added=0, lines_removed=0)
        for day, sessions in zip(
            timeline.days, timeline.daily_sessions, strict=True
        )
    ]
    branches = [
        RepoBranch(
            repo=repo,
            sessions=timeline.branch_days[repo][-1].sessions,
            lines_added=timeline.branch_days[repo][-1].lines_added,
            lines_removed=timeline.branch_days[repo][-1].lines_removed,
            output_tokens=timeline.branch_days[repo][-1].output_tokens,
            input_tokens=timeline.branch_days[repo][-1].input_tokens,
            cost=timeline.branch_days[repo][-1].cost,
            prompts=timeline.branch_days[repo][-1].prompts,
        )
        for repo in timeline.branch_order
    ]
    model_efforts = [
        ModelCloud(
            model=label,
            output_tokens=timeline.model_effort_days[label][-1].output_tokens,
            input_tokens=timeline.model_effort_days[label][-1].input_tokens,
        )
        for label in timeline.model_effort_order
    ]
    tools = [
        ToolBush(tool=tool, count=timeline.tool_days[tool][-1].count)
        for tool in timeline.tool_order
    ]
    skills = [
        SkillFruit(skill=s, count=timeline.skill_days[s][-1].count)
        for s in timeline.skill_order
    ]
    return GardenData(
        rings=rings,
        branches=branches,
        cache_read_tokens=timeline.cache_read_tokens,
        cache_write_tokens=timeline.cache_write_tokens,
        model_efforts=model_efforts,
        tools=tools,
        skills=skills,
        total_tokens=(
            timeline.cumulative_total_tokens[-1]
            if timeline.cumulative_total_tokens
            else 0
        ),
    )


def _render_tap_tooltip(
    view_height: float,
    key_times: list[float] | None = None,
    duration: float = 0.0,
) -> str:
    """A tap-activated stand-in for `<title>`, which never fires on touch.

    Browsers only surface a native `<title>` on hover, so on a phone every
    shape in the garden is silent. This draws the same text as real SVG
    content instead, and it has to live inside this document rather than
    the host page because the site embeds the garden through `<object>`,
    which nothing in the page's own DOM can draw over.

    On the timeline, a shape's stats keep growing after it's drawn (a
    branch mid-animation is not yet at its final session count), so a
    static `<title>` set once to the final day is wrong for most of the
    replay. Elements that grow carry a `data-tt` attribute instead (see
    `_tt_attr`) -- one label per day -- and this reads the SMIL clock via
    `getCurrentTime()` to pick the label matching what's on screen right
    now, for both the tap gesture and (since native `<title>` can't do
    this at all) mouse hover.
    """
    key_times = key_times or [0.0]
    box = (
        f'<rect id="ccgarden-tooltip-box" x="0" y="0" width="10" '
        f'height="{TOOLTIP_HEIGHT:.1f}" rx="6" fill="#fbfbf3" '
        f'stroke="#3a2412" stroke-width="1" opacity="0.95" />'
    )
    text = (
        f'<text id="ccgarden-tooltip-text" x="{TOOLTIP_PAD:.1f}" '
        f'y="{TOOLTIP_PAD + TOOLTIP_FONT_SIZE * 0.8:.1f}" '
        f'font-family="Georgia, serif" '
        f'font-size="{TOOLTIP_FONT_SIZE:.1f}" fill="#2f3b23"></text>'
    )
    group = (
        f'<g id="ccgarden-tooltip" opacity="0" '
        f'style="pointer-events:none;">{box}{text}</g>'
    )
    script = (
        '<script><![CDATA[\n'
        '(function () {\n'
        '  var svg = document.documentElement;\n'
        '  var group = document.getElementById("ccgarden-tooltip");\n'
        '  var box = document.getElementById("ccgarden-tooltip-box");\n'
        '  var text = document.getElementById("ccgarden-tooltip-text");\n'
        f'  var pad = {TOOLTIP_PAD:.1f};\n'
        f'  var boxHeight = {TOOLTIP_HEIGHT:.1f};\n'
        f'  var viewWidth = {VIEWBOX_WIDTH:.1f};\n'
        f'  var viewHeight = {view_height:.1f};\n'
        f'  var keyTimes = [{",".join(f"{t:.4f}" for t in key_times)}];\n'
        f'  var duration = {duration:.4f};\n'
        '  function currentDayIndex() {\n'
        '    var t = svg.getCurrentTime();\n'
        '    if (duration <= 0 || t >= duration) {\n'
        '      return keyTimes.length - 1;\n'
        '    }\n'
        '    var frac = t / duration;\n'
        '    var idx = 0;\n'
        '    for (var i = 0; i < keyTimes.length; i++) {\n'
        '      if (keyTimes[i] <= frac + 1e-6) { idx = i; } else { break; }\n'
        '    }\n'
        '    return idx;\n'
        '  }\n'
        '  function findTooltip(node) {\n'
        '    while (node && node !== svg) {\n'
        '      if (node.id === "ccgarden-scrubber") { return null; }\n'
        '      var days = node.getAttribute\n'
        '        ? node.getAttribute("data-tt")\n'
        '        : null;\n'
        '      if (days) {\n'
        '        var list = JSON.parse(days);\n'
        '        var idx = Math.min(currentDayIndex(), list.length - 1);\n'
        '        return { label: list[idx], dynamic: true };\n'
        '      }\n'
        '      var kids = node.childNodes || [];\n'
        '      for (var i = 0; i < kids.length; i++) {\n'
        '        if (kids[i].nodeName === "title") {\n'
        '          return { label: kids[i].textContent, dynamic: false };\n'
        '        }\n'
        '      }\n'
        '      node = node.parentNode;\n'
        '    }\n'
        '    return null;\n'
        '  }\n'
        '  function toUserSpace(event) {\n'
        '    var ctm = svg.getScreenCTM();\n'
        '    if (!ctm) { return null; }\n'
        '    var point = svg.createSVGPoint();\n'
        '    point.x = event.clientX;\n'
        '    point.y = event.clientY;\n'
        '    return point.matrixTransform(ctm.inverse());\n'
        '  }\n'
        '  function hide() { group.setAttribute("opacity", "0"); }\n'
        '  function show(label, at) {\n'
        '    text.textContent = label;\n'
        '    var width = text.getComputedTextLength() + pad * 2;\n'
        '    box.setAttribute("width", width.toFixed(1));\n'
        '    var x = at.x - width / 2;\n'
        '    var y = at.y - boxHeight - 14;\n'
        '    if (x < 4) { x = 4; }\n'
        '    if (x + width > viewWidth - 4) {\n'
        '      x = viewWidth - 4 - width;\n'
        '    }\n'
        '    if (y < 4) { y = at.y + 18; }\n'
        '    if (y + boxHeight > viewHeight - 4) {\n'
        '      y = viewHeight - 4 - boxHeight;\n'
        '    }\n'
        '    group.setAttribute(\n'
        '      "transform",\n'
        '      "translate(" + x.toFixed(1) + "," + y.toFixed(1) + ")"\n'
        '    );\n'
        '    group.setAttribute("opacity", "1");\n'
        '  }\n'
        '  var dynamicNodes = svg.querySelectorAll("[data-tt]");\n'
        '  for (var d = 0; d < dynamicNodes.length; d++) {\n'
        '    var dKids = dynamicNodes[d].childNodes;\n'
        '    for (var k = dKids.length - 1; k >= 0; k--) {\n'
        '      if (dKids[k].nodeName === "title") {\n'
        '        dynamicNodes[d].removeChild(dKids[k]);\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '  svg.addEventListener("pointerdown", function (event) {\n'
        '    if (event.pointerType === "mouse") { return; }\n'
        '    var found = findTooltip(event.target);\n'
        '    var at = found ? toUserSpace(event) : null;\n'
        '    if (at) { show(found.label, at); } else { hide(); }\n'
        '  });\n'
        '  svg.addEventListener("pointermove", function (event) {\n'
        '    if (event.pointerType !== "mouse") { return; }\n'
        '    var found = findTooltip(event.target);\n'
        '    if (found && found.dynamic) {\n'
        '      show(found.label, toUserSpace(event));\n'
        '    } else {\n'
        '      hide();\n'
        '    }\n'
        '  });\n'
        '  // A touch pointer "leaves" the moment the finger lifts, which\n'
        '  // would undo the tap we just handled -- only a cursor exit.\n'
        '  svg.addEventListener("pointerleave", function (event) {\n'
        '    if (event.pointerType !== "mouse") { return; }\n'
        '    hide();\n'
        '  });\n'
        '})();\n'
        ']]></script>'
    )
    return group + script


def _render_scrubber(
    timeline: GardenTimeline,
    key_times: list[float],
    duration: float,
    scrubber_top: float = LEGEND_BAND_BOTTOM,
) -> str:
    """A ground-strip slider that seeks the timelapse's own SMIL clock.

    Every `<animate>`/`<animateTransform>` the timeline renders shares this
    same `key_times`/`duration` pair (see `render_timeline_svg`), so a single
    document-time value fully determines every element's frame -- scrubbing
    is just `svg.pauseAnimations()` once, then `svg.setCurrentTime(t)` per
    drag, with no separate day-state to keep in sync. Stays hidden and
    non-interactive until the initial playthrough finishes, per the request
    to add the scrubber *after* the animation rather than replacing it.
    """
    day_count = len(timeline.days)
    day_labels = [_format_day(day) for day in timeline.days]
    key_times_js = '[' + ','.join(f'{t:.4f}' for t in key_times) + ']'
    day_labels_js = (
        '[' + ','.join(f'"{_escape_xml(label)}"' for label in day_labels) + ']'
    )

    panel_x = LEGEND_X
    panel_width = LEGEND_WIDTH
    scrubber_y = scrubber_top + SCRUBBER_MARGIN
    ground_fill = (
        f'<rect x="0" y="{scrubber_top:.1f}" '
        f'width="{VIEWBOX_WIDTH:.1f}" '
        f'height="{SCRUBBER_TOTAL_HEIGHT:.1f}" fill="#3f7a3f" />'
    )
    panel = (
        f'<rect x="{panel_x:.1f}" y="{scrubber_y:.1f}" '
        f'width="{panel_width:.1f}" height="{SCRUBBER_HEIGHT:.1f}" rx="8" '
        f'fill="#fbfbf3" stroke="#3a2412" stroke-width="1" opacity="0.88" />'
    )
    foreign = (
        f'<foreignObject x="{panel_x + 14:.1f}" y="{scrubber_y + 5:.1f}" '
        f'width="{panel_width - 28:.1f}" height="{SCRUBBER_HEIGHT - 10:.1f}">'
        '<div xmlns="http://www.w3.org/1999/xhtml" '
        'style="font-family: Georgia, serif; color: #2f3b23; '
        'display: flex; align-items: center; gap: 10px; height: 100%;">'
        '<span style="font-size: 9px; opacity: 0.75; white-space: nowrap;">'
        'Time travel</span>'
        '<input id="ccgarden-scrubber-input" type="range" '
        f'min="0" max="{day_count - 1}" value="{day_count - 1}" step="1" '
        'style="flex: 1;" />'
        '<span id="ccgarden-scrubber-label" '
        'style="font-size: 11px; font-weight: bold; white-space: nowrap;">'
        f'{_escape_xml(day_labels[-1])}</span>'
        '</div>'
        '</foreignObject>'
    )
    group = (
        f'<g id="ccgarden-scrubber" '
        f'style="opacity:0;pointer-events:none;transition:opacity 0.6s ease;">'
        f'{panel}{foreign}</g>'
    )
    script = (
        '<script><![CDATA[\n'
        '(function () {\n'
        '  var svg = document.documentElement;\n'
        '  var group = document.getElementById("ccgarden-scrubber");\n'
        '  var input = document.getElementById("ccgarden-scrubber-input");\n'
        '  var label = document.getElementById("ccgarden-scrubber-label");\n'
        f'  var duration = {duration:.4f};\n'
        f'  var keyTimes = {key_times_js};\n'
        f'  var dayLabels = {day_labels_js};\n'
        '  var paused = false;\n'
        '  function reveal() {\n'
        '    group.style.opacity = "1";\n'
        '    group.style.pointerEvents = "auto";\n'
        '  }\n'
        '  function seek(dayIndex) {\n'
        '    if (!paused) { svg.pauseAnimations(); paused = true; }\n'
        '    svg.setCurrentTime(keyTimes[dayIndex] * duration);\n'
        '    label.textContent = dayLabels[dayIndex];\n'
        '  }\n'
        '  input.addEventListener("input", function () {\n'
        '    seek(parseInt(input.value, 10));\n'
        '  });\n'
        '  window.setTimeout(reveal, duration * 1000 + 150);\n'
        '})();\n'
        ']]></script>'
    )
    return ground_fill + group + script


def render_timeline_svg(timeline: GardenTimeline) -> str:
    """Render the tree with its real day-by-day history replayed as growth.

    Every shape's geometry is driven by a SMIL <animate> keyed to the
    actual cumulative stats on each day in `timeline.days`, so the tree
    grows exactly the way the underlying repos actually grew. Falls back
    to the plain (non-animated) render when there's fewer than two days
    of history to replay.
    """
    day_count = len(timeline.days)
    if day_count < TIMELINE_MIN_DAYS_TO_ANIMATE:
        return render_svg(_timeline_final_garden(timeline))

    daily_sessions = timeline.daily_sessions or [1] * day_count
    weather = (timeline.daily_nightness, timeline.daily_vitality)
    duration = _timeline_duration(
        1.0 + sum(_frame_weights(daily_sessions, *weather))
    )
    key_times = _weighted_key_times(daily_sessions, *weather)
    timeline_skills = [
        SkillFruit(
            skill=s,
            count=timeline.skill_days[s][-1].count,
        )
        for s in timeline.skill_order
        if timeline.skill_days[s][-1].count >= FRUIT_MIN_CALLS
    ]
    fk_height = _fruit_key_height(timeline_skills)

    base_half_width_by_day = _trunk_half_widths_for_timeline(
        timeline.cumulative_sessions
    )
    final_base_half_width = base_half_width_by_day[-1]
    trunk_day_labels = [
        f'Trunk — {sessions} total sessions'
        for sessions in timeline.cumulative_sessions
    ]
    trunk_title = _title(trunk_day_labels[-1])
    trunk_tt = _tt_attr(trunk_day_labels)

    body = (
        _render_timeline_night(timeline, key_times, duration, veil=False)
        + _render_timeline_sun(timeline, key_times, duration)
        + _render_timeline_clouds(timeline, key_times, duration)
        + _render_timeline_birds(timeline)
        + _render_tree_growth(
            f'<g class="trunk-group" {trunk_tt}>{trunk_title}'
            + _render_timeline_trunk(
                base_half_width_by_day, key_times, duration
            )
            + '</g>'
            + _render_timeline_rings(
                timeline,
                final_base_half_width,
                base_half_width_by_day,
                key_times,
                duration,
            )
            + _render_timeline_branches_and_leaves(
                timeline,
                final_base_half_width,
                base_half_width_by_day,
                key_times,
                duration,
            )
            # Inside the growth group, not beside it: fruit hangs in the
            # canopy, so it has to rise with the tree like anything else
            # drawn into it.
            + _render_timeline_fruit(
                timeline, final_base_half_width, duration
            ),
            _tree_growth_scales(timeline.cumulative_sessions),
            key_times,
            duration,
        )
        # Behind the bushes -- see the same ordering note in `render_svg`.
        + _render_timeline_sunflowers(timeline, key_times, duration)
        + _render_timeline_bushes(timeline, key_times, duration)
        + _render_timeline_flowers_on_bushes(timeline, key_times, duration)
        # Over the garden but under the legend -- as in `render_svg`.
        + _render_timeline_rain(timeline, key_times, duration)
        + _render_timeline_storm(timeline, key_times, duration)
        + _render_timeline_night(timeline, key_times, duration, veil=True)
        + _render_legend(
            with_birds=bool(timeline.birds),
            with_night=any(timeline.daily_nightness),
            with_seasons=any(value < 1.0 for value in timeline.daily_vitality),
            with_rain=any(
                _rain_intensity(value) > 0 for value in timeline.daily_vitality
            ),
            with_fruit=bool(timeline.skill_order),
        )
        + _render_fruit_key(timeline_skills, LEGEND_BAND_BOTTOM)
        + _render_scrubber(
            timeline,
            key_times,
            duration,
            scrubber_top=LEGEND_BAND_BOTTOM + fk_height,
        )
        + _render_tap_tooltip(
            TIMELINE_VIEWBOX_HEIGHT + fk_height,
            key_times,
            duration,
        )
    )

    leaf_animations, ground_animations, canopy_animations = _season_animations(
        timeline.daily_vitality or [1.0] * day_count, key_times, duration
    )
    tl_height = TIMELINE_VIEWBOX_HEIGHT + fk_height
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {VIEWBOX_WIDTH} {tl_height:.1f}" '
        f'width="{VIEWBOX_WIDTH}" height="{tl_height:.1f}">'
        f'{
            _render_defs(leaf_animations, ground_animations, canopy_animations)
        }'
        f'{_wind_style()}'
        f'{_render_background()}'
        f'{body}'
        f'</svg>'
    )
