from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
PLAYERS = Path("data/raw/wnba_players_live.json")
RAW = Path("data/raw")

TEAM_ABBR = {
    "Golden State Valkyries": "GSV", "Toronto Tempo": "TOR", "Minnesota Lynx": "MIN",
    "Connecticut Sun": "CON", "Indiana Fever": "IND", "Los Angeles Sparks": "LAS",
    "Washington Mystics": "WAS", "Seattle Storm": "SEA", "Las Vegas Aces": "LVA",
    "Dallas Wings": "DAL", "New York Liberty": "NYL", "Chicago Sky": "CHI",
    "Phoenix Mercury": "PHX", "Atlanta Dream": "ATL", "Portland Fire": "POR",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists(): return json.load(path.open(encoding="utf-8"))
    except Exception: pass
    return default


def to_num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""): return default
        return float(value)
    except (TypeError, ValueError): return default


def clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(float(value), 2)


def abbr(team: str) -> str:
    if not team: return ""
    return TEAM_ABBR.get(team, "".join(x[:1] for x in team.split()).upper()[:3])


def norm_player(value: Any) -> str:
    text=str(value or "").lower().replace("’", "'")
    text=re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv)\b", "", text)
    return " ".join(re.sub(r"[^a-z0-9' -]", "", text).split())


def last_name(value: Any) -> str:
    parts=norm_player(value).replace("-", " ").split()
    return parts[-1] if parts else ""


def game_parts(game: str) -> tuple[str, str]:
    if " @ " in game:
        away, home = game.split(" @ ", 1); return away.strip(), home.strip()
    return "", ""


def build_team_logos(master: dict[str, Any]) -> dict[str, str]:
    logos: dict[str, str] = {}
    for g in master.get("games", []) or []:
        if g.get("away_team") and g.get("away_logo"): logos[g["away_team"]] = g["away_logo"]
        if g.get("home_team") and g.get("home_logo"): logos[g["home_team"]] = g["home_logo"]
    return logos


def load_game_opponents() -> dict[tuple[str, str], str]:
    opponents: dict[tuple[str, str], str] = {}
    for path in sorted(RAW.glob("scores_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    gid=str(row.get("game_id") or "").strip(); home=str(row.get("home_team") or "").strip(); away=str(row.get("away_team") or "").strip()
                    if gid and home and away:
                        opponents[(gid,home)]=away; opponents[(gid,away)]=home
        except Exception: continue
    return opponents


def boxscore_paths() -> list[Path]:
    preferred=[RAW/"boxscores_wehoop.csv", RAW/"wehoop_player_boxscores.csv"]
    extras=sorted(RAW.glob("boxscores_*.csv"), key=lambda p:p.stat().st_mtime if p.exists() else 0, reverse=True)
    result=[]
    for path in extras+preferred:
        if path.exists() and path not in result: result.append(path)
    return result


def row_quality(row: dict[str,Any], path:Path) -> tuple[int,float]:
    fields=("pts","reb","ast","minutes","game_id","opponent")
    complete=sum(row.get(x) not in (None,"") for x in fields)
    return complete, path.stat().st_mtime if path.exists() else 0


def is_placeholder(row:dict[str,Any])->bool:
    minutes=to_num(row.get("minutes"),0)
    stats=[to_num(row.get(k),0) for k in ("pts","reb","ast","stl","blk","tov")]
    status=str(row.get("status") or row.get("comment") or "").upper()
    return minutes<=0 and not any(stats) and not any(x in status for x in ("DNP","DID NOT PLAY","INACTIVE"))


def load_player_game_logs(target_date: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    opponents=load_game_opponents(); chosen:dict[tuple[str,str],tuple[dict[str,Any],tuple[int,float]]]={};source_rows={};rejected_placeholders=0;duplicates_replaced=0
    for path in boxscore_paths():
        accepted=0
        try:
            with path.open(encoding="utf-8",newline="") as handle:
                for row in csv.DictReader(handle):
                    player=str(row.get("player") or row.get("athlete_display_name") or row.get("athlete") or "").strip();player_id=str(row.get("player_id") or row.get("athlete_id") or "").strip()
                    pkey=player_id or norm_player(player);game_date=str(row.get("game_date") or row.get("date") or "")[:10];game_id=str(row.get("game_id") or row.get("event_id") or "").strip();team=str(row.get("team") or row.get("team_name") or "").strip()
                    if not pkey or not game_date or game_date>=target_date: continue
                    if is_placeholder(row):rejected_placeholders+=1;continue
                    unique_game=game_id or f"{game_date}|{team}"
                    key=(pkey,unique_game);quality=row_quality(row,path)
                    opponent=str(row.get("opponent") or row.get("opponent_name") or opponents.get((game_id,team),"")).strip();opponent_abbr=str(row.get("opponent_abbr") or "").strip() or abbr(opponent)
                    item={"player":player,"player_id":player_id,"game_date":game_date,"game_id":game_id,"team":team,"opponent":opponent,"opponent_abbr":opponent_abbr,"pts":to_num(row.get("pts")),"reb":to_num(row.get("reb")),"ast":to_num(row.get("ast")),"threes":to_num(row.get("threes",row.get("fg3m"))),"stl":to_num(row.get("stl")),"blk":to_num(row.get("blk")),"tov":to_num(row.get("tov")),"minutes":to_num(row.get("minutes")),"history_file":path.name}
                    current=chosen.get(key)
                    if current is None or quality>current[1]:
                        if current is not None:duplicates_replaced+=1
                        chosen[key]=(item,quality)
                    accepted+=1
        except Exception: continue
        source_rows[path.name]=accepted
    logs:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for item,_ in chosen.values():
        logs[norm_player(item.get("player"))].append(item)
        if item.get("player_id"):logs[f"id:{item['player_id']}"] .append(item)
    for values in logs.values():values.sort(key=lambda item:(item.get("game_date",""),item.get("game_id","")),reverse=True)
    return logs,{"files":source_rows,"players":len({k for k in logs if not k.startswith('id:')}),"game_rows":len(chosen),"placeholder_rows_rejected":rejected_placeholders,"duplicate_rows_replaced":duplicates_replaced}


def stat_value(row: dict[str, Any], stat: str) -> float | None:
    key=str(stat or "").upper().replace(" ","").replace("THREES","3PM")
    pts,reb,ast=row["pts"],row["reb"],row["ast"]
    return {"PTS":pts,"REB":reb,"AST":ast,"3PM":row["threes"],"STL":row["stl"],"BLK":row["blk"],"TOV":row["tov"],"PR":pts+reb,"PA":pts+ast,"RA":reb+ast,"PRA":pts+reb+ast,"PTS+REB":pts+reb,"PTS+AST":pts+ast,"REB+AST":reb+ast,"PTS+REB+AST":pts+reb+ast}.get(key)


def history_for(logs: list[dict[str, Any]], stat: str, limit: int) -> list[dict[str, Any]]:
    history=[]
    for row in logs:
        value=stat_value(row,stat)
        if value is None: continue
        opponent=str(row.get("opponent") or "");opponent_abbr=str(row.get("opponent_abbr") or "") or abbr(opponent)
        history.append({"value":clean_number(value),"opponent":opponent,"opponent_abbr":opponent_abbr or "-","game_date":row.get("game_date"),"game_id":row.get("game_id"),"source":row.get("history_file")})
        if len(history)>=limit: break
    return history


def find_logs(player_logs: dict[str,list[dict[str,Any]]], player: str, player_id:str="") -> list[dict[str,Any]]:
    if player_id and f"id:{player_id}" in player_logs:return player_logs[f"id:{player_id}"]
    key=norm_player(player)
    if key in player_logs:return player_logs[key]
    surname=last_name(player);matches=[rows for name,rows in player_logs.items() if not name.startswith('id:') and last_name(name)==surname]
    return matches[0] if len(matches)==1 else []


def main() -> None:
    players_raw=load_json(PLAYERS,{});players:dict[str,dict[str,Any]]={}
    if isinstance(players_raw,dict):
        for name,row in players_raw.items():
            if isinstance(row,dict):players[norm_player(row.get("player") or name)]=row
    for path in MASTER_PATHS:
        master=load_json(path,{})
        if not isinstance(master,dict) or not master:continue
        target_date=str(master.get("target_date") or date.today().isoformat())[:10];player_logs,diagnostics=load_player_game_logs(target_date);logos=build_team_logos(master);changed=history_count=full5_count=0;missing=[]
        for prop in master.get("props",[]) or []:
            if not isinstance(prop,dict):continue
            player=str(prop.get("player","")).strip();pkey=norm_player(player);prow=players.get(pkey,{});player_id=str(prow.get("player_id") or prop.get("player_id") or "").strip();team=str(prow.get("team") or prop.get("team") or prop.get("player_team") or "").strip();away,home=game_parts(str(prop.get("game") or ""))
            if team not in (away,home) and not team:team=away or home
            opp=home if team==away else away if team==home else ""
            if team:prop["player_team"]=team;prop["team_abbr"]=abbr(team);prop["team_logo"]=logos.get(team,"")
            if opp:prop["opponent"]=opp;prop["opponent_abbr"]=abbr(opp);prop["opponent_logo"]=logos.get(opp,"")
            logs=find_logs(player_logs,player,player_id);last10=history_for(logs,str(prop.get("stat") or ""),10);last5=last10[:5]
            prop["last5"]=last5;prop["last10"]=last10;prop["last5_values"]=[item["value"] for item in last5];prop["last10_values"]=[item["value"] for item in last10]
            prop["last5_average"]=round(sum(prop["last5_values"])/len(last5),2) if last5 else None;prop["last10_average"]=round(sum(prop["last10_values"])/len(last10),2) if last10 else None
            prop["history_source"]="wehoop season boxscores";prop["history_games_available"]=len(last10);prop["latest_completed_game_date"]=last10[0].get("game_date") if last10 else None
            prop["history_integrity_status"]="complete" if len(last5)>=5 and all(x.get("game_id") or x.get("game_date") for x in last5) else "limited"
            if last5:history_count+=1
            if len(last5)>=5:full5_count+=1
            elif player not in missing:missing.append(player)
            changed+=1
        master["prop_history_diagnostics"]={**diagnostics,"props_enriched":changed,"props_with_history":history_count,"props_with_full_last5":full5_count,"players_with_short_history":missing[:50]}
        path.write_text(json.dumps(master,indent=2),encoding="utf-8")
        print(f"V4 prop context enriched {changed} props in {path}; {full5_count} have full last-five history; diagnostics={diagnostics}")

if __name__=="__main__":main()
