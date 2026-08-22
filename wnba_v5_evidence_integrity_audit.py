"""Audit immutable V5 prediction history and explicit closing-line evidence.

This is a research/operations integrity gate. It does not alter predictions, grading,
or CLV. Hard chronology/identity violations are RED; insufficient evidence coverage is
YELLOW because it blocks promotion but is not itself data corruption.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DASH = ROOT / 'data' / 'dashboard'
FORWARD = ROOT / 'data' / 'history' / 'wnba_v5_forward_predictions.jsonl'
MODEL_HISTORY = ROOT / 'data' / 'history' / 'wnba_model_history.jsonl'
CLOSING = DASH / 'wnba_v5_closing_lines.csv'
CLV = DASH / 'wnba_v5_clv_summary.json'
QUEUE = DASH / 'wnba_v5_clv_queue.json'
OUT = DASH / 'wnba_v5_evidence_integrity.json'
CURRENT_MODEL_VERSION = 'sprint19_player_props_v5_m02_action_v2'
CLOSE_WINDOW_MIN = 15.0
CONTEXT_FUTURE_WARN_MIN = 5.0
CONTEXT_FUTURE_RED_MIN = 30.0


def load_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:
        return default


def parse_ts(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
    except Exception:
        return None


def f(value: Any):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def boolish(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1','true','yes','y'}


def read_jsonl(path: Path):
    rows, errors = [], []
    if not path.exists():
        return rows, ['missing_file']
    for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
            else:
                errors.append(f'line_{n}_not_object')
        except Exception as exc:
            errors.append(f'line_{n}_invalid_json:{type(exc).__name__}')
    return rows, errors


def section_status(red: list[str], yellow: list[str]) -> str:
    return 'RED' if red else ('YELLOW' if yellow else 'GREEN')


def audit_forward():
    rows, parse_errors = read_jsonl(FORWARD)
    red = list(parse_errors)
    yellow: list[str] = []
    ids = [str(r.get('prediction_id') or '').strip() for r in rows]
    missing_id = sum(not x for x in ids)
    duplicates = [k for k, n in Counter(x for x in ids if x).items() if n > 1]
    missing_key = sum(not str(r.get('ranking_key') or '').strip() for r in rows)
    missing_issued = sum(parse_ts(r.get('prediction_generated_at_utc')) is None for r in rows)
    if missing_id:
        red.append(f'missing_prediction_id:{missing_id}')
    if duplicates:
        red.append(f'duplicate_prediction_id:{len(duplicates)}')
    if missing_key:
        red.append(f'missing_ranking_key:{missing_key}')
    if missing_issued:
        red.append(f'missing_or_invalid_prediction_timestamp:{missing_issued}')

    resolved = [r for r in rows if str(r.get('outcome') or '').upper() in {'WIN','LOSS','PUSH'}]
    bad_actual = sum(r.get('actual') is None for r in resolved)
    bad_graded = sum(parse_ts(r.get('graded_at_utc')) is None for r in resolved)
    grade_before_issue = 0
    for r in resolved:
        issued = parse_ts(r.get('prediction_generated_at_utc'))
        graded = parse_ts(r.get('graded_at_utc'))
        if issued and graded and graded < issued:
            grade_before_issue += 1
    if bad_actual:
        red.append(f'resolved_missing_actual:{bad_actual}')
    if bad_graded:
        red.append(f'resolved_missing_graded_timestamp:{bad_graded}')
    if grade_before_issue:
        red.append(f'graded_before_prediction_issued:{grade_before_issue}')

    context_rows = 0
    resolved_context = 0
    context_future_warn = 0
    context_future_red = 0
    max_future_minutes = 0.0
    context_keys = ('ctx_snapshot_matchup_generated_at_utc','ctx_snapshot_lineup_generated_at_utc')
    for r in rows:
        has_context = any(k.startswith('ctx_') and r.get(k) is not None for k in r)
        if has_context:
            context_rows += 1
            if r in resolved:
                resolved_context += 1
        issued = parse_ts(r.get('prediction_generated_at_utc'))
        if not issued:
            continue
        for key in context_keys:
            snap = parse_ts(r.get(key))
            if not snap:
                continue
            delta = (snap-issued).total_seconds()/60.0
            max_future_minutes = max(max_future_minutes, delta)
            if delta > CONTEXT_FUTURE_RED_MIN:
                context_future_red += 1
            elif delta > CONTEXT_FUTURE_WARN_MIN:
                context_future_warn += 1
    if context_future_red:
        red.append(f'context_snapshot_materially_after_issuance:{context_future_red}')
    if context_future_warn:
        yellow.append(f'context_snapshot_slightly_after_issuance:{context_future_warn}')

    ranking_counts = Counter(str(r.get('ranking_key') or '') for r in rows if r.get('ranking_key'))
    reissued_keys = sum(n > 1 for n in ranking_counts.values())
    return {
        'status': section_status(red, yellow),
        'path': str(FORWARD.relative_to(ROOT)),
        'rows': len(rows),
        'unique_prediction_ids': len(set(x for x in ids if x)),
        'unique_ranking_keys': len(ranking_counts),
        'ranking_keys_with_reissues': reissued_keys,
        'resolved_rows': len(resolved),
        'pending_rows': len(rows)-len(resolved),
        'context_rows': context_rows,
        'resolved_context_rows': resolved_context,
        'context_future_max_minutes': round(max_future_minutes, 3),
        'hard_violations': red,
        'warnings': yellow,
        'contract': 'Issued predictions are immutable; grading must occur after issuance; prospective context cannot be materially newer than issuance.',
    }


def audit_model_history():
    rows, parse_errors = read_jsonl(MODEL_HISTORY)
    red = list(parse_errors)
    yellow: list[str] = []
    current = [r for r in rows if str(r.get('model_version') or '') == CURRENT_MODEL_VERSION]
    keys = [str(r.get('history_key') or '').strip() for r in current]
    dup = [k for k,n in Counter(x for x in keys if x).items() if n > 1]
    missing_key = sum(not x for x in keys)
    if dup:
        red.append(f'current_model_duplicate_history_key:{len(dup)}')
    if missing_key:
        red.append(f'current_model_missing_history_key:{missing_key}')
    resolved = [r for r in current if str(r.get('outcome') or '').upper() in {'WIN','LOSS','PUSH','VOID'}]
    missing_actual = sum(r.get('actual') is None and str(r.get('outcome') or '').upper() != 'VOID' for r in resolved)
    if missing_actual:
        red.append(f'current_model_resolved_missing_actual:{missing_actual}')
    bad_grade_order = 0
    for r in resolved:
        captured = parse_ts(r.get('captured_at_utc'))
        graded = parse_ts(r.get('graded_at_utc'))
        if captured and graded and graded < captured:
            bad_grade_order += 1
    if bad_grade_order:
        red.append(f'current_model_graded_before_capture:{bad_grade_order}')
    quarantined = sum(str(r.get('result_scope') or '').upper() == 'QUARANTINED' for r in current)
    return {
        'status': section_status(red, yellow),
        'path': str(MODEL_HISTORY.relative_to(ROOT)),
        'all_history_rows': len(rows),
        'current_model_rows': len(current),
        'current_model_resolved_rows': len(resolved),
        'current_model_quarantined_rows': quarantined,
        'unique_current_history_keys': len(set(x for x in keys if x)),
        'hard_violations': red,
        'warnings': yellow,
        'contract': 'Current-model result history must be key-unique and resolved results must carry verified actuals after capture.',
    }


def audit_closing():
    red: list[str] = []
    yellow: list[str] = []
    rows = []
    if not CLOSING.exists():
        red.append('missing_closing_lines_file')
    else:
        try:
            rows = list(csv.DictReader(CLOSING.open(encoding='utf-8-sig', newline='')))
        except Exception as exc:
            red.append(f'closing_csv_parse_error:{type(exc).__name__}')
    ids = [str(r.get('snapshot_id') or '').strip() for r in rows]
    dup = [k for k,n in Counter(x for x in ids if x).items() if n > 1]
    if dup:
        red.append(f'duplicate_close_snapshot_id:{len(dup)}')
    missing_id = sum(not x for x in ids)
    if missing_id:
        red.append(f'missing_close_snapshot_id:{missing_id}')
    bad_class = sum(str(r.get('capture_class') or '') != 'EXPLICIT_PRETIP_CLOSE' for r in rows)
    bad_flag = sum(not boolish(r.get('is_explicit_close')) for r in rows)
    bad_window = 0
    capture_after_tip = 0
    invalid_time = 0
    for r in rows:
        minutes = f(r.get('minutes_to_tip'))
        if minutes is None:
            invalid_time += 1
        elif minutes < -1e-6 or minutes > CLOSE_WINDOW_MIN + 1e-6:
            bad_window += 1
        captured = parse_ts(r.get('captured_at_utc'))
        tip = parse_ts(r.get('commence_time'))
        if captured and tip and captured > tip:
            capture_after_tip += 1
    if bad_class:
        red.append(f'non_explicit_capture_class_rows:{bad_class}')
    if bad_flag:
        red.append(f'explicit_close_flag_false_rows:{bad_flag}')
    if bad_window:
        red.append(f'close_rows_outside_0_{int(CLOSE_WINDOW_MIN)}m_window:{bad_window}')
    if capture_after_tip:
        red.append(f'close_rows_captured_after_tip:{capture_after_tip}')
    if invalid_time:
        yellow.append(f'close_rows_missing_minutes_to_tip:{invalid_time}')

    queue = load_json(QUEUE, {})
    report = queue.get('report', {}) if isinstance(queue, dict) else {}
    qstatus = str(report.get('status') or 'MISSING')
    valid_noop = qstatus in {'WAITING_FOR_CLOSE_WINDOW','WAITING_FOR_M11_SCORES','BLOCKED_STALE_SLATE','WAITING_FOR_ODDS_API_KEY'}
    valid_active = qstatus in {'CAPTURED_EXPLICIT_CLOSES','NO_MATCHING_PROP_MARKETS'}
    if qstatus == 'MISSING':
        yellow.append('clv_queue_report_missing')
    elif not (valid_noop or valid_active):
        yellow.append(f'unrecognized_clv_queue_status:{qstatus}')
    reported_total = int(report.get('total_close_rows') or 0)
    if rows and reported_total and reported_total != len(rows):
        yellow.append(f'queue_total_close_rows_mismatch:{reported_total}!={len(rows)}')
    return {
        'status': section_status(red, yellow),
        'path': str(CLOSING.relative_to(ROOT)),
        'rows': len(rows),
        'unique_snapshot_ids': len(set(x for x in ids if x)),
        'queue_status': qstatus,
        'queue_valid_noop': valid_noop,
        'queue_candidate_predictions': report.get('candidate_predictions'),
        'queue_eligible_events': report.get('eligible_events'),
        'queue_new_close_rows': report.get('new_close_rows'),
        'hard_violations': red,
        'warnings': yellow,
        'contract': f'Closing evidence must be explicit Odds API observations captured 0-{int(CLOSE_WINDOW_MIN)} minutes before tip; no inferred/post-tip close is accepted.',
    }


def audit_clv():
    red: list[str] = []
    yellow: list[str] = []
    p = load_json(CLV, {})
    if not isinstance(p, dict) or not p:
        red.append('missing_or_invalid_clv_summary')
        return {'status':'RED','path':str(CLV.relative_to(ROOT)),'hard_violations':red,'warnings':yellow}
    if p.get('status') != 'READY':
        yellow.append(f"clv_engine_status:{p.get('status')}")
    forward = int(p.get('forward_predictions') or 0)
    explicit = int(p.get('explicit_close_predictions') or 0)
    missing = int(p.get('missing_explicit_close_predictions') or 0)
    coverage = f(p.get('explicit_clv_coverage_pct')) or 0.0
    minimum = f(p.get('minimum_promotion_clv_coverage_pct')) or 60.0
    if explicit > forward:
        red.append(f'explicit_close_predictions_exceed_forward:{explicit}>{forward}')
    if forward and explicit + missing != forward:
        yellow.append(f'clv_coverage_partition_mismatch:{explicit}+{missing}!={forward}')
    if coverage < minimum:
        yellow.append(f'promotion_clv_coverage_not_met:{coverage:.1f}%<{minimum:.1f}%')
    return {
        'status': section_status(red, yellow),
        'path': str(CLV.relative_to(ROOT)),
        'engine_status': p.get('status'),
        'forward_predictions': forward,
        'explicit_close_predictions': explicit,
        'missing_explicit_close_predictions': missing,
        'explicit_clv_coverage_pct': coverage,
        'minimum_promotion_clv_coverage_pct': minimum,
        'same_book_close_rows': p.get('same_book_close_rows'),
        'same_line_close_rows': p.get('same_line_close_rows'),
        'avg_line_clv': p.get('avg_line_clv'),
        'positive_line_clv_pct': p.get('positive_line_clv_pct'),
        'avg_price_clv_probability': p.get('avg_price_clv_probability'),
        'positive_price_clv_pct': p.get('positive_price_clv_pct'),
        'hard_violations': red,
        'warnings': yellow,
        'contract': 'Promotion requires explicit pre-tip close evidence; missing closes remain missing and are never inferred.',
    }


def main():
    sections = {
        'forward_ledger': audit_forward(),
        'model_history': audit_model_history(),
        'explicit_closing_evidence': audit_closing(),
        'clv_readiness': audit_clv(),
    }
    reds = sum(s.get('status') == 'RED' for s in sections.values())
    yellows = sum(s.get('status') == 'YELLOW' for s in sections.values())
    greens = sum(s.get('status') == 'GREEN' for s in sections.values())
    status = 'RED' if reds else ('YELLOW' if yellows else 'GREEN')
    payload = {
        'version': 'V5',
        'module': 'EVIDENCE_INTEGRITY_AUDIT',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': status,
        'research_only': True,
        'production_mutation': False,
        'summary': {
            'sections': len(sections),
            'green': greens,
            'yellow': yellows,
            'red': reds,
            'hard_violation_count': sum(len(s.get('hard_violations') or []) for s in sections.values()),
            'warning_count': sum(len(s.get('warnings') or []) for s in sections.values()),
        },
        'sections': sections,
        'policy': 'RED means evidence integrity/chronology is unsafe. YELLOW means evidence is structurally valid but incomplete or below a research/promotion threshold. This audit never repairs or rewrites historical evidence.',
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, allow_nan=False))
    if status == 'RED':
        raise SystemExit('V5 evidence integrity audit found hard violations')


if __name__ == '__main__':
    main()
