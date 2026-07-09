from __future__ import annotations
import argparse, csv, importlib.util, json, os, math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

MASTER_DIR="data/master"; DASH_DIR="data/dashboard"; RAW_DIR="data/raw"; WNBA_DIR="data/wnba"; CONFIG="config/source_registry.json"
ET = ZoneInfo("America/New_York")
TEAM_MAP={
    "GSV":"Golden State Valkyries","GS":"Golden State Valkyries","GOL":"Golden State Valkyries",
    "WAS":"Washington Mystics","MIN":"Minnesota Lynx","CON":"Connecticut Sun","SEA":"Seattle Storm",
    "LAS":"Los Angeles Sparks","LOS":"Los Angeles Sparks","LA":"Los Angeles Sparks","ATL":"Atlanta Dream",
    "CHI":"Chicago Sky","DAL":"Dallas Wings","IND":"Indiana Fever","NYL":"New York Liberty",
    "NY":"New York Liberty","PHO":"Phoenix Mercury","PHX":"Phoenix Mercury","LVA":"Las Vegas Aces",
    "LV":"Las Vegas Aces","POR":"Portland Fire","TOR":"Toronto Tempo"
}

def load_json(path:str, default:Any):
    try:
        if os.path.exists(path): return json.load(open(path,encoding='utf-8'))
    except Exception: pass
    return default

def read_csv(path:str):
    try:
        if os.path.exists(path): return list(csv.DictReader(open(path,encoding='utf-8')))
    except Exception: pass
    return []

def first_csv(paths:list[str]):
    for p in paths:
        rows=read_csv(p)
        if rows: return rows,p
    return [],None

def team_name(v:Any)->str:
    if isinstance(v,dict):
        v = v.get('name') or v.get('displayName') or v.get('abbreviation') or v.get('abbr') or ''
    v=str(v or '').strip()
    return TEAM_MAP.get(v.upper(), v)

def norm_team(row:dict,side:str)->str:
    for k in [f'{side}_team',side,f'{side}_name','visitor_team' if side=='away' else 'home_team']:
        v=row.get(k)
        if v: return team_name(v)
    return ''

def norm_score(row:dict,side:str):
    for k in [f'{side}_score',f'score_{side}','visitor_score' if side=='away' else 'home_score']:
        if row.get(k) not in (None,''): return row.get(k)
    if side in row and isinstance(row.get(side),dict): return row[side].get('score')
    return ''

def game_key(away:str,home:str,game_date:str)->str: return f"{game_date}|{away.strip().lower()}|{home.strip().lower()}"
def display_game(away:str,home:str)->str: return f'{away} @ {home}' if away and home else ''
def parse_game_text(g:str):
    if ' @ ' in g: return [team_name(x) for x in g.split(' @ ',1)]
    if ' at ' in g: return [team_name(x) for x in g.split(' at ',1)]
    if ' vs ' in g:
        home,away=g.split(' vs ',1); return team_name(away),team_name(home)
    return '',''

def clean_num(v):
    try:
        if v in (None,''): return ''
        f=float(v); return int(f) if f.is_integer() else round(f,2)
    except Exception: return v or ''

def as_float(v, default=None):
    try:
        if v in (None,''): return default
        f=float(v)
        if math.isnan(f): return default
        return f
    except Exception: return default

def iso_local_date(value:str):
    try:
        if not value: return ''
        s=str(value).replace('Z','+00:00')
        dt=datetime.fromisoformat(s)
        if dt.tzinfo is None: return dt.date().isoformat()
        return dt.astimezone(ET).date().isoformat()
    except Exception:
        return ''

def event_target_date(event:dict, fallback:str):
    # ESPN/sports-skills games can start after midnight UTC while still being the prior Eastern slate.
    d=iso_local_date(event.get('start_time') or event.get('date') or '')
    return d or fallback

def sports_schedule_games(target:str):
    raw=load_json(f'{WNBA_DIR}/scores.json',{})
    events=[]
    if isinstance(raw,dict):
        data=raw.get('data',raw)
        if isinstance(data,dict): events=data.get('events') or data.get('games') or data.get('scoreboard') or []
        elif isinstance(data,list): events=data
    if not isinstance(events,list): events=[]
    out=[]
    for e in events:
        if not isinstance(e,dict): continue
        if event_target_date(e,target)!=target: continue
        home=away=''; hs=ascore=''; hlogo=alogo=''
        for c in e.get('competitors',[]) or []:
            if not isinstance(c,dict): continue
            t=team_name(c.get('team',{})); logo=(c.get('team') or {}).get('logo','') if isinstance(c.get('team'),dict) else ''
            if c.get('home_away')=='home': home=t; hs=c.get('score',''); hlogo=logo
            elif c.get('home_away')=='away': away=t; ascore=c.get('score',''); alogo=logo
        if (not home or not away) and e.get('name'):
            away,home=parse_game_text(e.get('name'))
        if not home or not away: continue
        odds=e.get('odds',{}) if isinstance(e.get('odds'),dict) else {}
        out.append({
            'game_id':e.get('id') or game_key(away,home,target),'game_date':target,'bucket':'today',
            'game':display_game(away,home),'away_team':away,'home_team':home,'away_score': '' if str(ascore)=='0' and e.get('status')=='not_started' else ascore,
            'home_score': '' if str(hs)=='0' and e.get('status')=='not_started' else hs,'status': e.get('status_detail') or e.get('status') or 'Pregame',
            'start_time':e.get('start_time') or '', 'spread':clean_num(odds.get('spread')),'total':clean_num(odds.get('over_under')),
            'moneyline_home':clean_num((odds.get('moneyline') or {}).get('home')),'moneyline_away':clean_num((odds.get('moneyline') or {}).get('away')),
            'home_logo':hlogo,'away_logo':alogo,'source':'data/wnba/scores.json'
        })
    return dedupe_games(out,target)

def prediction_games(target:str):
    pred=load_json(f'predictions/predictions_{target}.json',{})
    games=[]
    for g in pred.get('games',[]):
        away=team_name(g.get('away')) or team_name(g.get('away_team','')); home=team_name(g.get('home')) or team_name(g.get('home_team',''))
        if not away or not home: continue
        spread=g.get('spread',{}) if isinstance(g.get('spread'),dict) else {}; totals=g.get('totals',{}) if isinstance(g.get('totals'),dict) else {}
        games.append({'game_id':g.get('game_id') or game_key(away,home,target),'game_date':target,'bucket':'today','game':display_game(away,home),'away_team':away,'home_team':home,'away_score':'','home_score':'','status':'Pregame','start_time':g.get('tip') or g.get('start_time') or '', 'spread':clean_num(spread.get('posted_line') if spread else g.get('spread_home')),'model_spread':spread.get('model_line') if spread else '', 'total':clean_num(totals.get('line') if totals else g.get('total')),'model_total':clean_num(totals.get('pred') if totals else ''),'total_play':totals.get('play') if totals else '', 'source':'predictions_schedule'})
    return dedupe_games(games,target)

def games_from_scores(target:str,bucket:str='yesterday'):
    y=str(datetime.strptime(target,'%Y-%m-%d').date()-timedelta(days=1)) if len(target)==10 else ''
    paths=[f'{RAW_DIR}/scores_{y}.csv'] if bucket=='yesterday' else [f'{RAW_DIR}/scores_{target}.csv',f'{RAW_DIR}/scores_today.csv']
    rows,src=first_csv(paths); out=[]
    for r in rows:
        gd=r.get('game_date') or r.get('date') or (target if bucket=='today' else y)
        away=norm_team(r,'away'); home=norm_team(r,'home')
        if (not away or not home) and r.get('game'): away,home=parse_game_text(str(r.get('game')))
        if not away or not home: continue
        away_score=norm_score(r,'away'); home_score=norm_score(r,'home')
        out.append({'game_id':r.get('game_id') or r.get('event_id') or game_key(away,home,gd),'game_date':gd,'bucket':bucket,'game':display_game(away,home),'away_team':away,'home_team':home,'away_score':away_score,'home_score':home_score,'status':r.get('status') or r.get('game_status') or ('Final' if away_score or home_score else 'Pregame'),'start_time':r.get('commence_time') or r.get('start_time') or r.get('tip') or r.get('time') or '', 'spread':r.get('spread') or r.get('spread_home') or r.get('posted_spread') or '', 'total':r.get('total') or r.get('posted_total') or '', 'source':src or 'scores_csv'})
    return dedupe_games(out, y if bucket=='yesterday' else target)

def odds_games(target:str):
    rows,src=first_csv([f'{RAW_DIR}/odds_{target}.csv',f'{RAW_DIR}/odds_today.csv']); latest={}
    for r in rows:
        away=norm_team(r,'away'); home=norm_team(r,'home')
        if not away or not home: continue
        ct=r.get('commence_time') or r.get('start_time') or ''
        # Skip stale odds rows copied into today's filename.
        if ct and iso_local_date(ct) and iso_local_date(ct)!=target: continue
        key=game_key(away,home,target)
        latest[key]={'game_id':r.get('game_id') or key,'game_date':target,'bucket':'today','game':display_game(away,home),'away_team':away,'home_team':home,'away_score':'','home_score':'','status':'Pregame','start_time':ct, 'spread':clean_num(r.get('spread_home')),'total':clean_num(r.get('total')),'moneyline_home':clean_num(r.get('ml_home')),'moneyline_away':clean_num(r.get('ml_away')),'source':src or 'odds_csv'}
    return list(latest.values())

def consensus_games(target:str):
    sb=load_json(f'{DASH_DIR}/wnba_sportsbook_consensus.json',{}); latest={}
    for m in sb.get('markets',[]):
        away,home=parse_game_text(str(m.get('game') or ''))
        if not away or not home: continue
        key=game_key(away,home,target)
        latest[key]={'game_id':key,'game_date':target,'bucket':'today','game':display_game(away,home),'away_team':away,'home_team':home,'away_score':'','home_score':'','status':'Pregame','start_time':'','spread':'','total':'','source':'sportsbook_consensus'}
    return list(latest.values())

def dedupe_games(games:list[dict],target:str):
    merged={}
    for g in games:
        away=g.get('away_team',''); home=g.get('home_team','')
        if not away or not home: continue
        key=game_key(away,home,target)
        if key not in merged: merged[key]=dict(g)
        else:
            for k,v in g.items():
                if merged[key].get(k) in (None,'','Pregame') and v not in (None,''): merged[key][k]=v
    return list(merged.values())

def attach_market_data(schedule_games:list[dict],extras:list[dict],target:str):
    by_key={game_key(g['away_team'],g['home_team'],target):g for g in schedule_games if g.get('away_team') and g.get('home_team')}
    for g in extras:
        if not g.get('away_team') or not g.get('home_team'): continue
        key=game_key(g['away_team'],g['home_team'],target)
        if key not in by_key: continue
        base=by_key[key]
        for k,v in g.items():
            if base.get(k) in (None,'','Pregame') and v not in (None,''): base[k]=v
    return list(by_key.values())

def merge_today_games(target:str):
    schedule=sports_schedule_games(target) or prediction_games(target)
    if schedule: return attach_market_data(schedule, odds_games(target)+consensus_games(target), target)
    return dedupe_games(odds_games(target) or consensus_games(target),target)

def player_stats_from_live():
    players=load_json(f'{RAW_DIR}/wnba_players_live.json',{}); out=[]
    if isinstance(players,dict):
        for name,p in players.items():
            out.append({'player':p.get('player') or name,'team':p.get('team',''),'pos':p.get('pos',''),'gp':p.get('gp',0),'mpg':p.get('mpg',0),'ppg':p.get('ppg',0),'rpg':p.get('reb',0),'apg':p.get('ast',0),'usage':p.get('usage',0),'roll5_pts':p.get('roll5_pts',p.get('ppg',0)),'roll5_reb':p.get('roll5_reb',p.get('reb',0)),'roll5_ast':p.get('roll5_ast',p.get('ast',0)),'roll5_mpg':p.get('roll5_mpg',p.get('mpg',0)),'roll5_threes':p.get('roll5_threes',0),'source':p.get('source','wnba_players_live')})
    return out

def projection_for_stat(p:dict, stat:str):
    stat=(stat or '').upper(); pts=as_float(p.get('roll5_pts'),as_float(p.get('ppg'),0)) or 0; reb=as_float(p.get('roll5_reb'),as_float(p.get('rpg'),0)) or 0; ast=as_float(p.get('roll5_ast'),as_float(p.get('apg'),0)) or 0; threes=as_float(p.get('roll5_threes'),0) or 0
    if stat=='PTS': return round(pts,1)
    if stat=='REB': return round(reb,1)
    if stat=='AST': return round(ast,1)
    if stat=='PRA': return round(pts+reb+ast,1)
    if stat=='PR': return round(pts+reb,1)
    if stat=='PA': return round(pts+ast,1)
    if stat=='RA': return round(reb+ast,1)
    if stat in ('3PM','FG3M'): return round(threes,1)
    return ''

def implied_prob(price):
    price=as_float(price)
    if price is None: return None
    return round(abs(price)/(abs(price)+100),4) if price<0 else round(100/(price+100),4)

def enrich_prop(m:dict, players_by_name:dict):
    p=players_by_name.get(str(m.get('player','')).lower(),{}); line=as_float(m.get('consensus_line')); proj=projection_for_stat(p,m.get('stat')) if p else ''
    edge=round(as_float(proj,0)-line,2) if proj!='' and line is not None else ''; side='OVER' if edge!='' and edge>0.25 else 'UNDER' if edge!='' and edge<-0.25 else 'PASS'
    confidence=0
    if edge!='' and line: confidence=min(99, round(50+abs(edge)*8 + min(int(m.get('book_count',0))*3,12),1))
    best_book=m.get('best_over_book') if side=='OVER' else m.get('best_under_book') if side=='UNDER' else (m.get('best_over_book') or m.get('best_under_book'))
    best_price=m.get('best_over_price') if side=='OVER' else m.get('best_under_price') if side=='UNDER' else ''
    return {'player':m.get('player',''),'game':m.get('game',''),'stat':m.get('stat',''),'line':m.get('consensus_line'),'projection':proj,'pred':proj,'edge':edge,'signal':side,'side':side,'confidence':confidence,'best_book':best_book,'book':best_book,'best_price':best_price,'best_over_book':m.get('best_over_book'),'best_over_price':m.get('best_over_price'),'best_under_book':m.get('best_under_book'),'best_under_price':m.get('best_under_price'),'over_prob':m.get('consensus_over_probability') or implied_prob(m.get('best_over_price')),'under_prob':m.get('consensus_under_probability') or implied_prob(m.get('best_under_price')),'book_count':m.get('book_count',0),'books':m.get('books',[]),'market_status':m.get('status'),'source':'master_consensus_enriched'}

def props_from_consensus(players:list[dict], allowed_games:set[str]|None=None):
    sb=load_json(f'{DASH_DIR}/wnba_sportsbook_consensus.json',{}); by_name={str(p.get('player','')).lower():p for p in players}; out=[]
    for m in sb.get('markets',[]):
        if allowed_games and m.get('game') not in allowed_games: continue
        out.append(enrich_prop(m,by_name))
    return out

def build_best_bets(props:list[dict]):
    candidates=[]
    for p in props:
        if p.get('signal') in ('OVER','UNDER') and as_float(p.get('confidence'),0)>=60 and p.get('book_count',0)>=2:
            label='BET' if as_float(p.get('confidence'),0)>=80 else 'LEAN'
            candidates.append({**p,'final_action':label,'final_score':p.get('confidence'),'recommendation':f"{p.get('player')} {p.get('stat')} {p.get('signal')}", 'reason':f"Projection {p.get('projection')} vs line {p.get('line')} with {p.get('book_count')} books."})
    return sorted(candidates,key=lambda x:as_float(x.get('final_score'),0),reverse=True)[:30]

def source_status(name:str,status:str,rows:int=0,detail:str=''):
    return {'source':name,'status':status,'rows':rows,'detail':detail,'checked_at_utc':datetime.now(timezone.utc).isoformat()}

def optional_package_status(pkg:str): return 'installed' if importlib.util.find_spec(pkg) else 'not_installed'

def build(target:str):
    registry=load_json(CONFIG,{})
    today_games=merge_today_games(target); yesterday_games=games_from_scores(target,'yesterday'); games=today_games+yesterday_games
    players=player_stats_from_live(); allowed={g.get('game') for g in today_games}; props=props_from_consensus(players, allowed if allowed else None); best_bets=build_best_bets(props)
    odds=load_json(f'{DASH_DIR}/wnba_sportsbook_consensus.json',{}); stats_quality=load_json(f'{DASH_DIR}/wnba_stats_quality.json',{}); source_health=load_json(f'{DASH_DIR}/wnba_source_health.json',{})
    health=[source_status('sports_skills_schedule','ok' if sports_schedule_games(target) else 'missing',len(sports_schedule_games(target)),'Primary active slate schedule from data/wnba/scores.json.'),source_status('sportsdataverse','optional_package_'+optional_package_status('sportsdataverse'),len(today_games),'Package schedule backup.'),source_status('nba_api','optional_package_'+optional_package_status('nba_api'),len(players),'Advanced stats falls back to owned boxscore warehouse.'),source_status('boxscore_warehouse','ok' if players else 'missing',len(players),'wnba_players_live.json generated from official stats or boxscore fallback.'),source_status('odds_pipeline','ok' if props else 'missing',len(props),'sportsbook consensus markets normalized into master props.'),source_status('the_odds_api','backup_only',0,'Do not use as primary because credits burn quickly.'),source_status('litellm','optional_package_'+optional_package_status('litellm'),0,'AI gateway planned; not required for current dashboard.'),source_status('optuna','optional_package_'+optional_package_status('optuna'),0,'Model tuning planned; not required for current dashboard.')]
    master={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'schema_version':'master-v5-active-slate','registry':registry,'summary':{'games':len(games),'today_games':len(today_games),'yesterday_games':len(yesterday_games),'players':len(players),'props':len(props),'best_bets':len(best_bets),'sportsbook_markets':odds.get('summary',{}).get('markets',0),'books':odds.get('summary',{}).get('books_detected',[])},'games':games,'players':players,'props':props,'best_bets':best_bets,'odds_summary':odds.get('summary',{}),'stats_quality':stats_quality,'source_health':source_health,'source_matrix':health}
    os.makedirs(MASTER_DIR,exist_ok=True); os.makedirs(DASH_DIR,exist_ok=True)
    for p in [f'{MASTER_DIR}/wnba_master.json',f'{DASH_DIR}/wnba_master.json']:
        json.dump(master,open(p,'w',encoding='utf-8'),indent=2)
    json.dump({'generated_at_utc':master['generated_at_utc'],'target_date':target,'summary':master['summary'],'sources':health},open(f'{DASH_DIR}/wnba_master_source_health.json','w',encoding='utf-8'),indent=2)
    print('Master source built:',master['summary']); return master

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); build(args.date)
if __name__=='__main__': main()
