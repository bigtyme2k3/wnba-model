"""Build betting intelligence from the unified WNBA Odds Warehouse V2.

Outputs normalized intelligence tables in SQLite plus dashboard-ready JSON.
Only graded wagers are used for ROI. CLV and movement use opening/closing
snapshots for the same event/book/market/outcome.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path("data/warehouse/wnba_odds_warehouse_v2.sqlite")
OUT = Path("data/dashboard/wnba_betting_intelligence.json")
WAREHOUSE_OUT = Path("data/warehouse/wnba_betting_intelligence.json")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pct(n: float, d: float) -> float | None:
    return None if not d else round(100.0 * n / d, 2)


def avg(values: list[float]) -> float | None:
    return None if not values else round(sum(values) / len(values), 4)


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript("""
    CREATE TABLE IF NOT EXISTS roi_intelligence(
      dimension_type TEXT NOT NULL,
      dimension_value TEXT NOT NULL,
      bets INTEGER NOT NULL,
      wins INTEGER NOT NULL,
      losses INTEGER NOT NULL,
      pushes INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_price REAL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(dimension_type,dimension_value)
    );
    CREATE TABLE IF NOT EXISTS clv_intelligence(
      dimension_type TEXT NOT NULL,
      dimension_value TEXT NOT NULL,
      observations INTEGER NOT NULL,
      avg_line_move REAL,
      avg_price_move REAL,
      beat_close_pct REAL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(dimension_type,dimension_value)
    );
    CREATE TABLE IF NOT EXISTS sportsbook_intelligence(
      sportsbook TEXT PRIMARY KEY,
      graded_bets INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_price REAL,
      avg_line_move REAL,
      avg_price_move REAL,
      generated_at_utc TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS market_intelligence(
      market TEXT PRIMARY KEY,
      graded_bets INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      avg_price REAL,
      avg_line_move REAL,
      avg_price_move REAL,
      generated_at_utc TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS team_intelligence(
      team TEXT NOT NULL,
      market TEXT NOT NULL,
      graded_bets INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(team,market)
    );
    CREATE TABLE IF NOT EXISTS player_intelligence(
      player TEXT NOT NULL,
      market TEXT NOT NULL,
      graded_bets INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      generated_at_utc TEXT NOT NULL,
      PRIMARY KEY(player,market)
    );
    CREATE TABLE IF NOT EXISTS trend_intelligence(
      trend_key TEXT PRIMARY KEY,
      category TEXT NOT NULL,
      label TEXT NOT NULL,
      sample_size INTEGER NOT NULL,
      win_pct REAL,
      units REAL NOT NULL,
      roi_pct REAL,
      confidence TEXT NOT NULL,
      generated_at_utc TEXT NOT NULL
    );
    """)


def graded_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute("""
      SELECT w.*, g.grade, g.profit_units, e.home_team, e.away_team,
             e.game_date_utc, s.returned_at_utc
      FROM wagers w
      JOIN grades g ON g.wager_id=w.wager_id
      JOIN events e ON e.event_id=w.event_id
      JOIN snapshots s ON s.snapshot_id=w.snapshot_id
      WHERE g.grade IN ('win','loss','push')
    """).fetchall())


def movement_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    data = list(con.execute("""
      SELECT w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,w.selection,
             w.participant,w.point,w.american_price,s.returned_at_utc,e.commence_time_utc
      FROM wagers w
      JOIN snapshots s ON s.snapshot_id=w.snapshot_id
      JOIN events e ON e.event_id=w.event_id
      WHERE s.returned_at_utc<=e.commence_time_utc
      ORDER BY w.event_id,w.bookmaker_key,w.market_key,w.outcome_key,s.returned_at_utc
    """).fetchall())
    groups: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in data:
        groups[(row["event_id"],row["bookmaker_key"],row["market_key"],row["outcome_key"])].append(row)
    out: list[dict[str, Any]] = []
    for key, rows in groups.items():
        if not rows:
            continue
        opening, closing = rows[0], rows[-1]
        op, cp = opening["point"], closing["point"]
        oo, co = opening["american_price"], closing["american_price"]
        line_move = None if op is None or cp is None else float(cp)-float(op)
        price_move = None if oo is None or co is None else int(co)-int(oo)
        selection = str(closing["selection"])
        favorable = None
        if line_move is not None:
            if selection == "Over": favorable = line_move > 0
            elif selection == "Under": favorable = line_move < 0
            else: favorable = line_move > 0
        elif price_move is not None:
            favorable = price_move > 0
        out.append({
          "event_id":key[0],"sportsbook":key[1],"market":key[2],"outcome_key":key[3],
          "participant":closing["participant"],"selection":selection,
          "opening_line":op,"closing_line":cp,"line_move":line_move,
          "opening_price":oo,"closing_price":co,"price_move":price_move,
          "beat_close":favorable,
        })
    return out


def summarize(rows: list[sqlite3.Row], key_fn) -> list[dict[str, Any]]:
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        groups[str(key_fn(r))].append(r)
    result=[]
    for key, rs in groups.items():
        wins=sum(r["grade"]=="win" for r in rs); losses=sum(r["grade"]=="loss" for r in rs); pushes=sum(r["grade"]=="push" for r in rs)
        settled=wins+losses; units=sum(float(r["profit_units"] or 0) for r in rs); bets=len(rs)
        prices=[float(r["american_price"]) for r in rs if r["american_price"] is not None]
        result.append({"key":key,"bets":bets,"wins":wins,"losses":losses,"pushes":pushes,
                       "win_pct":pct(wins,settled),"units":round(units,4),"roi_pct":pct(units,bets),"avg_price":avg(prices)})
    return sorted(result,key=lambda x:(x["roi_pct"] if x["roi_pct"] is not None else -999,x["bets"]),reverse=True)


def movement_summary(rows: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    groups: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in rows: groups[str(r[key_name])].append(r)
    out=[]
    for key,rs in groups.items():
        lm=[float(r["line_move"]) for r in rs if r["line_move"] is not None]
        pm=[float(r["price_move"]) for r in rs if r["price_move"] is not None]
        known=[r for r in rs if r["beat_close"] is not None]
        out.append({"key":key,"observations":len(rs),"avg_line_move":avg(lm),"avg_price_move":avg(pm),
                    "beat_close_pct":pct(sum(bool(r["beat_close"]) for r in known),len(known))})
    return sorted(out,key=lambda x:x["observations"],reverse=True)


def confidence(sample: int) -> str:
    return "high" if sample>=100 else "medium" if sample>=40 else "low"


def build(db: Path) -> dict[str, Any]:
    if not db.exists(): raise SystemExit(f"Warehouse not found: {db}")
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row; ensure_schema(con)
    graded=graded_rows(con); moves=movement_rows(con); stamp=now()
    by_book=summarize(graded,lambda r:r["bookmaker_key"])
    by_market=summarize(graded,lambda r:r["market_key"])
    by_team=summarize([r for r in graded if r["selection"] in (r["home_team"],r["away_team"])],lambda r:f"{r['selection']}|{r['market_key']}")
    by_player=summarize([r for r in graded if str(r["market_key"]).startswith("player_")],lambda r:f"{r['participant']}|{r['market_key']}")
    mv_book=movement_summary(moves,"sportsbook"); mv_market=movement_summary(moves,"market")
    mvb={x['key']:x for x in mv_book}; mvm={x['key']:x for x in mv_market}

    con.execute("DELETE FROM roi_intelligence"); con.execute("DELETE FROM clv_intelligence")
    con.execute("DELETE FROM sportsbook_intelligence"); con.execute("DELETE FROM market_intelligence")
    con.execute("DELETE FROM team_intelligence"); con.execute("DELETE FROM player_intelligence"); con.execute("DELETE FROM trend_intelligence")
    for dim,items in (("sportsbook",by_book),("market",by_market)):
        for x in items:
            con.execute("INSERT INTO roi_intelligence VALUES(?,?,?,?,?,?,?,?,?,?,?)",(dim,x['key'],x['bets'],x['wins'],x['losses'],x['pushes'],x['win_pct'],x['units'],x['roi_pct'],x['avg_price'],stamp))
    for dim,items in (("sportsbook",mv_book),("market",mv_market)):
        for x in items:
            con.execute("INSERT INTO clv_intelligence VALUES(?,?,?,?,?,?,?)",(dim,x['key'],x['observations'],x['avg_line_move'],x['avg_price_move'],x['beat_close_pct'],stamp))
    for x in by_book:
        m=mvb.get(x['key'],{})
        con.execute("INSERT INTO sportsbook_intelligence VALUES(?,?,?,?,?,?,?,?,?)",(x['key'],x['bets'],x['win_pct'],x['units'],x['roi_pct'],x['avg_price'],m.get('avg_line_move'),m.get('avg_price_move'),stamp))
    for x in by_market:
        m=mvm.get(x['key'],{})
        con.execute("INSERT INTO market_intelligence VALUES(?,?,?,?,?,?,?,?,?)",(x['key'],x['bets'],x['win_pct'],x['units'],x['roi_pct'],x['avg_price'],m.get('avg_line_move'),m.get('avg_price_move'),stamp))
    for x in by_team:
        team,market=x['key'].rsplit('|',1); con.execute("INSERT INTO team_intelligence VALUES(?,?,?,?,?,?,?)",(team,market,x['bets'],x['win_pct'],x['units'],x['roi_pct'],stamp))
    for x in by_player:
        player,market=x['key'].rsplit('|',1); con.execute("INSERT INTO player_intelligence VALUES(?,?,?,?,?,?,?)",(player,market,x['bets'],x['win_pct'],x['units'],x['roi_pct'],stamp))
    trends=[]
    for category,items in (("sportsbook",by_book),("market",by_market),("team_market",by_team),("player_market",by_player)):
        for x in items:
            if x['bets']<20: continue
            trends.append({"trend_key":f"{category}|{x['key']}","category":category,"label":x['key'],"sample_size":x['bets'],"win_pct":x['win_pct'],"units":x['units'],"roi_pct":x['roi_pct'],"confidence":confidence(x['bets'])})
    trends=sorted(trends,key=lambda x:(x['roi_pct'] if x['roi_pct'] is not None else -999,x['sample_size']),reverse=True)
    for x in trends:
        con.execute("INSERT INTO trend_intelligence VALUES(?,?,?,?,?,?,?,?,?)",(x['trend_key'],x['category'],x['label'],x['sample_size'],x['win_pct'],x['units'],x['roi_pct'],x['confidence'],stamp))
    con.commit()
    payload={"generated_at_utc":stamp,"database":str(db),"graded_wagers":len(graded),"movement_series":len(moves),
             "sportsbooks":by_book,"markets":by_market,"team_markets":by_team[:100],"player_markets":by_player[:100],
             "clv_by_sportsbook":mv_book,"clv_by_market":mv_market,"top_trends":trends[:100],
             "health":{"has_graded_wagers":bool(graded),"has_line_movement":any(x['observations']>0 for x in mv_book),"tables_built":7}}
    for path in (OUT,WAREHOUSE_OUT):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return payload


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--db",type=Path,default=DB); args=p.parse_args()
    print(json.dumps(build(args.db),indent=2))


if __name__=="__main__": main()
