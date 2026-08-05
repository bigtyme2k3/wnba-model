# Player Prop Generator Lineage

- Target date: `2026-08-05`
- Current games: 4

## Candidate generators
- `wnba_player_props_ingestion.py` — exists=False, odds_api=False, writes_master=False, writes_player_props=False
- `scrape_odds_props.py` — exists=True, odds_api=True, writes_master=False, writes_player_props=False
- `wnba_player_prop_intelligence.py` — exists=True, odds_api=False, writes_master=False, writes_player_props=False
- `wnba_master_source_builder.py` — exists=True, odds_api=False, writes_master=True, writes_player_props=False
- `wnba_current_slate.py` — exists=True, odds_api=True, writes_master=True, writes_player_props=False
- `build_dashboard_v4.py` — exists=True, odds_api=False, writes_master=True, writes_player_props=False
- `patch_dashboard_navigation_v2.py` — exists=True, odds_api=False, writes_master=True, writes_player_props=False

## Output health
- `data/dashboard/wnba_master.json` — rows=60, current=0, off_slate=60, missing_team=60, target=2026-08-05
- `data/dashboard/wnba_player_props.json` — rows=0, current=0, off_slate=0, missing_team=0, target=None
- `data/dashboard/wnba_player_prop_intelligence.json` — rows=0, current=0, off_slate=0, missing_team=0, target=None
- `data/dashboard/wnba_player_props_current_slate.json` — rows=0, current=0, off_slate=0, missing_team=0, target=2026-08-05
