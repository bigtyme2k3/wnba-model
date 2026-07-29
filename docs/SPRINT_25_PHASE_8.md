# Sprint 25 Phase 8 — Live Slate Intelligence

## Purpose

Keep the Best Bets card useful throughout the slate without recommending markets from games that have already started or finished.

## Behavior

- Removes completed, live, in-progress and already-started games from the Best Bets candidate pool.
- Uses game status fields when available and scheduled start timestamps as a fallback.
- Rebuilds the evidence-scored, correlation-aware shortlist from remaining pregame markets only.
- Displays remaining games, remaining props and active opportunities.
- Preserves player, matchup and hard-dedup exposure controls.
- Uses a slightly lower late-slate display threshold when two or fewer games remain, while still requiring positive projection edge and the same evidence-scoring penalties.

## Safety

- No model projections, probabilities, sportsbook prices or production recommendations are changed.
- This phase changes dashboard eligibility, ranking display and slate-state presentation only.
- In-game betting recommendations are not generated.
