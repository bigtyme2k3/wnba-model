# Databallr Finals player feature snapshot (research only)

Source: user-provided databallr 2026 WNBA player Defense, Shooting and Creation exports for Atlanta Dream and Golden State Valkyries, regular season and playoffs. Joined on (team, season_type, player), with missing values preserved. Data snapshot recorded 2026-10-19; the exported tables do not establish a per-game historical as-of timestamp.

File: `data/research/wnba_v5_finals_joined_research_2026.csv`. 55 unique player/season rows, 48 defensive records, 48 shooting eFG records, 51 creation turnover records. No duplicate composite keys.

**Leakage restriction:** This snapshot must not be used to backtest Game 1 or other historical games; its 2026 playoff statistics incorporate games played by October 19. `backtest_eligible=False` is intentional. Only forward analysis after the snapshot date is permitted without earlier dated source snapshots.

**No production changes:** This file is research-only and is not an input to the V5 production prediction, grading, injury, sportsbook, or betting-decision pipelines. Do not infer a betting edge from these features alone. Missing player/category values remain missing rather than zero. Player on-court defensive rating is not an individual causal defensive effect.

Illustrative shooting eFG%: Rhyne Howard 51.6 regular vs 37.1 playoff; Gabby Williams 47.5 regular vs 51.2 playoff. The joined file permits systematic defensive-versus-offensive feature comparisons, but quantitative predictive lift needs dated forward observations and validation.
