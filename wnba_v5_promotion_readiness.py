"""Conservative V5 promotion-readiness monitor.

This module aggregates already-certified forward evidence. It never promotes a model,
changes a prediction, or changes production routing. It exists so the dashboard can
show exactly which evidence gates are satisfied and which remain blocked.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DASH = Path('data/dashboard')
M12 = DASH/'wnba_v5_m12_report.json'
ADAPTIVE = DASH/'wnba_v5_adaptive_challenger_v2.json'
CHALLENGER = DASH/'wnba_v5_forward_challenger.json'
INTEGRITY = DASH/'wnba_v5_evidence_integrity.json'
HEALTH = DASH/'wnba_v5_current_data_health.json'
CLV = DASH/'wnba_v5_clv_summary.json'
OUT = DASH/'wnba_v5_promotion_readiness.json'

MIN_FORWARD = 300
MIN_CONTEXT_RESEARCH = 60
MIN_CONTEXT_PROMOTION = 300
MIN_CLV_PCT = 60.0


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def gate(name, current, required, passed, detail=''):
    return {
        'name': name,
        'current': current,
        'required': required,
        'pass': bool(passed),
        'detail': detail,
    }


def main():
    m12=load(M12); adaptive=load(ADAPTIVE); challenger=load(CHALLENGER)
    integrity=load(INTEGRITY); health=load(HEALTH); clv=load(CLV)
    metrics=m12.get('metrics') or {}

    forward=int(metrics.get('binary_graded_predictions') or m12.get('promotion_gate',{}).get('current_forward_rows') or 0)
    resolved_context=int(adaptive.get('resolved_context_rows') or 0)
    pending_context=int(adaptive.get('pending_context_rows') or 0)
    captured_context=int(adaptive.get('rows_with_any_frozen_context') or 0)
    clv_pct=float(clv.get('explicit_clv_coverage_pct') or 0.0)

    # Baseline chronological challenger evidence is useful, but contextual promotion
    # is evaluated only on prospective context rows.
    adaptive_results=adaptive.get('results') or []
    contextual=[r for r in adaptive_results if r.get('group') in {'MINUTES_ROLE','LINEUP_INJURY','MATCHUP'}]
    scored_contextual=[r for r in contextual if int(r.get('chronologically_scored_rows') or 0)>0]
    best_contextual=None
    if scored_contextual:
        best_contextual=min(scored_contextual,key=lambda r: float((r.get('model') or {}).get('brier') or 999))
    context_beats_market=bool(best_contextual and best_contextual.get('beats_market_brier'))
    context_beats_previous=bool(best_contextual and best_contextual.get('beats_previous_group_brier'))

    health_ok=health.get('status')=='GREEN'
    integrity_ok=integrity.get('status') in {'GREEN','YELLOW'} and int((integrity.get('summary') or {}).get('hard_violation_count') or 0)==0

    gates=[
        gate('Current data health',health.get('status'),'GREEN',health_ok,'All current canonical critical feeds must be green.'),
        gate('Evidence integrity',(integrity.get('summary') or {}).get('hard_violation_count',0),0,integrity_ok,'No hard chronology, identity, grading, or closing-line violations.'),
        gate('Forward graded sample',forward,MIN_FORWARD,forward>=MIN_FORWARD,'Minimum immutable graded forward evidence.'),
        gate('Resolved contextual research sample',resolved_context,MIN_CONTEXT_RESEARCH,resolved_context>=MIN_CONTEXT_RESEARCH,'Minimum sample before contextual ablation is interpreted.'),
        gate('Resolved contextual promotion sample',resolved_context,MIN_CONTEXT_PROMOTION,resolved_context>=MIN_CONTEXT_PROMOTION,'Materially larger prospective context sample required before promotion can be considered.'),
        gate('Explicit CLV coverage',round(clv_pct,2),MIN_CLV_PCT,clv_pct>=MIN_CLV_PCT,'Only explicit pre-tip closes count; missing closes remain missing.'),
        gate('Context challenger beats MARKET',best_contextual.get('group') if best_contextual else 'NOT_SCORED','Brier superiority',context_beats_market,'Best eligible contextual challenger must beat market Brier on chronological unseen rows.'),
        gate('Context challenger beats prior layer',best_contextual.get('group') if best_contextual else 'NOT_SCORED','Brier superiority',context_beats_previous,'Added context must improve on the preceding surviving feature layer.'),
    ]

    research_ready=health_ok and integrity_ok and forward>=MIN_FORWARD and resolved_context>=MIN_CONTEXT_RESEARCH
    promotion_evidence_ready=(research_ready and resolved_context>=MIN_CONTEXT_PROMOTION and clv_pct>=MIN_CLV_PCT and context_beats_market and context_beats_previous)
    # Deliberately no automated production promotion. A separate reviewed promotion
    # decision would still be required even when evidence gates become green.
    production_ready=False
    blockers=[g['name'] for g in gates if not g['pass']]
    status='EVIDENCE_READY_FOR_REVIEW' if promotion_evidence_ready else ('CONTEXT_RESEARCH_READY' if research_ready else 'ACCUMULATING_EVIDENCE')

    payload={
        'version':'V5',
        'module':'PROMOTION_READINESS_MONITOR',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':status,
        'research_ready':research_ready,
        'promotion_evidence_ready':promotion_evidence_ready,
        'production_ready':production_ready,
        'automatic_promotion_enabled':False,
        'context':{
            'captured_context_rows':captured_context,
            'resolved_context_rows':resolved_context,
            'pending_context_rows':pending_context,
            'minimum_research_rows':MIN_CONTEXT_RESEARCH,
            'minimum_promotion_rows':MIN_CONTEXT_PROMOTION,
        },
        'clv':{
            'coverage_pct':round(clv_pct,2),
            'required_pct':MIN_CLV_PCT,
            'explicit_close_predictions':clv.get('explicit_close_predictions'),
            'forward_predictions':clv.get('forward_predictions'),
        },
        'challenger':{
            'best_contextual_group':best_contextual.get('group') if best_contextual else None,
            'chronologically_scored_rows':int(best_contextual.get('chronologically_scored_rows') or 0) if best_contextual else 0,
            'brier':(best_contextual.get('model') or {}).get('brier') if best_contextual else None,
            'market_same_rows_brier':(best_contextual.get('market_same_rows') or {}).get('brier') if best_contextual else None,
            'beats_market_brier':context_beats_market,
            'beats_previous_group_brier':context_beats_previous,
        },
        'gates':gates,
        'blockers':blockers,
        'decision':'HOLD_SHADOW' if not promotion_evidence_ready else 'READY_FOR_HUMAN_PROMOTION_REVIEW',
        'policy':'No automatic promotion. V5 remains shadow until prospective context, explicit CLV, integrity, health, and chronological challenger gates all pass; even then a separate reviewed production change is required.',
    }
    OUT.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
