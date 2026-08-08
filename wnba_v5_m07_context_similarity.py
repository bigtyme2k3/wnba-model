"""V5-M07 Context + Player Similarity Intelligence.

Research-only, leakage-safe enrichment of the M05 walk-forward predictions.
For every evaluation row, context is derived only from games dated strictly before
the target game. Player similarity is computed within the same stat market using
the latest prior profile for other players. No future outcomes are used.
"""
from __future__ import annotations

import csv, json, math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

FEATURES=Path('data/dashboard/wnba_v5_historical_features.csv')
M05=Path('data/dashboard/wnba_v5_m05_predictions.csv')
M06=Path('data/dashboard/wnba_v5_m06_report.json')
OUT_CSV=Path('data/dashboard/wnba_v5_context_similarity.csv')
SIM_JSON=Path('data/dashboard/wnba_v5_player_similarity.json')
STATE_JSON=Path('data/dashboard/wnba_v5_context_state.json')
REPORT=Path('data/dashboard/wnba_v5_m07_report.json')

PROFILE_FIELDS=[
    'rolling5_actual_mean',
    'rolling5_actual_std',
    'rolling5_trend_slope',
    'historical_hit_rate_at_current_line',
    'historical_hit_rate_l5_at_current_line',
    'line_minus_prior_mean',
]
K=5


def norm(v:Any)->str:
    return ' '.join(str(v or '').strip().lower().replace('’',"'").split())

def f(v:Any,default=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except Exception:return default

def parse_date(v:Any):
    try:return date.fromisoformat(str(v)[:10])
    except Exception:return None

def clamp(x,lo=0.0,hi=100.0):return max(lo,min(hi,x))

def read_csv(path:Path):
    with path.open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))

def game_history(features):
    # Unique player-game dates only; ALT price variants must not inflate workload.
    by_player=defaultdict(set)
    for r in features:
        d=str(r.get('game_date') or '')[:10]
        if d:by_player[norm(r.get('player'))].add(d)
    return {p:sorted(ds) for p,ds in by_player.items()}

def schedule_context(player,target_date,hist):
    td=parse_date(target_date); prior=[]
    if td:
        prior=[parse_date(d) for d in hist.get(norm(player),[]) if parse_date(d) and parse_date(d)<td]
    prior=[d for d in prior if d]
    prev=max(prior) if prior else None
    gap=(td-prev).days if td and prev else None
    rest_days=(gap-1) if gap is not None else None
    games7=sum(1 for d in prior if 0<(td-d).days<=7) if td else 0
    games14=sum(1 for d in prior if 0<(td-d).days<=14) if td else 0
    b2b=gap==1
    three_in_four=games7>=3 and any((td-d).days<=3 for d in prior) if td else False
    fatigue=75.0
    if rest_days is None: fatigue=58.0
    elif rest_days<=0: fatigue-=20
    elif rest_days==1: fatigue-=7
    elif rest_days>=3: fatigue+=8
    fatigue-=max(0,games7-2)*5
    if three_in_four:fatigue-=7
    return {
        'days_since_previous_game':gap,'rest_days':rest_days,'back_to_back':b2b,
        'games_last_7d':games7,'games_last_14d':games14,'three_in_four_proxy':three_in_four,
        'fatigue_score':round(clamp(fatigue),2),
    }

def vector(r):
    vals=[]
    for k in PROFILE_FIELDS:
        x=f(r.get(k))
        if x is None:return None
        vals.append(x)
    return vals

def nearest_peers(target,features):
    td=str(target.get('game_date') or '')[:10]; stat=str(target.get('stat') or '').upper(); player=norm(target.get('player'))
    tv=vector(target)
    if tv is None:return []
    # Latest strictly-prior profile per other player in same stat.
    latest={}
    for r in features:
        if str(r.get('stat') or '').upper()!=stat:continue
        rp=norm(r.get('player')); rd=str(r.get('game_date') or '')[:10]
        if not rd or rd>=td or rp==player:continue
        if int(f(r.get('prior_games'),0) or 0)<3:continue
        if vector(r) is None:continue
        prior=latest.get(rp)
        if prior is None or str(prior.get('game_date'))<rd:latest[rp]=r
    candidates=list(latest.values())
    if not candidates:return []
    matrix=[tv]+[vector(r) for r in candidates]
    mu=[mean(row[j] for row in matrix) for j in range(len(PROFILE_FIELDS))]
    sd=[]
    for j in range(len(PROFILE_FIELDS)):
        s=pstdev(row[j] for row in matrix);sd.append(s if s>1e-8 else 1.0)
    zt=[(tv[j]-mu[j])/sd[j] for j in range(len(tv))]
    scored=[]
    for r in candidates:
        v=vector(r);z=[(v[j]-mu[j])/sd[j] for j in range(len(v))]
        dist=math.sqrt(sum((a-b)**2 for a,b in zip(zt,z))/len(z))
        sim=1/(1+dist)
        scored.append((dist,sim,r))
    scored.sort(key=lambda x:x[0])
    out=[]
    for dist,sim,r in scored[:K]:
        out.append({
            'player':r.get('player'),'game_date':r.get('game_date'),'stat':stat,
            'similarity':round(sim,6),'distance':round(dist,6),
            'prior_games':int(f(r.get('prior_games'),0) or 0),
            'rolling5_actual_mean':f(r.get('rolling5_actual_mean')),
            'rolling5_actual_std':f(r.get('rolling5_actual_std')),
            'historical_hit_rate':f(r.get('historical_hit_rate_at_current_line')),
            'observed_win':int(f(r.get('target_win'),0) or 0) if f(r.get('target_win')) in (0.0,1.0) else None,
        })
    return out

def main():
    if not FEATURES.exists() or not M05.exists():raise SystemExit('M07_INPUT_MISSING')
    feats=read_csv(FEATURES); preds=read_csv(M05); hist=game_history(feats)
    by_archive={str(r.get('archive_index')):r for r in feats}
    rows=[]; sim_payload=[]
    for p in preds:
        base=by_archive.get(str(p.get('archive_index')),{})
        merged={**base,**p}
        sched=schedule_context(p.get('player'),p.get('game_date'),hist)
        peers=nearest_peers(merged,feats)
        peer_wins=[x['observed_win'] for x in peers if x['observed_win'] is not None]
        peer_hit=mean(peer_wins) if peer_wins else None
        peer_sim=mean([x['similarity'] for x in peers]) if peers else None
        volatility=f(merged.get('rolling5_actual_std'))
        trend=f(merged.get('rolling5_trend_slope'))
        h5=f(merged.get('historical_hit_rate_l5_at_current_line'))
        history_depth=int(f(merged.get('prior_games'),0) or 0)
        stability=70.0
        if volatility is None:stability-=15
        else:stability-=min(25,volatility*3)
        stability+=min(12,history_depth*1.5)
        support=50.0 if peer_hit is None else peer_hit*100
        similarity_conf=0.0 if peer_sim is None else peer_sim*100
        context_score=(sched['fatigue_score']*0.30 + clamp(stability)*0.25 + support*0.25 + similarity_conf*0.20)
        knn=f(p.get('knn_probability'))
        peer_delta=None if peer_hit is None or knn is None else peer_hit-knn
        row={
            'archive_index':p.get('archive_index'),'game_date':p.get('game_date'),'game_id':p.get('game_id'),
            'player':p.get('player'),'stat':p.get('stat'),'side':p.get('side'),'alt_line':p.get('alt_line'),
            'target_win':p.get('target_win'),'knn_probability':knn,'ensemble_probability':f(p.get('ensemble_probability')),
            **sched,
            'rolling5_actual_mean':f(merged.get('rolling5_actual_mean')),
            'rolling5_actual_std':volatility,'rolling5_trend_slope':trend,
            'historical_hit_rate_l5':h5,'prior_games':history_depth,
            'similar_peer_count':len(peers),'avg_peer_similarity':None if peer_sim is None else round(peer_sim,6),
            'similar_peer_hit_rate':None if peer_hit is None else round(peer_hit,6),
            'peer_minus_knn_probability':None if peer_delta is None else round(peer_delta,6),
            'context_score':round(clamp(context_score),3),
            'context_class':'STRONG' if context_score>=70 else ('NEUTRAL' if context_score>=55 else 'WEAK'),
        }
        rows.append(row)
        sim_payload.append({'archive_index':p.get('archive_index'),'player':p.get('player'),'stat':p.get('stat'),'game_date':p.get('game_date'),'peers':peers})

    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
    SIM_JSON.write_text(json.dumps({'schema':'v5-m07-player-similarity-v1','k':K,'profile_fields':PROFILE_FIELDS,'records':sim_payload},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    classes=defaultdict(int)
    for r in rows:classes[r['context_class']]+=1
    with_peers=sum(r['similar_peer_count']>0 for r in rows)
    b2b=sum(bool(r['back_to_back']) for r in rows)
    strong=[r for r in rows if r['context_class']=='STRONG']
    weak=[r for r in rows if r['context_class']=='WEAK']
    def perf(xs):
        if not xs:return {'n':0,'wins':0,'hit_rate':None}
        wins=sum(int(float(x['target_win'])) for x in xs)
        return {'n':len(xs),'wins':wins,'hit_rate':round(wins/len(xs),6)}
    m06=json.loads(M06.read_text(encoding='utf-8')) if M06.exists() else {}
    state={
        'version':'V5','module':'V5-M07','stage':'CONTEXT_PLAYER_SIMILARITY','status':'READY',
        'evaluation_rows':len(rows),'rows_with_similarity_peers':with_peers,
        'similarity_coverage_pct':round(100*with_peers/len(rows),2) if rows else 0.0,
        'back_to_back_rows':b2b,'context_class_counts':dict(classes),
        'strong_context_performance':perf(strong),'weak_context_performance':perf(weak),
        'm06_snapshot_match_coverage_pct':m06.get('snapshot_match_coverage_pct'),
        'research_only':True,
        'leakage_policy':'schedule and peer profiles use strictly prior game dates only',
        'next_module':'V5-M08 Context-Aware Challenger Validation',
    }
    STATE_JSON.write_text(json.dumps(state,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    REPORT.write_text(json.dumps({**state,'profile_fields':PROFILE_FIELDS,'k_neighbors':K,'methodology':{
        'schedule_context':'unique prior player-game dates; ALT variants do not inflate workload',
        'similarity':'same-stat latest prior profile per other player, standardized Euclidean distance',
        'context_score':'fatigue 30%, player stability 25%, peer observed support 25%, peer similarity confidence 20%',
    }},indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(state,indent=2))

if __name__=='__main__':main()
