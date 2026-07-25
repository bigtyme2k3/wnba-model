"""QA for Sprint 15 Commit 4 CLV intelligence."""
from __future__ import annotations

import json
from pathlib import Path

FILES = {
    "results": Path("data/market/clv_results.json"),
    "books": Path("data/market/sportsbook_clv.json"),
    "players": Path("data/market/player_clv.json"),
    "teams": Path("data/market/team_clv.json"),
    "markets": Path("data/market/market_clv.json"),
    "leaderboard": Path("data/market/clv_leaderboard.json"),
    "summary": Path("data/dashboard/wnba_clv_summary.json"),
}


def load(path: Path):
    if not path.exists():
        raise AssertionError(f"Missing output: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    payloads = {name: load(path) for name, path in FILES.items()}
    records = payloads["results"].get("records", [])
    summary = payloads["summary"]

    assert isinstance(records, list)
    assert summary["status"] in {"READY", "STANDBY"}
    assert summary["observations_analyzed"] == len(records)
    assert summary["markets_analyzed"] == len({r["market_id"] for r in records})

    seen = set()
    non_close = 0
    classes = {"POSITIVE", "NEGATIVE", "NEUTRAL"}
    for row in records:
        key = (row["market_id"], row["observation_index"])
        assert key not in seen, f"Duplicate CLV record: {key}"
        seen.add(key)
        assert row["clv_class"] in classes
        assert isinstance(row["is_closing_observation"], bool)
        if row["is_closing_observation"]:
            if row.get("point_clv") is not None:
                assert abs(float(row["point_clv"])) < 1e-8
            if row.get("implied_probability_clv") is not None:
                assert abs(float(row["implied_probability_clv"])) < 1e-8
        else:
            non_close += 1

    assert summary["non_closing_observations"] == non_close
    assert (
        summary["positive_clv_observations"]
        + summary["negative_clv_observations"]
        + summary["neutral_clv_observations"]
        == non_close
    )

    books = payloads["books"].get("sportsbooks", [])
    assert all(0 <= float(x["positive_clv_rate"]) <= 1 for x in books)
    assert {x["key"] for x in books}.issubset({"draftkings", "fanduel"})

    best = payloads["leaderboard"].get("best", [])
    worst = payloads["leaderboard"].get("worst", [])
    assert all(not x["is_closing_observation"] for x in best + worst)

    if records:
        assert summary["status"] == "READY"
    else:
        assert summary["status"] == "STANDBY"

    print(json.dumps({
        "status": "PASS",
        "markets": summary["markets_analyzed"],
        "observations": len(records),
        "non_closing": non_close,
        "positive": summary["positive_clv_observations"],
        "negative": summary["negative_clv_observations"],
        "sportsbooks": len(books),
    }, indent=2))


if __name__ == "__main__":
    main()
