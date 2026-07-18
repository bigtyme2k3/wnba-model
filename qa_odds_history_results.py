"""Acceptance tests for historical result matching and outcome grading."""
from __future__ import annotations

import csv
import sqlite3
import tempfile
from pathlib import Path

import wnba_odds_history_results_importer as importer
import wnba_odds_history_outcome_engine as outcomes
import wnba_odds_history_warehouse as warehouse


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "test.sqlite"
        raw = root / "raw"
        raw.mkdir()
        con = warehouse.connect(db)
        con.execute(
            """INSERT INTO games(game_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,updated_at_utc)
            VALUES('odds-1','basketball_wnba','2024-07-02T23:00:00Z','2024-07-02','New York Liberty','Minnesota Lynx','now')"""
        )
        con.execute(
            """INSERT INTO snapshots(requested_at_utc,snapshot_time_utc,created_at_utc)
            VALUES('2024-07-02T22:00:00Z','2024-07-02T21:55:00Z','now')"""
        )
        sid = con.execute("SELECT snapshot_id FROM snapshots").fetchone()[0]
        for book in ("draftkings", "fanduel"):
            con.execute(
                """INSERT INTO odds(snapshot_id,game_id,bookmaker_key,home_spread,total)
                VALUES(?,?,?,?,?)""", (sid, 'odds-1', book, -4.5, 160.5)
            )
        con.commit()

        path = raw / "wehoop_team_box_2024.csv"
        fields = ["game_id", "game_date", "team_name", "home_away", "points"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({"game_id": "espn-1", "game_date": "2024-07-02", "team_name": "New York Liberty", "home_away": "home", "points": "82"})
            writer.writerow({"game_id": "espn-1", "game_date": "2024-07-02", "team_name": "Minnesota Lynx", "home_away": "away", "points": "75"})

        import_report = importer.attach(db, raw)
        assert import_report["summary"]["matched_this_run"] == 1
        check = sqlite3.connect(db).execute("SELECT completed,home_score,away_score FROM games").fetchone()
        assert check == (1, 82, 75)

        outcome_report = outcomes.build(db)
        assert outcome_report["summary"]["completed_games"] == 1
        assert outcome_report["summary"]["game_book_outcome_rows"] == 2
        assert outcome_report["by_bookmaker"]["draftkings"]["favorites"]["covers"] == 1
        assert outcome_report["by_bookmaker"]["fanduel"]["totals"]["under"] == 1
        print("PASS historical results importer and outcome engine")


if __name__ == "__main__":
    main()
