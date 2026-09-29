from __future__ import annotations
import csv,json,math
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(".")
LOG=ROOT/"data/raw/player_game_logs_2026.csv"
M02=ROOT/"data/dashboard/wnba_s19_m02_predictions.json"
OUT=ROOT/"data/dashboard/wnba_playoff_rotation_shadow.json"
PLAYOFF_START="2026-09-27"

def norm(x): return " ".join(str(x or "").lower().replace("’","'").split())
def f(x):
    try:
        y=float(x); return y if math.isfinite(y) else None
    except: return None

def main():
    payload=json.loads(M02.read_text())
    target=str(payload.get("target_date",""))[:10]
    rows=list(csv.DictReader(LOG.open(encoding="utf-8")))
    by={}
    for r in rows:
        d=str(r.get("game_date",""))[:10]; m=f(r.get("minutes"))
        if not r.get("player") or m is None or d>=PLAYOFF_START: continue
        by.setdefault(norm(r["player"]),[]).append((d,m))
    box=ROOT/f"data/raw/wnba_boxscores_{PLAYOFF_START}.json"
    g1=json.loads(box.read_text()).get("players",[]) if box.exists() else []
    g1m={norm(r.get("player")):f(r.get("minutes")) for r in g1 if r.get("player")}
    player_ctx={}
    for p in payload.get("player_props",[]):
        key=norm(p.get("player"))
        if key in player_ctx: continue
        hist=sorted(by.get(key,[]),key=lambda x:x[0])[-10:]
        base=sum(x[1] for x in hist)/len(hist) if hist else None
        gm=g1m.get(key)
        if base and gm is not None:
            raw=gm/base
            # One playoff game is informative, not definitive. Blend 35% of the
            # observed minute shift and cap projection impact at +/-10%.
            factor=max(.90,min(1.10,1.0+0.35*(raw-1.0)))
            exp=base*factor
        else: factor=1.0; exp=base
        player_ctx[key]={"player":p.get("player"),"regular_l10_minutes":round(base,2) if base else None,
          "game1_minutes":gm,"observed_game1_ratio":round(gm/base,3) if base and gm is not None else None,
          "shadow_minutes_factor":round(factor,4),"shadow_expected_minutes":round(exp,2) if exp else None,
          "sample_games":len(hist)}
    shadow=[]
    for p in payload.get("player_props",[]):
        c=player_ctx[norm(p.get("player"))]; proj=f(p.get("model_projection"))
        item={k:p.get(k) for k in ("player","team","game","stat","line","recommendation","confidence","final_action")}
        item.update(c)
        item["production_projection"]=proj
        item["shadow_projection"]=round(proj*c["shadow_minutes_factor"],2) if proj is not None else None
        item["shadow_edge"]=round(item["shadow_projection"]-float(p["line"]),2) if item["shadow_projection"] is not None and f(p.get("line")) is not None else None
        item["research_only"]=True
        shadow.append(item)
    out={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"target_date":target,
      "status":"SHADOW","production_mutation":False,"method":"L10 regular-season minutes vs Game 1; 35% blend; projection factor capped +/-10%",
      "players":list(player_ctx.values()),"rows":shadow}
    OUT.write_text(json.dumps(out,indent=2)+"\n")
if __name__=="__main__": main()
