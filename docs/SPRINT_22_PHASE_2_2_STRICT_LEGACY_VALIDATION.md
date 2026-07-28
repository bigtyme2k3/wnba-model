# Sprint 22 Phase 2.2 strict legacy validation

Historical backfill collection must not silently continue when a requested legacy player season cannot be converted into a usable table.

The compatibility entrypoint now validates every requested season after collection. A valid player file must exist, contain rows, include `game_id`, and include either `athlete_id` or `athlete_display_name`. The workflow removes stale generated files for the requested range before collection so an earlier malformed CSV cannot be mistaken for a successful season.

When validation fails, the workflow stops during collection and reports the season, file path, row count, and recovered columns. This preserves the 11-season QA requirement and provides the exact schema evidence needed for any remaining legacy mapping adjustment.
