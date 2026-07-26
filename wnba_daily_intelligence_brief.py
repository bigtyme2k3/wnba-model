"""Sprint 17 Commit 5: generate a concise daily WNBA intelligence brief.

The brief summarizes the active slate, ranked research opportunities, market alerts,
closing-line forecasts, sportsbook context, and system readiness. It does not claim
profitability or instruct the user to place a wager.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIVE=Path('data/forecast/live_opportunity_scanner.json')
LIVE_SUMMARY=Path('data/dashboard/wnba_live_scanner_summary.json')
STEAM=Path('data/dashboard/wnba_steam_sharp_summary.json')
PRED=Path('data/dashboard/wnba_closing_line_predictor_summary.json')
BOOK=Path('data/dashboard/wnba_sportsbook_leader_normalized_summary.json')
TRENDS=Path('data/dashboard/wnba_trend_discovery_summary.json')
OUT=Path('data/forecast/daily_intelligence_brief.json')
MARKDOWN=Path('data/forecast/daily_intelligence_brief.md')
DASH=Path('data/dashboard/wnba_daily_intelligence_brief.json')


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw=json.loads(path.read_text(encoding='utf-8'))
    return raw if isinstance(raw,dict) else {}


def number(value: Any, default: float=0.0) -> float:
    try:
        return float(value)
    except (TypeError,ValueError):
        return default


def compact_market(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'market_id':row.get('market_id'),
        'event_id':row.get('event_id'),
        'commence_time_utc':row.get('commence_time_utc'),
        'matchup':f"{row.get('away_team')} @ {row.get('home_team')}",
        'bookmaker':row.get('bookmaker'),
        'market':row.get('market'),
        'participant':row.get('participant'),
        'selection':row.get('selection'),
        'current_point':row.get('current_point'),
        'current_price':row.get('current_price'),
        'projected_closing_point':row.get('projected_closing_point'),
        'projected_closing_price':row.get('projected_closing_price'),
        'score':row.get('live_opportunity_score',row.get('opportunity_score')),
        'tier':row.get('tier'),
        'action':row.get('scanner_recommendation'),
        'entry_action':row.get('entry_action'),
        'signal':row.get('signal'),
        'freshness_score':row.get('freshness_score'),
        'hours_to_tip':row.get('hours_to_tip'),
        'reasons':row.get('reasons',[])[:5],
    }


def line(row: dict[str, Any]) -> str:
    participant=row.get('participant') or row.get('matchup') or 'Market'
    selection=row.get('selection') or ''
    point=row.get('current_point')
    price=row.get('current_price')
    bits=[str(participant),str(selection)]
    if point is not None: bits.append(str(point))
    if price is not None: bits.append(str(price))
    return ' '.join(x for x in bits if x and x!='None')


def build_markdown(brief: dict[str, Any]) -> str:
    lines=['# WNBA Daily Intelligence Brief','',f"Generated: {brief['generated_at_utc']}",'']
    lines.append(f"**Status:** {brief['status']}")
    lines.append(f"**Slate:** {brief['slate']['events']} events, {brief['slate']['live_markets']} fresh markets")
    lines.append('')
    if brief['status']=='STANDBY':
        lines.extend(['No fresh WNBA markets begin within the active 48-hour horizon.',''])
    else:
        lines.extend(['## Top Opportunities',''])
        for i,row in enumerate(brief['top_opportunities'][:10],1):
            lines.append(f"{i}. **{line(row)}** — {row.get('bookmaker')} — score {row.get('score')} — {row.get('action')}")
        lines.append('')
    lines.extend(['## Market Alerts',''])
    if brief['market_alerts']:
        for row in brief['market_alerts'][:10]:
            lines.append(f"- {line(row)} — {row.get('signal')} — score {row.get('score')}")
    else:
        lines.append('- No active high-priority alerts.')
    lines.extend(['','## System Context',''])
    context=brief['system_context']
    lines.append(f"- Closing-line predictor: {context.get('predictor_status','UNKNOWN')} ({context.get('model_ready',0)} model-ready markets)")
    lines.append(f"- Normalized sportsbook leader: {context.get('sportsbook_leader') or 'UNRESOLVED'}")
    lines.append(f"- Qualified CLV trends: {context.get('qualified_trends',0)}")
    lines.extend(['',f"_Research intelligence only. {brief['warning']}_",''])
    return '\n'.join(lines)


def run() -> dict[str, Any]:
    live_payload=read(LIVE)
    live_summary=read(LIVE_SUMMARY)
    steam=read(STEAM)
    predictor=read(PRED)
    book=read(BOOK)
    trends=read(TRENDS)
    markets=live_payload.get('markets',[]) if isinstance(live_payload.get('markets'),list) else []
    compact=[compact_market(x) for x in markets]
    compact.sort(key=lambda x:(-number(x.get('score')),x.get('commence_time_utc') or ''))
    top=[x for x in compact if x.get('action') in {'BET_NOW','WATCH'} or number(x.get('score'))>=55][:25]
    alerts=[x for x in compact if x.get('signal') in {'STEAM','SHARP','LATE_MONEY','POSSIBLE_INJURY'}]
    alerts.sort(key=lambda x:(-number(x.get('score')),x.get('hours_to_tip') or 9999))
    generated=now()
    status='READY' if markets else 'STANDBY'
    brief={
        'generated_at_utc':generated,
        'status':status,
        'slate':{
            'horizon_hours':live_summary.get('horizon_hours',live_payload.get('horizon_hours',48)),
            'events':live_summary.get('events',0),
            'live_markets':len(markets),
            'status_counts':live_summary.get('status_counts',{}),
            'tier_counts':live_summary.get('tier_counts',{}),
            'recommendation_counts':live_summary.get('recommendation_counts',{}),
        },
        'top_opportunities':top,
        'market_alerts':alerts[:25],
        'pass_count':sum(x.get('action')=='PASS' for x in compact),
        'system_context':{
            'predictor_status':predictor.get('status','UNKNOWN'),
            'model_ready':predictor.get('model_ready',0),
            'walk_forward_predictions':predictor.get('walk_forward_predictions',0),
            'sportsbook_leader':book.get('overall_leader'),
            'synced_comparisons':(book.get('classification_counts') or {}).get('SYNCED',0),
            'qualified_trends':trends.get('qualified_trends',0),
            'steam_alerts':steam.get('steam_alerts',steam.get('steam',0)),
            'sharp_movements':steam.get('sharp_movements',steam.get('sharp',0)),
        },
        'headline':('No fresh WNBA markets in the next 48 hours.' if status=='STANDBY' else f"{len(markets)} fresh markets across {live_summary.get('events',0)} events; {len(top)} opportunities merit review."),
        'warning':'Rankings and forecasts are research estimates, not guarantees or instructions to wager.',
    }
    OUT.parent.mkdir(parents=True,exist_ok=True); DASH.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(brief,indent=2),encoding='utf-8')
    DASH.write_text(json.dumps(brief,indent=2),encoding='utf-8')
    MARKDOWN.write_text(build_markdown(brief),encoding='utf-8')
    print(json.dumps(brief,indent=2))
    return brief


if __name__=='__main__':
    run()
