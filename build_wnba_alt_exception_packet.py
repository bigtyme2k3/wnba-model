"""Build a review-ready recovery packet for unresolved ALT archive records.

This step does not change archive outcomes. It groups every remaining PENDING row,
shows nearby player-game candidates, quantifies matchup/date evidence, and emits a
blank manual-override template. Overrides can later be applied only after an
operator verifies the authoritative game identity.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARCHIVE = Path('data/history/wnba_alt_streak_history.jsonl')
LOGS = Path('data/warehouse/wnba_player_game_logs.json')
JSON_OUT = Path('data/warehouse/wnba_alt_exception_packet.json')
DASH_OUT = Path('data/dashboard/wnba_alt_exception_packet.json')
CSV_OUT = Path('data/warehouse/wnba_alt_exception_packet.csv')
OVERRIDE_OUT = Path('data/manual/wnba_alt_game_mapping_overrides.csv')


def norm(v: Any) -> str:
    return ' '.join(str(v or '').strip().lower().replace('’', "'").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows=[]
    if path.exists():
        for line in path.open(encoding='utf-8'):
            try:
                row=json.loads(line)
                if isinstance(row,dict): rows.append(row)
            except Exception:
                pass
    return rows


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def date_distance(a: str, b: str) -> int | None:
    try:
        da=datetime.fromisoformat(a[:10]); db=datetime.fromisoformat(b[:10])
        return (db-da).days
    except Exception:
        return None


def record_label(r: dict[str, Any]) -> str:
    for key in ('game','matchup'):
        if r.get(key): return str(r[key])
    team=r.get('team') or r.get('team_name') or ''
    opp=r.get('opponent') or r.get('opponent_name') or ''
    return f'{team} vs {opp}'.strip()


def tokens(v: Any) -> set[str]:
    text=norm(v).replace('@',' ').replace('vs.',' ').replace('vs',' ')
    stop={'new','york','los','angeles','las','vegas','golden','state'}
    return {x for x in text.split() if len(x)>2 and x not in stop}


def evidence_score(row: dict[str,Any], rec: dict[str,Any], delta: int) -> tuple[int,list[str]]:
    reasons=[]; score=0
    at=tokens(row.get('game') or row.get('opponent'))
    rt=tokens(record_label(rec))
    overlap=sorted(at & rt)
    if overlap:
        score += min(60, len(overlap)*20)
        reasons.append('matchup tokens: '+', '.join(overlap))
    if delta==0: score+=30; reasons.append('same date')
    elif abs(delta)==1: score+=20; reasons.append('adjacent date')
    elif abs(delta)<=3: score+=10; reasons.append(f'{delta:+d} day date drift')
    row_team=norm(row.get('team'))
    rec_text=norm(record_label(rec)+' '+str(rec.get('team') or rec.get('team_name') or ''))
    if row_team and row_team in rec_text:
        score+=20; reasons.append('player team match')
    return min(score,100), reasons


def main() -> None:
    archive=read_jsonl(ARCHIVE)
    logs=load(LOGS,{'records':[]})
    by_player: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in logs.get('records',[]):
        if isinstance(r,dict) and r.get('player') and r.get('game_date'):
            by_player[norm(r['player'])].append(r)

    unresolved=[]
    grouped=Counter()
    for row_no,row in enumerate(archive,1):
        if str(row.get('outcome') or 'PENDING').upper()!='PENDING': continue
        player=norm(row.get('player')); target=str(row.get('date') or '')[:10]
        candidates=[]
        for rec in by_player.get(player,[]):
            rec_date=str(rec.get('game_date') or '')[:10]
            delta=date_distance(target,rec_date)
            if delta is None or abs(delta)>7: continue
            score,reasons=evidence_score(row,rec,delta)
            candidates.append({
                'game_date':rec_date,'date_delta_days':delta,'game':record_label(rec),
                'team':rec.get('team') or rec.get('team_name'),'opponent':rec.get('opponent') or rec.get('opponent_name'),
                'game_id':rec.get('game_id') or rec.get('event_id'),'evidence_score':score,'evidence':reasons,
            })
        candidates.sort(key=lambda x:(x['evidence_score'],-abs(x['date_delta_days'])),reverse=True)
        top=candidates[:5]
        classification='no_nearby_actual'
        if top:
            if len(top)>1 and top[0]['evidence_score']==top[1]['evidence_score']:
                classification='ambiguous_tie'
            elif top[0]['evidence_score']<70:
                classification='low_confidence'
            else:
                classification='reviewable_candidate'
        grouped[classification]+=1
        unresolved.append({
            'row_number':row_no,'candidate_id':row.get('candidate_id'),'player':row.get('player'),
            'archive_date':target,'archive_game':row.get('game'),'stat':row.get('stat'),'side':row.get('side'),
            'line':row.get('alt_line'),'classification':classification,'candidate_count':len(candidates),
            'top_candidates':top,
        })

    now=datetime.now(timezone.utc).isoformat()
    report={
        'generated_at_utc':now,
        'status':'review_required' if unresolved else 'complete',
        'summary':{'pending_records':len(unresolved),**{k:int(v) for k,v in grouped.items()}},
        'policy':{
            'automatic_changes':False,
            'minimum_manual_evidence':'authoritative schedule or box score confirming player, teams and date',
            'override_file':str(OVERRIDE_OUT),
        },
        'records':unresolved,
    }
    for p in (JSON_OUT,DASH_OUT):
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')

    flat=[]
    for row in unresolved:
        top=row['top_candidates'][0] if row['top_candidates'] else {}
        flat.append({
            'candidate_id':row['candidate_id'],'player':row['player'],'archive_date':row['archive_date'],
            'archive_game':row['archive_game'],'stat':row['stat'],'side':row['side'],'line':row['line'],
            'classification':row['classification'],'candidate_count':row['candidate_count'],
            'top_candidate_date':top.get('game_date'),'top_candidate_game':top.get('game'),
            'top_candidate_game_id':top.get('game_id'),'top_evidence_score':top.get('evidence_score'),
            'top_evidence':' | '.join(top.get('evidence',[])),
        })
    CSV_OUT.parent.mkdir(parents=True,exist_ok=True)
    with CSV_OUT.open('w',encoding='utf-8',newline='') as h:
        fields=list(flat[0].keys()) if flat else ['candidate_id','classification']
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(flat)

    if not OVERRIDE_OUT.exists():
        OVERRIDE_OUT.parent.mkdir(parents=True,exist_ok=True)
        with OVERRIDE_OUT.open('w',encoding='utf-8',newline='') as h:
            fields=['candidate_id','verified_game_date','verified_game_id','verified_game','source_url','reviewer','reviewed_at_utc','notes']
            csv.DictWriter(h,fieldnames=fields).writeheader()

    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__': main()
