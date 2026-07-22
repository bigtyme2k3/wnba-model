"""Merge the legacy core-odds SQLite warehouse into Warehouse V2."""
from __future__ import annotations
import argparse, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
import wnba_odds_warehouse_v2 as v2

LEGACY=Path('data/warehouse/wnba_odds_history.sqlite')
TARGET=Path('data/warehouse/wnba_odds_warehouse_v2.sqlite')
REPORT=Path('data/warehouse/wnba_warehouse_migration_report.json')

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def has(c,n): return c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(n,)).fetchone() is not None
def n(c,t): return int(c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]) if has(c,t) else 0
def dec(p): return None if not p else round(1+(p/100 if p>0 else 100/abs(p)),6)
def units(p,g):
    if g=='loss': return -1.0
    if g=='push': return 0.0
    return None if not p else round(p/100 if p>0 else 100/abs(p),6)

def inv(a,b):
    r=int(a.execute('SELECT COUNT(*) FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL').fetchone()[0])
    return {'legacy':{'games':n(a,'games'),'snapshots':n(a,'snapshots'),'odds_rows':n(a,'odds'),'closing_rows':n(a,'closing_odds'),'games_with_results':r},
            'v2':{'events':n(b,'events'),'snapshots':n(b,'snapshots'),'wagers':n(b,'wagers'),'grades':n(b,'grades'),'closing_wagers':n(b,'closing_wagers')}}

def grade(g,m,s,p):
    h,a=g['home_score'],g['away_score']
    if h is None or a is None: return None,None
    if m=='h2h':
        w=g['home_team'] if h>a else g['away_team'] if a>h else None
        return 1.0 if s==w else 0.0, 'push' if w is None else 'win' if s==w else 'loss'
    if m=='spreads' and p is not None:
        x=(h if s==g['home_team'] else a)+float(p)-(a if s==g['home_team'] else h)
        return x,'win' if x>0 else 'loss' if x<0 else 'push'
    if m=='totals' and p is not None:
        x=h+a
        if x==p:return x,'push'
        return x,'win' if (x>p if s=='Over' else x<p) else 'loss'
    return None,None

def migrate(a,b):
    stamp=now(); stats={'events':0,'snapshots':0,'inserted':0,'skipped':0,'graded':0}
    b.execute("CREATE TABLE IF NOT EXISTS migration_runs(run_id INTEGER PRIMARY KEY,source TEXT,started_at TEXT,finished_at TEXT,status TEXT,report_json TEXT)")
    run=b.execute("INSERT INTO migration_runs(source,started_at,status) VALUES('legacy_v1',?,'running')",(stamp,)).lastrowid
    games={r['game_id']:r for r in a.execute('SELECT * FROM games')}
    for g in games.values():
        done=int(g['home_score'] is not None and g['away_score'] is not None)
        b.execute("""INSERT INTO events(event_id,sport_key,commence_time_utc,game_date_utc,home_team,away_team,completed,home_score,away_score,updated_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET commence_time_utc=excluded.commence_time_utc,game_date_utc=excluded.game_date_utc,
        home_team=excluded.home_team,away_team=excluded.away_team,completed=MAX(events.completed,excluded.completed),
        home_score=COALESCE(events.home_score,excluded.home_score),away_score=COALESCE(events.away_score,excluded.away_score),updated_at_utc=excluded.updated_at_utc""",
        (g['game_id'],g['sport_key'],g['commence_time_utc'],g['game_date_utc'],g['home_team'],g['away_team'],done,g['home_score'],g['away_score'],stamp)); stats['events']+=1
    sm={}
    for s in a.execute('SELECT * FROM snapshots ORDER BY snapshot_time_utc'):
        x=b.execute('SELECT snapshot_id FROM snapshots WHERE returned_at_utc=? ORDER BY snapshot_id LIMIT 1',(s['snapshot_time_utc'],)).fetchone()
        if x: sid=int(x[0])
        else:
            sid=b.execute("""INSERT INTO snapshots(requested_at_utc,returned_at_utc,endpoint_type,event_id,previous_snapshot_utc,next_snapshot_utc,requests_last,requests_used,requests_remaining,created_at_utc)
            VALUES(?,?, 'legacy_core',NULL,?,?,?,?,?,?)""",(s['requested_at_utc'],s['snapshot_time_utc'],s['previous_snapshot_utc'],s['next_snapshot_utc'],s['api_requests_last'],s['api_requests_used'],s['api_requests_remaining'],stamp)).lastrowid
        sm[int(s['snapshot_id'])]=sid; stats['snapshots']+=1
    for o in a.execute('SELECT * FROM odds ORDER BY odds_id'):
        g=games.get(o['game_id']); sid=sm[int(o['snapshot_id'])]
        if not g: continue
        match=f"{g['away_team']} @ {g['home_team']}"
        outs=[('h2h',g['home_team'],g['home_team'],None,o['home_moneyline']),('h2h',g['away_team'],g['away_team'],None,o['away_moneyline']),
              ('spreads',g['home_team'],g['home_team'],o['home_spread'],o['home_spread_price']),('spreads',g['away_team'],g['away_team'],o['away_spread'],o['away_spread_price']),
              ('totals',match,'Over',o['total'],o['over_price']),('totals',match,'Under',o['total'],o['under_price'])]
        for m,part,sel,pt,price in outs:
            if price is None: continue
            ptkey='' if pt is None else f'{float(pt):g}'
            key=f'legacy_v1|{m}|{part}|{sel}|{ptkey}'
            before=b.total_changes
            b.execute("""INSERT OR IGNORE INTO wagers(snapshot_id,event_id,bookmaker_key,bookmaker_title,bookmaker_last_update_utc,market_key,market_last_update_utc,participant,description,selection,point,american_price,decimal_price,outcome_key,created_at_utc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(sid,o['game_id'],o['bookmaker_key'],o['bookmaker_title'],o['bookmaker_last_update_utc'],m,o['bookmaker_last_update_utc'],part,'migrated from legacy core warehouse',sel,pt,price,dec(price),key,stamp))
            stats['inserted' if b.total_changes>before else 'skipped']+=1
            w=b.execute('SELECT * FROM wagers WHERE snapshot_id=? AND event_id=? AND bookmaker_key=? AND market_key=? AND outcome_key=?',(sid,o['game_id'],o['bookmaker_key'],m,key)).fetchone()
            actual,result=grade(g,m,sel,pt)
            if w and result:
                b.execute("""INSERT INTO grades(wager_id,actual_result,grade,profit_units,graded_at_utc,grading_source,notes) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(wager_id) DO UPDATE SET actual_result=excluded.actual_result,grade=excluded.grade,profit_units=excluded.profit_units,graded_at_utc=excluded.graded_at_utc,grading_source=excluded.grading_source,notes=excluded.notes""",
                (w['wager_id'],actual,result,units(price,result),stamp,'legacy_v1_final_scores','verified migration grade')); stats['graded']+=1
    b.execute("UPDATE migration_runs SET finished_at=?,status='complete',report_json=? WHERE run_id=?",(now(),json.dumps(stats),run)); b.commit(); return stats

def validate(a,b):
    dup=int(b.execute("SELECT COUNT(*) FROM (SELECT snapshot_id,event_id,bookmaker_key,market_key,outcome_key,COUNT(*) c FROM wagers GROUP BY 1,2,3,4,5 HAVING c>1)").fetchone()[0])
    mig=int(b.execute("SELECT COUNT(*) FROM wagers WHERE description='migrated from legacy core warehouse'").fetchone()[0])
    lr=int(a.execute('SELECT COUNT(*) FROM games WHERE home_score IS NOT NULL AND away_score IS NOT NULL').fetchone()[0]); vr=int(b.execute('SELECT COUNT(*) FROM events WHERE home_score IS NOT NULL AND away_score IS NOT NULL').fetchone()[0])
    ok=n(b,'events')>=n(a,'games') and mig>0 and vr>=lr and dup==0
    return {'legacy_games':n(a,'games'),'v2_events':n(b,'events'),'migrated_wagers':mig,'legacy_results':lr,'v2_results':vr,'duplicate_keys':dup,'passed':ok}

def main():
    p=argparse.ArgumentParser();p.add_argument('--legacy-db',type=Path,default=LEGACY);p.add_argument('--v2-db',type=Path,default=TARGET);p.add_argument('--report',type=Path,default=REPORT);p.add_argument('--execute',action='store_true');x=p.parse_args()
    if not x.legacy_db.exists():raise SystemExit(f'Missing {x.legacy_db}')
    a=sqlite3.connect(x.legacy_db);a.row_factory=sqlite3.Row;b=v2.connect(x.v2_db)
    out={'generated_at_utc':now(),'mode':'execute' if x.execute else 'inventory','before':inv(a,b)}
    if x.execute:out['migration']=migrate(a,b);out['validation']=validate(a,b);out['after']=inv(a,b)
    x.report.parent.mkdir(parents=True,exist_ok=True);x.report.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
    if x.execute and not out['validation']['passed']:raise SystemExit('validation failed')
if __name__=='__main__':main()
