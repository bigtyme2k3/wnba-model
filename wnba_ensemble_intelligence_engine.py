from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DASH = Path('data/dashboard')
WARE = Path('data/warehouse')
EDGES = DASH / 'wnba_daily_edges.json'
ADAPTIVE = DASH / 'wnba_adaptive_confidence.json'
OUTS = [DASH / 'wnba_ensemble_intelligence.json', WARE / 'wnba_ensemble_intelligence.json']

WEIGHTS = {
    'projection': 0.22,
    'recent_form': 0.14,
    'season_history': 0.10,
    'market_value': 0.14,
    'clv': 0.12,
    'roi': 0.08,
    'sample_strength': 0.08,
    'adaptive_calibration': 0.12,
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


def grade(score: float, evidence_count: int, extrapolated: bool) -> tuple[str, str]:
    if extrapolated:
        if score >= 80 and evidence_count >= 4:
            return 'B+', 'UNVALIDATED_HIGH'
        if score >= 68:
            return 'B', 'MODERATE'
        return 'C', 'LEAN'
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
    adaptive_prob = num(row.get('calibrated_probability'))
    if adaptive_prob is None:
        adaptive_prob = num(row.get('model_probability'))
    adaptive_score = clamp((adaptive_prob or 0.5) * 100)

    component_values = {
        'projection': num(comps.get('projection')) or 50.0,
        'recent_form': num(comps.get('recent_form')) or 50.0,
        'season_history': num(comps.get('season_history')) or 50.0,
        'market_value': num(comps.get('market_value')) or 50.0,
        'clv': num(comps.get('clv')) or 50.0,
        'roi': num(comps.get('roi')) or 50.0,
        'sample_strength': num(comps.get('sample_strength')) or 20.0,
        'adaptive_calibration': adaptive_score,
    }
    evidence_count = sum(
        component_values[k] != 50.0
        for k in ('projection', 'recent_form', 'season_history', 'market_value', 'clv', 'roi', 'adaptive_calibration')
    )
    raw = sum(component_values[k] * WEIGHTS[k] for k in WEIGHTS)
    missing_penalty = max(0, 4 - evidence_count) * 3.5
    extrapolated = bool(row.get('calibration_extrapolated'))
    extrapolation_penalty = 7.0 if extrapolated else 0.0
    score = clamp(raw - missing_penalty - extrapolation_penalty)
    letter, confidence = grade(score, evidence_count, extrapolated)

    breakdown = {
        key: {
            'score': round(component_values[key], 2),
            'weight': WEIGHTS[key],
            'contribution': round(component_values[key] * WEIGHTS[key], 2),
        }
        for key in WEIGHTS
    }

    reasons = list(row.get('evidence') or [])[:6]
    if adaptive_prob is not None:
        reasons.append(f'Calibrated probability {adaptive_prob:.1%}')
    if extrapolated:
        reasons.append('Score lies outside the historically validated calibration range')

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
        'ensemble_score': round(score, 2),
        'grade': letter,
        'ensemble_confidence': confidence,
        'adaptive_probability': round(adaptive_prob, 4) if adaptive_prob is not None else None,
        'calibration_extrapolated': extrapolated,
        'evidence_count': evidence_count,
        'component_breakdown': breakdown,
        'reasons': reasons,
        'source_edge_score': row.get('edge_score'),
        'source_confidence': row.get('confidence'),
    }


def build() -> dict[str, Any]:
    edges = load(EDGES, {})
    adaptive = load(ADAPTIVE, {})
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
            'extrapolated': sum(r['calibration_extrapolated'] for r in scored),
            'top_score': scored[0]['ensemble_score'] if scored else None,
            'adaptive_curve_points': adaptive.get('summary', {}).get('curve_points') if isinstance(adaptive, dict) else None,
        },
        'top_10': scored[:10],
        'elite_plays': [r for r in scored if r['grade'] == 'A+'][:20],
        'ranked_edges': scored[:100],
        'methodology': {
            'weights': WEIGHTS,
            'explainable': True,
            'calibration_aware': True,
            'warning': 'Ensemble grades rank agreement across model evidence. They are not guarantees and must remain subject to live validation.',
        },
    }
    for path in OUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, path.open('w', encoding='utf-8'), indent=2, allow_nan=False)
    print(json.dumps(report['summary'], indent=2))
    return report


if __name__ == '__main__':
    build()
