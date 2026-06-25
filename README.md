# WNBA Betting Model

Automated daily betting model covering spreads, totals, and player props.
Runs on GitHub Actions — no computer needed, works from any device.

## Setup (one time)

1. Fork this repo
2. Go to **Actions** tab → run **Bootstrap** workflow
3. Go to **Settings → Pages** → set Source to `main` branch, `/docs` folder
4. Your dashboard is live at `https://YOUR-USERNAME.github.io/wnba-model`

## Daily workflow (automatic)

Every morning at 9 AM ET, GitHub Actions:
- Scrapes stats from Basketball-Reference
- Scrapes lines from OddsShark
- Scrapes props from PrizePicks
- Scrapes scores from ESPN
- Runs all three models
- Updates the dashboard

## Models

| Model | Algorithm | Strong plays |
|-------|-----------|-------------|
| Spread | Ridge v2 (quality floor fix) | 81.5% ATS |
| Totals | Random Forest | 55.4% O/U |
| Props  | Ridge | 75.4% hit rate |

## Manual trigger

Actions tab → **WNBA Daily Pipeline** → Run workflow
