# Sprint 24.1 Best Bets Ledger

## Schema

The append-only ledger is stored at `data/history/best_bets_ledger.csv` and contains:

`snapshot_id`, `snapshot_time_utc`, `dashboard_version`, `model_version`, `slate_date`, `event_id`, `game`, `player_id`, `player_name`, `team`, `opponent`, `sportsbook`, `market`, `side`, `line`, `odds`, `projection`, `edge`, `evidence_score`, `confidence_tier`, `display_rank`, `correlation_group`, `supporting_books`, `archived_before_lock`, and `workflow_run_id`.

`data/history/best_bets_summary.json` records the latest archive operation, snapshot IDs, display ranks, workflow run, and status.

## Workflow

The production order is data collection, prediction generation, Best Bets generation, correlation filtering, Live Slate Intelligence, ledger archive, QA validation, and dashboard publication.

`archive_best_bets.py` reproduces the final dashboard shortlist after evidence scoring, hard deduplication, correlation-family reduction, player and game exposure caps, ranking, and live-slate removal. Only the final displayed card is written.

## Duplicate logic

The archive identity uses slate date, event ID, player ID, market, side, line, sportsbook, and odds. An identical snapshot is skipped. A changed line or changed odds creates a new immutable snapshot.

## Recovery

The CSV is append-only. Restore a damaged ledger from Git history, verify the header and snapshot IDs, then rerun `python archive_best_bets.py`. Existing snapshot IDs are skipped and eligible missing snapshots are appended.

## QA

The workflow fails when the ledger is missing, the schema is incomplete or reordered, a snapshot ID is duplicated, the active card has duplicate display ranks, a row is archived after lock, the dashboard markers do not match the production Best Bets pipeline, or the ledger cannot be parsed safely.

Run:

```bash
python archive_best_bets.py
python archive_best_bets.py --validate-only
```
