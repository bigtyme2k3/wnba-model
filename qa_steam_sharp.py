"""QA for Sprint 15 Commit 3 steam and sharp movement intelligence."""
from __future__ import annotations

import json
from pathlib import Path

FILES = {
    "classifications": (Path("data/market/movement_classifications.json"), "classifications"),
    "steam": (Path("data/market/steam_alerts.json"), "alerts"),
    "sharp": (Path("data/market/sharp_movements.json"), "movements"),
    "consensus": (Path("data/market/consensus_movements.json"), "movements"),
    "signals": (Path("data/market/market_signals.json"), "signals"),
}
SUMMARY = Path("data/dashboard/wnba_steam_sharp_summary.json")
VALID = {"NORMAL", "SHARP", "STEAM", "BOOK_LEADER", "MARKET_CORRECTION", "LATE_MONEY", "POSSIBLE_INJURY"}


def load(path: Path) -> dict:
    if not path.exists():
        raise AssertionError(f"missing output: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"invalid JSON object: {path}"
    return payload


def main() -> None:
    payloads = {name: load(path) for name, (path, _) in FILES.items()}
    summary = load(SUMMARY)
    rows = payloads["classifications"].get("classifications", [])
    assert isinstance(rows, list)
    ids = [x.get("market_id") for x in rows]
    assert len(ids) == len(set(ids)), "duplicate classified market_id"
    for row in rows:
        assert row.get("classification") in VALID
        confidence = row.get("confidence")
        assert isinstance(confidence, (int, float)) and 0 <= confidence <= 100
        assert isinstance(row.get("reasons"), list) and row["reasons"]
        lag = row.get("movement_lag_minutes")
        assert lag is None or lag >= 0
        mbt = row.get("minutes_before_tip")
        assert mbt is None or isinstance(mbt, (int, float))
        if row.get("possible_injury"):
            assert row["classification"] == "POSSIBLE_INJURY"
            assert row.get("consensus_move") is True
    steam = payloads["steam"].get("alerts", [])
    assert all(x.get("classification") == "STEAM" for x in steam)
    sharp = payloads["sharp"].get("movements", [])
    assert all(x.get("classification") in {"SHARP", "POSSIBLE_INJURY"} for x in sharp)
    consensus = payloads["consensus"].get("movements", [])
    assert all(x.get("consensus_move") is True for x in consensus)
    signals = payloads["signals"].get("signals", [])
    event_ids = [x.get("event_id") for x in signals]
    assert len(event_ids) == len(set(event_ids)), "duplicate event signal"
    assert summary.get("markets_analyzed") == len(rows)
    assert summary.get("steam_alerts") == len(steam)
    assert summary.get("sharp_movements") == len(sharp)
    assert summary.get("consensus_movements") == len(consensus)
    assert summary.get("events_with_signals") == len(signals)
    expected = "READY" if rows else "STANDBY"
    assert summary.get("status") == expected
    print(json.dumps({
        "status": "PASS",
        "markets": len(rows),
        "signals": summary.get("markets_with_signals", 0),
        "steam": len(steam),
        "sharp": len(sharp),
        "consensus": len(consensus),
        "possible_injury": summary.get("possible_injury_flags", 0),
    }, indent=2))


if __name__ == "__main__":
    main()
