from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
import pandas as pd

def load_json(path, default):
    try:
        if os.path.exists(path): return json.load(open(path,encoding='utf-8'))
    except Exception: pass
    return default

def csv_rows(path):
    try:
        if os.path.exists(path): return len(pd.read_csv(path))
    except Exception: pass
    return 0

def build(target):
    stats_status=load_json('data/raw/wnba_stats_status.json',{})
    players=load_json('data/raw/wnba_players_live.json',{})
    intel=load_json('data/warehouse/wnba_player_intelligence.json',{})
    player_rows=len(players) if isinstance(players,dict) else 0
    intel_rows=len(intel.get('players',[])) if isinstance(intel,dict) else 0
    base_rows=csv_rows('data/raw/wnba_player_stats.csv')
    recent_rows=csv_rows('data/raw/wnba_player_recent5.csv')
    status='ok' if player_rows>=80 and recent_rows>=50 else 'degraded' if player_rows>0 else 'missing'
    issues=[]
    if not player_rows: issues.append('wnba_players_live.json missing or empty')
    if not recent_rows: issues.append('recent 5 stats missing; recent form may fallback to season averages')
    if intel_rows<player_rows and player_rows: issues.append('player intelligence did not match all live players')
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':status,'summary':{'live_players':player_rows,'player_intelligence_rows':intel_rows,'season_stats_rows':base_rows,'recent5_rows':recent_rows,'advanced_rows':csv_rows('data/raw/wnba_player_advanced.csv'),'team_stats_rows':csv_rows('data/raw/wnba_team_stats.csv')},'issues':issues,'stats_status':stats_status,'note':'Stats are trusted only when live_players and recent5_rows are populated. Otherwise projections should lean more on market odds and be labeled degraded.'}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_stats_quality.json','data/dashboard/wnba_stats_quality.json']:
        json.dump(report,open(p,'w',encoding='utf-8'),indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Stats quality built:', build(args.date)['summary'])
if __name__=='__main__': main()
