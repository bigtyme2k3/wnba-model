from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone, date
from pathlib import Path

DASH = Path('data/dashboard')
MASTER = DASH / 'wnba_master.json'
PERF = DASH / 'wnba_game_performance.json'
RATINGS = DASH / 'wnba_team_ratings.json'
PREDS = DASH / 'wnba_sprint2_predictions.json'
INJURY = DASH / 'wnba_injury_intelligence.json'
OUT = DASH / 'wnba_sprint2_phase2.json'


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return default


def f(v, default=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def parse_day(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def team_history(perf, team):
    rows=[]
    for r in perf.get('recent_games') or []:
        if not isinstance(r,dict) or not r.get('graded'):
            continue
        away=str(r.get('away_team') or '').strip(); home=str(r.get('home_team') or '').strip()
        if team not in {away,home}: continue
        a=f(r.get('actual_away_score')); h=f(r.get('actual_home_score'))
        if a is None or h is None: continue
        is_home=team==home
        pf=h if is_home else a; pa=a if is_home else h
        rows.append({'date':str(r.get('target_date') or ''),'pf':pf,'pa':pa,'home':is_home,'total':pf+pa,'margin':pf-pa})
    rows.sort(key=lambda x:x['date'], reverse=True)
    return rows


def avg(vals, default=0.0):
    vals=[f(x) for x in vals]; vals=[x for x in vals if x is not None]
    return sum(vals)/len(vals) if vals else default


def injury_map(injury, target):
    if str(injury.get('target_date') or '') != target:
        return {}
    out={}
    for row in injury.get('adjustments') or []:
        if not isinstance(row,dict): continue
        team=str(row.get('team') or '').strip()
        if not team: continue
        d=out.setdefault(team,{'players':0,'out':0,'questionable':0,'probable':0,'minutes_lost':0.0,'confidence_penalty':0.0,'impact':0.0})
        sev=str(row.get('severity') or row.get('status') or '').upper()
        if sev=='BENEFICIARY':
            continue
        d['players']+=1
        if bool(row.get('is_out')) or sev=='OUT': d['out']+=1
        if sev in {'QUESTIONABLE','DOUBTFUL'}: d['questionable']+=1
        if sev=='PROBABLE': d['probable']+=1
        delta=f(row.get('minutes_delta'),0.0) or 0.0
        d['minutes_lost'] += max(0.0,-delta)
        d['confidence_penalty'] += f(row.get('confidence_penalty'),0.0) or 0.0
    for d in out.values():
        # Transparent injury impact proxy, bounded to avoid overwhelming the model.
        d['impact']=round(clamp(d['minutes_lost']*0.055 + d['out']*0.65 + d['questionable']*0.25,0,4.5),2)
        d['minutes_lost']=round(d['minutes_lost'],1)
        d['confidence_penalty']=round(clamp(d['confidence_penalty'],0,100),1)
    return out


def grade(conf, spread_edge, total_edge):
    edge=max(abs(f(spread_edge,0) or 0), abs(f(total_edge,0) or 0)*0.65)
    score=(f(conf,35) or 35) + min(edge,8)*1.6
    if score>=91:return 'A+'
    if score>=86:return 'A'
    if score>=81:return 'A-'
    if score>=76:return 'B+'
    if score>=70:return 'B'
    if score>=64:return 'B-'
    if score>=58:return 'C+'
    return 'C'


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',required=True); args=ap.parse_args()
    target=args.date
    master=load(MASTER,{}); perf=load(PERF,{}); ratings=load(RATINGS,{}); preds=load(PREDS,{}); injury=load(INJURY,{})
    if str(master.get('target_date') or '') != target: raise SystemExit('master date mismatch')
    if str(preds.get('target_date') or '') != target: raise SystemExit('predictions date mismatch')
    if str(injury.get('target_date') or '') != target: raise SystemExit('injury intelligence date mismatch')

    injury_generated_at=str(injury.get('generated_at_utc') or injury.get('generated_at') or '')
    if not injury_generated_at:
        raise SystemExit('injury intelligence generation timestamp missing')

    inj=injury_map(injury,target)
    by_team=ratings.get('by_team') or {}
    target_day=parse_day(target)

    enriched_ratings={}
    for team, base in by_team.items():
        hist=team_history(perf,team)
        l5=hist[:5]; l10=hist[:10]
        last_day=parse_day(hist[0]['date']) if hist else None
        rest_days=(target_day-last_day).days if target_day and last_day else None
        home=[r for r in hist[:12] if r['home']]; away=[r for r in hist[:12] if not r['home']]
        pace_proxy=avg([r['total'] for r in l10],164.0)/164.0*100.0
        item=dict(base)
        item.update({
            'last5_net_margin':round(avg([r['margin'] for r in l5],0),2),
            'last10_net_margin':round(avg([r['margin'] for r in l10],0),2),
            'home_net_margin':round(avg([r['margin'] for r in home],0),2),
            'away_net_margin':round(avg([r['margin'] for r in away],0),2),
            'pace_index':round(pace_proxy,2),
            'pace_label':'FAST' if pace_proxy>=103 else ('SLOW' if pace_proxy<=97 else 'NEUTRAL'),
            'rest_days':rest_days,
            'back_to_back':bool(rest_days is not None and rest_days<=1),
            'injury':inj.get(team,{'players':0,'out':0,'questionable':0,'probable':0,'minutes_lost':0.0,'confidence_penalty':0.0,'impact':0.0}),
        })
        enriched_ratings[team]=item

    cards=[]
    for p in preds.get('games') or []:
        away=p.get('away_team'); home=p.get('home_team')
        ar=enriched_ratings.get(away,{}); hr=enriched_ratings.get(home,{})
        projection=dict(p.get('projection') or {})
        edge=dict(p.get('edge') or {})
        market=dict(p.get('market') or {})
        a_injury=ar.get('injury') or {}
        h_injury=hr.get('injury') or {}
        # Apply only current-date injury adjustments. Positive impact weakens that team.
        a_imp=f(a_injury.get('impact'),0) or 0
        h_imp=f(h_injury.get('impact'),0) or 0
        a_score=f(projection.get('away_score')); h_score=f(projection.get('home_score'))
        if a_score is not None and h_score is not None:
            a_score -= a_imp*0.55; h_score -= h_imp*0.55
            projection['away_score']=round(a_score,1); projection['home_score']=round(h_score,1)
            margin=h_score-a_score; total=a_score+h_score
            projection['home_margin']=round(margin,2); projection['model_home_spread']=round(-margin,2); projection['total']=round(total,1)
            projection['home_win_probability']=round(1/(1+math.exp(-margin/6.5)),4)
            projection['away_win_probability']=round(1-projection['home_win_probability'],4)
            if f(market.get('home_spread')) is not None: edge['spread']=round(f(market.get('home_spread'))-projection['model_home_spread'],2)
            if f(market.get('total')) is not None: edge['total']=round(projection['total']-f(market.get('total')),2)
        conf=f(p.get('confidence'),35) or 35
        penalty=((f(a_injury.get('confidence_penalty'),0) or 0)+(f(h_injury.get('confidence_penalty'),0) or 0))*0.05
        conf=round(clamp(conf-penalty,35,88),1)
        spread_edge=f(edge.get('spread')); total_edge=f(edge.get('total'))
        spread_pick='PASS'
        if spread_edge is not None and abs(spread_edge)>=2: spread_pick=home if spread_edge>0 else away
        total_pick='PASS'
        if total_edge is not None and abs(total_edge)>=3: total_pick='OVER' if total_edge>0 else 'UNDER'
        rest_adv=None
        if ar.get('rest_days') is not None and hr.get('rest_days') is not None: rest_adv=hr['rest_days']-ar['rest_days']
        pace=round(avg([ar.get('pace_index'),hr.get('pace_index')],100),1)
        card_injury_count=sum(int(x or 0) for x in [a_injury.get('players'),h_injury.get('players')])
        cards.append({
            'game':p.get('game'),'away_team':away,'home_team':home,'start_time':p.get('start_time'),
            'market':market,'projection':projection,'edge':edge,'confidence':conf,
            'model_grade':grade(conf,spread_edge,total_edge),
            'recommendation':{'spread':spread_pick,'total':total_pick},
            'pace_index':pace,'pace_label':'FAST' if pace>=103 else ('SLOW' if pace<=97 else 'NEUTRAL'),
            'rest_advantage_home':rest_adv,
            'teams':{'away':ar,'home':hr},
            'injury_adjusted':bool(a_imp or h_imp),
            'injury_context':{
                'source':'wnba_injury_intelligence.json',
                'target_date':target,
                'generated_at_utc':injury_generated_at,
                'fresh':True,
                'listed_players':card_injury_count,
                'out':int(a_injury.get('out') or 0)+int(h_injury.get('out') or 0),
                'questionable':int(a_injury.get('questionable') or 0)+int(h_injury.get('questionable') or 0),
                'probable':int(a_injury.get('probable') or 0)+int(h_injury.get('probable') or 0),
                'away_impact':a_imp,
                'home_impact':h_imp,
            },
            'edge_value_pct':{
                'spread':round(abs(spread_edge or 0)/max(1,abs(f(market.get('home_spread'),1) or 1))*100,1) if spread_edge is not None else None,
                'total':round(abs(total_edge or 0)/max(1,f(market.get('total'),1) or 1)*100,1) if total_edge is not None else None,
            }
        })

    generated_at=datetime.now(timezone.utc).isoformat()
    payload={
        'generated_at_utc':generated_at,
        'target_date':target,
        'schema_version':'sprint19-m01-injury-aware-games-v1',
        'status':'PASS',
        'injury_source':{
            'path':'data/dashboard/wnba_injury_intelligence.json',
            'target_date':target,
            'generated_at_utc':injury_generated_at,
            'consumed_before_projection_generated':True,
        },
        'method_notes':{
            'pace_index':'score-tempo proxy centered near 100; not possessions per 40',
            'offense_defense':'score-based model indices; not official ORtg/DRtg',
            'injury_adjustment':'current-date official injury intelligence only; bounded impact proxy',
            'edge_value_pct':'relative model-vs-market gap; not expected ROI'
        },
        'team_ratings':enriched_ratings,
        'games':cards,
        'summary':{
            'games':len(cards),
            'injury_context_games':sum(1 for x in cards if (x.get('injury_context') or {}).get('listed_players',0)>0),
            'injury_adjusted_games':sum(1 for x in cards if x['injury_adjusted']),
            'listed_injuries_on_slate':sum((x.get('injury_context') or {}).get('listed_players',0) for x in cards),
            'graded_A_range':sum(1 for x in cards if str(x['model_grade']).startswith('A'))
        }
    }
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(json.dumps({'target_date':target,'games':len(cards),'injury_adjusted_games':payload['summary']['injury_adjusted_games'],'status':'PASS'}))

if __name__=='__main__': main()
