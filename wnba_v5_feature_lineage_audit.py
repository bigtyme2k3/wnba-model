"""Audit which intelligence datasets actually feed the live V5 prediction/decision path.

Static repository audit only: no model behavior is changed. The report distinguishes
feature-producing datasets from datasets consumed by M11 live inference and M10 live
adaptive decisions so dormant intelligence is visible instead of assumed active.
"""
from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('.')
OUT=Path('data/dashboard/wnba_v5_feature_lineage_audit.json')
WARE=Path('data/warehouse/wnba_v5_feature_lineage_audit.json')

CRITICAL={
 'historical_features':'data/dashboard/wnba_v5_historical_features.csv',
 'opportunity_rankings':'data/warehouse/wnba_opportunity_rankings.json',
 'market_movement':'data/dashboard/market_movement.json',
 'injury_intelligence':'data/dashboard/wnba_injury_intelligence.json',
 'minutes_projection_v2':'data/dashboard/wnba_minutes_projection_v2.json',
 'player_intelligence':'data/dashboard/wnba_player_intelligence.json',
 'matchup_intelligence':'data/dashboard/wnba_matchup_intelligence.json',
 's4_matchup_adjustments':'data/dashboard/wnba_v5_matchup_adjustments.csv',
 's4_lineup_adjustments':'data/dashboard/wnba_v5_lineup_adjustments.csv',
 's4_lineup_intelligence':'data/dashboard/wnba_v5_lineup_intelligence.json',
 'teamrankings_live_features':'data/dashboard/wnba_v5_team_matchup_features.json',
 'teamrankings_history_join':'data/dashboard/wnba_v5_teamrankings_history_join.json',
 'teamrankings_challenger':'data/dashboard/wnba_v5_teamrankings_challenger.json',
}
LIVE={'M11':'wnba_v5_m11_live_inference.py','M10':'wnba_v5_m10_live_decision_engine.py'}

def read(p):
 try:return Path(p).read_text(encoding='utf-8',errors='replace')
 except Exception:return ''

def references(text,path):
 name=Path(path).name
 return path in text or name in text

def main():
 pyfiles=[p for p in ROOT.glob('*.py') if p.name!='wnba_v5_feature_lineage_audit.py']
 texts={p.name:read(p) for p in pyfiles}
 live_text={k:read(v) for k,v in LIVE.items()}
 rows=[]
 for key,path in CRITICAL.items():
  consumers=sorted(name for name,text in texts.items() if references(text,path))
  live_consumers=[stage for stage,text in live_text.items() if references(text,path)]
  exists=Path(path).exists()
  rows.append({'key':key,'path':path,'exists':exists,'repository_consumers':consumers,'live_consumers':live_consumers,'feeds_live_path':bool(live_consumers)})

 # Explicit live feature contract from M11.
 m11=live_text['M11']
 m=re.search(r'FEATURE_NAMES\s*=\s*\[(.*?)\]',m11,re.S)
 feats=re.findall(r"['\"]([^'\"]+)['\"]",m.group(1)) if m else []

 dormant=[r['key'] for r in rows if r['exists'] and not r['feeds_live_path']]
 active=[r['key'] for r in rows if r['feeds_live_path']]
 payload={
  'version':'V5','module':'FEATURE_LINEAGE_AUDIT','status':'READY_AUDIT','generated_at_utc':datetime.now(timezone.utc).isoformat(),
  'production_changed':False,'live_path':{'M11':LIVE['M11'],'M10':LIVE['M10']},
  'm11_feature_names':feats,
  'summary':{'critical_datasets':len(rows),'active_live_inputs':active,'dormant_or_shadow_inputs':dormant},
  'finding':'A dataset is classified active only when M11 or M10 directly references it. Repository presence alone does not imply live influence.',
  'datasets':rows,
 }
 OUT.parent.mkdir(parents=True,exist_ok=True); WARE.parent.mkdir(parents=True,exist_ok=True)
 s=json.dumps(payload,indent=2)+'\n'; OUT.write_text(s,encoding='utf-8'); WARE.write_text(s,encoding='utf-8')
 print(json.dumps(payload['summary'],indent=2))

if __name__=='__main__':main()
