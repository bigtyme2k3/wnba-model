"""Phase 10B: recover unresolved ALT rows from repository-local raw files first.

Uses data/raw/boxscores_*.csv plus odds_*.csv game metadata. Never rewrites existing
warehouse rows; appends only unique player-game records and emits Phase10-compatible
official resolutions. No network dependency.
"""
from __future__ import annotations
import csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

UNRES=Path('data/dashboard/wnba_alt_archive_unresolved_v3.csv')
AUDIT=Path('data/dashboard/wnba_alt_game_identity_audit.json')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
OVR=Path('data/warehouse/wnba_alt_phase10_official_resolutions.json')
OUT=Path('data/dashboard/wnba_alt_phase10b_local_recovery.json')
OUTCSV=Path('data/dashboard/wnba_alt_phase10b_local_recovery.csv')
OUTW=Path('data/warehouse/wnba_alt_phase10b_local_recovery.json')
RAW=Path('data/raw')
TEAM_ALIASES={'aces':'las vegas aces','dream':'atlanta dream','fever':'indiana fever','liberty':'new york liberty','lynx':'minnesota lynx','mercury':'phoenix mercury','mystics':'washington mystics','sky':'chicago sky','sparks':'los angeles sparks','storm':'seattle storm','sun':'connecticut sun','wings':'dallas wings','valkyries':'golden state valkyries','tempo':'toronto tempo','fire':'portland fire'}

def norm(v:Any)->str:
    x=' '.join(str(v or '').strip().lower().replace('’',"'").split());return TEAM_ALIASES.get(x,x)
def num(v:Any):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except Exception:return None
def load(p,default):
    try:return json.loads(Path(p).read_text(encoding='utf-8')) if Path(p).exists() else default
    except Exception:return default
def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def parse_game(g):
    s=str(g or '').replace(' vs. ',' @ ').replace(' vs ',' @ ')
    if '@' not in s:return ('','')
    a,b=s.split('@',1);return norm(a),norm(b)

def raw_rows():
    rows=[]
    for p in sorted(RAW.glob('boxscores_*.csv')):
        try:
            with p.open(encoding='utf-8-sig',newline='') as h:
                for r in csv.DictReader(h):
                    if r.get('player') and (r.get('game_id') or r.get('event_id')):
                        r['_source_file']=str(p);rows.append(r)
        except Exception:pass
    return rows

def game_meta():
    meta={}
    for p in sorted(RAW.glob('odds_*.csv')):
        try:
            with p.open(encoding='utf-8-sig',newline='') as h:
                for r in csv.DictReader(h):
                    gid=str(r.get('game_id') or '')
                    if gid:
                        away=r.get('away_team') or '';home=r.get('home_team') or ''
                        meta[gid]={'away':norm(away),'home':norm(home),'game':f'{away} @ {home}','date':str(r.get('game_date') or '')[:10]}
        except Exception:pass
    return meta

def build(rr,meta,method):
    gid=str(rr.get('game_id') or rr.get('event_id') or '');day=str(rr.get('game_date') or '')[:10]
    pts=num(rr.get('pts'));reb=num(rr.get('reb'));ast=num(rr.get('ast'));stl=num(rr.get('stl'));blk=num(rr.get('blk'));tov=num(rr.get('tov'));pf=num(rr.get('pf'));three=num(rr.get('threes') or rr.get('three_pm') or rr.get('3pm'));oreb=num(rr.get('oreb'));dreb=num(rr.get('dreb'))
    return {'record_id':f"{gid}|{norm(rr.get('player'))}",'game_id':gid,'event_id':gid,'game_date':day,'game':(meta.get(gid) or {}).get('game'),'player':rr.get('player'),'team':rr.get('team'),'scoring':{'total_pts':pts,'three_pm':three,'ftm':num(rr.get('ftm')),'fta':num(rr.get('fta')),'free_throw_points':num(rr.get('ftm'))},'boxscore':{'reb':reb,'oreb':oreb,'dreb':dreb,'ast':ast,'stl':stl,'blk':blk,'tov':tov},'fouls':{'total_committed':pf},'derived':{'pra':None if None in (pts,reb,ast) else pts+reb+ast,'pr':None if None in (pts,reb) else pts+reb,'pa':None if None in (pts,ast) else pts+ast,'ra':None if None in (reb,ast) else reb+ast},'phase10b_recovered':True,'phase10b_resolution_method':method,'source':rr.get('_source_file'),'recovered_at_utc':datetime.now(timezone.utc).isoformat()}

def main():
    unresolved=list(csv.DictReader(UNRES.open(encoding='utf-8'))) if UNRES.exists() else []
    audit=load(AUDIT,{'records':[]});diags={int(r.get('archive_index',i)):r for i,r in enumerate(audit.get('records',[])) if isinstance(r,dict)}
    raw=raw_rows();meta=game_meta();logs=load(LOGS,{'records':[]});records=[r for r in logs.get('records',[]) if isinstance(r,dict)]
    existing={(str(r.get('game_id') or r.get('event_id') or ''),norm(r.get('player') or r.get('player_name'))) for r in records}
    by_gid_player=defaultdict(list);by_date_player=defaultdict(list)
    for r in raw:
        gid=str(r.get('game_id') or r.get('event_id') or '');p=norm(r.get('player'));d=str(r.get('game_date') or '')[:10]
        by_gid_player[(gid,p)].append(r);by_date_player[(d,p)].append(r)
    resolutions={};results=[];appended=[];counts=Counter()
    for row in unresolved:
        idx=int(row.get('archive_index') or -1);diag=diags.get(idx,{});p=norm(row.get('player'));ad=str(row.get('date') or '')[:10];ga,gh=parse_game(row.get('game'))
        chosen=None;method=None
        gid=str(diag.get('warehouse_game_id') or '')
        exact=by_gid_player.get((gid,p),[]) if gid else []
        if len(exact)==1:
            chosen=exact[0];method='local_raw_audit_game_id'
        if chosen is None:
            same=by_date_player.get((ad,p),[])
            if ga and gh:
                same_match=[r for r in same if (meta.get(str(r.get('game_id') or '')) or {}).get('away')==ga and (meta.get(str(r.get('game_id') or '')) or {}).get('home')==gh]
                gids={str(r.get('game_id') or '') for r in same_match}
                if len(gids)==1 and len(same_match)>=1:
                    chosen=same_match[0];method='local_raw_exact_matchup_same_date'
            if chosen is None:
                gids={str(r.get('game_id') or '') for r in same}
                if len(gids)==1 and len(same)>=1:
                    chosen=same[0];method='local_raw_unique_player_game_same_date'
        if chosen is None and ga and gh:
            near=[]
            for (d,pp),lst in by_date_player.items():
                if pp!=p:continue
                for r in lst:
                    gm=meta.get(str(r.get('game_id') or '')) or {}
                    if gm.get('away')==ga and gm.get('home')==gh:near.append(r)
            gids={str(r.get('game_id') or '') for r in near}
            if len(gids)==1 and near:
                chosen=near[0];method='local_raw_unique_exact_matchup_any_date'
        if chosen is None:
            counts['UNRESOLVED_LOCAL']+=1;results.append({'archive_index':idx,'player':row.get('player'),'date':ad,'game':row.get('game'),'status':'UNRESOLVED_LOCAL'});continue
        gid=str(chosen.get('game_id') or chosen.get('event_id') or '');day=str(chosen.get('game_date') or '')[:10];key=(gid,p)
        if key not in existing:
            rec=build(chosen,meta,method);records.append(rec);appended.append(rec);existing.add(key)
        gm=meta.get(gid) or {};game=gm.get('game') or row.get('game')
        resolutions[str(idx)]={'archive_index':idx,'player':row.get('player'),'canonical_game_id':gid,'canonical_game_date':day,'canonical_game':game,'resolution_method':method,'source':chosen.get('_source_file')}
        results.append({'archive_index':idx,'player':row.get('player'),'date':ad,'game':row.get('game'),'status':'RESOLVED_LOCAL','canonical_game_id':gid,'canonical_game_date':day,'method':method,'source':chosen.get('_source_file')});counts['RESOLVED_LOCAL']+=1
    logs['records']=records;logs['phase10b_recovered_records']=len(appended);logs['phase10b_updated_at_utc']=datetime.now(timezone.utc).isoformat();save(LOGS,logs)
    save(OVR,{'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source':'repository_local_raw','resolutions':resolutions,'count':len(resolutions)})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input_unresolved':len(unresolved),'raw_boxscore_files':len(list(RAW.glob('boxscores_*.csv'))),'raw_odds_files':len(list(RAW.glob('odds_*.csv'))),'raw_player_rows':len(raw),'resolved':len(resolutions),'warehouse_appended':len(appended),'status_counts':dict(counts),'records':results}
    save(OUT,report);save(OUTW,report)
    fields=sorted({k for r in results for k in r}) if results else ['archive_index','status'];OUTCSV.parent.mkdir(parents=True,exist_ok=True)
    with OUTCSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(results)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
    if unresolved and not raw:
        raise SystemExit('RECOVERY_SOURCE_UNAVAILABLE: no repository-local raw boxscores found')

if __name__=='__main__':main()
