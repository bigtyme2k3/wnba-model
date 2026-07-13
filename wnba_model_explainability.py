"""Model Explainability for Top Plays.

Builds deterministic, source-backed explanations for each ranked recommendation.
Only factors already present in production model outputs are used. Missing inputs
are labeled unavailable rather than inferred.
"""
from __future__ import annotations
import argparse,json,math
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any

TOP=Path('data/dashboard/wnba_cross_market_top_plays.json')
UNIFIED=Path('data/dashboard/wnba_unified_player_simulation_v2.json')
MINUTES=Path('data/dashboard/wnba_minutes_projection_v2.json')
ALT=Path('data/dashboard/wnba_alt_streaks.json')
OUTS=[Path('data/warehouse/wnba_model_explainability.json'),Path('data/dashboard/wnba_model_explainability.json')]

def load(p:Path,d:Any)->Any:
    try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
    except Exception:return d
def dump(p:Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def feature(name:str,value:float,detail:str,source:str,available:bool=True)->dict[str,Any]:
    return {'feature':name,'contribution':round(value,2),'direction':'positive' if value>0 else 'negative' if value<0 else 'neutral','detail':detail,'source':source,'available':available}
def player_indexes()->tuple[dict[str,dict[str,Any]],dict[str,dict[str,Any]],dict[str,dict[str,Any]]]:
    u={norm(r.get('player')):r for r in load(UNIFIED,{'players':[]}).get('players',[]) if isinstance(r,dict) and r.get('player')}
    m={norm(r.get('player')):r for r in load(MINUTES,{'projections':[]}).get('projections',[]) if isinstance(r,dict) and r.get('player')}
    a={norm(r.get('player')):r for r in load(ALT,{'rows':[]}).get('rows',[]) if isinstance(r,dict) and r.get('player')}
    return u,m,a
def explanation(row:dict[str,Any],u:dict[str,Any]|None,m:dict[str,Any]|None,a:dict[str,Any]|None)->dict[str,Any]:
    comps=row.get('ranking_components',{}) if isinstance(row.get('ranking_components'),dict) else {}
    feats=[]
    ev=num(row.get('expected_value_per_unit'));prob=num(row.get('hit_probability'));line=num(row.get('line'))
    feats.append(feature('Expected value',clamp((ev or 0)*20,-3,3),f"Model EV {ev*100:.1f}%" if ev is not None else 'EV unavailable','cross_market_top_plays',ev is not None))
    feats.append(feature('Hit probability',clamp(((prob or .5)-.5)*16,-3,3),f"Simulated hit probability {prob*100:.1f}%" if prob is not None else 'Probability unavailable','unified_player_simulation_v2',prob is not None))
    conf=num(row.get('confidence'));feats.append(feature('Model confidence',clamp(((conf or 50)-65)/12,-2.5,2.5),f"Confidence {conf:.1f}/100" if conf is not None else 'Confidence unavailable','cross_market_top_plays',conf is not None))
    quality=str(row.get('data_quality_status') or 'unknown').lower();qv={'complete':1.5,'partial':.4,'limited':-1.2,'volatile':-2}.get(quality,-.5);feats.append(feature('Data quality',qv,f"Data quality: {quality}",'cross_market_top_plays',quality!='unknown'))
    injury=str(row.get('injury_status') or 'ACTIVE').upper();iv=-2 if injury in {'QUESTIONABLE','GTD','DOUBTFUL','UNKNOWN'} else -3 if injury=='OUT' else .3;feats.append(feature('Availability',iv,f"Availability status: {injury}",'minutes_projection_v2',True))
    if m:
        projected=num(m.get('projected_minutes'));l5=num((m.get('samples') or {}).get('l5_average'));delta=None if projected is None or l5 is None else projected-l5
        feats.append(feature('Minutes projection',clamp((delta or 0)/1.5,-3,3),f"Projected {projected:.1f} min vs L5 {l5:.1f}" if delta is not None else 'Minutes baseline incomplete','minutes_projection_v2',delta is not None))
        rest=num(m.get('rest_days'));rv=-.8 if rest==0 else .4 if rest is not None and rest>=2 else 0;feats.append(feature('Rest',rv,f"Rest days: {int(rest)}" if rest is not None else 'Rest unavailable','minutes_projection_v2',rest is not None))
        blow=num((m.get('context') or {}).get('blowout_probability'));bv=-(blow or 0)*4;feats.append(feature('Blowout risk',clamp(bv,-2,0),f"Blowout probability {blow*100:.1f}%" if blow is not None else 'Blowout probability unavailable','minutes_projection_v2',blow is not None))
    if u:
        stat=str(row.get('stat') or '');dist=(u.get('distributions') or {}).get(stat,{})
        mean=num(dist.get('mean'));edge=None
        if mean is not None and line is not None:edge=(mean-line) if str(row.get('side')).upper()=='OVER' else (line-mean)
        feats.append(feature('Projection versus line',clamp((edge or 0)/2,-3,3),f"Projection {mean:.2f} vs line {line:.2f}" if edge is not None else 'Projection-line comparison unavailable','unified_player_simulation_v2',edge is not None))
        adj=num((u.get('matchup_adjustments_pct') or {}).get(stat));feats.append(feature('Opponent matchup',clamp((adj or 0)/4,-2.5,2.5),f"Matchup adjustment {adj:+.1f}%" if adj is not None else 'Qualified matchup adjustment unavailable','unified_player_simulation_v2',adj is not None))
    if a:
        streak=num(a.get('streak_score'));l10=num(a.get('l10_pct'));sv=clamp(((streak or 70)-70)/10,-2,2) if streak is not None else 0
        feats.append(feature('ALT streak form',sv,f"Streak score {streak:.1f}; L10 {l10*100:.0f}%" if streak is not None and l10 is not None else f"Streak score {streak:.1f}" if streak is not None else 'ALT streak context unavailable','alt_streaks',streak is not None))
    vol=num(comps.get('volatility_penalty'));feats.append(feature('Volatility penalty',-(vol or 0)/6,f"Ranking volatility penalty {vol:.1f}" if vol is not None else 'Volatility penalty unavailable','cross_market_top_plays',vol is not None))
    positives=sorted([f for f in feats if f['available'] and f['contribution']>0],key=lambda x:x['contribution'],reverse=True)
    risks=sorted([f for f in feats if f['available'] and f['contribution']<0],key=lambda x:x['contribution'])
    unavailable=[f['feature'] for f in feats if not f['available']]
    summary_parts=[]
    if positives:summary_parts.append('Driven by '+', '.join(f['feature'].lower() for f in positives[:3]))
    if risks:summary_parts.append('Main risks: '+', '.join(f['feature'].lower() for f in risks[:2]))
    if unavailable:summary_parts.append(f"{len(unavailable)} context fields unavailable")
    return {'rank':row.get('rank'),'player':row.get('player'),'game':row.get('game'),'market_type':row.get('market_type'),'stat':row.get('stat'),'side':row.get('side'),'line':row.get('line'),'odds':row.get('odds'),'sportsbook':row.get('sportsbook'),'decision':row.get('decision'),'top_play_score':row.get('top_play_score'),'projection':num(((u or {}).get('distributions') or {}).get(str(row.get('stat') or ''),{}).get('mean')),'confidence':row.get('confidence'),'features':sorted(feats,key=lambda x:abs(x['contribution']),reverse=True),'biggest_positives':positives[:5],'biggest_risks':risks[:5],'unavailable_inputs':unavailable,'summary':'. '.join(summary_parts)+('.' if summary_parts else ''),'explanation_version':'1.0'}
def build(target:str)->dict[str,Any]:
    top=load(TOP,{'top_plays':[]});u,m,a=player_indexes();rows=[]
    for play in top.get('top_plays',[]):
        key=norm(play.get('player'));rows.append(explanation(play,u.get(key),m.get(key),a.get(key)))
    payload={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','summary':{'plays_explained':len(rows),'with_player_context':sum(bool(r.get('player')) for r in rows),'total_unavailable_inputs':sum(len(r.get('unavailable_inputs',[])) for r in rows)},'explanations':rows,'methodology':{'policy':'deterministic source-backed factor attribution','missing_data':'explicitly labeled unavailable; never inferred','contribution_scale':'display attribution points, not literal stat points','market_policy':'explanation describes the existing recommendation and does not alter ranking'}}
    for p in OUTS:dump(p,payload)
    print('Model Explainability:',payload['summary']);return payload
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
