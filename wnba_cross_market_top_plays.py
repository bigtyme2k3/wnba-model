"""Rank game and player markets into one constrained Top Plays board.

Primary inputs are the unified player simulation, verified streak context, game
market model, and historical CLV context. Scores are calibrated to preserve
separation between plays; 99 is reserved for truly exceptional, fully supported
markets rather than being a routine ceiling value.
"""
from __future__ import annotations
import argparse,json,math
from collections import defaultdict
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
ALT=Path('data/dashboard/wnba_alt_streaks.json')
GAMES=Path('data/dashboard/wnba_game_market_model.json')
CLV=Path('data/dashboard/wnba_alt_performance.json')
OUTS=[Path('data/warehouse/wnba_cross_market_top_plays.json'),Path('data/dashboard/wnba_cross_market_top_plays.json')]
MAX_TOTAL_UNITS=5.0;MAX_GAME_UNITS=2.0;MAX_PLAYER_PRIMARY=1

def load(path:Path,default:Any)->Any:
    try:return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:return default
def dump(path:Path,payload:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True);json.dump(payload,path.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().split())
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def quality_score(v:Any)->float:return {'complete':92,'partial':72,'limited':48,'volatile':35}.get(str(v or '').lower(),55)
def risk_label(score:float)->str:return 'Low' if score>=86 else 'Medium' if score>=74 else 'High'
def score_tier(score:float)->str:
    return 'ELITE' if score>=95 else 'PREMIUM' if score>=90 else 'STRONG' if score>=84 else 'SOLID' if score>=78 else 'LEAN' if score>=70 else 'WATCH'
def action(score:float,ev:float|None,prob:float|None)->str:
    if ev is not None and prob is not None and score>=84 and ev>=.05 and prob>=.56:return 'BET'
    if score>=74 and ev is not None and ev>0:return 'LEAN'
    if score>=64:return 'WATCH'
    return 'PASS'
def clv_context()->dict[str,float|None]:
    payload=load(CLV,{});summary=payload.get('clv',{}).get('summary',{}) if isinstance(payload,dict) else {}
    return {'positive_rate':num(summary.get('positive_rate')),'average_line_clv':num(summary.get('average_line_clv'))}
def score_candidate(row:dict[str,Any],clv:dict[str,float|None])->dict[str,Any]:
    ev=num(row.get('expected_value_per_unit'));prob=num(row.get('hit_probability'));confidence=clamp(num(row.get('confidence')) or 50,0,96)
    quality=quality_score(row.get('data_quality_status'));injury=str(row.get('injury_status') or 'ACTIVE').upper();volatility=0
    if injury in {'QUESTIONABLE','GTD','DOUBTFUL','UNKNOWN'}:volatility=14
    elif injury=='OUT':volatility=35
    price=num(row.get('odds'));price_quality=50 if price is None else clamp(88-abs(price+110)*.12,40,92)
    ev_score=45 if ev is None else clamp(48+ev*135,20,96)
    prob_score=45 if prob is None else clamp(50+(prob-.50)*165,20,96)
    clv_score=50
    if clv.get('positive_rate') is not None:clv_score=clamp(42+float(clv['positive_rate'])*45,35,90)
    base=.28*ev_score+.24*prob_score+.18*confidence+.12*quality+.08*price_quality+.10*clv_score
    support_penalty=0
    if ev is None:support_penalty+=8
    if prob is None:support_penalty+=8
    if str(row.get('data_quality_status') or '').lower()!='complete':support_penalty+=3
    score=clamp(base-volatility-support_penalty,0,97)
    exceptional=prob is not None and prob>=.72 and ev is not None and ev>=.20 and confidence>=92 and quality>=90 and volatility==0
    if exceptional:score=min(99,score+2)
    row['ranking_components']={'ev':round(ev_score,1),'probability':round(prob_score,1),'confidence':round(confidence,1),'data_quality':round(quality,1),'price_quality':round(price_quality,1),'clv_history':round(clv_score,1),'volatility_penalty':volatility,'support_penalty':support_penalty}
    row['top_play_score']=round(score,1);row['score_tier']=score_tier(score);row['risk_level']=risk_label(score);row['decision']=action(score,ev,prob)
    row['raw_recommended_units']=round(clamp(num(row.get('recommended_units')) or 0,0,1),2);return row

def player_candidates()->list[dict[str,Any]]:
    payload=load(UNIFIED,{'players':[]});out=[]
    for p in payload.get('players',[]):
        if not isinstance(p,dict):continue
        for market in p.get('markets',[]):
            if not isinstance(market,dict) or num(market.get('odds')) is None:continue
            out.append({'market_type':'PLAYER_PROP','player':p.get('player'),'team':p.get('team'),'opponent':p.get('opponent'),'game':f"{p.get('team','')} vs {p.get('opponent','')}",'stat':market.get('stat'),'side':market.get('side'),'line':market.get('line'),'odds':num(market.get('odds')),'sportsbook':market.get('sportsbook'),'hit_probability':market.get('hit_probability'),'expected_value_per_unit':market.get('expected_value_per_unit'),'recommended_units':market.get('recommended_units'),'confidence':p.get('confidence'),'data_quality_status':p.get('data_quality_status'),'injury_status':p.get('injury_status'),'source':'unified_player_simulation_v2'})
    return out
def alt_candidates()->list[dict[str,Any]]:
    payload=load(ALT,{'rows':[]});out=[]
    for r in payload.get('rows',[]):
        if not isinstance(r,dict) or r.get('line_type')!='alternate' or num(r.get('best_odds')) is None:continue
        out.append({'market_type':'ALT_PROP','player':r.get('player'),'team':r.get('team'),'opponent':r.get('opponent'),'game':r.get('game'),'stat':r.get('stat'),'side':r.get('side'),'line':r.get('alt_line'),'odds':num(r.get('best_odds')),'sportsbook':r.get('best_book'),'hit_probability':r.get('l10_pct') or r.get('season_pct'),'expected_value_per_unit':r.get('expected_edge'),'recommended_units':min(1,max(0,(num(r.get('streak_score')) or 0)-70)/25),'confidence':r.get('streak_score'),'data_quality_status':'complete' if r.get('history_source')=='player_game_log_warehouse' else 'partial','injury_status':r.get('injury_status'),'source':'alt_streak_confidence'})
    return out
def game_candidates()->list[dict[str,Any]]:
    payload=load(GAMES,{});rows=payload.get('markets',[]) or payload.get('games',[]) or [];out=[]
    for r in rows:
        if not isinstance(r,dict):continue
        game=r.get('game') or f"{r.get('away_team','')} @ {r.get('home_team','')}"
        for kind in ('spread','total'):
            side=r.get(f'{kind}_pick') or r.get(f'predicted_{kind}_side');line=num(r.get(f'{kind}_line') or r.get('line') if r.get('market_type')==kind else None);odds=num(r.get(f'{kind}_odds') or r.get('odds') if r.get('market_type')==kind else None);prob=num(r.get(f'{kind}_probability') or r.get('probability') if r.get('market_type')==kind else None);ev=num(r.get(f'{kind}_ev') or r.get('expected_value_per_unit') if r.get('market_type')==kind else None)
            if not side or line is None or odds is None:continue
            out.append({'market_type':'GAME_'+kind.upper(),'player':None,'team':r.get('team'),'opponent':None,'game':game,'stat':kind.upper(),'side':side,'line':line,'odds':odds,'sportsbook':r.get(f'{kind}_book') or r.get('sportsbook'),'hit_probability':prob,'expected_value_per_unit':ev,'recommended_units':r.get('recommended_units') or .5,'confidence':r.get(f'{kind}_confidence') or r.get('confidence') or 65,'data_quality_status':r.get('data_quality_status') or 'partial','injury_status':'ACTIVE','source':'game_market_model'})
    return out
def dedupe(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    best={}
    for r in rows:
        key=(norm(r.get('player')),norm(r.get('game')),str(r.get('stat')),str(r.get('side')),num(r.get('line')));current=best.get(key)
        if current is None or (num(r.get('expected_value_per_unit')) or -999)>(num(current.get('expected_value_per_unit')) or -999):best[key]=r
    return list(best.values())
def allocate(rows:list[dict[str,Any]])->list[dict[str,Any]]:
    selected=[];total=0.0;game_units=defaultdict(float);player_primary=defaultdict(int)
    for r in rows:
        units=num(r.get('raw_recommended_units')) or 0
        if r['decision'] not in {'BET','LEAN'}:r['recommended_units_final']=0;selected.append(r);continue
        player=norm(r.get('player'));game=norm(r.get('game'))
        if player and player_primary[player]>=MAX_PLAYER_PRIMARY:r['exposure_penalty']='secondary_player_market';r['decision']='WATCH';r['recommended_units_final']=0;selected.append(r);continue
        allowed=max(0,min(units,MAX_TOTAL_UNITS-total,MAX_GAME_UNITS-game_units[game]))
        if allowed<.1:r['exposure_penalty']='portfolio_cap';r['decision']='WATCH';r['recommended_units_final']=0
        else:
            r['recommended_units_final']=round(allowed,2);total+=allowed;game_units[game]+=allowed
            if player:player_primary[player]+=1
        selected.append(r)
    return selected
def build(target:str)->dict[str,Any]:
    clv=clv_context();rows=[score_candidate(r,clv) for r in dedupe(player_candidates()+alt_candidates()+game_candidates())]
    rows.sort(key=lambda r:(r['top_play_score'],num(r.get('expected_value_per_unit')) or -999),reverse=True);rows=allocate(rows)
    actionable=[r for r in rows if r['decision'] in {'BET','LEAN'} and (num(r.get('recommended_units_final')) or 0)>0]
    for i,r in enumerate(rows,1):r['rank']=i
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'candidates':len(rows),'bets':sum(r['decision']=='BET' for r in rows),'leans':sum(r['decision']=='LEAN' for r in rows),'watches':sum(r['decision']=='WATCH' for r in rows),'passes':sum(r['decision']=='PASS' for r in rows),'allocated_units':round(sum(num(r.get('recommended_units_final')) or 0 for r in rows),2),'elite':sum(r['score_tier']=='ELITE' for r in rows),'premium':sum(r['score_tier']=='PREMIUM' for r in rows),'strong':sum(r['score_tier']=='STRONG' for r in rows)},'top_plays':rows[:25],'portfolio':actionable,'methodology':{'score_weights':{'expected_value':.28,'hit_probability':.24,'confidence':.18,'data_quality':.12,'price_quality':.08,'clv_history':.10},'score_policy':'calibrated 0-99 scale; 99 requires exceptional probability, EV, confidence, quality, and clean availability','constraints':{'max_total_units':MAX_TOTAL_UNITS,'max_game_units':MAX_GAME_UNITS,'max_primary_plays_per_player':MAX_PLAYER_PRIMARY},'stale_price_policy':'markets without verified odds are excluded','dedupe_policy':'same player/game/stat/side/line keeps highest EV price','market_policy':'game, standard prop, and verified alternate prop candidates ranked together'}}
    for p in OUTS:dump(p,payload)
    print('Cross-Market Top Plays:',payload['summary']);return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));args=ap.parse_args();build(args.date)
if __name__=='__main__':main()
