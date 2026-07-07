"""
scrape_wnba_stats.py
--------------------
Pulls live WNBA player and team stats from stats.wnba.com.

Fixes:
- Avoids pandas DataFrame truth-value errors.
- Saves a clear status file when official stats are blocked or empty.
- Builds player baselines from season stats and Last 5 Games stats when available.
"""
from __future__ import annotations
import argparse,json,os,time
from datetime import date,datetime,timezone
from typing import Any,Dict,Optional
import pandas as pd
import requests
BASE_URL='https://stats.wnba.com/stats'; LEAGUE_ID='10'; DEFAULT_OUT='data/raw'
HEADERS={'User-Agent':'Mozilla/5.0 (Linux; Android 13; Tablet) AppleWebKit/537.36 Chrome/120 Safari/537.36','Accept':'application/json, text/plain, */*','Accept-Language':'en-US,en;q=0.9','Accept-Encoding':'gzip, deflate, br','Connection':'keep-alive','Host':'stats.wnba.com','Origin':'https://stats.wnba.com','Referer':'https://stats.wnba.com/','x-nba-stats-origin':'stats','x-nba-stats-token':'true'}
COMMON_PARAMS={'LeagueID':LEAGUE_ID,'SeasonType':'Regular Season','DateFrom':'','DateTo':'','GameSegment':'','LastNGames':'0','Location':'','Month':'0','OpponentTeamID':'0','Outcome':'','PORound':'0','PaceAdjust':'N','Period':'0','PlusMinus':'N','Rank':'N','SeasonSegment':'','ShotClockRange':'','VsConference':'','VsDivision':''}
PLAYER_EXTRA_PARAMS={'College':'','Conference':'','Country':'','DraftPick':'','DraftYear':'','Height':'','PlayerExperience':'','PlayerPosition':'','StarterBench':'','TeamID':'0','TwoWay':'0','Weight':''}
TEAM_EXTRA_PARAMS={'Conference':'','Division':'','TeamID':'0'}

def request_stats(endpoint:str,params:dict,label:str)->pd.DataFrame:
    url=f'{BASE_URL}/{endpoint}'; response=requests.get(url,headers=HEADERS,params=params,timeout=30)
    print(f'  {label}: HTTP {response.status_code}'); response.raise_for_status(); data=response.json()
    result_sets=data.get('resultSets') or data.get('resultSet') or []
    if isinstance(result_sets,dict): result_sets=[result_sets]
    if not result_sets: print(f'  [WARN] {label}: no resultSets returned'); return pd.DataFrame()
    first=result_sets[0]; headers=first.get('headers',[]); rows=first.get('rowSet',[]); df=pd.DataFrame(rows,columns=headers)
    print(f'  {label}: {len(df)} rows, {len(df.columns)} columns'); return df

def player_stats_params(season:str,measure_type:str,last_n_games:int=0)->dict:
    params=dict(COMMON_PARAMS); params.update(PLAYER_EXTRA_PARAMS); params.update({'Season':season,'MeasureType':measure_type,'PerMode':'PerGame','LastNGames':str(last_n_games)}); return params

def team_stats_params(season:str,measure_type:str)->dict:
    params=dict(COMMON_PARAMS); params.update(TEAM_EXTRA_PARAMS); params.update({'Season':season,'MeasureType':measure_type,'PerMode':'PerGame'}); return params

def norm_num(value:Any,default:Optional[float]=None)->Optional[float]:
    try:
        if pd.isna(value): return default
        return float(value)
    except Exception: return default

def find_col(df:pd.DataFrame,candidates:list[str])->str|None:
    if df is None or df.empty: return None
    cols={str(c).upper():c for c in df.columns}
    for cand in candidates:
        if cand.upper() in cols: return cols[cand.upper()]
    return None

def row_lookup(df:pd.DataFrame|None,name_candidates=('PLAYER_NAME','PLAYER'),team_candidates=('TEAM_ABBREVIATION','TEAM_ABBREV','TEAM'))->dict:
    lookup={}
    if df is None or df.empty: return lookup
    name_col=find_col(df,list(name_candidates)); team_col=find_col(df,list(team_candidates))
    if not name_col: return lookup
    for _,row in df.iterrows():
        name=str(row.get(name_col,'')).strip(); team=str(row.get(team_col,'')).strip() if team_col else ''
        if name: lookup[(name,team)]=row; lookup[(name,'')]=row
    return lookup

def team_lookup(team_adv:pd.DataFrame|None,opp_df:pd.DataFrame|None)->dict:
    lookup={}
    if team_adv is None or team_adv.empty: return lookup
    opp_df=opp_df if opp_df is not None else pd.DataFrame()
    abbr_col=find_col(team_adv,['TEAM_ABBREVIATION','TEAM_ABBREV','TEAM']); name_col=find_col(team_adv,['TEAM_NAME','TEAM']); ortg_col=find_col(team_adv,['OFF_RATING','ORTG','OFFRTG']); drtg_col=find_col(team_adv,['DEF_RATING','DRTG','DEFRTG']); pace_col=find_col(team_adv,['PACE'])
    opp_key_col=find_col(opp_df,['TEAM_ABBREVIATION','TEAM_ABBREV','TEAM_NAME','TEAM']); opp_pts_col=find_col(opp_df,['OPP_PTS','PTS','OPPONENT_PTS','PTS_ALLOWED'])
    opp_map={}
    if not opp_df.empty and opp_key_col and opp_pts_col:
        for _,row in opp_df.iterrows(): opp_map[str(row.get(opp_key_col,''))]=norm_num(row.get(opp_pts_col))
    for _,row in team_adv.iterrows():
        abbr=str(row.get(abbr_col,'')) if abbr_col else ''; name=str(row.get(name_col,'')) if name_col else abbr
        payload={'team':abbr or name,'team_name':name,'ortg':norm_num(row.get(ortg_col)) if ortg_col else None,'drtg':norm_num(row.get(drtg_col)) if drtg_col else None,'pace':norm_num(row.get(pace_col)) if pace_col else None,'opp_pts_allowed':opp_map.get(abbr) or opp_map.get(name)}
        for key in [abbr,name]:
            if key: lookup[str(key)]=payload
    return lookup

def build_live_players(base_df:pd.DataFrame,adv_df:pd.DataFrame,team_adv:pd.DataFrame,opp_df:pd.DataFrame,recent5_df:pd.DataFrame|None=None)->dict:
    if base_df is None or base_df.empty: return {}
    recent5_df=recent5_df if recent5_df is not None else pd.DataFrame(); adv_df=adv_df if adv_df is not None else pd.DataFrame(); team_adv=team_adv if team_adv is not None else pd.DataFrame(); opp_df=opp_df if opp_df is not None else pd.DataFrame()
    name_col=find_col(base_df,['PLAYER_NAME','PLAYER']); team_col=find_col(base_df,['TEAM_ABBREVIATION','TEAM_ABBREV','TEAM']); pos_col=find_col(base_df,['PLAYER_POSITION','POSITION','POS']); gp_col=find_col(base_df,['GP']); min_col=find_col(base_df,['MIN','MINUTES']); pts_col=find_col(base_df,['PTS']); reb_col=find_col(base_df,['REB']); ast_col=find_col(base_df,['AST']); fg3m_col=find_col(base_df,['FG3M','3PM'])
    adv_lookup=row_lookup(adv_df); recent_lookup=row_lookup(recent5_df); teams=team_lookup(team_adv,opp_df); players:Dict[str,dict]={}; now=datetime.now(timezone.utc).isoformat()
    r_min_col=find_col(recent5_df,['MIN','MINUTES']); r_pts_col=find_col(recent5_df,['PTS']); r_reb_col=find_col(recent5_df,['REB']); r_ast_col=find_col(recent5_df,['AST']); r_fg3m_col=find_col(recent5_df,['FG3M','3PM']); r_gp_col=find_col(recent5_df,['GP'])
    usg_col=find_col(adv_df,['USG_PCT','USG%','USAGE']); ts_col=find_col(adv_df,['TS_PCT','TS%']); net_col=find_col(adv_df,['NET_RATING','NETRTG']); pace_col=find_col(adv_df,['PACE'])
    for _,row in base_df.iterrows():
        name=str(row.get(name_col,'')).strip() if name_col else ''
        if not name: continue
        team=str(row.get(team_col,'')).strip() if team_col else ''; adv=adv_lookup.get((name,team)) or adv_lookup.get((name,'')); recent=recent_lookup.get((name,team)) or recent_lookup.get((name,'')); team_payload=teams.get(team,{})
        ppg=norm_num(row.get(pts_col),0) if pts_col else 0; mpg=norm_num(row.get(min_col),0) if min_col else 0; reb=norm_num(row.get(reb_col),0) if reb_col else None; ast=norm_num(row.get(ast_col),0) if ast_col else None; threes=norm_num(row.get(fg3m_col),0) if fg3m_col else 0
        roll5_pts=norm_num(recent.get(r_pts_col),ppg) if recent is not None and r_pts_col else ppg; roll5_reb=norm_num(recent.get(r_reb_col),reb) if recent is not None and r_reb_col else reb; roll5_ast=norm_num(recent.get(r_ast_col),ast) if recent is not None and r_ast_col else ast; roll5_mpg=norm_num(recent.get(r_min_col),mpg) if recent is not None and r_min_col else mpg; roll5_threes=norm_num(recent.get(r_fg3m_col),threes) if recent is not None and r_fg3m_col else threes; roll5_gp=norm_num(recent.get(r_gp_col),None) if recent is not None and r_gp_col else None
        usage=norm_num(adv.get(usg_col),0.25) if adv is not None and usg_col else 0.25; ts_pct=norm_num(adv.get(ts_col),0.55) if adv is not None and ts_col else 0.55
        if usage is not None and usage>1.5: usage/=100.0
        if ts_pct is not None and ts_pct>1.5: ts_pct/=100.0
        players[name]={'player':name,'team':team,'pos':str(row.get(pos_col,'')).strip() if pos_col else '','gp':norm_num(row.get(gp_col),0) if gp_col else 0,'ppg':ppg,'mpg':mpg,'usage':usage,'ts':ts_pct,'ts_pct':ts_pct,'reb':reb,'ast':ast,'roll5_pts':roll5_pts,'roll5_reb':roll5_reb,'roll5_ast':roll5_ast,'roll5_mpg':roll5_mpg,'roll5_threes':roll5_threes,'roll5_gp':roll5_gp,'recent_source':'stats.wnba.com LastNGames=5' if recent is not None else 'season fallback','net_rating':norm_num(adv.get(net_col)) if adv is not None and net_col else None,'pace':norm_num(adv.get(pace_col)) if adv is not None and pace_col else team_payload.get('pace'),'team_ortg':team_payload.get('ortg'),'team_drtg':team_payload.get('drtg'),'team_pace':team_payload.get('pace'),'opp_pts_allowed_team':team_payload.get('opp_pts_allowed'),'source':'stats.wnba.com','updated_at':now}
    return players

def save_csv(df:pd.DataFrame,path:str)->None:
    os.makedirs(os.path.dirname(path),exist_ok=True); df.to_csv(path,index=False); print(f'  Saved → {path}')

def main()->None:
    parser=argparse.ArgumentParser(); parser.add_argument('--season',default=str(date.today().year)); parser.add_argument('--out',default=DEFAULT_OUT); parser.add_argument('--delay',type=float,default=1.2); args=parser.parse_args(); os.makedirs(args.out,exist_ok=True)
    print(f'\n═══ WNBA OFFICIAL STATS — {args.season} ═══\n')
    status={'status':'unknown','season':args.season,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'players_base_rows':0,'players_recent5_rows':0,'players_advanced_rows':0,'team_advanced_rows':0,'team_opp_rows':0,'players_live_rows':0,'error':None}
    try:
        player_base=request_stats('leaguedashplayerstats',player_stats_params(args.season,'Base',0),'Player base'); time.sleep(args.delay)
        player_recent5=request_stats('leaguedashplayerstats',player_stats_params(args.season,'Base',5),'Player recent 5'); time.sleep(args.delay)
        player_adv=request_stats('leaguedashplayerstats',player_stats_params(args.season,'Advanced',0),'Player advanced'); time.sleep(args.delay)
        team_adv=request_stats('leaguedashteamstats',team_stats_params(args.season,'Advanced'),'Team advanced'); time.sleep(args.delay)
        team_opp=request_stats('leaguedashteamstats',team_stats_params(args.season,'Opponent'),'Team opponent')
        save_csv(player_base,os.path.join(args.out,'wnba_player_stats.csv')); save_csv(player_recent5,os.path.join(args.out,'wnba_player_recent5.csv')); save_csv(player_adv,os.path.join(args.out,'wnba_player_advanced.csv')); save_csv(team_adv,os.path.join(args.out,'wnba_team_stats.csv')); save_csv(team_opp,os.path.join(args.out,'wnba_opp_stats.csv'))
        players_live=build_live_players(player_base,player_adv,team_adv,team_opp,player_recent5); live_path=os.path.join(args.out,'wnba_players_live.json'); json.dump(players_live,open(live_path,'w',encoding='utf-8'),indent=2); print(f'  Saved → {live_path}')
        status.update({'status':'ok' if players_live else 'empty','players_base_rows':int(len(player_base)),'players_recent5_rows':int(len(player_recent5)),'players_advanced_rows':int(len(player_adv)),'team_advanced_rows':int(len(team_adv)),'team_opp_rows':int(len(team_opp)),'players_live_rows':int(len(players_live))})
        if players_live:
            print('\n  Player sample:')
            for p in list(players_live.values())[:10]: print(f"  {p['player']} ({p['team']}) — PPG {p['ppg']}, MPG {p['mpg']}, L5 PTS {p.get('roll5_pts')}, L5 MPG {p.get('roll5_mpg')}")
    except Exception as exc:
        status['status']='error'; status['error']=str(exc); print(f'  [ERROR] WNBA official stats scrape failed: {exc}')
    status_path=os.path.join(args.out,'wnba_stats_status.json'); json.dump(status,open(status_path,'w',encoding='utf-8'),indent=2); print(f'  Status → {status_path}'); print('\n✅ WNBA official stats scrape complete.' if status['status']=='ok' else f"\n⚠️ WNBA official stats status: {status['status']}")
if __name__=='__main__': main()
