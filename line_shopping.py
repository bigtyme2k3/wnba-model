"""
line_shopping.py
----------------
Collects per-book WNBA lines from The Odds API so the dashboard can recommend
where to bet, not just what to bet.
"""

from __future__ import annotations

import argparse, json, os, time
from datetime import date, datetime, timezone
import pandas as pd
import requests

API_KEY = os.getenv("ODDS_API_KEY")
SPORT = "basketball_wnba"
BASE_URL = "https://api.the-odds-api.com/v4/sports"
REGIONS = "us"
ODDS_FMT = "american"
GAME_MARKETS = "h2h,spreads,totals"
PROP_MARKETS = {
    "player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST", "player_threes": "3PM",
    "player_points_rebounds_assists": "PRA", "player_points_assists": "PA", "player_points_rebounds": "PR",
    "player_rebounds_assists": "RA", "player_double_double": "DD", "player_triple_double": "TD",
}
PREFERRED_BOOKS = {"draftkings", "fanduel", "fanatics", "betmgm", "espnbet", "caesars"}
COLUMNS = ["game_date","event_id","game","commence_time","market_type","market_key","side","team","player","stat","book_key","book_title","line","odds","is_preferred_book","source","scraped_at"]


def empty_df(): return pd.DataFrame(columns=COLUMNS)


def api_get(path, params):
    if not API_KEY: raise ValueError("ODDS_API_KEY not set")
    url=f"{BASE_URL}/{SPORT}{path}"; resp=requests.get(url,params={"apiKey":API_KEY,**params},timeout=20)
    print(f"  GET {path}: HTTP {resp.status_code} | used {resp.headers.get('x-requests-used','?')} remaining {resp.headers.get('x-requests-remaining','?')}")
    if resp.status_code in (404,422): return [] if path in {"/odds","/events"} else {}
    resp.raise_for_status(); return resp.json()


def parse_game_markets(games,target_date):
    rows=[]; events=[]; scraped_at=datetime.now(timezone.utc).isoformat()
    for g in games or []:
        eid=g.get("id",""); home=g.get("home_team",""); away=g.get("away_team",""); game=f"{away} @ {home}"
        events.append({"id":eid,"home_team":home,"away_team":away,"commence_time":g.get("commence_time","")})
        for book in g.get("bookmakers",[]) or []:
            bkey=book.get("key",""); btitle=book.get("title",bkey)
            for mkt in book.get("markets",[]) or []:
                key=mkt.get("key")
                for outcome in mkt.get("outcomes",[]) or []:
                    name=outcome.get("name",""); point=outcome.get("point"); price=outcome.get("price")
                    if price is None: continue
                    if key=="spreads": market_type,side,team="SPREAD",name,name
                    elif key=="totals": market_type,side,team="TOTAL",name.upper(),""
                    elif key=="h2h": market_type,side,team="MONEYLINE",name,name
                    else: continue
                    rows.append({"game_date":target_date,"event_id":eid,"game":game,"commence_time":g.get("commence_time",""),"market_type":market_type,"market_key":key,"side":side,"team":team,"player":"","stat":"","book_key":bkey,"book_title":btitle,"line":point,"odds":price,"is_preferred_book":bkey in PREFERRED_BOOKS,"source":"the-odds-api","scraped_at":scraped_at})
    return rows,events


def parse_prop_event(event_data,target_date):
    if not event_data: return []
    rows=[]; scraped_at=datetime.now(timezone.utc).isoformat(); eid=event_data.get("id",""); home=event_data.get("home_team",""); away=event_data.get("away_team",""); game=f"{away} @ {home}"
    for book in event_data.get("bookmakers",[]) or []:
        bkey=book.get("key",""); btitle=book.get("title",bkey)
        for mkt in book.get("markets",[]) or []:
            mkey=mkt.get("key"); stat=PROP_MARKETS.get(mkey)
            if not stat: continue
            for outcome in mkt.get("outcomes",[]) or []:
                player=outcome.get("description") or ""; side=str(outcome.get("name","")).upper(); point=outcome.get("point"); price=outcome.get("price")
                if not player or price is None: continue
                if side not in {"OVER","UNDER","YES","NO","RECORD"}: continue
                if point is None: point=0.5
                rows.append({"game_date":target_date,"event_id":eid,"game":game,"commence_time":event_data.get("commence_time",""),"market_type":"PROP","market_key":mkey,"side":"YES" if side=="RECORD" else side,"team":"","player":player,"stat":stat,"book_key":bkey,"book_title":btitle,"line":point,"odds":price,"is_preferred_book":bkey in PREFERRED_BOOKS,"source":"the-odds-api","scraped_at":scraped_at})
    return rows


def summarize_best(df):
    if df.empty: return pd.DataFrame()
    rows=[]; group_cols=["market_type","game","player","stat","side"]
    for keys,g in df.groupby(group_cols,dropna=False):
        g=g.copy(); side=keys[4]
        if keys[0]=="SPREAD": g=g.sort_values(["line","odds"],ascending=[False,False])
        elif keys[0] in {"TOTAL","PROP"} and side=="OVER": g=g.sort_values(["line","odds"],ascending=[True,False])
        elif keys[0] in {"TOTAL","PROP"} and side=="UNDER": g=g.sort_values(["line","odds"],ascending=[False,False])
        else: g=g.sort_values(["odds"],ascending=[False])
        best=g.iloc[0].to_dict(); best["available_books"]=int(g["book_key"].nunique()); best["all_books"]=",".join(sorted(set(g["book_key"].dropna().astype(str)))); rows.append(best)
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--date",default=str(date.today())); parser.add_argument("--out",default="data/raw"); parser.add_argument("--delay",type=float,default=1.0); args=parser.parse_args(); os.makedirs(args.out,exist_ok=True)
    print(f"\n═══ LINE SHOPPING — {args.date} ═══\n"); status={"status":"unknown","target_date":args.date,"rows":0,"events":0,"books":[],"error":None}
    try:
        games=api_get("/odds",{"regions":REGIONS,"markets":GAME_MARKETS,"oddsFormat":ODDS_FMT}); rows,events=parse_game_markets(games,args.date); status["events"]=len(events)
        for event in events:
            eid=event.get("id")
            if not eid: continue
            data=api_get(f"/events/{eid}/odds",{"regions":REGIONS,"markets":".".join([]) if False else ",".join(PROP_MARKETS.keys()),"oddsFormat":ODDS_FMT})
            rows.extend(parse_prop_event(data,args.date)); time.sleep(args.delay)
        df=pd.DataFrame(rows,columns=COLUMNS) if rows else empty_df(); status["rows"]=int(len(df)); status["books"]=sorted(df["book_key"].dropna().unique().tolist()) if not df.empty else []; status["status"]="ok" if not df.empty else "empty"
        today=os.path.join(args.out,"line_shopping_today.csv"); dated=os.path.join(args.out,f"line_shopping_{args.date}.csv"); best_today=os.path.join(args.out,"line_shopping_best_today.csv"); best_dated=os.path.join(args.out,f"line_shopping_best_{args.date}.csv")
        df.to_csv(today,index=False); df.to_csv(dated,index=False); best=summarize_best(df); best.to_csv(best_today,index=False); best.to_csv(best_dated,index=False)
        print(f"  Saved → {today} ({len(df)} rows)"); print(f"  Saved → {best_today} ({len(best)} best-line rows)")
        if not best.empty: print(best[["market_type","game","player","stat","side","book_key","line","odds","available_books"]].head(25).to_string(index=False))
    except Exception as exc:
        status["status"]="error"; status["error"]=str(exc); print(f"  [ERROR] {exc}"); empty_df().to_csv(os.path.join(args.out,"line_shopping_today.csv"),index=False)
    with open(os.path.join(args.out,"line_shopping_status.json"),"w") as f: json.dump(status,f,indent=2)
    print("✅ Line shopping complete.")

if __name__=="__main__": main()
