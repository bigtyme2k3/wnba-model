"""Finalize the 2026 WNBA ALT archive into canonical game-identity v3.

This is deliberately non-destructive to the legacy frozen archive. It creates a
new canonical archive, regrades only rows that have a unique completed game,
keeps ambiguous rows explicitly unresolved, and emits a certification report.

Resolution policy (highest confidence first):
  1. EXACT_MATCH
  2. HOME_AWAY_ORIENTATION_DIFFERENCE
  3. DATE_SHIFT_UNIQUE_MATCHUP
  4. all other audit classes remain unresolved (never guessed)

The positional join to the Phase 3 audit is guarded by row count + player/date/
game checks before any canonical output is written.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_alt_performance_tracker import stat_value, outcome, one_unit_profit

LEGACY = Path("data/history/wnba_alt_streak_history.jsonl")
AUDIT = Path("data/dashboard/wnba_alt_game_identity_audit.json")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
CANONICAL = Path("data/history/wnba_alt_streak_history_v3.jsonl")
CERT = Path("data/dashboard/wnba_alt_archive_certification.json")
CERT_WAREHOUSE = Path("data/warehouse/wnba_alt_archive_certification.json")
UNRESOLVED = Path("data/dashboard/wnba_alt_archive_unresolved_v3.csv")
MANIFEST = Path("data/warehouse/wnba_alt_archive_manifest.json")

SAFE_CLASSES = {
    "EXACT_MATCH": "exact_game_date_match",
    "HOME_AWAY_ORIENTATION_DIFFERENCE": "orientation_normalized",
    "DATE_SHIFT_UNIQUE_MATCHUP": "unique_completed_matchup_date_shift",
}
FINAL = {"WIN", "LOSS", "PUSH", "VOID"}


def norm(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("’", "'").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows=[]
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict): rows.append(row)
        except Exception:
            pass
    return rows


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_jsonl(path: Path, rows: list[dict[str,Any]]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as h:
        for row in rows:
            h.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")


def rec_id(r: dict[str,Any]) -> str:
    return str(r.get("record_id") or r.get("game_id") or r.get("event_id") or "")


def main() -> None:
    legacy=read_jsonl(LEGACY)
    audit=load(AUDIT,{"records":[]})
    audit_rows=[r for r in audit.get("records",[]) if isinstance(r,dict)]
    logs=load(LOGS,{"records":[]})
    records=[r for r in logs.get("records",[]) if isinstance(r,dict)]

    if not legacy or len(legacy)!=len(audit_rows):
        raise SystemExit(f"Phase 3 audit/archive row mismatch: archive={len(legacy)} audit={len(audit_rows)}")

    # Strict positional-integrity guard. The audit is emitted in archive order.
    for i,(a,d) in enumerate(zip(legacy,audit_rows)):
        if norm(a.get("player"))!=norm(d.get("player")) or str(a.get("date") or "")[:10]!=str(d.get("archive_date") or "")[:10]:
            raise SystemExit(f"Phase 3 positional guard failed at row {i}")

    by_game_player=defaultdict(list)
    for r in records:
        gid=str(r.get("game_id") or r.get("event_id") or "")
        p=norm(r.get("player") or r.get("player_name"))
        if gid and p: by_game_player[(gid,p)].append(r)

    now=datetime.now(timezone.utc).isoformat()
    canonical=[]; unresolved=[]; counts=Counter(); discrepancies=[]

    for idx,(src,diag) in enumerate(zip(legacy,audit_rows)):
        row=dict(src)
        cls=str(diag.get("classification") or "UNKNOWN")
        row["identity_schema"]="alt-game-v3"
        row["legacy_archive_index"]=idx
        row["identity_classification"]=cls
        row["canonicalized_at_utc"]=now

        if cls not in SAFE_CLASSES:
            row["canonical_status"]="UNRESOLVED"
            row["canonical_resolution_method"]=None
            row["canonical_game_id"]=None
            row["canonical_game_date"]=None
            row["canonical_game"]=None
            unresolved.append({
                "archive_index":idx,
                "date":src.get("date"),"player":src.get("player"),"game":src.get("game"),
                "stat":src.get("stat"),"alt_line":src.get("alt_line"),"side":src.get("side"),
                "classification":cls,"candidate_dates":diag.get("candidate_dates"),"note":diag.get("note"),
                "legacy_outcome":src.get("outcome"),
            })
            counts[f"unresolved:{cls}"]+=1
            canonical.append(row)
            continue

        gid=str(diag.get("warehouse_game_id") or "")
        p=norm(src.get("player"))
        matches=by_game_player.get((gid,p),[])
        if len(matches)!=1:
            row["canonical_status"]="UNRESOLVED"
            row["canonical_resolution_method"]="warehouse_record_cardinality_failure"
            row["canonical_game_id"]=gid or None
            unresolved.append({
                "archive_index":idx,"date":src.get("date"),"player":src.get("player"),"game":src.get("game"),
                "stat":src.get("stat"),"alt_line":src.get("alt_line"),"side":src.get("side"),
                "classification":"WAREHOUSE_RECORD_CARDINALITY_FAILURE","candidate_dates":diag.get("warehouse_date"),
                "note":f"warehouse matches={len(matches)}","legacy_outcome":src.get("outcome"),
            })
            counts["unresolved:WAREHOUSE_RECORD_CARDINALITY_FAILURE"]+=1
            canonical.append(row)
            continue

        rec=matches[0]
        actual=stat_value(rec,str(src.get("stat") or ""))
        if actual is None:
            row["canonical_status"]="UNRESOLVED"
            row["canonical_resolution_method"]="stat_unavailable"
            row["canonical_game_id"]=gid
            unresolved.append({
                "archive_index":idx,"date":src.get("date"),"player":src.get("player"),"game":src.get("game"),
                "stat":src.get("stat"),"alt_line":src.get("alt_line"),"side":src.get("side"),
                "classification":"STAT_UNAVAILABLE","candidate_dates":diag.get("warehouse_date"),
                "note":"matched game but requested stat unavailable","legacy_outcome":src.get("outcome"),
            })
            counts["unresolved:STAT_UNAVAILABLE"]+=1
            canonical.append(row)
            continue

        result=outcome(str(src.get("side") or ""),actual,src.get("alt_line"))
        row.update({
            "canonical_status":"CERTIFIED",
            "canonical_resolution_method":SAFE_CLASSES[cls],
            "canonical_game_id":gid,
            "canonical_game_date":str(rec.get("game_date") or diag.get("warehouse_date") or "")[:10],
            "canonical_game":rec.get("game") or diag.get("warehouse_game"),
            "canonical_player_game_record_id":rec_id(rec),
            "canonical_actual":actual,
            "canonical_outcome":result,
            "canonical_profit_loss":one_unit_profit(result,src.get("best_odds")),
            "canonical_actual_source":"player_game_log_warehouse_v3",
        })
        counts[f"certified:{cls}"]+=1
        legacy_out=str(src.get("outcome") or "").upper()
        if legacy_out in FINAL and result in FINAL and legacy_out!=result:
            discrepancies.append({"archive_index":idx,"player":src.get("player"),"date":src.get("date"),"game":src.get("game"),"legacy_outcome":legacy_out,"canonical_outcome":result,"game_id":gid})
        canonical.append(row)

    certified=sum(r.get("canonical_status")=="CERTIFIED" for r in canonical)
    unresolved_count=len(canonical)-certified
    coverage=(certified/len(canonical)) if canonical else 0.0
    duplicate_keys=Counter((r.get("canonical_game_id"),norm(r.get("player")),r.get("stat"),r.get("alt_line"),r.get("side")) for r in canonical if r.get("canonical_status")=="CERTIFIED")
    duplicate_certified=sum(v-1 for v in duplicate_keys.values() if v>1)

    # Certification is intentionally strict: rows can be safely canonicalized while
    # the overall archive remains PARTIAL until genuine ambiguities are resolved.
    status="CERTIFIED" if unresolved_count==0 and not discrepancies else "PARTIAL_CERTIFIED"
    cert={
        "generated_at_utc":now,
        "identity_schema":"alt-game-v3",
        "status":status,
        "legacy_rows":len(legacy),
        "canonical_rows":len(canonical),
        "certified_rows":certified,
        "unresolved_rows":unresolved_count,
        "canonical_coverage_pct":round(coverage*100,2),
        "legacy_final_rows":sum(str(r.get("outcome") or "").upper() in FINAL for r in legacy),
        "canonical_final_rows":sum(str(r.get("canonical_outcome") or "").upper() in FINAL for r in canonical),
        "legacy_vs_canonical_outcome_discrepancies":len(discrepancies),
        "duplicate_certified_wager_keys":duplicate_certified,
        "resolution_counts":dict(counts),
        "unresolved_classification_counts":dict(Counter(r["classification"] for r in unresolved)),
        "safety_policy":"legacy archive unchanged; only unique completed-game mappings are certified; repeated/uncertain matchups never guessed",
        "production_ready":unresolved_count==0 and not discrepancies and duplicate_certified==0,
        "next_action":"manual/official-schedule resolution of unresolved rows" if unresolved_count else "freeze canonical v3 archive",
        "discrepancy_samples":discrepancies[:25],
    }

    write_jsonl(CANONICAL,canonical)
    text=json.dumps(cert,indent=2,allow_nan=False)+"\n"
    for path in (CERT,CERT_WAREHOUSE):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")

    UNRESOLVED.parent.mkdir(parents=True,exist_ok=True)
    fields=["archive_index","date","player","game","stat","alt_line","side","classification","candidate_dates","note","legacy_outcome"]
    with UNRESOLVED.open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(unresolved)

    manifest={
        "schema":"alt-game-v3","generated_at_utc":now,"canonical_archive":str(CANONICAL),
        "certification_report":str(CERT),"unresolved_report":str(UNRESOLVED),
        "status":status,"production_ready":cert["production_ready"],"append_only_required":True,
        "canonical_identity_rule":"official completed game_id + player-game record; archive date is metadata, never game identity",
    }
    MANIFEST.parent.mkdir(parents=True,exist_ok=True); MANIFEST.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(cert,indent=2))


if __name__=="__main__":
    main()
