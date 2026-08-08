"""Phase 9: reconstruct missing ALT player-game warehouse rows from raw boxscores.

Targets only canonical v3 rows currently unresolved as WAREHOUSE_RECORD_CARDINALITY_FAILURE.
The recovery is append-only: existing warehouse rows are never rewritten or deleted.
A row is appended only when the canonical game_id + normalized player uniquely identifies
an authoritative raw boxscore row and the requested ALT stat can be derived.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wnba_alt_performance_tracker import stat_value

WAREHOUSE = Path('data/warehouse/wnba_player_game_logs.json')
CANONICAL = Path('data/history/wnba_alt_streak_history_v3.jsonl')
RAW_DIR = Path('data/raw')
REPORT = Path('data/dashboard/wnba_alt_phase9_warehouse_recovery.json')
REPORT_CSV = Path('data/dashboard/wnba_alt_phase9_warehouse_recovery.csv')
WAREHOUSE_REPORT = Path('data/warehouse/wnba_alt_phase9_warehouse_recovery.json')


def norm(v: Any) -> str:
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def num(v: Any) -> float | None:
    try:
        if v is None or str(v).strip()=='' or str(v).lower()=='nan': return None
        return float(v)
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str,Any]]:
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            r=json.loads(line)
            if isinstance(r,dict): out.append(r)
        except Exception: pass
    return out


def load(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception: return default


def raw_rows() -> tuple[list[dict[str,str]], dict[str,list[str]]]:
    rows=[]; teams=defaultdict(list)
    for path in sorted(RAW_DIR.glob('boxscores_*.csv')):
        try:
            with path.open(encoding='utf-8',newline='') as h:
                for r in csv.DictReader(h):
                    gid=str(r.get('game_id') or '').strip()
                    player=str(r.get('player') or '').strip()
                    if not gid or not player: continue
                    r['_source_file']=str(path)
                    rows.append(r)
                    team=str(r.get('team') or '').strip()
                    if team and team not in teams[gid]: teams[gid].append(team)
        except Exception:
            continue
    return rows,teams


def build_record(r: dict[str,str], teams: dict[str,list[str]]) -> dict[str,Any]:
    gid=str(r.get('game_id') or '').strip(); player=str(r.get('player') or '').strip(); team=str(r.get('team') or '').strip()
    pair=teams.get(gid,[])
    opp=next((t for t in pair if norm(t)!=norm(team)),None)
    game=' @ '.join(pair[:2]) if len(pair)>=2 else (f'{team} @ {opp}' if team and opp else None)
    pts=num(r.get('pts')); reb=num(r.get('reb')); ast=num(r.get('ast')); stl=num(r.get('stl')); blk=num(r.get('blk')); tov=num(r.get('tov')); threes=num(r.get('threes')); ftm=num(r.get('ftm')); fta=num(r.get('fta'))
    rec={
        'record_id':f'{gid}|{norm(player)}',
        'game_id':gid,'event_id':gid,'game_date':str(r.get('game_date') or '')[:10],
        'game':game,'player':player,'team':team,'opponent':opp,
        'position':r.get('position'),'starter':str(r.get('starter') or '').lower()=='true','minutes':num(r.get('minutes')),
        'scoring':{'total_pts':pts,'three_pm':threes,'ftm':ftm,'fta':fta,'free_throw_points':ftm},
        'boxscore':{'reb':reb,'ast':ast,'stl':stl,'blk':blk,'tov':tov},
        'fouls':{},
        'derived':{
            'pra':None if None in (pts,reb,ast) else pts+reb+ast,
            'pr':None if None in (pts,reb) else pts+reb,
            'pa':None if None in (pts,ast) else pts+ast,
            'ra':None if None in (reb,ast) else reb+ast,
        },
        'source':'raw_boxscore_phase9_recovery','source_file':r.get('_source_file'),
        'recovered_at_utc':datetime.now(timezone.utc).isoformat(),
        'identity_schema':'player-game-v2',
    }
    return rec


def main() -> None:
    canonical=read_jsonl(CANONICAL)
    payload=load(WAREHOUSE,{'records':[]})
    existing=[r for r in payload.get('records',[]) if isinstance(r,dict)]
    raw,teams=raw_rows()
    raw_index=defaultdict(list)
    for r in raw:
        raw_index[(str(r.get('game_id') or ''),norm(r.get('player'))) ].append(r)
    wh_keys={(str(r.get('game_id') or r.get('event_id') or ''),norm(r.get('player') or r.get('player_name'))) for r in existing}

    targets=[]
    for i,row in enumerate(canonical):
        if row.get('canonical_status')=='UNRESOLVED' and row.get('canonical_resolution_method')=='warehouse_record_cardinality_failure':
            targets.append((i,row))

    appended=[]; diagnostics=[]; counts=Counter()
    for idx,row in targets:
        gid=str(row.get('canonical_game_id') or '')
        player=str(row.get('player') or '')
        key=(gid,norm(player)); candidates=raw_index.get(key,[])
        diag={'archive_index':idx,'date':row.get('date'),'player':player,'game':row.get('game'),'stat':row.get('stat'),'canonical_game_id':gid,'raw_matches':len(candidates)}
        if not gid:
            cls='NO_CANONICAL_GAME_ID'
        elif key in wh_keys:
            cls='ALREADY_PRESENT'
        elif len(candidates)==0:
            # secondary name-normalization scan inside the same official game
            same_game=[r for r in raw if str(r.get('game_id') or '')==gid]
            near=[r for r in same_game if norm(r.get('player')).replace('-',' ')==norm(player).replace('-',' ')]
            if len(near)==1: candidates=near
            else: cls='RAW_BOXSCORE_PLAYER_MISSING'
        if len(candidates)>1:
            # exact duplicate raw rows are safe if core stats agree
            sigs={(r.get('pts'),r.get('reb'),r.get('ast'),r.get('stl'),r.get('blk'),r.get('tov'),r.get('threes')) for r in candidates}
            if len(sigs)==1: candidates=[candidates[0]]
            else: cls='RAW_BOXSCORE_CONFLICT'
        if len(candidates)==1 and key not in wh_keys:
            rec=build_record(candidates[0],teams)
            actual=stat_value(rec,str(row.get('stat') or ''))
            diag['reconstructed_actual']=actual
            if actual is None:
                cls='REQUESTED_STAT_UNAVAILABLE'
            else:
                existing.append(rec); wh_keys.add(key); appended.append(rec); cls='RECOVERED'
        counts[cls]+=1; diag['classification']=cls; diagnostics.append(diag)

    payload['records']=existing
    payload['phase9_recovery']={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),'targets':len(targets),'appended':len(appended),
        'classification_counts':dict(counts),'append_only':True,
    }
    WAREHOUSE.parent.mkdir(parents=True,exist_ok=True)
    WAREHOUSE.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'targets':len(targets),'warehouse_before':len(existing)-len(appended),'warehouse_after':len(existing),'appended':len(appended),'classification_counts':dict(counts),'records':diagnostics}
    text=json.dumps(report,indent=2,allow_nan=False)+'\n'
    for p in (REPORT,WAREHOUSE_REPORT): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')
    REPORT_CSV.parent.mkdir(parents=True,exist_ok=True)
    fields=['archive_index','date','player','game','stat','canonical_game_id','raw_matches','reconstructed_actual','classification']
    with REPORT_CSV.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(diagnostics)
    print(json.dumps({k:report[k] for k in ('targets','warehouse_before','warehouse_after','appended','classification_counts')},indent=2))

if __name__=='__main__': main()
