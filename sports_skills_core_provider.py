"""
sports_skills_core_provider.py
------------------------------
Turns sports-skills into the primary free WNBA data provider.

This script does not depend on The Odds API. It installs/uses the sports-skills
CLI when available, saves raw JSON, and creates a normalized provider status.

Outputs:
- data/wnba/scores.json
- data/wnba/injuries.json
- data/wnba/standings.json
- data/wnba/futures.json
- data/warehouse/sports_skills_provider_status.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List

COMMANDS = {
    "scores": ["sports-skills", "wnba", "get_scoreboard"],
    "injuries": ["sports-skills", "wnba", "get_injuries"],
    "standings": ["sports-skills", "wnba", "get_standings"],
    "futures": ["sports-skills", "wnba", "get_futures"],
}


def run_command(cmd: List[str], timeout: int = 45) -> Dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        raw = (proc.stdout or "").strip()
        parsed = json.loads(raw) if raw else {}
        return {
            "ok": proc.returncode == 0 and bool(parsed),
            "returncode": proc.returncode,
            "bytes": len(raw),
            "data": parsed,
            "stderr": (proc.stderr or "").strip()[:1000],
        }
    except Exception as exc:
        return {"ok": False, "returncode": None, "bytes": 0, "data": {}, "stderr": str(exc)}


def save_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload if payload else {}, f, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2026")
    ap.add_argument("--out", default="data/wnba")
    ap.add_argument("--warehouse", default="data/warehouse")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.warehouse, exist_ok=True)

    status = {
        "source": "sports-skills",
        "role": "primary_free_wnba_provider",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": args.season,
        "commands": {},
        "ready": False,
    }

    for key, base_cmd in COMMANDS.items():
        cmd = list(base_cmd)
        if key == "standings":
            cmd += ["--season", args.season]
        result = run_command(cmd)
        save_json(os.path.join(args.out, f"{key}.json"), result.get("data", {}))
        status["commands"][key] = {
            "ok": bool(result.get("ok")),
            "returncode": result.get("returncode"),
            "bytes": result.get("bytes"),
            "stderr": result.get("stderr"),
            "output_file": f"data/wnba/{key}.json",
        }

    status["ready"] = all(v["ok"] for v in status["commands"].values())
    save_json(os.path.join(args.warehouse, "sports_skills_provider_status.json"), status)
    print(json.dumps(status, indent=2))
    print("✅ sports-skills provider refresh complete")


if __name__ == "__main__":
    main()
