"""WNBA V5 Operations Sprint 3 M02 - explicit pre-tip closing capture.

Captures sportsbook observations only when the Sprint 3 freshness guard allows
live inference and an event is inside a strict pre-tip close window. Observations
outside the window or after tip are never labeled as closing lines.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

DASH = Path('data/dashboard')
FRESH = DASH/'wnba_v5_s3_m01_freshness.json'
INFERENCE = DASH/'wnba_v5_live_inference.json'
OUT_CSV = DASH/'wnba_v5_closing_lines.csv'
OUT_SNAPSHOT = DASH/'wnba_v5_closing_snapshot.json'
OUT_QUEUE = DASH/'wnba_v5_clv_queue.json'
OUT_REPORT = DASH/'wnba_v5_s3_m02_report.json'

SPORT='basketball_wnba'
BASE='https://api.the-odds-api.com/v4/sports'
BOOKMAKERS=os.getenv('V5_CLOSE_BOOKMAKERS','fanduel,draftkings')
CLOSE_WINDOW_MIN=int(os.getenv('V5_CLOSE_WINDOW_MIN','15'))
API_KEY=os.getenv('ODDS_API_KEY')

STAT_MARKETS={
 'PTS':['player_points','player_points_alternate'],
 'REB':['player_rebounds','player_rebounds_alternate'],
 'AST':['player_assists','player_assists_alternate'],
 '3PM':['player_threes','player_threes_alternate'],
 'PRA':['player_points_rebounds_assists','player_points_rebounds_assists_alternate'],
 'PA':['player_points_assists','player_points_assists_alternate'],
 'PR':['player_points_rebounds','player_points_rebounds_alternate'],
 'RA':['player_rebounds_assists','player_rebounds_assists_alternate'],
}
MARKET_STAT={m:s for s,ms in STAT_MARKETS.items() for m in ms}
FIELDS=['snapshot_id','captured_at_utc','event_id','commence_time','minutes_to_tip','game','player','stat','side','point','price','sportsbook','sportsbook_key','market_key','capture_class','is_explicit_close','source']

def load(path, default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def dt(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None

def api(path, params):
    if not API_KEY: raise RuntimeError('ODDS_API_KEY is not configured')
    q=dict(params);q['apiKey']=API_KEY
    with urlopen(f"{BASE}/{SPORT}/{path}?{urlencode(q)}",timeout=25) as r:
        return json.loads(r.read().decode('utf-8'))

def game_tokens(game):
    x=norm(game).replace(' vs. ',' @ ').replace(' vs ',' @ ')
    return {p.strip() for p in x.split('@') if p.strip()}

def event_matches(game,event):
    want=game_tokens(game); have={norm(event.get('home_team')),norm(event.get('away_team'))}
    return bool(want) and want==have

def existing_rows():
    if not OUT_CSV.exists():return []
    try:return list(csv.DictReader(OUT_CSV.open(encoding='utf-8-sig',newline='')))
    except Exception:return []

def write_csv(rows):
    OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
    with OUT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=FIELDS);w.writeheader();w.writerows([{k:r.get(k) for k in FIELDS} for r in rows])

def finish(report,snapshot,queue):
    OUT_SNAPSHOT.write_text(json.dumps(snapshot,indent=2)+'\n',encoding='utf-8')
    OUT_QUEUE.write_text(json.dumps(queue,indent=2)+'\n',encoding='utf-8')
    OUT_REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

def main():
    now=datetime.now(timezone.utc); nowiso=now.isoformat()
    fresh=load(FRESH,{})
    payload=load(INFERENCE,{})
    scored=payload.get('scored',[]) if isinstance(payload,dict) else []
    base={'version':'V5','sprint':'OPERATIONS_SPRINT_3','module':'S3-M02','stage':'EXPLICIT_CLOSING_LINE_CAPTURE','generated_at_utc':nowiso,'close_window_minutes':CLOSE_WINDOW_MIN,'bookmakers':BOOKMAKERS.split(','),'research_only':True,'production_ready':False}
    history=existing_rows()
    if not fresh.get('allow_live_inference'):
        report={**base,'status':'BLOCKED_STALE_SLATE','candidate_predictions':0,'eligible_events':0,'api_calls':0,'new_close_rows':0,'total_close_rows':len(history),'reason':'S3-M01 did not authorize the current slate. No odds API call was made.'}
        write_csv(history);finish(report,{'report':report,'observations':[]},{'report':report,'predictions':[]});return
    if not scored:
        report={**base,'status':'WAITING_FOR_M11_SCORES','candidate_predictions':0,'eligible_events':0,'api_calls':0,'new_close_rows':0,'total_close_rows':len(history),'reason':'No current M11 scored rows are available.'}
        write_csv(history);finish(report,{'report':report,'observations':[]},{'report':report,'predictions':[]});return
    if not API_KEY:
        report={**base,'status':'WAITING_FOR_ODDS_API_KEY','candidate_predictions':len(scored),'eligible_events':0,'api_calls':0,'new_close_rows':0,'total_close_rows':len(history),'reason':'ODDS_API_KEY secret is required for explicit live capture.'}
        write_csv(history);finish(report,{'report':report,'observations':[]},{'report':report,'predictions':[]});return

    events=api('events',{}); api_calls=1
    by_event={}
    queue=[]
    for p in scored:
        game=p.get('game'); stat=str(p.get('market') or '').upper(); match=next((e for e in events if event_matches(game,e)),None)
        item={'ranking_key':p.get('ranking_key'),'date':p.get('date'),'game':game,'player':p.get('player'),'stat':stat,'side':str(p.get('side') or '').upper(),'issued_line':p.get('line'),'issued_odds':p.get('odds'),'event_id':match.get('id') if match else None,'commence_time':match.get('commence_time') if match else None,'close_status':'NO_EVENT_MATCH'}
        if match:
            tip=dt(match.get('commence_time')); mins=(tip-now).total_seconds()/60 if tip else None
            item['minutes_to_tip']=round(mins,2) if mins is not None else None
            if mins is not None and 0 <= mins <= CLOSE_WINDOW_MIN:
                item['close_status']='ELIGIBLE_CAPTURE_WINDOW';by_event.setdefault(match['id'],{'event':match,'predictions':[]})['predictions'].append(p)
            elif mins is not None and mins < 0:item['close_status']='PAST_TIP_NO_CLOSE'
            else:item['close_status']='WAITING_FOR_CLOSE_WINDOW'
        queue.append(item)

    observations=[]
    for eid,b in by_event.items():
        relevant_stats={str(p.get('market') or '').upper() for p in b['predictions']}
        markets=sorted({m for s in relevant_stats for m in STAT_MARKETS.get(s,[])})
        if not markets:continue
        data=api(f'events/{eid}/odds',{'regions':'us','markets':','.join(markets),'oddsFormat':'american','bookmakers':BOOKMAKERS});api_calls+=1
        tip=dt(data.get('commence_time') or b['event'].get('commence_time'));mins=(tip-now).total_seconds()/60 if tip else None
        if mins is None or not (0 <= mins <= CLOSE_WINDOW_MIN):continue
        game=f"{data.get('away_team')} @ {data.get('home_team')}"
        for book in data.get('bookmakers',[]) or []:
            for market in book.get('markets',[]) or []:
                stat=MARKET_STAT.get(str(market.get('key') or ''))
                if not stat:continue
                for o in market.get('outcomes',[]) or []:
                    player=str(o.get('description') or '').strip();side=str(o.get('name') or '').upper();point=o.get('point');price=o.get('price')
                    if not player or side not in {'OVER','UNDER'} or point is None or price is None:continue
                    raw='|'.join(map(str,[nowiso,eid,book.get('key'),market.get('key'),player,side,point,price]))
                    observations.append({'snapshot_id':hashlib.sha256(raw.encode()).hexdigest()[:24],'captured_at_utc':nowiso,'event_id':eid,'commence_time':tip.isoformat(),'minutes_to_tip':round(mins,2),'game':game,'player':player,'stat':stat,'side':side,'point':point,'price':price,'sportsbook':book.get('title'),'sportsbook_key':book.get('key'),'market_key':market.get('key'),'capture_class':'EXPLICIT_PRETIP_CLOSE','is_explicit_close':True,'source':'the-odds-api'})

    seen={r.get('snapshot_id') for r in history};new=[r for r in observations if r['snapshot_id'] not in seen];allrows=history+new;write_csv(allrows)
    for q in queue:
        matches=[o for o in observations if norm(o['game'])==norm(q.get('game')) and norm(o['player'])==norm(q.get('player')) and o['stat']==q.get('stat') and o['side']==q.get('side')]
        if matches:q['close_status']='EXPLICIT_CLOSE_CAPTURED';q['close_observation_count']=len(matches)
        else:q['close_observation_count']=0
    status='CAPTURED_EXPLICIT_CLOSES' if new else ('WAITING_FOR_CLOSE_WINDOW' if not by_event else 'NO_MATCHING_PROP_MARKETS')
    report={**base,'status':status,'candidate_predictions':len(scored),'eligible_events':len(by_event),'api_calls':api_calls,'new_close_rows':len(new),'total_close_rows':len(allrows),'explicit_close_predictions':sum(q.get('close_status')=='EXPLICIT_CLOSE_CAPTURED' for q in queue),'policy':'Only API observations captured at or before tip and within the configured pre-tip window are labeled explicit closes. No post-tip or inferred close is accepted.'}
    finish(report,{'report':report,'observations':observations},{'report':report,'predictions':queue})

if __name__=='__main__':main()
