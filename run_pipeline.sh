#!/bin/bash
# WNBA Betting Model — Daily Pipeline
# Cron (9 AM daily): 0 9 * * * cd /path/to/wnba && ./run_pipeline.sh
set -e
cd "$(dirname "$0")"
DATE=$(date +%Y-%m-%d)
YEAR=$(date +%Y)
LOG="logs/pipeline_${DATE}.log"
mkdir -p logs predictions data/raw data/processed models

echo "═══ WNBA Pipeline — $DATE ═══" | tee "$LOG"

echo "[$(date +%H:%M)] Step 1: Stats (Basketball-Reference)..." | tee -a "$LOG"
python3 collect_stats.py --start 2022 --end "$YEAR" --out data/raw 2>&1 | tee -a "$LOG"

echo "[$(date +%H:%M)] Step 2: Odds (OddsShark)..." | tee -a "$LOG"
python3 scrape_odds.py --out data/raw 2>&1 | tee -a "$LOG"

echo "[$(date +%H:%M)] Step 3: Props (PrizePicks)..." | tee -a "$LOG"
python3 scrape_props.py --out data/raw 2>&1 | tee -a "$LOG"

echo "[$(date +%H:%M)] Step 4: Scores (ESPN)..." | tee -a "$LOG"
python3 scrape_scores.py --out data/raw --boxscores 2>&1 | tee -a "$LOG"

echo "[$(date +%H:%M)] Step 5: Merge + features..." | tee -a "$LOG"
python3 merge_data.py --year all --raw data/raw --out data/processed 2>&1 | tee -a "$LOG"

# Retrain every Monday
if [ "$(date +%u)" = "1" ]; then
    echo "[$(date +%H:%M)] Step 6: Monday retrain..." | tee -a "$LOG"
    python3 spread_model.py --mode train --data data/processed/master_all.csv 2>&1 | tee -a "$LOG"
    python3 totals_model.py --mode train --data data/processed/master_all.csv 2>&1 | tee -a "$LOG"
    python3 props_model.py  --mode train 2>&1 | tee -a "$LOG"
fi

echo "[$(date +%H:%M)] Step 7: Daily predictions..." | tee -a "$LOG"
OUT="predictions/predictions_${DATE}.json"
python3 daily_runner.py --date "$DATE" --out "$OUT" 2>&1 | tee -a "$LOG"

echo "[$(date +%H:%M)] Step 8: Update dashboard..." | tee -a "$LOG"
python3 update_dashboard.py --predictions "$OUT" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "── Best Bets ──" | tee -a "$LOG"
python3 -c "
import json
with open('$OUT') as f: d = json.load(f)
for b in d['best_bets']:
    e = f\"+{b['edge']}\" if b['edge'] > 0 else str(b['edge'])
    print(f\"  #{ b['rank']} [{ b['type']:<6}] { b['play']:<42} {e:>6} pts  {'★'*b['stars']}\")
print(f\"\n  {len(d['games'])} games  |  {sum(1 for b in d['best_bets'] if b['stars']==3)} high conf\")
" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "✅ Pipeline done. → $OUT" | tee -a "$LOG"
