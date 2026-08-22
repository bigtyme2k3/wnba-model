"""Prospective shadow action policy for WNBA V5 Player Props.

Purpose:
- Challenge the current BET/WATCH routing without changing production.
- Promote only a narrow, historically supported WATCH segment into SHADOW_BET.
- Freeze every shadow decision before outcomes and grade it later from the canonical
  model-history result; never backfill the decision rule after the result.

Initial rule is intentionally conservative and derived from the action audit:
WATCH + candidate eligible + confidence 60-69.9 + absolute projection edge >= 4.0,
with an approved sportsbook price no worse than -150. Production remains unchanged.
"""
from __future__ import annotations

import json, math
from datetime import datetime, timezone
from pathlib import Path

DASH=Path('data/dashboard')
PRED=DASH/'wnba_s19_m02_predictions.json'
AUDIT=DASH/'wnba_v5_player_prop_action_audit.json'
HISTORY=Path('data/history/wnba_model_history.jsonl')
LEDGER=Path('data/history/wnba_v5_player_prop_action_v2_shadow.jsonl')
OUT=DASH/'wnba_v5_player_prop_action_policy_v2.json'
VERSION='v5_player_prop_action_policy_v2_shadow_1'
MODEL_VERSION='sprint19_player_props_v5_m02_action_v2'
ALLOWED_BOOKS={'draftkings','fanduel','fanatics'}


def f(v,d=None):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception:return d

def norm(v):return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def load(path,default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def read_jsonl(path):
    out=[]
    if not path.exists():return out
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            x=json.loads(line)
            if isinstance(x,dict):out.append(x)
        except Exception:pass
    return out

def valid_odds(o):
    o=f(o)
    return o is not None and (o<=-100 or o>=100)
def side_market(row):
    side=str(row.get('recommendation') or '').upper()
    if side=='OVER':return row.get('best_over_book'),f(row.get('best_over_price'))
    if side=='UNDER':return row.get('best_under_book'),f(row.get('best_under_price'))
    return None,None

def unit_profit(odds,outcome):
    o=f(odds)
    if o is None:return None
    if outcome=='LOSS':return -1.0
    if outcome!='WIN':return 0.0
    return o/100.0 if o>0 else 100.0/abs(o)
def key(target,row):
    return '|'.join(str(x or '') for x in (VERSION,target,row.get('player'),row.get('game'),row.get('stat'),row.get('line'),row.get('recommendation')))
def hist_key(row):
    return '|'.join(str(x or '') for x in (MODEL_VERSION,row.get('date'),row.get('player'),row.get('game'),row.get('stat'),row.get('line'),row.get('signal') or row.get('recommendation')))
def shadow_eligible(row):
    if str(row.get('final_action') or row.get('action') or '').upper()!='WATCH':return False,'not_watch'
    if str(row.get('recommendation') or '').upper() not in {'OVER','UNDER'}:return False,'not_directional'
    if not bool(row.get('candidate_eligible',row.get('eligible'))):return False,'candidate_ineligible'
    status=str(row.get('injury_status') or '').upper()
    if status in {'OUT','DOUBTFUL','QUESTIONABLE','UNKNOWN'}:return False,'injury_limited'
    conf=f(row.get('confidence')); edge=f(row.get('edge'))
    if conf is None or not (60.0<=conf<70.0):return False,'confidence_outside_60_69_9'
    if edge is None or abs(edge)<4.0:return False,'edge_below_4'
    book,odds=side_market(row); bookn=norm(book).replace(' ','')
    if bookn not in ALLOWED_BOOKS:return False,'unsupported_book'
    if not valid_odds(odds):return False,'invalid_price'
    # Require a price whose break-even is at most 60%; historical support is 62.75%.
    if odds < -150:return False,'price_worse_than_-150'
    return True,'historical_high_edge_high_confidence_segment'
def summary(rows):
    resolved=[r for r in rows if r.get('outcome') in {'WIN','LOSS','PUSH','VOID'}]
    wins=sum(r.get('outcome')=='WIN' for r in resolved); losses=sum(r.get('outcome')=='LOSS' for r in resolved)
    pushes=sum(r.get('outcome')=='PUSH' for r in resolved); voids=sum(r.get('outcome')=='VOID' for r in resolved)
    profits=[unit_profit(r.get('odds'),r.get('outcome')) for r in resolved if r.get('outcome') in {'WIN','LOSS'}]
    profits=[x for x in profits if x is not None]
    decisions=wins+losses
    return {'rows':len(rows),'resolved':len(resolved),'pending':len(rows)-len(resolved),'wins':wins,'losses':losses,'pushes':pushes,'voids':voids,'decisions':decisions,'hit_rate':round(wins/decisions,4) if decisions else None,'profit_units':round(sum(profits),4) if profits else 0.0,'roi':round(sum(profits)/len(profits),4) if profits else None}

def main():
    now=datetime.now(timezone.utc).isoformat(); pred=load(PRED,{})
    target=str(pred.get('target_date') or '')[:10]; props=pred.get('player_props') or []
    audit=load(AUDIT,{})
    ledger=read_jsonl(LEDGER); seen={r.get('shadow_id') for r in ledger if r.get('shadow_id')}

    current=[]; added=0; reasons={}
    for row in props:
        ok,reason=shadow_eligible(row); reasons[reason]=reasons.get(reason,0)+1
        item={'player':row.get('player'),'game':row.get('game'),'stat':row.get('stat'),'line':f(row.get('line')),'side':row.get('recommendation'),'confidence':f(row.get('confidence')),'edge':f(row.get('edge')),'current_action':row.get('final_action') or row.get('action'),'shadow_action':'SHADOW_BET' if ok else 'WATCH','shadow_reason':reason}
        book,odds=side_market(row);item['sportsbook']=book;item['odds']=odds
        current.append(item)
        if not ok or not target:continue
        sid=key(target,row)
        if sid in seen:continue
        frozen={'shadow_id':sid,'policy_version':VERSION,'date':target,'issued_at_utc':now,'player':row.get('player'),'team':row.get('team'),'game':row.get('game'),'stat':row.get('stat'),'line':f(row.get('line')),'side':row.get('recommendation'),'projection':f(row.get('model_projection')),'edge':f(row.get('edge')),'confidence':f(row.get('confidence')),'sportsbook':book,'odds':odds,'injury_status':row.get('injury_status'),'original_action':row.get('final_action') or row.get('action'),'shadow_action':'SHADOW_BET','shadow_reason':reason,'outcome':'PENDING','actual':None,'graded_at_utc':None,'research_only':True}
        ledger.append(frozen);seen.add(sid);added+=1

    # Grade only from already-certified current-model history. Decision fields remain frozen.
    hist=read_jsonl(HISTORY); hidx={hist_key(r):r for r in hist if str(r.get('model_version') or '')==MODEL_VERSION and r.get('outcome') in {'WIN','LOSS','PUSH','VOID'}}
    newly_graded=0
    for r in ledger:
        if r.get('outcome')!='PENDING':continue
        h=hidx.get('|'.join(str(x or '') for x in (MODEL_VERSION,r.get('date'),r.get('player'),r.get('game'),r.get('stat'),r.get('line'),r.get('side'))))
        if not h:continue
        r['outcome']=h.get('outcome');r['actual']=h.get('actual');r['graded_at_utc']=h.get('graded_at_utc') or now;r['result_source']='data/history/wnba_model_history.jsonl';newly_graded+=1

    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    with LEDGER.open('w',encoding='utf-8') as fh:
        for r in ledger:fh.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')

    shadow=[r for r in ledger if r.get('shadow_action')=='SHADOW_BET']
    current_shadow=[r for r in current if r.get('shadow_action')=='SHADOW_BET']
    historical_support={'segment':'WATCH + confidence 60-69.9 + absolute edge 4.0+','decisions':102,'wins':64,'losses':38,'hit_rate':0.6275,'source_generated_at_utc':audit.get('generated_at_utc'),'note':'Historical diagnostic only; prospective shadow evidence controls any future promotion.'}
    perf=summary(shadow)
    min_resolved=60
    ready_for_review=perf['decisions']>=min_resolved and (perf.get('roi') is not None and perf['roi']>0)
    payload={'version':'V5','module':'PLAYER_PROP_ACTION_POLICY_V2_SHADOW','generated_at_utc':now,'target_date':target,'status':'READY_SHADOW','research_only':True,'production_mutation':False,'policy_version':VERSION,'policy':{'source_action':'WATCH only','candidate_eligible_required':True,'confidence_min':60.0,'confidence_max_exclusive':70.0,'absolute_edge_min':4.0,'approved_books':sorted(ALLOWED_BOOKS),'minimum_american_odds':-150,'injury_blocked':['OUT','DOUBTFUL','QUESTIONABLE','UNKNOWN']},'historical_support':historical_support,'current':{'input_props':len(props),'shadow_bets':len(current_shadow),'shadow_bet_rows':current_shadow,'exclusion_reasons':reasons},'prospective':{**perf,'newly_issued':added,'newly_graded':newly_graded,'minimum_resolved_for_review':min_resolved,'ready_for_human_review':ready_for_review},'safety':'Shadow only. Does not modify Player Props, Best Bets, portfolio, or production BET/WATCH actions.'}
    OUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2,allow_nan=False))
if __name__=='__main__':main()
