# ALT Props Architecture Audit

## Purpose

Freeze the current ALT Props architecture before additional feature patching. The goal is to stop renderer-on-renderer changes from hiding data or allowing stale ALT datasets into a new dashboard.

## Current pipeline

1. `wnba_alt_market_warehouse.py`
   - Reads exact sportsbook alternate markets from `data/raw/alt_props_bookmakers_<date>.csv` or the `today` fallback.
   - Enriches exact thresholds with player game-log history.
   - Writes `data/{warehouse,dashboard}/wnba_alt_market_warehouse.json`.

2. `wnba_alt_streaks.py`
   - Reads exact ALT warehouse rows.
   - Also reads standard daily props and can append qualifying standard-prop streak rows.
   - Writes `data/{warehouse,dashboard}/wnba_alt_streaks.json`.

3. `wnba_alt_streak_confidence.py`
   - Adds score, grade, action, expected edge, risk and explanation fields to `wnba_alt_streaks.json`.

4. `wnba_alt_performance_tracker.py`
   - Freezes scored selections in the history archive.
   - Grades prior selections against verified player game logs.
   - Writes `data/{warehouse,dashboard}/wnba_alt_performance.json`.

5. `patch_dashboard_alt_props_table.py`
   - Reconstructs visible ALT ladders from `WNBA_CANONICAL_DAILY.props` in browser JavaScript.
   - Adds filters and sortable columns.

6. `patch_dashboard_alt_props_scores.py`
   - Loads scored rows from `wnba_alt_streaks.json`.
   - Attempts to match them to the already-rendered table.
   - Historically hid any visible row that had no score match.

7. `patch_dashboard_alt_props_performance_panel.py`
   - Wraps the ALT route/filter behavior again and appends historical performance.

8. `.github/workflows/deploy_wnba_dashboard.yml`
   - Scores/snapshots ALT rows before dashboard compilation.
   - Does not currently guarantee that the ALT warehouse and streak source were rebuilt for `$TARGET` immediately before scoring.

## Confirmed defects

### 1. Split source of truth

The current market table, score overlay and exact sportsbook ALT warehouse are separate datasets:

- visible table: `WNBA_CANONICAL_DAILY.props`
- scoring overlay: `wnba_alt_streaks.json`
- exact sportsbook ALT data: `wnba_alt_market_warehouse.json`

This makes row identity depend on browser-side reconciliation instead of one canonical record.

### 2. Destructive score overlay

A missing score match must not remove a valid sportsbook market. Scoring eligibility and current-market visibility are separate concerns.

### 3. Stale-data exposure

The deployment workflow may score an existing `wnba_alt_streaks.json` without proving its `target_date` equals the dashboard `$TARGET`.

### 4. Multiple runtime wrappers

The ALT table, score overlay and performance panel all wrap runtime functions. Their behavior is therefore order-sensitive.

### 5. Mixed semantics in the streak source

`wnba_alt_streaks.py` can combine exact alternate markets with qualifying standard-prop rows. Every row must carry an explicit market type and the UI must not silently present a standard line as an exact sportsbook alternate ladder.

## Current repository evidence

At the time of this audit, `data/dashboard/wnba_alt_streaks.json` is dated `2026-08-04` while the dashboard target is later. The current `data/dashboard/wnba_alt_market_warehouse.json` is also empty. These are data-pipeline defects, not table-layout defects.

## Locked repair architecture

The ALT Props tab should converge on one canonical current payload:

`data/dashboard/wnba_alt_props_current.json`

Each visible row should contain:

- target_date
- game
- player
- team
- opponent
- stat
- side
- alt_line
- line_type
- sportsbook
- odds
- available books/prices
- streak
- L5
- L10
- season
- average
- opponent rank
- model score
- grade
- action
- performance eligibility

## Invariants

- No synthetic ALT lines.
- No cross-book averaging of thresholds.
- No valid current market hidden because a score is missing.
- No stale ALT target date allowed into deployment.
- One owner for the current ALT table renderer.
- Performance history is freeze/append based; later model changes do not rewrite prior snapshots.
- The generated `docs/index.html` must be re-read and validated after every renderer change.

## Repair sequence

1. Stop the destructive behavior that hides unscored current markets.
2. Rebuild the ALT warehouse and ALT streak source for `$TARGET` before scoring.
3. Add a hard freshness gate for ALT source dates.
4. Build a canonical `wnba_alt_props_current.json` payload.
5. Point the table directly at that payload.
6. Fold score rendering into the table renderer and retire the browser reconciliation overlay.
7. Keep ALT Performance read-only and sourced from `wnba_alt_performance.json`.
8. Add final-artifact QA for freshness, row preservation, one renderer owner and correct route behavior.
