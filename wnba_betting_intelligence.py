"""WNBA betting intelligence: query, trend discovery, opportunity scanning, and natural-language research.

Research outputs are descriptive and use the latest stored pregame line per sportsbook.
They do not prove a future betting edge and should be validated out of sample.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DB = Path("data/warehouse/wnba_odds_history.sqlite")
WAREHOUSE_OUT = Path("data/warehouse/wnba_betting_intelligence.json")
DASHBOARD_OUT = Path("data/dashboard/wnba_betting_intelligence.json")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def american_profit(price: float | None, stake: float = 1.0) -> float:
    if price is None or price == 0:
        price = -110
    return stake * (100.0 / abs(price) if price < 0 else price / 100.0)


def roi(wins: int, losses: int, pushes: int = 0, price: float = -110.0) -> float | None:
    risked = wins + losses
    if not risked:
        return None
    profit = wins * american_profit(price) - losses
    return round(100.0 * profit / risked, 2)


def pct(a: int, b: int) -> float | None:
    return round(100.0 * a / b, 2) if b else None


def wilson_low(wins: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adj = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - adj) / den


def load_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    raw = con.execute(
        """
        SELECT g.game_id,g.game_date_utc,g.commence_time_utc,g.away_team,g.home_team,
               g.completed,g.away_score,g.home_score,c.bookmaker_key,c.home_spread,c.total,
               c.home_moneyline,c.away_moneyline,
               (SELECT MIN(o.home_spread) FROM odds o WHERE o.game_id=g.game_id AND o.bookmaker_key=c.bookmaker_key) AS min_home_spread,
               (SELECT MAX(o.home_spread) FROM odds o WHERE o.game_id=g.game_id AND o.bookmaker_key=c.bookmaker_key) AS max_home_spread,
               (SELECT MIN(o.total) FROM odds o WHERE o.game_id=g.game_id AND o.bookmaker_key=c.bookmaker_key) AS min_total,
               (SELECT MAX(o.total) FROM odds o WHERE o.game_id=g.game_id AND o.bookmaker_key=c.bookmaker_key) AS max_total,
               (SELECT COUNT(*) FROM odds o WHERE o.game_id=g.game_id AND o.bookmaker_key=c.bookmaker_key) AS snapshot_count
        FROM games g JOIN closing_odds c ON c.game_id=g.game_id
        ORDER BY g.commence_time_utc,g.game_id,c.bookmaker_key
        """
    ).fetchall()
    rows: list[dict[str, Any]] = []
    for x in raw:
        r = dict(x)
        spread = r.get("home_spread")
        total = r.get("total")
        if r.get("completed") and r.get("home_score") is not None and r.get("away_score") is not None:
            margin = int(r["home_score"]) - int(r["away_score"])
            actual_total = int(r["home_score"]) + int(r["away_score"])
            ats_margin = margin + float(spread) if spread is not None else None
            r["ats_result"] = "PUSH" if ats_margin == 0 else "HOME" if ats_margin and ats_margin > 0 else "AWAY" if ats_margin is not None else "NO_LINE"
            r["total_result"] = "PUSH" if total is not None and actual_total == float(total) else "OVER" if total is not None and actual_total > float(total) else "UNDER" if total is not None else "NO_LINE"
            r["actual_margin"] = margin
            r["actual_total"] = actual_total
        else:
            r["ats_result"] = r["total_result"] = None
        r["favorite_side"] = "HOME" if spread is not None and float(spread) < 0 else "AWAY" if spread is not None and float(spread) > 0 else "PICK"
        r["spread_bucket"] = spread_bucket(spread)
        r["total_bucket"] = total_bucket(total)
        r["spread_move_range"] = round(float(r["max_home_spread"])-float(r["min_home_spread"]), 1) if r.get("min_home_spread") is not None and r.get("max_home_spread") is not None else None
        r["total_move_range"] = round(float(r["max_total"])-float(r["min_total"]), 1) if r.get("min_total") is not None and r.get("max_total") is not None else None
        rows.append(r)
    return rows


def spread_bucket(v: float | None) -> str:
    if v is None: return "no_line"
    a = abs(float(v))
    if a <= 2.5: return "pick_to_2_5"
    if a <= 5.5: return "3_to_5_5"
    if a <= 8.5: return "6_to_8_5"
    return "9_plus"


def total_bucket(v: float | None) -> str:
    if v is None: return "no_line"
    v = float(v)
    if v < 160: return "under_160"
    if v < 170: return "160s"
    if v < 180: return "170s"
    return "180_plus"


def side_records(rows: list[dict[str, Any]], side: str) -> dict[str, Any]:
    wins = sum(r.get("ats_result") == side for r in rows)
    losses = sum(r.get("ats_result") in {"HOME", "AWAY"} and r.get("ats_result") != side for r in rows)
    pushes = sum(r.get("ats_result") == "PUSH" for r in rows)
    n = wins + losses
    return {"wins": wins, "losses": losses, "pushes": pushes, "graded": n, "win_pct": pct(wins, n), "roi_at_minus_110": roi(wins, losses), "wilson_low_pct": round(100*wilson_low(wins,n),2) if n else None}


def total_records(rows: list[dict[str, Any]], target: str) -> dict[str, Any]:
    wins = sum(r.get("total_result") == target for r in rows)
    losses = sum(r.get("total_result") in {"OVER", "UNDER"} and r.get("total_result") != target for r in rows)
    pushes = sum(r.get("total_result") == "PUSH" for r in rows)
    n = wins + losses
    return {"wins": wins, "losses": losses, "pushes": pushes, "graded": n, "win_pct": pct(wins,n), "roi_at_minus_110": roi(wins,losses), "wilson_low_pct": round(100*wilson_low(wins,n),2) if n else None}


def grouped(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str], market: str, min_games: int = 8) -> list[dict[str, Any]]:
    groups: dict[str,list[dict[str,Any]]] = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    out=[]
    for key,items in groups.items():
        if market == "ats_home": rec=side_records(items,"HOME")
        elif market == "ats_away": rec=side_records(items,"AWAY")
        else: rec=total_records(items,market)
        if rec["graded"] >= min_games:
            out.append({"angle":key,**rec})
    return sorted(out,key=lambda x:(x["wilson_low_pct"] or 0,x["graded"]),reverse=True)


def team_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out=[]
    for r in rows:
        for side in ("HOME","AWAY"):
            t=dict(r)
            t["team"] = r["home_team"] if side=="HOME" else r["away_team"]
            t["opponent"] = r["away_team"] if side=="HOME" else r["home_team"]
            t["venue"] = "home" if side=="HOME" else "away"
            t["team_side"] = side
            t["team_ats_result"] = "WIN" if r.get("ats_result")==side else "LOSS" if r.get("ats_result") in {"HOME","AWAY"} else r.get("ats_result")
            t["team_is_favorite"] = r.get("favorite_side")==side
            out.append(t)
    return out


def discover(rows: list[dict[str, Any]], min_games: int = 12) -> list[dict[str, Any]]:
    completed=[r for r in rows if r.get("ats_result")]
    trows=team_rows(completed)
    candidates: list[dict[str,Any]]=[]
    dimensions = {
        "team": lambda r:r["team"],
        "venue": lambda r:r["venue"],
        "favorite_status": lambda r:"favorite" if r["team_is_favorite"] else "underdog",
        "spread_bucket": lambda r:r["spread_bucket"],
        "team_x_venue": lambda r:f"{r['team']}|{r['venue']}",
        "team_x_role": lambda r:f"{r['team']}|{'favorite' if r['team_is_favorite'] else 'underdog'}",
        "venue_x_role_x_bucket": lambda r:f"{r['venue']}|{'favorite' if r['team_is_favorite'] else 'underdog'}|{r['spread_bucket']}",
    }
    for name,fn in dimensions.items():
        groups: dict[str,list[dict[str,Any]]] = defaultdict(list)
        for r in trows: groups[fn(r)].append(r)
        for value,items in groups.items():
            w=sum(x["team_ats_result"]=="WIN" for x in items); l=sum(x["team_ats_result"]=="LOSS" for x in items); p=sum(x["team_ats_result"]=="PUSH" for x in items)
            n=w+l
            if n>=min_games:
                candidates.append({"market":"ATS","dimension":name,"value":value,"wins":w,"losses":l,"pushes":p,"graded":n,"win_pct":pct(w,n),"roi_at_minus_110":roi(w,l),"wilson_low_pct":round(100*wilson_low(w,n),2)})
    for target in ("OVER","UNDER"):
        dims={"team":lambda r:r["team"],"venue":lambda r:r["venue"],"total_bucket":lambda r:r["total_bucket"],"team_x_total_bucket":lambda r:f"{r['team']}|{r['total_bucket']}"}
        for name,fn in dims.items():
            groups=defaultdict(list)
            for r in trows: groups[fn(r)].append(r)
            for value,items in groups.items():
                rec=total_records(items,target)
                if rec["graded"]>=min_games:
                    candidates.append({"market":target,"dimension":name,"value":value,**rec})
    candidates.sort(key=lambda x:((x.get("wilson_low_pct") or 0),x["graded"]),reverse=True)
    return candidates[:100]


def streaks_and_martingale(rows: list[dict[str,Any]], max_steps: int = 5) -> dict[str,Any]:
    trows=team_rows([r for r in rows if r.get("ats_result")])
    by=defaultdict(list)
    for r in trows: by[(r["bookmaker_key"],r["team"])].append(r)
    current=[]
    simulations=[]
    for (book,team),games in by.items():
        games.sort(key=lambda r:r["commence_time_utc"])
        seq=[r["team_ats_result"] for r in games if r["team_ats_result"] in {"WIN","LOSS"}]
        cur_loss=0
        for v in reversed(seq):
            if v=="LOSS": cur_loss+=1
            else: break
        current.append({"bookmaker_key":book,"team":team,"current_ats_loss_streak":cur_loss,"games":len(seq)})
        for trigger in range(1,4):
            cycles=won=failed=0; total_profit=0.0; i=trigger
            while i < len(seq):
                if all(x=="LOSS" for x in seq[i-trigger:i]):
                    cycles+=1; stake=1.0; cycle_profit=0.0; resolved=False
                    for step in range(max_steps):
                        if i+step>=len(seq): break
                        if seq[i+step]=="WIN":
                            cycle_profit += american_profit(-110,stake); won+=1; resolved=True; break
                        cycle_profit -= stake; stake*=2
                    if not resolved: failed+=1
                    total_profit+=cycle_profit
                    i += max_steps
                else: i+=1
            simulations.append({"bookmaker_key":book,"team":team,"trigger_losses":trigger,"max_steps":max_steps,"cycles":cycles,"cycles_won":won,"cycles_failed":failed,"net_units":round(total_profit,2),"warning":"Descriptive backtest; doubling stakes creates severe tail risk."})
    current.sort(key=lambda x:x["current_ats_loss_streak"],reverse=True)
    simulations.sort(key=lambda x:(x["net_units"],x["cycles"]),reverse=True)
    return {"current_streaks":current,"martingale_simulations":simulations}


def scan(rows: list[dict[str,Any]], trends: list[dict[str,Any]]) -> list[dict[str,Any]]:
    upcoming=[r for r in rows if not r.get("completed")]
    strong=[t for t in trends if t["graded"]>=12 and (t.get("wilson_low_pct") or 0)>=50 and (t.get("roi_at_minus_110") or -999)>0]
    out=[]
    for r in upcoming:
        for side,team,venue in (("HOME",r["home_team"],"home"),("AWAY",r["away_team"],"away")):
            role="favorite" if r["favorite_side"]==side else "underdog"
            vals={"team":team,"venue":venue,"favorite_status":role,"spread_bucket":r["spread_bucket"],"team_x_venue":f"{team}|{venue}","team_x_role":f"{team}|{role}","venue_x_role_x_bucket":f"{venue}|{role}|{r['spread_bucket']}"}
            matches=[t for t in strong if t["market"]=="ATS" and vals.get(t["dimension"])==t["value"]]
            if matches:
                score=round(sum((t["wilson_low_pct"]-50)*math.log1p(t["graded"]) for t in matches),2)
                out.append({"game_id":r["game_id"],"commence_time_utc":r["commence_time_utc"],"bookmaker_key":r["bookmaker_key"],"team":team,"side":side,"role":role,"spread":r["home_spread"] if side=="HOME" else -r["home_spread"] if r["home_spread"] is not None else None,"signal_score":score,"matched_angles":matches[:8]})
    return sorted(out,key=lambda x:x["signal_score"],reverse=True)


def natural_query(rows: list[dict[str,Any]], question: str) -> dict[str,Any]:
    q=question.lower(); filtered=team_rows([r for r in rows if r.get("ats_result")])
    teams=sorted({r["team"] for r in filtered},key=len,reverse=True)
    found=next((t for t in teams if t.lower() in q),None)
    if found: filtered=[r for r in filtered if r["team"]==found]
    if "home" in q: filtered=[r for r in filtered if r["venue"]=="home"]
    if "road" in q or "away" in q: filtered=[r for r in filtered if r["venue"]=="away"]
    if "favorite" in q: filtered=[r for r in filtered if r["team_is_favorite"]]
    if "underdog" in q or "dog" in q: filtered=[r for r in filtered if not r["team_is_favorite"]]
    market="ATS"
    if "over" in q: market="OVER"
    elif "under" in q: market="UNDER"
    if market=="ATS":
        w=sum(r["team_ats_result"]=="WIN" for r in filtered); l=sum(r["team_ats_result"]=="LOSS" for r in filtered); p=sum(r["team_ats_result"]=="PUSH" for r in filtered)
        result={"wins":w,"losses":l,"pushes":p,"graded":w+l,"win_pct":pct(w,w+l),"roi_at_minus_110":roi(w,l)}
    else: result=total_records(filtered,market)
    return {"question":question,"interpreted":{"team":found,"market":market,"filters_detected":[x for x in ("home" if "home" in q else None,"away" if "away" in q or "road" in q else None,"favorite" if "favorite" in q else None,"underdog" if "underdog" in q or "dog" in q else None) if x]},"result":result,"sample_games":filtered[-20:]}


def build(db_path: Path=DB, min_games: int=12) -> dict[str,Any]:
    if not db_path.exists(): raise SystemExit(f"Warehouse not found: {db_path}")
    con=sqlite3.connect(db_path); rows=load_rows(con); con.close()
    completed=[r for r in rows if r.get("ats_result")]
    trends=discover(rows,min_games)
    streak_data=streaks_and_martingale(rows)
    payload={
        "generated_at_utc":now_utc(),"status":"ready" if completed else "waiting_for_results","database":str(db_path),
        "summary":{"game_book_rows":len(rows),"completed_game_book_rows":len(completed),"discovered_trends":len(trends),"upcoming_opportunities":0},
        "research_api":{
            "ats_by_book":grouped(completed,lambda r:r["bookmaker_key"],"ats_home",min_games=1),
            "home_ats_by_spread_bucket":grouped(completed,lambda r:f"{r['bookmaker_key']}|{r['spread_bucket']}","ats_home",min_games=5),
            "overs_by_total_bucket":grouped(completed,lambda r:f"{r['bookmaker_key']}|{r['total_bucket']}","OVER",min_games=5),
            "unders_by_total_bucket":grouped(completed,lambda r:f"{r['bookmaker_key']}|{r['total_bucket']}","UNDER",min_games=5),
        },
        "trend_discovery":trends,
        "streak_and_martingale":streak_data,
        "opportunity_scanner":[],
        "natural_language_examples":["Indiana Fever as a road underdog ATS","home favorites ATS","unders in 170s totals"],
        "methodology":{"minimum_games":min_games,"default_price":-110,"ranking":"Wilson lower confidence bound, then sample size","warning":"Patterns are exploratory. Validate on unseen seasons before wagering."},
    }
    payload["opportunity_scanner"]=scan(rows,trends)
    payload["summary"]["upcoming_opportunities"]=len(payload["opportunity_scanner"])
    for p in (WAREHOUSE_OUT,DASHBOARD_OUT):
        p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(payload["summary"],indent=2))
    return payload


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",type=Path,default=DB)
    ap.add_argument("--min-games",type=int,default=12)
    ap.add_argument("--ask",default=None,help="Natural-language warehouse query")
    args=ap.parse_args()
    if args.ask:
        con=sqlite3.connect(args.db); data=natural_query(load_rows(con),args.ask); con.close(); print(json.dumps(data,indent=2,allow_nan=False))
    else: build(args.db,args.min_games)


if __name__=="__main__": main()
