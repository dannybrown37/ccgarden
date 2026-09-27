## v0.7.3 (2026-09-27)

### Fix

- add a top gate from the toolshed, have sprinklers look for empty dirt rather than intersect with plants

## v0.7.2 (2026-09-27)

### Fix

- improve tooltip for toolshed to show more info

## v0.7.1 (2026-09-27)

### Fix

- don't individually animate leaves on tree view

## v0.7.0 (2026-09-27)

### Feat

- add sprinklers to indicate recency worked

### Fix

- reduce weed onset days, remove rain barrel from legend

## v0.6.0 (2026-09-27)

### Feat

- continue wip, organize plants in a saner way
- continue wip on beatiful --plot option
- wip on plot
- phase 1 of render plot

### Fix

- don't hard-code species<->model/effort, just set a favorites order within category
- pricing in ccstats, tooltip appearance in legend
- show plant percentage in legend, hover in legend highlights only that plant, show start date in sessions counter
- more visual improvements to plot

## v0.5.2 (2026-09-17)

### Fix

- setup zizmor, version, other code quality improvements

## v0.5.1 (2026-09-17)

### Fix

- add non-timeline but still-animated web version of poster

## v0.5.0 (2026-09-15)

### Feat

- **plot**: add --style plot option for a top-down garden look. It's currently ugly but we shall work on that.

### Fix

- revert all --plot nonsense, it looked terrible. Add a --delete-repo flag to clean bad data
- don't animate plot (for now at least). Have timeline scrubber but fix to last day on render
- bed width in plot
- **plot**: 'plants' are now more lined up in each bed

## v0.4.0 (2026-09-12)

### Feat

- add --merge-repo flag, and --record flag to patch old records

## v0.3.5 (2026-09-12)

### Fix

- history now goes back longer than 30 days on ccstats, cartoon matches

## v0.3.4 (2026-09-12)

### Fix

- optimize animation by collapsing key frames and grouping opacity

## v0.3.3 (2026-08-21)

### Fix

- show a legend for fruit, min 5 calls for a tool to show up

## v0.3.2 (2026-08-21)

### Fix

- make fruit sway with tree

## v0.3.1 (2026-08-21)

### Fix

- (sort of) improve fruit implementation

## v0.3.0 (2026-08-17)

### Feat

- half-baked frut feature, need to enhance later

## v0.2.1 (2026-08-15)

### Fix

- add mypy to pre-commit

## v0.2.0 (2026-08-15)

### Feat

- add rain/storm/night/twinkling stars; all kinds of goodies. Attempt to smooth animation. Sun timing still needs much work
- add way more CLI options, add more qualitative indicators that aren't just more == growth

### Fix

- publish
- remove notional dollar figures from tooltips
- set up commitizen so that pypi gets latest versions
- rings grow with trunk, what a beautiful thing
- the legend
- smooth the sun/moon movement even more
- even better balance for single-repo work
- set minimum limbs to six so tree isn't ugly for one-repo'd people; set sky to dark for late-night prompts
- 6x4 legend -> 5x5 legend
- never count scratch directories
- start all items from zero
- start at day 0 rather than end of day 1
- reduce the V-shape of the tree by inverting the Y axis and putting lower branches on the bottom

## v0.1.0 (2026-08-02)
