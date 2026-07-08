from __future__ import annotations
import argparse, glob, json, os
from datetime import date, datetime, timezone
import pandas as pd

RAW='data/raw'

def safe_num(s):
    return pd.to_numeric(s, errors='coerce').fillna(0)

def build(out=RAW):
    paths=sorted(glob.glob(os.path.join(out,'boxscores_*.csv')))
    frames=[]
    for p in paths:
        try:
            df=pd.read_csv(p)
            if len(df)>0 and {'player','team','minutes','pts','reb','ast'}.issubset(set(df.columns)):
                frames.append(df)
        except Exception:
            pass
    status={'source':'boxscore_fallback','checked_at_utc':datetime.now(timezone.utc).isoformat(),'files':len(paths),'usable_files':len(frames),'players_live_rows':0,'status':'missing','error':None}
    if not frames:
        os.makedirs(out,exist_ok=True)
        json.dump(status,open(os.path.join(out,'wnba_stats_fallback_status.json'),'w',encoding='utf-8'),indent=2)
        return status
    df=pd.concat(frames,ignore_index=True)
    df['game_date']=pd.to_datetime(df.get('game_date'), errors='coerce')
    for c in ['minutes','pts','reb','ast','stl','blk','tov','threes']:
        if c not in df.columns: df[c]=0
        df[c]=safe_num(df[c])
    df=df.dropna(subset=['game_date'])
    players={}
    season_rows=[]; recent_rows=[]
    for name,g in df.groupby('player'):
        g=g.sort_values('game_date')
        if not str(name).strip(): continue
        recent=g.tail(5)
        team=str(g['team'].dropna().iloc[-1]) if 'team' in g and len(g['team'].dropna()) else ''
        pos=str(g['position'].dropna().iloc[-1]) if 'position' in g and len(g['position'].dropna()) else ''
        gp=int(g['game_id'].nunique()) if 'game_id' in g.columns else int(len(g))
        ppg=round(float(g['pts'].mean()),2); mpg=round(float(g['minutes'].mean()),2); reb=round(float(g['reb'].mean()),2); ast=round(float(g['ast'].mean()),2); threes=round(float(g['threes'].mean()),2)
        r_pts=round(float(recent['pts'].mean()),2); r_mpg=round(float(recent['minutes'].mean()),2); r_reb=round(float(recent['reb'].mean()),2); r_ast=round(float(recent['ast'].mean()),2); r_threes=round(float(recent['threes'].mean()),2)
        usage=max(0.12,min(0.36,0.18+(ppg/80)+(ast/120)))
        players[str(name)]={'player':str(name),'team':team,'pos':pos,'gp':gp,'ppg':ppg,'mpg':mpg,'usage':round(usage,3),'ts':0.55,'ts_pct':0.55,'reb':reb,'ast':ast,'roll5_pts':r_pts,'roll5_reb':r_reb,'roll5_ast':r_ast,'roll5_mpg':r_mpg,'roll5_threes':r_threes,'roll5_gp':int(len(recent)),'recent_source':'boxscores fallback last 5 available games','net_rating':None,'pace':None,'team_ortg':None,'team_drtg':None,'team_pace':None,'opp_pts_allowed_team':None,'source':'boxscores_fallback','updated_at':datetime.now(timezone.utc).isoformat()}
        season_rows.append({'PLAYER_NAME':name,'TEAM_ABBREVIATION':team,'PLAYER_POSITION':pos,'GP':gp,'MIN':mpg,'PTS':ppg,'REB':reb,'AST':ast,'FG3M':threes})
        recent_rows.append({'PLAYER_NAME':name,'TEAM_ABBREVIATION':team,'PLAYER_POSITION':pos,'GP':int(len(recent)),'MIN':r_mpg,'PTS':r_pts,'REB':r_reb,'AST':r_ast,'FG3M':r_threes})
    os.makedirs(out,exist_ok=True)
    pd.DataFrame(season_rows).to_csv(os.path.join(out,'wnba_player_stats.csv'),index=False)
    pd.DataFrame(recent_rows).to_csv(os.path.join(out,'wnba_player_recent5.csv'),index=False)
    json.dump(players,open(os.path.join(out,'wnba_players_live.json'),'w',encoding='utf-8'),indent=2)
    status.update({'players_live_rows':len(players),'status':'ok' if players else 'empty','output':'data/raw/wnba_players_live.json'})
    json.dump(status,open(os.path.join(out,'wnba_stats_fallback_status.json'),'w',encoding='utf-8'),indent=2)
    print('Boxscore fallback stats built:',status)
    return status

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',default=RAW); args=ap.parse_args(); build(args.out)
if __name__=='__main__': main()
