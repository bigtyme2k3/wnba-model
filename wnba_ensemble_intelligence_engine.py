from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASH = Path('data/dashboard')
WARE = Path('data/warehouse')
EDGES = DASH / 'wnba_daily_edges.json'
OUTS = [DASH / 'wnba_ensemble_intelligence.json', WARE / 'wnba_ensemble_intelligence.json']

# Production ensemble uses only contemporaneous/frozen evidence. Historical
# reconstructed calibration was retired because it was not a live pregame source.
WEIGHTS = {
    'projection': 0.25,
    'recent_form': 0.16,
    'season_history': 0.11,
    'market_value': 0.16,
    'clv': 0.14,
    'roi': 0.09,
    'sample_strength': 0.09,
}


def load(path: Path, default: Any) -> Any:
    try:
        return json.load(path.open(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def grade(score: float, evidence_count: int) -> tuple[str, str]:
    if score >= 90 and evidence_count >= 5:
        return 'A+', 'ELITE'
    if score >= 84 and evidence_count >= 4:
        return 'A', 'VERY_HIGH'
    if score >= 77 and evidence_count >= 4:
        return 'B+', 'HIGH'
    if score >= 68 and evidence_count >= 3:
        return 'B', 'MODERATE'
    if score >= 58:
        return 'C', 'LEAN'
    return 'D', 'PASS'


def score_candidate(row: dict[str, Any]) -> dict[str, Any]:
    comps = row.get('components') if isinstance(row.get('components'), dict) else {}
    component_values = {
        'projection': num(comps.get('projection')) or 50.0,
        'recent_form': num(comps.get('recent_form')) or 50.0,
        'season_history': num(comps.get('season_history')) or 50.0,
        'market_value': num(comps.get('market_value')) or 50.0,
        'clv': num(comps.get('clv')) or 50.0,
        'roi': num(comps.get('roi')) or 50.0,
        'sample_strength': num(comps.get('sample_strength')) or 20.0,
    }
    evidence_count = sum(
        component_values[k] != 50.0
        for k in ('projection', 'recent_form', 'season_history', 'market_value', 'clv', 'roi')
    )
    raw = sum(component_values[k] * WEIGHTS[k] for k in WEIGHTS)
    missing_penalty = max(0, 4 - evidence_count) * 3.5
    score = clamp(raw - missing_penalty)
    letter, confidence = grade(score, evidence_count)

    breakdown = {
        key: {
            'score': round(component_values[key], 2),
            'weight': WEIGHTS[key],
            'contribution': round(component_values[key] * WEIGHTS[key], 2),
        }
        for key in WEIGHTS
    }

    return {
        'player': row.get('player'),
        'team': row.get('team'),
        'game': row.get('game'),
        'market': row.get('market'),
        'side': row.get('side'),
        'line': row.get('line'),
        'sportsbook': row.get('sportsbook'),
        'odds': row.get('odds'),
        'projection': row.get('projection'),
        'market_type': row.get('market_type', 'standard'),
        'model_probability': row.get('model_probability'),
        'ensemble_score': round(score, 2),
        'grade': letter,
        'ensemble_confidence': confidence,
        'evidence_count': evidence_count,
        'component_breakdown': breakdown,
        'reasons': list(row.get('evidence') or [])[:6],
        'source_edge_score': row.get('edge_score'),
        'source_confidence': row.get('confidence'),
    }


def build() -> dict[str, Any]:
    edges = load(EDGES, {})
    rows = edges.get('top_edges', []) if isinstance(edges, dict) else []
    scored = [score_candidate(r) for r in rows if isinstance(r, dict)]
    scored.sort(key=lambda r: (r['ensemble_score'], r['evidence_count']), reverse=True)

    report = {
        'sprint': 9,
        'phase': 'ensemble-intelligence-engine',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_date': edges.get('target_date') if isinstance(edges, dict) else None,
        'status': 'ok' if scored else 'awaiting_live_slate',
        'summary': {
            'candidates_loaded': len(rows),
            'candidates_ranked': len(scored),
            'a_plus': sum(r['grade'] == 'A+' for r in scored),
            'a': sum(r['grade'] == 'A' for r in scored),
            'b_plus': sum(r['grade'] == 'B+' for r in scored),
            'high_or_better': sum(r['ensemble_confidence'] in {'ELITE', 'VERY_HIGH', 'HIGH'} for r in scored),
            'top_score': scored[0]['ensemble_score'] if scored else None,
        },
        'top_10': scored[:10],
        'elite_plays': [r for r in scored if r['grade'] == 'A+'][:20],
        'ranked_edges': scored[:100],
        'methodology': {
            'weights': WEIGHTS,
            'explainable': True,
            'calibration_aware': False,
            'historical_reconstruction_used': False,
            'warning': 'Ensemble grades rank agreement across current model evidence. They are not guarantees and remain subject to forward validation.',
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)
    print(json.dumps(report['summary'], indent=2))
    return report


if __name__ == '__main__':
    build()
