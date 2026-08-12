"""M17 deterministic results grading with duplicate protection and P/L accounting."""
from __future__ import annotations
import argparse,json,math,os
from datetime import date,datetime,timezone
from typing import Any
import pandas as pd

HISTORY_PATH='data/history/wnba_model_history.jsonl'

def norm(v): return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def sf(v,d=None):
    try:
        n=float(v); return n if math.isfinite(n) else d
    except Exception:return d

def clean(v: Any)->Any:
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,float):return v if math.isfinite(v) else None
    if v is None or isinstance(v,(str,int,bool)):return v
    try:
        if pd.isna(v):return None
    except Exception:pass
    try:
        if hasattr(v,'item'):return clean(v.item())
    except Exception:pass
    return str(v)

def read_history():
    out=[]
    if os.path.exists(HISTORY_PATH):
        for line in open(HISTORY_PATH,encoding='utf-8'):
            try:out.append(json.loads(line))
            except Exception:pass
    return out

def write_history(rows):
    os.makedirs(os.path.dirname(HISTORY_PATH),exist_ok=True)
    with open(HISTORY_PATH,'w',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(clean(r),separators=(',',':'),allow_nan=False)+'\n')

def _date_filter(df,target):
    for column in ('game_date','date','game_date_utc'):
        if column in df.columns:
            return df[df[column].astype(str).str[:10]==target].copy()
    return df

def _canonical_actuals(target):
    path='data/warehouse/wnba_player_game_logs.json'
    if not os.path.exists(path):return pd.DataFrame()
    try:
        payload=json.load(open(path,encoding='utf-8'))
        rows=[]
        for r in payload.get('records',[]):
            if str(r.get('game_date') or '')[:10]!=target:continue
            scoring=r.get('scoring') if isinstance(r.get('scoring'),dict) else {}
            box=r.get('boxscore') if isinstance(r.get('boxscore'),dict) else {}
            rows.append({'game_date':target,'game':r.get('game'),'player':r.get('player'),'team':r.get('team'),'pts':scoring.get('total_pts'),'reb':box.get('reb'),'ast':box.get('ast'),'threes':scoring.get('three_pm'),'stl':box.get('stl'),'blk':box.get('blk'),'tov':box.get('tov')})
        return pd.DataFrame(rows)
    except Exception:return pd.DataFrame()

def _raw_json_actuals(target):
    """Load the canonical daily ESPN fallback emitted by wnba_live_results.py."""
    path=f'data/raw/wnba_boxscores_{target}.json'
    if not os.path.exists(path):return pd.DataFrame(),None
    try:
        payload=json.load(open(path,encoding='utf-8'))
        rows=payload.get('players',[]) if isinstance(payload,dict) else []
        df=_date_filter(pd.DataFrame(rows),target) if rows else pd.DataFrame()
        if not df.empty and 'player' in df.columns:return df,path
    except Exception:pass
    return pd.DataFrame(),None

def load_actuals(target):
    candidates=(
        f'data/raw/player_results_{target}.csv',
        f'data/raw/boxscore_player_stats_{target}.csv',
        f'data/raw/wnba_boxscores_{target}.csv',
        'data/raw/boxscores_wehoop.csv',
    )
    for p in candidates:
        if os.path.exists(p):
            try:
                df=_date_filter(pd.read_csv(p),target)
                if not df.empty and 'player' in df.columns:return df,p
            except Exception:pass
    df,source=_raw_json_actuals(target)
    if not df.empty:return df,source
    df=_canonical_actuals(target)
    if not df.empty and 'player' in df.columns:return df,'data/warehouse/wnba_player_game_logs.json'
    return pd.DataFrame(),None

def game_pair(value):
    text=norm(value).replace(' vs. ',' @ ').replace(' vs ',' @ ')
    if ' @ ' not in text:return None
    left,right=[norm(x) for x in text.split(' @ ',1)]
    if not left or not right:return None
    return frozenset((left,right))

def completed_game_pairs(actuals):
    if actuals.empty or 'game' not in actuals.columns:return set()
    pairs=set()
    for value in actuals['game'].dropna().tolist():
        pair=game_pair(value)
        if pair:pairs.add(pair)
    return pairs

def actual_value(row,stat):
    stat=str(stat or '').upper(); pts=sf(row.get('pts',row.get('PTS')),0); reb=sf(row.get('reb',row.get('REB')),0); ast=sf(row.get('ast',row.get('AST')),0); th=sf(row.get('threes',row.get('3pm',row.get('3PM',row.get('fg3m')))),0)
    return {'PTS':pts,'REB':reb,'AST':ast,'3PM':th,'PRA':pts+reb+ast,'PA':pts+ast,'PR':pts+reb,'RA':reb+ast}.get(stat,sf(row.get(stat.lower())))

def grade(signal,actual,line):
    if actual is None or line is None:return 'PENDING'
    if actual==line:return 'PUSH'
    s=str(signal or '').upper()
    if s in {'OVER','YES'}:return 'WIN' if actual>line else 'LOSS'
    if s in {'UNDER','NO'}:return 'WIN' if actual<line else 'LOSS'
    return 'VOID'

def profit(outcome,stake,odds):
    stake=sf(stake,0) or 0; odds=sf(odds,-110) or -110
    if outcome=='WIN':return stake*(100/abs(odds) if odds<0 else odds/100)
    if outcome=='LOSS':return -stake
    return 0.0

def build(target):
    hist=read_history(); actuals,source=load_actuals(target); amap={norm(r.get('player')):clean(r.to_dict()) for _,r in actuals.iterrows()} if not actuals.empty else {}
    completed_pairs=completed_game_pairs(actuals)
    counts={k:0 for k in ('WIN','LOSS','PUSH','VOID','PENDING')}; graded=0; total_stake=0.0; pnl=0.0; missing=[]
    target_rows=0; dnp_voided=0
    for r in hist:
        if r.get('date')!=target:continue
        target_rows+=1
        if r.get('outcome') in {'WIN','LOSS','PUSH','VOID'}:
            counts[r['outcome']]+=1; continue
        a=amap.get(norm(r.get('player')))
        if not a:
            archived_pair=game_pair(r.get('game'))
            # A missing player row is a sportsbook void only when we can prove the
            # archived matchup itself is present in the completed daily boxscore.
            # This handles DNP/inactive players without treating a missing feed as
            # a statistical zero or guessing across games.
            if archived_pair and archived_pair in completed_pairs:
                r['actual']=None; r['outcome']='VOID'; r['graded_at_utc']=datetime.now(timezone.utc).isoformat(); r['grading_reason']='completed game verified; player did not record participation'; r['profit_loss']=0.0
                counts['VOID']+=1; graded+=1; dnp_voided+=1
                continue
            counts['PENDING']+=1; missing.append({'player':r.get('player'),'game':r.get('game'),'reason':'actual player row unavailable and completed matchup could not be verified'}); continue
        val=actual_value(a,r.get('stat')); out=grade(r.get('signal'),val,sf(r.get('line')))
        if out=='PENDING':missing.append({'player':r.get('player'),'reason':'actual stat or line unavailable'})
        r['actual']=val; r['outcome']=out; r['graded_at_utc']=datetime.now(timezone.utc).isoformat(); stake=sf(r.get('stake',r.get('recommended_stake')),0) or 0; p=profit(out,stake,r.get('american_odds')); r['profit_loss']=round(p,2)
        counts[out]+=1; graded+=out in {'WIN','LOSS','PUSH','VOID'}; total_stake+=stake if out in {'WIN','LOSS'} else 0; pnl+=p
    write_history(hist); decisions=counts['WIN']+counts['LOSS']; roi=pnl/total_stake if total_stake else 0
    status='ok' if decisions or counts['PUSH'] or counts['VOID'] else 'no_archived_predictions' if target_rows==0 else 'waiting_for_actuals'
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':status,'actual_source':source,'actual_rows':len(actuals),'archived_predictions':target_rows,'completed_matchups_verified':len(completed_pairs),'summary':{'graded_this_run':graded,'dnp_voided':dnp_voided,**{k.lower():v for k,v in counts.items()},'win_rate':round(counts['WIN']/decisions,4) if decisions else 0,'total_stake':round(total_stake,2),'profit_loss':round(pnl,2),'roi':round(roi,4)},'missing_actuals':missing[:100]}
    os.makedirs('data/warehouse',exist_ok=True);os.makedirs('data/dashboard',exist_ok=True)
    for p in ('data/warehouse/wnba_results_grading.json','data/dashboard/wnba_results_grading.json'):json.dump(clean(report),open(p,'w',encoding='utf-8'),indent=2,allow_nan=False)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();print('Results grading:',build(a.date))
if __name__=='__main__':main()
