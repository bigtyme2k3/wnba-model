# WNBA Model Version 4 Roadmap

Version 4 moves the project from a dashboard-first prototype into a modular betting intelligence platform.

## Goal

Build one system that combines:

- Automated GitHub Actions
- WNBA daily schedule source of truth
- Multi-book odds and prop consensus
- Player props projections
- Spread and totals models
- Closing Line Value tracking
- Bankroll and risk allocation
- Feature importance and calibration
- Hyperparameter optimization
- Daily retraining
- Ensemble learning
- Expected value decision engine
- Clean dashboard views

## Architecture

```text
Source Registry
  -> Schedule Core
  -> Odds Source Manager
  -> Player Stats Warehouse
  -> Sportsbook Consensus
  -> Master Source Builder
  -> Projection / Matchup / Market Engines
  -> EV / Decision / Risk / Portfolio Engines
  -> Results / CLV / Self-Learning Engines
  -> Dashboard V4
```

## V4 module manifest

The source of truth for the Version 4 build is:

```text
config/v4_modules.json
```

The daily module status output is:

```text
data/dashboard/wnba_v4_status.json
```

## Build phases

### Phase 1 — Foundation

- Lock the official daily schedule as the source of truth.
- Keep odds, props, stats, and results as attached layers.
- Add Version 4 module manifest.
- Add V4 status engine.

### Phase 2 — Player Props Intelligence

- Separate props by game.
- Show over/under prices.
- Show last 5 stat boxes.
- Color stat boxes green/red based on whether the recommended side would have hit.
- Add hit rates and trend context.

### Phase 3 — Matchup Intelligence

- Pace adjustment.
- Defensive matchup by stat.
- Home/away splits.
- Rest and travel.
- Injury/usage impact.
- Blowout risk.

### Phase 4 — Projection Engine 2.0

Weighted blend:

```text
30% Last 5
20% Last 10
15% Season
10% Home/Away
10% Opponent Defense
10% Usage / Minutes
5% Rest / Fatigue
```

### Phase 5 — EV and Best Bets

- Convert projection edge and price into EV.
- Rank plays by confidence and value.
- Split into Elite / Strong / Lean / Pass.

### Phase 6 — Portfolio and Risk

- Bankroll-aware staking.
- Kelly cap.
- Correlation limits.
- Exposure caps by game, team, player, stat, and book.

### Phase 7 — Results and CLV

- Grade every pick.
- Track closing line value.
- Track model accuracy by market, stat, book, confidence tier, and edge range.

### Phase 8 — Self-Learning

- Store outcome history.
- Adjust weights safely.
- Flag weak features.
- Prepare calibration and hyperparameter tuning.

## Immediate next modules

1. Real last 5 / last 10 player game logs.
2. Real hit-rate calculations from historical boxscores.
3. True team mapping for player logos/abbreviations.
4. EV formula using sportsbook price.
5. Confidence tiers for Best Bets.
