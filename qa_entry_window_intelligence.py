from __future__ import annotations
import json
from pathlib import Path

HISTORY = Path('data/market/entry_window_history.json')
RECS = Path('data/market/entry_window_recommendations.json')
SUMMARY = Path('data/dashboard/wnba_entry_window_summary.json')
VALID_ACTIONS = {'BET_NOW','WAIT','WATCH','PASS'}
VALID_WINDOWS = {'24H_PLUS','12_TO_24H','6_TO_12H','3_TO_6H','1_TO_3H','FINAL_HOUR','UNKNOWN','POST_TIP'}


def load(path: Path):
    if not path.exists():
        raise SystemExit(f'missing output: {path}')
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    history = load(HISTORY).get('windows', [])
    recs = load(RECS).get('recommendations', [])
    summary = load(SUMMARY)
    assert isinstance(history, list) and isinstance(recs, list)
    assert summary.get('status') in {'READY','STANDBY'}
    keys = set()
    for row in history:
        key = (row.get('bookmaker'), row.get('market'), row.get('window'))
        assert key not in keys, f'duplicate window: {key}'
        keys.add(key)
        assert row.get('window') in VALID_WINDOWS
        assert 0 <= float(row.get('window_score', 0)) <= 100
        assert 0 <= float(row.get('positive_clv_rate', 0)) <= 1
        assert int(row.get('observations', 0)) >= 0
    mids = set()
    for row in recs:
        mid = row.get('market_id')
        assert mid and mid not in mids, f'duplicate market recommendation: {mid}'
        mids.add(mid)
        assert row.get('action') in VALID_ACTIONS
        assert row.get('entry_window') in VALID_WINDOWS
        assert 0 <= float(row.get('confidence', 0)) <= 100
        assert int(row.get('historical_observations', 0)) >= 0
        assert isinstance(row.get('reasons'), list)
    counts = {a: sum(1 for x in recs if x.get('action') == a) for a in VALID_ACTIONS}
    assert summary.get('markets_scored') == len(recs)
    assert summary.get('historical_windows') == len(history)
    assert summary.get('actions') == counts
    if recs:
        assert summary.get('status') == 'READY'
    print(json.dumps({'status':'PASS','historical_windows':len(history),'markets_scored':len(recs),'actions':counts}, indent=2))


if __name__ == '__main__':
    main()
