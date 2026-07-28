"""QA for Sprint 23 Phase 5 explainable shadow intelligence."""
import json
from pathlib import Path

DATA = Path("data/dashboard/sprint23_shadow_intelligence.json")
ALLOWED_BOOKS = {"draftkings", "fanduel"}


def run() -> dict:
    payload = json.loads(DATA.read_text())
    cards = payload.get("cards", [])
    tests = {
        "status_pass": payload.get("status") == "PASS",
        "shadow_only": payload.get("deployment_status") == "SHADOW_ONLY",
        "production_unchanged": payload.get("production_recommendations_changed") is False,
        "card_count_matches": int(payload.get("card_count", -1)) == len(cards),
        "max_cards": len(cards) <= 30,
        "allowed_books": all(str(c.get("sportsbook_key", "")).lower() in ALLOWED_BOOKS for c in cards),
        "positive_ev_only": all(float(c.get("expected_value_per_dollar", 0)) > 0 for c in cards),
        "reasons_present": all(len(c.get("reasons", [])) >= 3 for c in cards),
        "validation_present": isinstance(payload.get("validation"), dict),
        "disclaimer_present": "not production" in str(payload.get("disclaimer", "")).lower(),
    }
    failed = [name for name, passed in tests.items() if not bool(passed)]
    result = {"status": "PASS" if not failed else "FAIL", "tests": {k: bool(v) for k, v in tests.items()}, "failed": failed}
    print(json.dumps(result, indent=2))
    if failed:
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    run()
