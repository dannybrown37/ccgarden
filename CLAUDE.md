# ccgarden

Renders local Claude Code session history as an animated SVG garden.
Zero runtime dependencies — stdlib + sqlite3 only. Python >= 3.12, `uv`.

## Pipeline

`~/.claude/projects/**/*.jsonl` → `claude_stats.py` → `~/.claude/ccstats.db`
→ `data.py` → `render.py` → `~/.claude/ccgarden.svg`

Three modules, each a stage; keep them in that order of dependency
(`render` never touches sqlite, `data` never parses JSONL).

- `src/ccgarden/claude_stats.py` — parses transcripts, prints the terminal
  report, and writes daily snapshots into sqlite. Entry point `ccstats`.
- `src/ccgarden/data.py` — reads the db back out into `GardenData` (single
  frame) and `GardenTimeline` (per-day cumulative frames). Pure dataclasses.
- `src/ccgarden/render.py` — turns those dataclasses into SVG strings.
  `render_svg` for a static garden, `render_timeline_svg` for the animated
  timelapse (what the CLI actually ships).
- `src/ccgarden/__init__.py` — the `ccgarden` CLI: record → load → render →
  write → open in browser (WSL-aware via `explorer.exe`).

## Data model

sqlite tables are all day-keyed and idempotent per day (`INSERT OR REPLACE`
on a `day` primary key), so re-running any day is safe and backfills via
`ccstats --record --since ... --until ...` are re-runnable:
`daily_totals`, `daily_repo_usage`, `daily_model_usage`,
`daily_model_effort_usage`, `daily_tool_usage`, `daily_effort_usage`,
`daily_hour_usage`.

`data.py` loads raw per-day rows then runs a `_cumulative_*` pass — for
every *shape*, the renderer receives cumulative values, since the garden
only ever grows. Adding a new shape means: new daily table → `_load_*` +
`_load_*_days` + `_cumulative_*_days` → new field on
`GardenData`/`GardenTimeline` → a `_render_*` and `_render_timeline_*`
pair → legend icon + entry.

Two channels are deliberately **not** cumulative, because they describe
the day rather than the total: `daily_nightness` (share of that day's
prompts typed after 22:00, which drives the sky) and `daily_vitality`
(decays with days since you last worked, which drives both the season and
the rain — `_rain_intensity` inverts vitality back into days away, so the
thresholds are in days rather than in a raw vitality number). Vitality
is the only value in the whole pipeline that can fall. Because the db only
holds days you actually worked, `_with_dormant_days` inserts all-zero
frames across every gap ≥ 4 days so a lapse has somewhere to be visible —
one per missed day up to `DORMANT_FRAMES_MAX`, then sampled across the
span, so a sabbatical costs no more frames than a fortnight but still walks
the calendar. Those frames carry no rows in any other table, so every
cumulative shape correctly holds its value there instead of growing. The
renderer then holds each of them `DORMANT_FRAME_DWELL`× longer than a
working day, and the day you come back on `RECOVERY_FRAME_DWELL`× longer
(`_weighted_key_times`, and `_timeline_duration` takes that total weight
rather than a day count so the dwell adds runtime instead of stealing it)
— frames are the timelapse's unit of time, so that's what gives a lapse
and its rain weight on screen, and going away and coming back have to
take comparable time or the recovery reads as a glitch.

New tables must be tolerated when absent — `daily_hour_usage` postdates the
first released schema, so its loaders check `_table_exists` and degrade to
"no opinion" rather than raising on an older db.

Seasonal colour is applied through **shared paints**, not per-element
fills: leaves reference `url(#leafPaint{n})` and the canopy uses
`canopyGradient`, so ten `stop-color` animations in `<defs>` recolour a
canopy of thousands of leaves. Never give a leaf its own colour animation.

## Rendering conventions

- SVG is built by string concatenation, not a DOM library. All user-derived
  text must go through `_escape_xml` / `_title`.
- Every visual dimension is driven by a module-level saturation constant
  (`*_SATURATION`) plus a min/max pair, so growth curves flatten instead of
  running off-canvas. Tune the constant, don't special-case the data.
- Animation is declarative SMIL (`_animate_tag`, `_animate_transform_tag`)
  over `_key_times` — no JS timers. The scrubber and tap-tooltip are the
  only inline-script parts. Pass `smooth=True` only for channels that sit
  still for days and then swing (rain, season, sky): those get eased
  `calcMode="spline"` segments, while geometry stays linear, since easing
  every day of steady growth turns it into a pulse.
- Idle motion (wind) is **CSS keyframes, never SMIL** — same compositor
  reason as the birds' drift. `_wind_style` emits every keyframe once and
  `_wind_group` opens a phase-shifted group per element; each one must
  carry `transform-origin` (with `transform-box: view-box`) so a limb
  hinges at the trunk and a sunflower at the soil. Never put a wind class
  on an element that already has a `transform` attribute or an
  `animateTransform` — CSS transform wins over both — always nest a new
  group. Wind runs on its own clock, so a finished, paused or scrubbed
  replay is still alive.
- Storm motion (`_render_storm_wind`: gusts, tumbling leaves, scud cloud)
  lives *inside* the rain group, which already animates its own per-day
  opacity: anything that should appear only during a lapse goes there
  rather than getting a second animation gated to the gap.
- A lapse freezes every cumulative shape by definition, so anything big
  enough to notice needs a *non-cumulative* channel to keep changing on —
  the sun, whose height is frozen with the token total, fades out behind
  the storm instead (`_sun_storm_opacity`). Idle wind is too slow to
  cover for that on its own: its periods are tens of seconds and a lapse
  is a few.
- The timeline starts on a synthetic empty day (`_with_seed_day`) and every
  shape is sized through `_grown_size`, which is zero — not the min — before
  a shape's first day of data, so the timelapse grows out of bare ground.
  Values animated as `d` must stay interpolable (a degenerate path, never an
  empty one) or SMIL falls back to discrete step-per-day snapping.
- Layout is deterministic given the data: positions come from seeded/derived
  jitter helpers, never `random` at render time, so the same db renders the
  same garden.
- Shapes stay off each other: clouds honor the tree keepout, birds check
  `_clear_of_sun`, bushes use `_bush_footprints`. Preserve those checks when
  moving things.
- The tree's skeleton is **limbs, not repos**. `_plan_limbs` apportions at
  least `MIN_LIMBS` limbs across the repos and keeps splitting the busiest
  past that until no limb carries more than `LIMB_MAX_SHARE` of the tree,
  and `_limb_share_of` cuts each repo's totals on cumulative boundaries so
  its limbs sum back to the repo exactly — leaf counts still equal
  `sessions * LEAVES_PER_SESSION`. Both renderers derive limbs from the
  *final* totals so the timelapse ends on the static tree. A repo that
  isn't split keeps `key == repo`, so a wide garden is unchanged. Anything
  seeded per-branch (placement, bow, collar, foliage) must seed off
  `limb.key`; anything user-facing (titles, `data-repo`) off the repo.

`cartoon` is an optional external binary. Every failure mode (missing,
non-zero exit, timeout, unparseable) must degrade to "no birds", never
an exception.

## Working here

```sh
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
uv run ccgarden --no-open     # regenerate without launching a browser
```

Pre-commit runs ruff-check, ruff-format, and pytest (via the `git-a-grip`
hook repo) plus gitleaks — commits fail on any of them, so run them first.

Style: ruff with a broad select set, line length 79, single quotes,
annotations required on non-test code (`ANN`). Tests relax `ANN`/`PLR2004`.
Private helpers are `_`-prefixed; the public surface is `main`,
`load_garden_*`, `render_*svg`, and `print_report`.

Tests mirror the modules (`tests/test_{claude_stats,data,render,cli}.py`)
and are pure-unit — they build dataclasses directly and assert on geometry
and on substrings of the emitted SVG. Follow that: no filesystem or db
fixtures beyond `tmp_path`, no golden-image comparison.

To eyeball a change, render to the scratchpad and screenshot it headless
(`google-chrome --headless --screenshot ... file://...`) rather than
diffing SVG text by hand.

## Release

Bump `version` in `pyproject.toml`, tag `v*`, push the tag — the
`Publish to PyPI` workflow builds with `uv build` and publishes via
trusted publishing.
