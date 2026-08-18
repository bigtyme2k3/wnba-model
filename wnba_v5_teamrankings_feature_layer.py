"""V5 TeamRankings matchup feature layer (research/shadow only).

Transforms the frozen raw TeamRankings team snapshot into compact, interpretable
opponent-context features. No production prediction is changed by this module.
Scores are cross-sectional z-scores within the frozen WNBA snapshot; positive
means a more favorable offensive environment for the named feature.
"""
from __future__ import annotations
import argparse,json,math,statistics
from pathlib import Path
from datetime import datetime,timezone

DASH=Path('data/dashboard')
SRC=DASH/'wnba_v5_team_matchup_intelligence.json'
OUT=DASH/'wnba_v5_team_matchup_features.json'
WARE=Path('data/warehouse/teamrankings/features')

FAMILIES={
 'paint_advantage': [('opp_points_paint',1),('opp_two_pt_pct',1),('opp_two_pt_rate',1)],
 'perimeter_advantage': [('opp_three_pt_pct',1),('opp_three_pt_rate',1),('opp_efg_pct',1)],
 'rebound_environment': [('opp_off_reb_pct',1),('opp_def_reb_pct',-1)],
 'assist_environment': [('opp_assists_game',1),('opp_assists_fgm',1),('opp_turnovers_poss',-1)],
 'pace_environment': [('possessions_game',1)],
 'foul_ft_environment': [('opp_personal_fouls_game',1),('opp_fta_fga',1)],
 'transition_environment': [('opp_fastbreak_points',1),('possessions_game',0.35)],
 'overall_scoring_environment': [('def_efficiency',1),('opp_efg_pct',1),('opp_points_paint',0.5),('possessions_game',0.5)],
}

def f(v):
 try:return float(v)
 except Exception:return None

def zmap(vals):
 good=[v for v in vals.values() if v is not None and math.isfinite(v)]
 if len(good)<2:return {k:0.0 for k in vals}
 mu=statistics.fmean(good); sd=statistics.pstdev(good)
 if sd<1e-12:return {k:0.0 for k in vals}
 return {k:(0.0 if v is None else (v-mu)/sd) for k,v in vals.items()}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--date'); a=ap.parse_args()
 raw=json.loads(SRC.read_text(encoding='utf-8'))
 if raw.get('status')!='READY_SHADOW': raise SystemExit('TeamRankings source not READY_SHADOW')
 teams=raw.get('teams',{}); target=a.date or raw.get('target_date')
 # Venue-neutral research layer: season, recent and venue splits remain separate.
 metric_z={}
 for metric in {m for fam in FAMILIES.values() for m,_ in fam}:
  for split in ('season','last3','home','away','recent_delta'):
   vals={tc:f((td.get('metrics',{}).get(metric,{}) or {}).get(split)) for tc,td in teams.items()}
   metric_z[(metric,split)]=zmap(vals)
 outteams={}
 for tc,td in teams.items():
  fams={}
  for family,parts in FAMILIES.items():
   rec={}
   for split in ('season','last3','home','away'):
    terms=[]; weights=[]
    for metric,w in parts:
     terms.append(metric_z[(metric,split)].get(tc,0.0)*w); weights.append(abs(w))
    rec[split+'_z']=round(sum(terms)/sum(weights),4) if weights else 0.0
   rec['recent_shift_z']=round(rec['last3_z']-rec['season_z'],4)
   rec['home_away_gap_z']=round(rec['home_z']-rec['away_z'],4)
   fams[family]=rec
  outteams[tc]={'team':td.get('team'),'team_code':tc,'feature_families':fams}
 payload={'version':'V5','module':'TEAMRANKINGS_MATCHUP_FEATURE_LAYER','status':'READY_SHADOW','production_ready':False,'research_only':True,'target_date':target,'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source_snapshot_generated_at_utc':raw.get('generated_at_utc'),'method':'cross-sectional z-score composites from immutable TeamRankings snapshot','interpretation':'positive score = more favorable offensive environment; venue-specific split must be selected from actual game venue before model use','families':{k:[{'metric':m,'weight':w} for m,w in v] for k,v in FAMILIES.items()},'teams':outteams}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
 WARE.mkdir(parents=True,exist_ok=True); (WARE/f'wnba_team_matchup_features_{target}.json').write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
 print(json.dumps({'status':payload['status'],'teams':len(outteams),'families':len(FAMILIES),'target_date':target},indent=2))
if __name__=='__main__':main()
