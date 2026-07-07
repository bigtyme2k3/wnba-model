"""Master database consolidates daily model, market, portfolio, coach, grading and CLV state."""
from __future__ import annotations
import argparse,json,os
from datetime import date,datetime,timezone
MASTER='data/history/wnba_master_database.jsonl'
def load(p,d):
    try:
        if os.path.exists(p): return json.load(open(p,encoding='utf-8'))
    except Exception: pass
    return d
def build(target):
    row={'date':target,'captured_at_utc':datetime.now(timezone.utc).isoformat(),'final':load('data/warehouse/wnba_decision_engine_final.json',{}).get('summary',{}),'portfolio':load('data/warehouse/wnba_portfolio_optimizer_v2.json',{}).get('summary',{}),'monte_carlo':load('data/warehouse/wnba_monte_carlo_engine.json',{}).get('summary',{}),'market':load('data/warehouse/wnba_market_engine.json',{}).get('summary',{}),'grading':load('data/warehouse/wnba_results_grading.json',{}),'clv':load('data/warehouse/wnba_clv_summary.json',{}),'source_health':load('data/warehouse/wnba_source_health.json',{}).get('summary',{})}
    os.makedirs('data/history',exist_ok=True)
    with open(MASTER,'a',encoding='utf-8') as f: f.write(json.dumps(row,separators=(',',':'))+'\n')
    summary={'generated_at_utc':row['captured_at_utc'],'target_date':target,'latest':row}
    os.makedirs('data/warehouse',exist_ok=True); os.makedirs('data/dashboard',exist_ok=True)
    for p in ['data/warehouse/wnba_master_database_summary.json','data/dashboard/wnba_master_database_summary.json']:
        json.dump(summary,open(p,'w',encoding='utf-8'),indent=2)
    return summary
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',default=str(date.today())); args=ap.parse_args(); print('Master database updated:', build(args.date)['target_date'])
if __name__=='__main__': main()
