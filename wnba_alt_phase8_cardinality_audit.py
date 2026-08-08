"""Phase 8 forensic audit for canonical ALT warehouse-cardinality failures.

Non-destructive. Explains every WAREHOUSE_RECORD_CARDINALITY_FAILURE from the
v3 certification and determines whether duplicate player-game records are safe
to collapse for the requested wager stat. Also audits legacy/canonical outcome
discrepancies (notably the July 14 cluster) with the underlying actual values.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_alt_performance_tracker import stat_value

LEGACY = Path("data/history/wnba_alt_streak_history.jsonl")
AUDIT = Path("data/dashboard/wnba_alt_game_identity_audit.json")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
CERT = Path("data/dashboard/wnba_alt_archive_certification.json")
OUT_JSON = Path("data/dashboard/wnba_alt_phase8_cardinality_audit.json")
OUT_CSV = Path("data/dashboard/wnba_alt_phase8_cardinality_audit.csv")
OUT_WAREHOUSE = Path("data/warehouse/wnba_alt_phase8_cardinality_audit.json")


def norm(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("’", "'").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict): out.append(row)
        except Exception: pass
    return out


def load(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception: return default


def gid(r: dict[str,Any]) -> str:
    return str(r.get("game_id") or r.get("event_id") or "")


def rec_date(r: dict[str,Any]) -> str:
    return str(r.get("game_date") or r.get("date") or r.get("event_date") or "")[:10]


def fingerprint(r: dict[str,Any]) -> tuple[Any,...]:
    return (
        gid(r), rec_date(r), norm(r.get("game") or r.get("matchup")),
        norm(r.get("player") or r.get("player_name")),
        norm(r.get("team") or r.get("team_name")),
        norm(r.get("opponent") or r.get("opponent_name")),
    )


def main() -> None:
    legacy=read_jsonl(LEGACY)
    audit=load(AUDIT,{"records":[]})
    audit_rows=[r for r in audit.get("records",[]) if isinstance(r,dict)]
    logs=load(LOGS,{"records":[]})
    records=[r for r in logs.get("records",[]) if isinstance(r,dict)]
    cert=load(CERT,{})
    if len(legacy)!=len(audit_rows):
        raise SystemExit(f"archive/audit row mismatch: {len(legacy)} vs {len(audit_rows)}")

    by_game_player=defaultdict(list)
    by_player_date=defaultdict(list)
    for r in records:
        p=norm(r.get("player") or r.get("player_name"))
        if gid(r) and p: by_game_player[(gid(r),p)].append(r)
        if p and rec_date(r): by_player_date[(p,rec_date(r))].append(r)

    phase8=[]; counts=Counter(); safe_indices=[]
    for idx,(src,diag) in enumerate(zip(legacy,audit_rows)):
        if str(diag.get("classification") or "") not in {"EXACT_MATCH","HOME_AWAY_ORIENTATION_DIFFERENCE","DATE_SHIFT_UNIQUE_MATCHUP"}:
            continue
        game_id=str(diag.get("warehouse_game_id") or "")
        p=norm(src.get("player"))
        matches=by_game_player.get((game_id,p),[])
        if len(matches)==1:
            continue

        stat=str(src.get("stat") or "")
        vals=[]
        for r in matches:
            try: vals.append(stat_value(r,stat))
            except Exception: vals.append(None)
        nonnull=[v for v in vals if v is not None]
        fps={fingerprint(r) for r in matches}
        record_ids=[str(r.get("record_id") or "") for r in matches]
        sources=[str(r.get("source") or r.get("data_source") or r.get("source_file") or "") for r in matches]

        if not matches:
            cls="ZERO_MATCH"
        elif len(fps)==1 and len(set(nonnull))<=1:
            cls="DUPLICATE_IDENTICAL_PLAYER_GAME"
        elif nonnull and len(nonnull)==len(matches) and len(set(nonnull))==1:
            cls="DUPLICATE_CONSISTENT_REQUESTED_STAT"
        elif nonnull and len(set(nonnull))==1:
            cls="DUPLICATE_PARTIAL_BUT_CONSISTENT_STAT"
        else:
            cls="DUPLICATE_CONFLICTING_REQUESTED_STAT"
        counts[cls]+=1
        safe = cls in {"DUPLICATE_IDENTICAL_PLAYER_GAME","DUPLICATE_CONSISTENT_REQUESTED_STAT","DUPLICATE_PARTIAL_BUT_CONSISTENT_STAT"} and bool(nonnull)
        if safe: safe_indices.append(idx)

        same_date=by_player_date.get((p,str(diag.get("warehouse_date") or "")[:10]),[])
        phase8.append({
            "archive_index":idx,"date":src.get("date"),"player":src.get("player"),"game":src.get("game"),
            "stat":stat,"alt_line":src.get("alt_line"),"side":src.get("side"),
            "audit_classification":diag.get("classification"),"warehouse_game_id":game_id,
            "warehouse_date":diag.get("warehouse_date"),"cardinality":len(matches),"classification":cls,
            "requested_stat_values":"|".join("" if v is None else str(v) for v in vals),
            "unique_requested_stat_values":len(set(nonnull)),"safe_to_collapse":safe,
            "record_ids":"|".join(record_ids),"sources":"|".join(sources),
            "candidate_games":"|".join(str(r.get("game") or r.get("matchup") or "") for r in matches[:8]),
            "same_player_date_candidate_count":len(same_date),
            "legacy_outcome":src.get("outcome"),"legacy_actual":src.get("actual"),
        })

    # Outcome discrepancy detail from the certification report.
    discrepancies=[]
    for d in cert.get("discrepancy_samples",[]) if isinstance(cert,dict) else []:
        try: idx=int(d.get("archive_index"))
        except Exception: continue
        if not (0<=idx<len(legacy)): continue
        src=legacy[idx]; diag=audit_rows[idx]
        game_id=str(diag.get("warehouse_game_id") or d.get("game_id") or "")
        p=norm(src.get("player")); matches=by_game_player.get((game_id,p),[])
        vals=[]
        for r in matches:
            try: vals.append(stat_value(r,str(src.get("stat") or "")))
            except Exception: vals.append(None)
        discrepancies.append({
            "archive_index":idx,"date":src.get("date"),"player":src.get("player"),"game":src.get("game"),
            "stat":src.get("stat"),"alt_line":src.get("alt_line"),"side":src.get("side"),"best_odds":src.get("best_odds"),
            "legacy_actual":src.get("actual"),"legacy_outcome":src.get("outcome"),"canonical_outcome":d.get("canonical_outcome"),
            "warehouse_game_id":game_id,"warehouse_cardinality":len(matches),
            "warehouse_requested_stat_values":vals,
        })

    report={
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "phase":"8-cardinality-audit",
        "legacy_rows":len(legacy),
        "certification_unresolved_rows":cert.get("unresolved_rows"),
        "cardinality_failure_rows":len(phase8),
        "classification_counts":dict(counts),
        "safe_to_collapse_rows":len(safe_indices),
        "unsafe_rows":len(phase8)-len(safe_indices),
        "safe_archive_indices":safe_indices,
        "july14_outcome_discrepancy_count":sum(str(x.get("date"))[:10]=="2026-07-14" for x in discrepancies),
        "outcome_discrepancies":discrepancies,
        "policy":"diagnostic only; no archive rows or warehouse records modified",
        "records":phase8,
    }
    text=json.dumps(report,indent=2,allow_nan=False)+"\n"
    for path in (OUT_JSON,OUT_WAREHOUSE):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")
    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    fields=list(phase8[0].keys()) if phase8 else ["archive_index","classification","cardinality"]
    with OUT_CSV.open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(phase8)
    print(json.dumps({k:v for k,v in report.items() if k not in {"records","outcome_discrepancies","safe_archive_indices"}},indent=2))
    print(json.dumps({"outcome_discrepancies":discrepancies[:15]},indent=2))

if __name__=="__main__": main()
