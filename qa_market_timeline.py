"""QA for Sprint 15 Commit 1 market timeline artifacts."""
from __future__ import annotations

import json
from pathlib import Path

SNAPSHOTS = Path("data/market/market_snapshots.json")
TIMELINE = Path("data/market/market_timeline.json")
CLOSING = Path("data/market/closing_lines.json")
SUMMARY = Path("data/dashboard/wnba_market_timeline_summary.json")


def load(path: Path):
    if not path.exists():
        raise SystemExit(f"Missing output: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    snapshots = load(SNAPSHOTS).get("records", [])
    timelines = load(TIMELINE).get("markets", [])
    closings = load(CLOSING).get("closing_lines", [])
    summary = load(SUMMARY)

    assert summary["status"] in {"READY", "STANDBY"}
    assert summary["deduplicated_snapshots"] == len(snapshots)
    assert summary["markets_tracked"] == len(timelines)
    assert summary["closing_lines"] == len(closings)
    assert set(summary["books"]).issubset({"draftkings", "fanduel"})

    seen = set()
    for row in snapshots:
        required = {
            "market_id", "event_id", "snapshot_time_utc", "bookmaker", "market",
            "selection", "american_price", "implied_probability", "outcome_key",
        }
        missing = required - row.keys()
        assert not missing, f"Snapshot missing fields: {missing}"
        assert row["bookmaker"] in {"draftkings", "fanduel"}
        key = (row["market_id"], row["snapshot_time_utc"], row.get("point"), row.get("american_price"))
        assert key not in seen, f"Duplicate compact snapshot: {key}"
        seen.add(key)

    for market in timelines:
        observations = market.get("observations", [])
        assert observations, f"Empty timeline: {market.get('market_id')}"
        assert market["observation_count"] == len(observations)
        stamps = [x["snapshot_time_utc"] for x in observations]
        assert stamps == sorted(stamps), f"Non-chronological timeline: {market['market_id']}"
        for previous, current in zip(observations, observations[1:]):
            assert (previous.get("point"), previous.get("american_price")) != (
                current.get("point"), current.get("american_price")
            ), f"Unchanged duplicate in timeline: {market['market_id']}"

    print(json.dumps({
        "status": "PASS",
        "snapshots": len(snapshots),
        "markets": len(timelines),
        "closing_lines": len(closings),
    }, indent=2))


if __name__ == "__main__":
    main()
