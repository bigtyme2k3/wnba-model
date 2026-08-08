"""Phase 12 safe local recovery for the remaining ALT archive edge cases.

Targets only explicit unresolved rows and only resolves when repository-local raw
boxscores identify exactly one player-game with the requested stat available.
Existing warehouse rows are enriched only where the target field is missing;
otherwise they are preserved. Ambiguous repeated matchups are never guessed.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter, defaultdict
from datetime import datetime, timezone, datetime as dt
from pathlib import Path
from typing import Any

UNRES=Path('data/dashboard/wnba_alt_archive_unresolved_v3.csv')
AUDIT=Path('data/dashboard/wnba_alt_game_identity_audit.json')
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
OUT=Path('data/dashboard/wnba_alt_phase12_recovery.json')
OUTCSV=Path('data/dashboard/wnba_alt_phase12_recovery.csv')
OUTW=Path('data/warehouse/wnba_alt_phase12_recovery.json')
OVR=Path('data/warehouse/wnba_alt_phase12_resolutions.json')
RAW=Path('data/raw')
TEAM_ALIASES={'aces':'las vegas aces','dream':'atlanta dream','fever':'indiana fever','liberty':'new york liberty','lynx':'minnesota lynx','mercury':'phoenix mercury','mystics':'washington mystics','sky':'chicago sky','sparks':'los angeles sparks','storm':'seattle storm','sun':'connecticut sun','wings':'dallas wings','valkyries':'golden state valkyries','tempo':'toronto tempo','fire':'portland fire'}

def norm(v:Any)->str:
    x=' '.join(str(v or '').strip().lower().replace('’',"'").split()); return TEAM_ALIASES.get(x,x)
def num(v:Any):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception:return None
def load(p,default):
    try:return json.loads(Path(p).read_text(encoding='utf-8')) if Path(p).exists() else default
    except Exception:return default
def save(p,obj):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def parse_game(g):
    s=str(g or '').replace(' vs. ',' @ ').replace(' vs ',' @ ')
    if '@' not in s:return ('','')
    a,b=s.split('@',1); return norm(a),norm(b)
def daydiff(a,b):
    try:return abs((dt.fromisoformat(a[:10])-dt.fromisoformat(b[:10])).days)
    except Exception:return 999

def raw_rows():
    rows=[]
    for p in sorted(RAW.glob('boxscores_*.csv')):
        try:
            with p.open(encoding='utf-8-sig',newline='') as h:
                for r in csv.DictReader(h):
                    if r.get('player') and (r.get('game_id') or r.get('event_id')):
                        r['_source_file']=str(p); rows.append(r)
        except Exception: pass
    return rows

def game_meta():
    meta={}
    for pat in ('odds_*.csv','scores_*.csv'):
        for p in sorted(RAW.glob(pat)):
            try:
                with p.open(encoding='utf-8-sig',newline='') as h:
                    for r in csv.DictReader(h):
                        gid=str(r.get('game_id') or r.get('event_id') or '')
                        if not gid: continue
                        away=r.get('away_team') or r.get('away') or ''
                        home=r.get('home_team') or r.get('home') or ''
                        date=str(r.get('game_date') or r.get('date') or '')[:10]
                        if away and home:
                            meta[gid]={'away':norm(away),'home':norm(home),'game':f'{away} @ {home}','date':date,'source':str(p)}
            except Exception: pass
    return meta

def stat_from_raw(r,stat):
    pts=num(r.get('pts')); reb=num(r.get('reb')); ast=num(r.get('ast')); three=num(r.get('threes') or r.get('three_pm') or r.get('3pm'))
    vals={'PTS':pts,'REB':reb,'AST':ast,'3PM':three}
    if pts is not None and reb is not None: vals['PR']=pts+reb
    if pts is not None and ast is not None: vals['PA']=pts+ast
    if reb is not None and ast is not None: vals['RA']=reb+ast
    if pts is not None and reb is not None and ast is not None: vals['PRA']=pts+reb+ast
    return vals.get(str(stat or '').upper())

def raw_to_record(rr,meta,method):
    gid=str(rr.get('game_id') or rr.get('event_id') or '')
    pts=num(rr.get('pts'));reb=num(rr.get('reb'));ast=num(rr.get('ast'));three=num(rr.get('threes') or rr.get('three_pm') or rr.get('3pm'))
    return {'record_id':f"{gid}|{norm(rr.get('player'))}",'game_id':gid,'event_id':gid,'game_date':str(rr.get('game_date') or (meta.get(gid) or {}).get('date') or '')[:10],
            'game':(meta.get(gid) or {}).get('game'),'player':rr.get('player'),'team':rr.get('team'),
            'scoring':{'total_pts':pts,'three_pm':three,'ftm':num(rr.get('ftm')),'fta':num(rr.get('fta')),'free_throw_points':num(rr.get('ftm'))},
            'boxscore':{'reb':reb,'oreb':num(rr.get('oreb')),'dreb':num(rr.get('dreb')),'ast':ast,'stl':num(rr.get('stl')),'blk':num(rr.get('blk')),'tov':num(rr.get('tov'))},
            'fouls':{'total_committed':num(rr.get('pf'))},
            'derived':{'pra':None if None in (pts,reb,ast) else pts+reb+ast,'pr':None if None in (pts,reb) else pts+reb,'pa':None if None in (pts,ast) else pts+ast,'ra':None if None in (reb,ast) else reb+ast},
            'phase12_recovered':True,'phase12_resolution_method':method,'source':rr.get('_source_file'),'recovered_at_utc':datetime.now(timezone.utc).isoformat()}

def merge_missing(dst,src):
    changed=False
    for section in ('scoring','boxscore','fouls','derived'):
        dst.setdefault(section,{})
        for k,v in (src.get(section) or {}).items():
            if dst[section].get(k) is None and v is not None:
                dst[section][k]=v; changed=True
    if changed:
        dst['phase12_enriched']=True; dst['phase12_enriched_at_utc']=datetime.now(timezone.utc).isoformat(); dst['phase12_source']=src.get('source')
    return changed

def main():
    unresolved=list(csv.DictReader(UNRES.open(encoding='utf-8'))) if UNRES.exists() else []
    audit=load(AUDIT,{'records':[]}); diags={i:r for i,r in enumerate(audit.get('records',[])) if isinstance(r,dict)}
    raw=raw_rows(); meta=game_meta(); logs=load(LOGS,{'records':[]}); records=[r for r in logs.get('records',[]) if isinstance(r,dict)]
    by_gp=defaultdict(list); by_dp=defaultdict(list)
    for rr in raw:
        gid=str(rr.get('game_id') or rr.get('event_id') or ''); p=norm(rr.get('player')); d=str(rr.get('game_date') or (meta.get(gid) or {}).get('date') or '')[:10]
        by_gp[(gid,p)].append(rr); by_dp[(d,p)].append(rr)
    wh=defaultdict(list)
    for r in records:
        gid=str(r.get('game_id') or r.get('event_id') or ''); p=norm(r.get('player') or r.get('player_name'))
        if gid and p: wh[(gid,p)].append(r)

    results=[]; resolutions={}; counts=Counter(); appended=0; enriched=0
    for row in unresolved:
        idx=int(row.get('archive_index') or -1); p=norm(row.get('player')); ad=str(row.get('date') or '')[:10]; stat=str(row.get('stat') or '').upper(); ga,gh=parse_game(row.get('game')); diag=diags.get(idx,{})
        candidates=[]
        # 1) audited warehouse game id, if local raw confirms player + requested stat.
        gid=str(diag.get('warehouse_game_id') or '')
        if gid:
            candidates.extend(by_gp.get((gid,p),[]))
        # 2) explicitly listed candidate dates.
        for d in str(row.get('candidate_dates') or '').split('|'):
            d=d.strip()[:10]
            if d: candidates.extend(by_dp.get((d,p),[]))
        # 3) archive date.
        candidates.extend(by_dp.get((ad,p),[]))
        # 4) nearby exact matchup, maximum seven days from archive metadata date.
        for (d,pp),lst in by_dp.items():
            if pp!=p or daydiff(d,ad)>7: continue
            for rr in lst:
                gm=meta.get(str(rr.get('game_id') or rr.get('event_id') or '')) or {}
                if ga and gh and gm.get('away')==ga and gm.get('home')==gh: candidates.append(rr)

        # Deduplicate raw candidates by game id, then require exact matchup where metadata exists.
        uniq={}
        for rr in candidates:
            rgid=str(rr.get('game_id') or rr.get('event_id') or '')
            if not rgid or stat_from_raw(rr,stat) is None: continue
            gm=meta.get(rgid) or {}
            if ga and gh and gm.get('away') and (gm.get('away')!=ga or gm.get('home')!=gh): continue
            uniq.setdefault(rgid,rr)
        if len(uniq)!=1:
            counts['UNRESOLVED_AMBIGUOUS_OR_MISSING']+=1
            results.append({'archive_index':idx,'player':row.get('player'),'classification':row.get('classification'),'status':'UNRESOLVED','candidate_game_ids':'|'.join(sorted(uniq))})
            continue
        rgid,rr=next(iter(uniq.items())); gm=meta.get(rgid) or {}; method='phase12_unique_local_player_matchup_stat'
        source_rec=raw_to_record(rr,meta,method)
        existing=wh.get((rgid,p),[])
        if len(existing)==0:
            records.append(source_rec); wh[(rgid,p)].append(source_rec); appended+=1
        elif len(existing)==1:
            if merge_missing(existing[0],source_rec): enriched+=1
        else:
            # Cardinality remains genuinely ambiguous; do not make it worse.
            counts['UNRESOLVED_WAREHOUSE_MULTIPLE']+=1
            results.append({'archive_index':idx,'player':row.get('player'),'classification':row.get('classification'),'status':'UNRESOLVED_WAREHOUSE_MULTIPLE','canonical_game_id':rgid})
            continue
        resolutions[str(idx)]={'archive_index':idx,'player':row.get('player'),'canonical_game_id':rgid,'canonical_game_date':str(rr.get('game_date') or gm.get('date') or '')[:10],
                               'canonical_game':gm.get('game') or row.get('game'),'resolution_method':method,'source':rr.get('_source_file')}
        counts['RESOLVED']+=1
        results.append({'archive_index':idx,'player':row.get('player'),'classification':row.get('classification'),'status':'RESOLVED','canonical_game_id':rgid,'canonical_game_date':resolutions[str(idx)]['canonical_game_date'],'source':rr.get('_source_file')})

    logs['records']=records; logs['phase12_appended']=appended; logs['phase12_enriched']=enriched; logs['phase12_updated_at_utc']=datetime.now(timezone.utc).isoformat(); save(LOGS,logs)
    save(OVR,{'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source':'phase12_repository_local_safe_recovery','count':len(resolutions),'resolutions':resolutions})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'input_unresolved':len(unresolved),'resolved':len(resolutions),'warehouse_appended':appended,'warehouse_enriched':enriched,'remaining_this_pass':len(unresolved)-len(resolutions),'status_counts':dict(counts),'records':results}
    save(OUT,report); save(OUTW,report)
    fields=sorted({k for r in results for k in r}) if results else ['archive_index','status']; OUTCSV.parent.mkdir(parents=True,exist_ok=True)
    with OUTCSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(results)
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))

if __name__=='__main__': main()
