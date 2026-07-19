"""Build Player Props & Best Bets V2 from simulations, prices, and verified history."""
from __future__ import annotations
import argparse,json,math
from datetime import date,datetime,timezone
from pathlib import Path
from typing import Any
MASTER_PATHS=[Path('data/master/wnba_master.json'),Path('data/dashboard/wnba_master.json')]
LOGS=Path('data/warehouse/wnba_player_game_logs.json')
OUTS=[Path('data/warehouse/wnba_prop_bet_cards.json'),Path('data/dashboard/wnba_prop_bet_cards.json')]
SUPPORTED={'PTS','REB','AST','3PM','STL','BLK','TOV','PRA','PR','PA','RA'}
def load(p:Path,d:Any)->Any:
 try:return json.load(p.open(encoding='utf-8')) if p.exists() else d
 except Exception:return d
def dump(p:Path,x:Any)->None:p.parent.mkdir(parents=True,exist_ok=True);json.dump(x,p.open('w',encoding='utf-8'),indent=2,allow_nan=False)
def num(v:Any)->float|None:
 try:
  x=float(v);return x if math.isfinite(x) else None
 except Exception:return None
def norm(v:Any)->str:return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def clamp(v:float,a:float,b:float)->float:return max(a,min(b,v))
def stat_value(r:dict[str,Any],stat:str)->float|None:
 s=r.get('scoring') or {};b=r.get('boxscore') or {};pts=num(s.get('total_pts'));reb=num(b.get('reb'));ast=num(b.get('ast'))
 vals={'PTS':pts,'REB':reb,'AST':ast,'3PM':num(s.get('three_pm')),'STL':num(b.get('stl')),'BLK':num(b.get('blk')),'TOV':num(b.get('tov')),
 'PRA':None if None in (pts,reb,ast) else pts+reb+ast,'PR':None if None in (pts,reb) else pts+reb,'PA':None if None in (pts,ast) else pts+ast,'RA':None if None in (reb,ast) else reb+ast}
 return vals.get(stat)
def histories()->dict[str,list[dict[str,Any]]]:
 p=load(LOGS,{'records':[]});out={}
 for r in p.get('records',[]) if isinstance(p,dict) else []:
  if isinstance(r,dict) and r.get('player'):out.setdefault(norm(r['player']),[]).append(r)
 for rows in out.values():rows.sort(key=lambda r:(str(r.get('game_date') or ''),str(r.get('game_id') or '')),reverse=True)
 return out
def hit(v:float,side:str,line:float)->bool:return v>line if side=='OVER' else v<line
def summary(rows:list[dict[str,Any]],stat:str,side:str,line:float,n:int|None=None,opp:str='',loc:str='')->dict[str,Any]:
 vals=[]
 for r in rows:
  if opp and norm(r.get('opponent') or r.get('opponent_team'))!=norm(opp):continue
  where=str(r.get('location') or r.get('home_away') or '').upper()
  if loc and where and not where.startswith(loc[0]):continue
  v=stat_value(r,stat)
  if v is None:continue
  vals.append(round(v,2))
  if n and len(vals)>=n:break
 wins=sum(hit(v,side,line) for v in vals)
 return {'sample':len(vals),'hits':wins,'hit_rate':round(wins/len(vals),4) if vals else None,'average':round(sum(vals)/len(vals),2) if vals else None,'values':vals}
def decimal(o:Any)->float|None:
 x=num(o)
 if x is None or x==0:return None
 return 1+(100/abs(x) if x<0 else x/100)
def fair(prob:float|None)->int|None:
 if prob is None or prob<=0 or prob>=1:return None
 return round(-100*prob/(1-prob)) if prob>=.5 else round(100*(1-prob)/prob)
def kelly(prob:float|None,odds:Any)->float|None:
 d=decimal(odds)
 if prob is None or d is None or d<=1:return None
 b=d-1;return clamp((b*prob-(1-prob))/b,0,1)
def letter(s:float)->str:
 return 'A+' if s>=92 else 'A' if s>=87 else 'B+' if s>=82 else 'B' if s>=76 else 'C+' if s>=70 else 'C' if s>=64 else 'D' if s>=58 else 'PASS'
def opponent(game:str,team:str)->str:
 p=[x.strip() for x in str(game or '').split(' @ ') if x.strip()];return next((x for x in p if norm(x)!=norm(team)),p[0] if p else '')
def location(game:str,team:str)->str:
 p=[x.strip() for x in str(game or '').split(' @ ') if x.strip()];return 'HOME' if len(p)==2 and norm(p[1])==norm(team) else 'AWAY' if len(p)==2 else ''
def build_card(prop:dict[str,Any],rows:list[dict[str,Any]])->dict[str,Any]|None:
 stat=str(prop.get('stat') or '').upper();line=num(prop.get('line') if prop.get('line') is not None else prop.get('consensus_line'));side=str(prop.get('signal') or prop.get('side') or '').upper()
 if stat not in SUPPORTED or line is None or side not in {'OVER','UNDER'}:return None
 sim=prop.get('unified_simulation_v2') or {};market=sim.get('best_market') or {};prob=num(market.get('hit_probability')) or num(prop.get('simulation_probability'))
 odds=prop.get('best_price') or (prop.get('best_over_price') if side=='OVER' else prop.get('best_under_price'));dec=decimal(odds);ev=num(market.get('expected_value_per_unit'))
 if ev is None and prob is not None and dec is not None:ev=prob*dec-1
 team=str(prop.get('team') or '');game=str(prop.get('game') or '');opp=opponent(game,team);loc=location(game,team)
 l5=summary(rows,stat,side,line,5);l10=summary(rows,stat,side,line,10);l20=summary(rows,stat,side,line,20);season=summary(rows,stat,side,line);vsopp=summary(rows,stat,side,line,opp=opp) if opp else summary([],stat,side,line);split=summary(rows,stat,side,line,loc=loc) if loc else summary([],stat,side,line)
 rates=[x['hit_rate'] for x in (l5,l10,l20,season) if x['hit_rate'] is not None];trend=sum(rates)/len(rates) if rates else .5
 quality=str(sim.get('data_quality_status') or prop.get('data_quality_status') or 'limited');q={'complete':1,'partial':.7,'limited':.4}.get(quality,.35);conf=(num(sim.get('confidence')) or num(prop.get('projection_confidence_v2')) or 50)/100;books=int(num(prop.get('book_count')) or 0);cons=min(1,(books/4)*.65+conf*.35)
 projection=num(prop.get('projection') or prop.get('proj') or prop.get('pred'));edge=None if projection is None else projection-line if side=='OVER' else line-projection;opening=num(prop.get('opening_line') or prop.get('open_line'));movement=None if opening is None else line-opening;k=kelly(prob,odds)
 comp={'simulation':clamp(((prob or .5)-.5)/.22,0,1)*30,'ev':clamp((ev or 0)/.16,0,1)*22,'history':clamp((trend-.45)/.30,0,1)*16,'quality':q*12,'confidence':clamp(conf,0,1)*8,'consensus':cons*7,'opponent':clamp(((vsopp.get('hit_rate') or .5)-.45)/.30,0,1)*5 if vsopp.get('sample',0)>=3 else 0};score=round(clamp(sum(comp.values()),0,95),1)
 reasons=[];risks=[]
 if prob is not None:reasons.append(f'10,000-run simulation: {prob:.1%} hit probability')
 if ev is not None:reasons.append(f'Expected value: {ev:+.1%} at {odds}')
 if l10['sample']:reasons.append(f'Last 10: {l10["hits"]}/{l10["sample"]}, average {l10["average"]}')
 if season['sample']:reasons.append(f'Season: {season["hits"]}/{season["sample"]} against this line')
 if vsopp['sample']>=3:reasons.append(f'Vs {opp}: {vsopp["hits"]}/{vsopp["sample"]}')
 if split['sample']>=5:reasons.append(f'{loc.title()} split: {split["hits"]}/{split["sample"]}')
 if edge is not None:reasons.append(f'Model projection edge: {edge:+.2f}')
 if books>=2:reasons.append(f'Compared across {books} sportsbooks')
 if quality!='complete':risks.append(f'Projection data quality: {quality}')
 if season['sample']<10:risks.append('Limited verified season sample')
 if prob is None:risks.append('Simulation probability unavailable')
 if ev is None:risks.append('Price-based EV unavailable')
 if books<2:risks.append('Only one sportsbook price available')
 if movement is None:risks.append('Opening line unavailable; movement and CLV withheld')
 action='BET' if score>=82 and prob is not None and prob>=.57 and ev is not None and ev>=.035 else 'LEAN' if score>=72 and (ev or 0)>0 else 'WATCH' if score>=62 else 'PASS'
 clv='POSITIVE' if movement is not None and ((side=='OVER' and movement<0) or (side=='UNDER' and movement>0)) else 'NEGATIVE' if movement is not None and movement!=0 else 'FLAT' if movement==0 else 'UNAVAILABLE'
 return {'player':prop.get('player'),'team':team,'game':game,'opponent':opp,'location':loc,'stat':stat,'side':side,'signal':side,'line':line,'sportsbook':prop.get('best_book') or prop.get('book'),'odds':odds,'projection':projection,'projection_edge':round(edge,2) if edge is not None else None,'simulation_probability':round(prob,4) if prob is not None else None,'fair_odds':fair(prob),'expected_value':round(ev,4) if ev is not None else None,'kelly_fraction':round(k,4) if k is not None else None,'recommended_units':round(min(1,(k or 0)*2.5),2) if k is not None else None,'research_grade':score,'letter_grade':letter(score),'action':action,'consensus_score':round(cons*100,1),'book_count':books,'trend':{'last5':l5,'last10':l10,'last20':l20,'season':season,'opponent':vsopp,'location':split},'line_movement':round(movement,2) if movement is not None else None,'clv_projection':clv,'data_quality':quality,'score_components':{k:round(v,2) for k,v in comp.items()},'reasons':reasons[:8],'risks':risks[:6],'source':'calibrated_prop_bet_card_v2'}
def build(target:str)->dict[str,Any]:
 master=next((load(p,{}) for p in MASTER_PATHS if p.exists()),{});hist=histories();cards=[];enriched=[]
 for prop in master.get('props',[]) or []:
  row=dict(prop);card=build_card(row,hist.get(norm(row.get('player')),[]))
  if card:row['bet_card']=card;cards.append(card)
  enriched.append(row)
 cards.sort(key=lambda x:(x['action']!='BET',-(x.get('expected_value') or -9),-x['research_grade']));ranked=[c for c in cards if c['action'] in {'BET','LEAN'}][:30]
 for p in MASTER_PATHS:
  payload=load(p,{})
  if not payload:continue
  payload['props']=enriched;payload['best_bets']=ranked;payload['prop_bet_cards']={'count':len(cards),'ranked':len(ranked),'version':'2.0','source':'data/dashboard/wnba_prop_bet_cards.json'}
  if isinstance(payload.get('summary'),dict):payload['summary']['best_bets']=len(ranked)
  dump(p,payload)
 report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'target_date':target,'status':'ok','schema_version':'2.0','summary':{'cards':len(cards),'bets':sum(c['action']=='BET' for c in cards),'leans':sum(c['action']=='LEAN' for c in cards),'watch':sum(c['action']=='WATCH' for c in cards),'history_attached':sum(c['trend']['season']['sample']>0 for c in cards)},'ranked_cards':ranked,'all_cards':cards,'scoring_note':'Research grade is a ranking score, not win probability. Ranked primarily by expected value after minimum quality gates.'}
 for p in OUTS:dump(p,report)
 print('PROP BET CARDS V2 ACTIVE',report['summary']);return report
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--date',default=str(date.today()));a=ap.parse_args();build(a.date)
if __name__=='__main__':main()
