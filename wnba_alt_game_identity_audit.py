"""Non-destructive forensic audit for ALT archive game identity mismatches.

Compares every frozen ALT row to the completed player-game warehouse without
changing grades. The goal is to explain why a strict player+date+matchup join
fails and quantify the dominant failure classes before any repair is applied.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE = Path("data/history/wnba_alt_streak_history.jsonl")
LOGS = Path("data/warehouse/wnba_player_game_logs.json")
JSON_OUT = Path("data/dashboard/wnba_alt_game_identity_audit.json")
CSV_OUT = Path("data/dashboard/wnba_alt_game_identity_audit.csv")
WAREHOUSE_OUT = Path("data/warehouse/wnba_alt_game_identity_audit.json")

TEAM_ALIASES = {
    "la sparks":"los angeles sparks","los angeles":"los angeles sparks","sparks":"los angeles sparks",
    "ny liberty":"new york liberty","new york":"new york liberty","liberty":"new york liberty",
    "gs valkyries":"golden state valkyries","golden state":"golden state valkyries","valkyries":"golden state valkyries",
    "lv aces":"las vegas aces","las vegas":"las vegas aces","aces":"las vegas aces",
    "washington":"washington mystics","mystics":"washington mystics",
    "connecticut":"connecticut sun","sun":"connecticut sun",
    "phoenix":"phoenix mercury","mercury":"phoenix mercury",
    "atlanta":"atlanta dream","dream":"atlanta dream",
    "dallas":"dallas wings","wings":"dallas wings",
    "seattle":"seattle storm","storm":"seattle storm",
    "chicago":"chicago sky","sky":"chicago sky",
    "minnesota":"minnesota lynx","lynx":"minnesota lynx",
    "indiana":"indiana fever","fever":"indiana fever",
    "portland":"portland fire","fire":"portland fire",
    "toronto":"toronto tempo","tempo":"toronto tempo",
}


def norm(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("’", "'").split())


def team_norm(v: Any) -> str:
    text = re.sub(r"[^a-z0-9' ]+", " ", norm(v))
    text = " ".join(text.split())
    return TEAM_ALIASES.get(text, text)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out=[]
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict): out.append(row)
            except Exception:
                pass
    return out


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def parse_game(v: Any) -> tuple[str,str] | None:
    text=str(v or "").strip()
    if "@" not in text:
        return None
    a,b=text.split("@",1)
    a,b=team_norm(a),team_norm(b)
    return (a,b) if a and b and a!=b else None


def row_game(row: dict[str,Any]) -> tuple[str,str] | None:
    return parse_game(row.get("game")) or parse_game(row.get("opponent"))


def record_game(row: dict[str,Any]) -> tuple[str,str] | None:
    direct=parse_game(row.get("game")) or parse_game(row.get("matchup")) or parse_game(row.get("opponent"))
    if direct: return direct
    away=team_norm(row.get("away_team")); home=team_norm(row.get("home_team"))
    if away and home and away!=home: return away,home
    team=team_norm(row.get("team") or row.get("team_name")); opp=team_norm(row.get("opponent") or row.get("opponent_name"))
    if team and opp and team!=opp: return tuple(sorted((team,opp)))  # orientation unknown
    return None


def unordered(g: tuple[str,str] | None) -> frozenset[str]:
    return frozenset(g or ())


def rec_date(r: dict[str,Any]) -> str:
    return str(r.get("game_date") or r.get("date") or r.get("event_date") or "")[:10]


def days(a: str,b: str) -> int | None:
    try: return abs((date.fromisoformat(a)-date.fromisoformat(b)).days)
    except Exception: return None


def main() -> None:
    archive=read_jsonl(ARCHIVE)
    payload=load(LOGS,{"records":[]})
    records=[r for r in payload.get("records",[]) if isinstance(r,dict)]
    by_player=defaultdict(list)
    for r in records:
        p=norm(r.get("player") or r.get("player_name"))
        if p: by_player[p].append(r)

    rows=[]; counts=Counter(); now=datetime.now(timezone.utc).isoformat()
    for a in archive:
        p=norm(a.get("player")); ad=str(a.get("date") or "")[:10]; ag=row_game(a); candidates=by_player.get(p,[])
        same=[r for r in candidates if rec_date(r)==ad]
        same_pairs=[(r,record_game(r)) for r in same]
        exact_same=[r for r,g in same_pairs if ag and g and unordered(ag)==unordered(g)]
        orient_same=[r for r,g in same_pairs if ag and g and ag==g]

        cls=""; chosen=None; candidate_dates=[]; note=""
        if not candidates:
            cls="NO_PLAYER_GAME_ANY_DATE"
        elif not same:
            nearby=[]
            for r in candidates:
                d=days(ad,rec_date(r))
                if d is not None and d<=7:
                    nearby.append((r,record_game(r),d))
            pair_near=[x for x in nearby if ag and x[1] and unordered(ag)==unordered(x[1])]
            uniq_dates=sorted({rec_date(x[0]) for x in pair_near})
            candidate_dates=uniq_dates
            if len(uniq_dates)==1:
                cls="DATE_SHIFT_UNIQUE_MATCHUP"; chosen=pair_near[0][0]
            elif len(uniq_dates)>1:
                cls="REPEATED_MATCHUP_DATE_AMBIGUOUS"
            else:
                cls="NO_COMPLETED_GAME_ON_ARCHIVE_DATE"
        elif not ag:
            cls="ARCHIVE_MATCHUP_MISSING"
        elif orient_same:
            cls="EXACT_MATCH"; chosen=orient_same[0]
        elif exact_same:
            cls="HOME_AWAY_ORIENTATION_DIFFERENCE"; chosen=exact_same[0]
        else:
            # Check whether only representation/alias differs after normalization.
            raw_candidates=[str(r.get("game") or r.get("matchup") or r.get("opponent") or "") for r in same]
            cls="SAME_DATE_DIFFERENT_MATCHUP"
            note=" | ".join(raw_candidates[:5])

        counts[cls]+=1
        if chosen is None and exact_same: chosen=exact_same[0]
        cg=record_game(chosen) if chosen else None
        rows.append({
            "archive_date":ad,
            "player":a.get("player"),
            "archive_game":a.get("game") or a.get("opponent"),
            "archive_away":ag[0] if ag else None,
            "archive_home":ag[1] if ag else None,
            "classification":cls,
            "warehouse_date":rec_date(chosen) if chosen else None,
            "warehouse_game":(chosen or {}).get("game") if chosen else None,
            "warehouse_away":cg[0] if cg else None,
            "warehouse_home":cg[1] if cg else None,
            "warehouse_game_id":(chosen or {}).get("game_id") or (chosen or {}).get("event_id") if chosen else None,
            "candidate_dates":"|".join(candidate_dates),
            "note":note,
            "outcome":a.get("outcome"),
            "actual_source":a.get("actual_source"),
        })

    report={
        "generated_at_utc":now,
        "rows":len(rows),
        "classification_counts":dict(counts),
        "non_exact_rows":sum(v for k,v in counts.items() if k!="EXACT_MATCH"),
        "exact_rows":counts.get("EXACT_MATCH",0),
        "policy":"diagnostic only; no archive rows or grades modified",
        "records":rows,
    }
    text=json.dumps(report,indent=2,allow_nan=False)+"\n"
    for p in (JSON_OUT,WAREHOUSE_OUT):
        p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding="utf-8")
    CSV_OUT.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0].keys()) if rows else ["archive_date","player","classification"]
    with CSV_OUT.open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(json.dumps({"rows":len(rows),"classification_counts":dict(counts)},indent=2))

if __name__=="__main__": main()
