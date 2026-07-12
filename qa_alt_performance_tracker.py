"""Deterministic acceptance tests for ALT snapshot, grading, and analytics."""
from __future__ import annotations
import json,os,tempfile
from contextlib import contextmanager
from pathlib import Path
import wnba_alt_performance_tracker as tracker

@contextmanager
def cwd():
    old=os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:yield
        finally:os.chdir(old)

def test_snapshot_grade_analyze():
    with cwd():
        Path('data/dashboard').mkdir(parents=True)
        Path('data/warehouse').mkdir(parents=True)
        alt={'rows':[{'player':'Player A','game':'X @ Y','stat':'PTS','side':'OVER','alt_line':9.5,'best_odds':-120,'best_book':'Book','streak_score':91,'streak_grade':'A+','streak_action':'BET','l5_hits':5,'l5_games':5,'l5_pct':1.0,'l10_hits':9,'l10_games':10,'l10_pct':.9,'season_hits':18,'season_games':20,'season_pct':.9,'opponent_rank_source':'wnba_pace_minutes_opponent_rankings'}]}
        json.dump(alt,open('data/dashboard/wnba_alt_streaks.json','w'))
        logs={'records':[{'player':'Player A','game_date':'2099-01-01','scoring':{'total_pts':12},'boxscore':{},'fouls':{},'derived':{}}]}
        json.dump(logs,open('data/warehouse/wnba_player_game_logs.json','w'))
        s=tracker.snapshot('2099-01-01');assert s['added']==1
        s2=tracker.snapshot('2099-01-01');assert s2['duplicates']==1
        g=tracker.grade_all();assert g['win']==1
        report=tracker.analyze('2099-01-01');assert report['summary']['wins']==1
        assert report['summary']['profit_loss_units']>0
        rows=tracker.read_jsonl(Path('data/history/wnba_alt_streak_history.jsonl'))
        assert rows[0]['outcome']=='WIN' and rows[0]['actual']==12

def test_missing_actual_stays_pending():
    with cwd():
        Path('data/dashboard').mkdir(parents=True);Path('data/warehouse').mkdir(parents=True)
        json.dump({'rows':[{'player':'Missing','stat':'REB','side':'UNDER','alt_line':5.5,'best_odds':-110}]},open('data/dashboard/wnba_alt_streaks.json','w'))
        json.dump({'records':[]},open('data/warehouse/wnba_player_game_logs.json','w'))
        tracker.snapshot('2099-01-01');g=tracker.grade_all();assert g['pending']==1

def main():
    tests=[('snapshot grade analyze',test_snapshot_grade_analyze),('pending actuals',test_missing_actual_stays_pending)];results=[]
    for name,fn in tests:
        try:fn();results.append({'test':name,'passed':True,'detail':''})
        except Exception as e:results.append({'test':name,'passed':False,'detail':str(e)})
    failed=[r for r in results if not r['passed']]
    report={'status':'green' if not failed else 'red','summary':{'tests':len(results),'passed':len(results)-len(failed),'failed':len(failed)},'tests':results}
    Path('data/dashboard').mkdir(parents=True,exist_ok=True);json.dump(report,open('data/dashboard/wnba_alt_performance_acceptance.json','w'),indent=2)
    print(report['summary'])
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
