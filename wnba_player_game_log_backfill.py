"""Backfill the cumulative player game-log warehouse from verified boxscore CSVs.

Supported inputs:
- data/raw/wehoop_player_box_<season>.csv
- data/raw/espn_wnba_player_box_<season>.csv

This backfills full-game statistics, free throws, and total personal fouls. It
does not invent quarter splits; those remain unavailable unless play-by-play is
present for the same player-game record. After backfill, production prop history
is rebuilt from the latest deduplicated game rows and unsupported rare markets
are removed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WAREHOUSE = Path("data/warehouse/wnba_player_game_logs.json")
DASHBOARD = Path("data/dashboard/wnba_player_game_logs.json")


def load(path: Path, default: Any) -> Any:
    try:return json.load(path.open(encoding="utf-8")) if path.exists() else default
    except Exception:return default

def num(value: Any) -> float | None:
    try:
        result=float(value);return result if math.isfinite(result) else None
    except Exception:return None

def boolean(value: Any) -> bool | None:
    if value is None or value=="":return None
    if isinstance(value,bool):return value
    return str(value).strip().lower() in {"true","1","yes","y"}
def norm(value: Any) -> str:return " ".join(str(value or "").strip().lower().replace("’", "'").split())
def first(row: dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value=row.get(field)
        if value not in (None,"","--","nan","NaN"):return value
    return None

def read_csvs(season: int | None) -> tuple[list[dict[str, Any]], list[str]]:
    patterns=["wehoop_player_box_*.csv","espn_wnba_player_box_*.csv"];files=[]
    for pattern in patterns:files.extend(Path("data/raw").glob(pattern))
    if season:files=[p for p in files if str(season) in p.stem]
    rows=[];used=[]
    for path in sorted(set(files)):
        try:
            with path.open(encoding="utf-8",newline="") as handle:current=[dict(r) for r in csv.DictReader(handle)]
            if current:rows.extend(current);used.append(str(path))
        except Exception:continue
    return rows,used

def record_key(row: dict[str, Any]) -> str:
    game_id=str(first(row,"game_id","event_id") or "").strip();player_id=str(first(row,"athlete_id","player_id") or "").strip();player=str(first(row,"athlete_display_name","player_name","player") or "").strip();game_date=str(first(row,"game_date","date") or "").strip()
    return f"{game_id or game_date}|{player_id or norm(player)}"
def game_identifier(row: dict[str, Any]) -> str:return str(first(row,"game_id","event_id") or first(row,"game_date","date") or "").strip()
def team_name(row: dict[str, Any]) -> str:return str(first(row,"team_name","team_location","team_abbreviation","team_abbr","team") or "").strip()
def build_opponents(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    teams=defaultdict(set)
    for row in rows:
        gid=game_identifier(row);team=team_name(row)
        if gid and team:teams[gid].add(team)
    mapping={}
    for gid,members in teams.items():
        for team in members:
            others=sorted(x for x in members if norm(x)!=norm(team))
            if others:mapping[(gid,norm(team))]=others[0]
    return mapping

def blank(row: dict[str, Any], opponent: str | None) -> dict[str, Any]:
    game_id=game_identifier(row);player=str(first(row,"athlete_display_name","player_name","player") or "").strip();team=team_name(row);home_away=str(first(row,"home_away","homeAway") or "").lower() or None;game_label=f"{opponent} @ {team}" if home_away=="home" and opponent else f"{team} @ {opponent}" if opponent else game_id
    return {"record_id":record_key(row),"game_id":game_id or None,"game":game_label,"game_date":first(row,"game_date","date"),"season":int(num(first(row,"season","season_year")) or 0) or None,"player_id":first(row,"athlete_id","player_id"),"player":player,"position":first(row,"athlete_position_abbreviation","position"),"team":team or None,"opponent":opponent,"home_away":home_away,"starter":boolean(first(row,"starter")),"did_not_play":boolean(first(row,"did_not_play","didNotPlay")),"minutes":num(first(row,"minutes","min","MIN")),"minutes_by_period":{"q1":None,"q2":None,"q3":None,"q4":None,"ot":None},"scoring":{"q1_pts":None,"q2_pts":None,"q3_pts":None,"q4_pts":None,"ot_pts":None,"first_half_pts":None,"second_half_pts":None,"total_pts":num(first(row,"points","pts","PTS")),"fgm":num(first(row,"field_goals_made","fg_made","fgm","FGM")),"fga":num(first(row,"field_goals_attempted","fg_att","fga","FGA")),"two_pm":None,"two_pa":None,"three_pm":num(first(row,"three_point_field_goals_made","threes_made","fg3m","3PM")),"three_pa":num(first(row,"three_point_field_goals_attempted","threes_att","fg3a","3PA")),"ftm":num(first(row,"free_throws_made","ft_made","ftm","FTM")),"fta":num(first(row,"free_throws_attempted","ft_att","fta","FTA")),"free_throw_points":num(first(row,"free_throws_made","ft_made","ftm","FTM"))},"fouls":{"personal":int(num(first(row,"fouls","pf","PF")) or 0),"offensive":None,"shooting":None,"technical":None,"flagrant":None,"total_committed":int(num(first(row,"fouls","pf","PF")) or 0),"fouls_drawn":None,"fouled_out":int(num(first(row,"fouls","pf","PF")) or 0)>=6},"boxscore":{"reb":num(first(row,"rebounds","reb","REB")),"oreb":num(first(row,"offensive_rebounds","oreb","OREB")),"dreb":num(first(row,"defensive_rebounds","dreb","DREB")),"ast":num(first(row,"assists","ast","AST")),"stl":num(first(row,"steals","stl","STL")),"blk":num(first(row,"blocks","blk","BLK")),"tov":num(first(row,"turnovers","tov","TO","TOV")),"plus_minus":num(first(row,"plus_minus","+/-"))},"derived":{"pra":None,"pr":None,"pa":None,"ra":None,"points_per_minute":None,"free_throw_points_per_minute":None,"fouls_per_minute":None},"data_quality":{"quarter_data_status":"unavailable","event_data_status":"unavailable","boxscore_data_status":"observed","quarter_points_match_total":None,"validation_flags":[],"sources":["wehoop_or_espn_player_boxscore"]}}

def finalize(record: dict[str, Any]) -> None:
    s,b,d=record["scoring"],record["boxscore"],record["derived"];pts,reb,ast=s.get("total_pts"),b.get("reb"),b.get("ast")
    if pts is not None and reb is not None:d["pr"]=pts+reb
    if pts is not None and ast is not None:d["pa"]=pts+ast
    if reb is not None and ast is not None:d["ra"]=reb+ast
    if pts is not None and reb is not None and ast is not None:d["pra"]=pts+reb+ast
    minutes=record.get("minutes")
    if minutes and minutes>0:d["points_per_minute"]=round((pts or 0)/minutes,4);d["free_throw_points_per_minute"]=round((s.get("free_throw_points") or 0)/minutes,4);d["fouls_per_minute"]=round(record["fouls"]["total_committed"]/minutes,4)
def quality(record: dict[str, Any]) -> tuple[int,int,int]:
    q=record.get("data_quality",{});return ({"complete":3,"partial":2,"unavailable":1}.get(q.get("quarter_data_status"),0),1 if q.get("event_data_status")=="observed" else 0,1 if q.get("boxscore_data_status")=="observed" else 0)
def build(season: int | None) -> dict[str, Any]:
    rows,files=read_csvs(season);opponents=build_opponents(rows);existing=load(WAREHOUSE,{"records":[]});merged={str(r.get("record_id") or record_key(r)):r for r in existing.get("records",[]) if isinstance(r,dict)};added=replaced=skipped_dnp=0
    for row in rows:
        player=str(first(row,"athlete_display_name","player_name","player") or "").strip()
        if not player:continue
        if boolean(first(row,"did_not_play","didNotPlay")) is True:skipped_dnp+=1;continue
        team=team_name(row);record=blank(row,opponents.get((game_identifier(row),norm(team))));finalize(record);key=record["record_id"];prior=merged.get(key)
        if prior is None:merged[key]=record;added+=1
        elif quality(record)>quality(prior) or (record.get('game_date') and not prior.get('game_date')):merged[key]=record;replaced+=1
    records=list(merged.values());records.sort(key=lambda r:(str(r.get("game_date") or ""),str(r.get("game_id") or ""),str(r.get("player") or "")),reverse=True);seasons=sorted({r.get("season") for r in records if r.get("season")})
    summary={"records":len(records),"players":len({norm(r.get('player')) for r in records if r.get('player')}),"games":len({str(r.get('game_id') or r.get('game')) for r in records}),"seasons":seasons,"source_rows":len(rows),"added":added,"replaced":replaced,"skipped_dnp":skipped_dnp,"quarter_complete":sum(r.get('data_quality',{}).get('quarter_data_status')=='complete' for r in records),"quarter_unavailable":sum(r.get('data_quality',{}).get('quarter_data_status')=='unavailable' for r in records),"records_with_free_throw_points":sum((r.get('scoring',{}).get('free_throw_points') or 0)>0 for r in records),"records_with_fouls":sum((r.get('fouls',{}).get('total_committed') or 0)>0 for r in records),"historical_backfill":True}
    payload=dict(existing);payload.update({"generated_at_utc":datetime.now(timezone.utc).isoformat(),"status":"ok","schema_version":"1.2","summary":summary,"records":records,"backfill":{"files":files,"requested_season":season,"boxscore_only_quarter_policy":"unavailable","record_identity":"game_id + player_id preferred"}})
    for path in (WAREHOUSE,DASHBOARD):path.parent.mkdir(parents=True,exist_ok=True);json.dump(payload,path.open("w",encoding="utf-8"),indent=2,allow_nan=False)
    print("Player game-log backfill:",summary);return payload

def refresh_prop_context()->None:
    try:
        from wnba_v4_prop_context import main as context_main
        context_main()
        from wnba_special_market_guard import main as guard_main
        guard_main()
    except Exception as exc:
        raise RuntimeError(f"Prop history refresh failed after backfill: {exc}") from exc

def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--season",type=int);args=parser.parse_args();build(args.season);refresh_prop_context()

if __name__=="__main__":main()
