"""
build_dashboard.py
------------------
Reads the target predictions JSON and bakes it into docs/index.html.

Fixes:
- Uses TARGET env var from the workflow instead of runner UTC date.
- Adds odds-health and sportsbook-consensus diagnostics to DATA so the
  existing dashboard shows odds as loaded when real sportsbook markets exist.
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List

import pandas as pd

PREDICTIONS_DIR = "predictions"
RAW_DIR = "data/raw"
DASH_DIR = "data/dashboard"
TRACKING_JSON = "data/tracking/model_tracking.json"
OUTPUT_HTML = "docs/index.html"


def target_today() -> str:
    return os.environ.get("TARGET") or os.environ.get("WNBA_TARGET_DATE") or str(date.today())


def load_json(path: str, default: Any):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def empty_tracking() -> Dict[str, Any]:
    return {"overall": "0-0-0", "wins": 0, "losses": 0, "pushes": 0, "win_pct": 0, "roi": 0, "profit_units": 0, "clv_avg": 0, "by_type": {}, "by_conf": {}, "recent_10": []}


def empty_dashboard_data() -> Dict[str, Any]:
    today = target_today()
    return {
        "date": today,
        "generated": datetime.now(timezone.utc).isoformat(),
        "games": [], "best_bets": [], "props": [], "player_points": [], "props_board": [], "line_shopping": [],
        "tracking": empty_tracking(), "model_tracking": empty_tracking(),
        "data_health": {"odds": "missing", "props": "missing", "line_shopping": "missing", "player_points": "missing", "spreads_found": 0, "totals_found": 0, "props_found": 0, "player_points_found": 0, "line_shopping_rows": 0, "games": 0, "actionable_bets": 0, "high_bets": 0, "last_updated_utc": None},
        "model_stats": {"spread": {"algo": "Ridge v2", "cv_mae": 9.72, "dir_acc": 0.716, "strong_ats": 0.815, "n": 0}, "totals": {"algo": "Random Forest", "cv_mae": 6.77, "ou_acc": 0.542, "strong_ou": 0.554, "n": 0}, "props": {"algo": "Ridge", "cv_mae": 6.00, "hit_rate": 0.721, "strong_hr": 0.754, "n": 0}},
    }


def find_predictions() -> Dict[str, Any]:
    target = target_today()
    candidates = [os.path.join(PREDICTIONS_DIR, f"predictions_{target}.json")]
    candidates += sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")), reverse=True)
    seen = set()
    for path in candidates:
        if path in seen: continue
        seen.add(path)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: data = json.load(f)
            print(f"  Loaded: {path} ({len(data.get('games', []))} games)")
            return data
    print("  [WARN] No predictions file found — using empty data")
    return empty_dashboard_data()


def csv_value(value: Any) -> Any:
    try:
        if pd.isna(value): return None
    except Exception: pass
    return value


def load_csv_rows(paths: List[str]) -> List[Dict[str, Any]]:
    for path in paths:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                if len(df) > 0:
                    print(f"  Loaded CSV: {path} ({len(df)} rows)")
                    return [{k: csv_value(v) for k, v in row.to_dict().items()} for _, row in df.iterrows()]
            except Exception as exc:
                print(f"  [WARN] Could not load {path}: {exc}")
    return []


def load_player_points_for_date(target_date: str) -> List[Dict[str, Any]]:
    return load_csv_rows([os.path.join(RAW_DIR, f"player_points_{target_date}.csv"), os.path.join(RAW_DIR, "player_points_today.csv")])


def load_line_shopping_for_date(target_date: str) -> List[Dict[str, Any]]:
    return load_csv_rows([os.path.join(RAW_DIR, f"line_shopping_best_{target_date}.csv"), os.path.join(RAW_DIR, f"line_shopping_{target_date}.csv"), os.path.join(RAW_DIR, "line_shopping_best_today.csv"), os.path.join(RAW_DIR, "line_shopping_today.csv")])


def load_tracking() -> Dict[str, Any]:
    if os.path.exists(TRACKING_JSON):
        try:
            with open(TRACKING_JSON, encoding="utf-8") as f: return json.load(f)
        except Exception as exc:
            print(f"  [WARN] Could not read model tracking: {exc}")
    return empty_tracking()


def apply_odds_health(data: Dict[str, Any]) -> Dict[str, Any]:
    target_date = data.get("date") or target_today()
    h = data.setdefault("data_health", {})
    odds_health = load_json(os.path.join(DASH_DIR, "wnba_odds_health.json"), {})
    book = load_json(os.path.join(DASH_DIR, "wnba_sportsbook_consensus.json"), {})
    live = load_json(os.path.join(DASH_DIR, "wnba_live_odds_layer.json"), {})
    oh = odds_health.get("summary", {}) if isinstance(odds_health, dict) else {}
    bs = book.get("summary", {}) if isinstance(book, dict) else {}
    live_sum = live.get("summary", {}) if isinstance(live, dict) else {}
    line_rows = int(bs.get("markets", 0) or 0)
    spreads = int(oh.get("spread_rows", 0) or 0)
    totals = int(oh.get("total_rows", 0) or 0)
    active_props = int(oh.get("active_prop_rows", 0) or 0)
    if line_rows or active_props or int(live_sum.get("rows", 0) or 0):
        h["odds"] = "loaded"
    else:
        h["odds"] = h.get("odds") or "missing"
    h["spreads_found"] = spreads
    h["totals_found"] = totals
    h["props_found"] = max(int(h.get("props_found", 0) or 0), active_props, line_rows)
    h["line_shopping"] = "loaded" if line_rows else h.get("line_shopping", "missing")
    h["line_shopping_rows"] = line_rows
    h["sportsbook_markets"] = line_rows
    h["multi_book_markets"] = int(bs.get("multi_book_markets", 0) or 0)
    h["books_detected"] = bs.get("books_detected", [])
    h["last_updated_utc"] = odds_health.get("generated_at_utc") or book.get("generated_at_utc") or datetime.now(timezone.utc).isoformat()
    data["odds_health"] = odds_health
    data["sportsbook_consensus"] = book
    return data


def enrich_data(data: Dict[str, Any]) -> Dict[str, Any]:
    target_date = target_today()
    data["date"] = target_date
    data["generated"] = datetime.now(timezone.utc).isoformat()
    points = data.get("props") or data.get("player_points") or load_player_points_for_date(target_date)
    if points:
        data["props"] = points
        data["player_points"] = points
        data["props_board"] = data.get("props_board") or points
        h = data.setdefault("data_health", {})
        h["player_points"] = "loaded"
        h["props"] = "loaded"
        h["player_points_found"] = len(points)
        h["props_found"] = max(int(h.get("props_found", 0) or 0), len(points))
    else:
        data.setdefault("props", []); data.setdefault("player_points", []); data.setdefault("props_board", [])
    line_rows = data.get("line_shopping") or load_line_shopping_for_date(target_date)
    data["line_shopping"] = line_rows
    if line_rows:
        h = data.setdefault("data_health", {})
        h["line_shopping"] = "loaded"
        h["line_shopping_rows"] = len(line_rows)
    tracking = data.get("tracking") or data.get("model_tracking") or load_tracking()
    data["tracking"] = tracking; data["model_tracking"] = tracking
    return apply_odds_health(data)


def fallback_html(data_json: str) -> str:
    return f"""<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"><title>WNBA Betting Model</title><style>body{{background:#07080f;color:#e2e8f0;font-family:'Courier New',monospace;margin:0}}.app{{max-width:1200px;margin:0 auto;padding:18px}}.title{{font-size:28px;font-weight:900}}.sub{{color:#94a3b8}}.tabs{{display:flex;gap:8px;margin:18px 0;flex-wrap:wrap}}button{{background:#121b30;color:#e2e8f0;border:1px solid #24314d;border-radius:12px;padding:10px 14px;font-family:inherit;font-weight:900}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card,.panel{{background:#0d1220;border:1px solid #ffffff12;border-radius:18px;padding:16px}}.value{{font-size:28px;font-weight:900;color:#00e5a0}}.bad{{color:#f87171}}.list{{display:flex;flex-direction:column;gap:10px}}.row{{background:#0d1220;border:1px solid #ffffff12;border-radius:14px;padding:14px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr 1fr}}}}</style><script id=\"dashboard-data\">const DATA = {data_json}; window.DATA = DATA;</script></head><body><div class=\"app\"><div class=\"title\">WNBA Betting Model</div><div class=\"sub\">Daily Report · <span id=\"date\"></span></div><div class=\"grid\" id=\"health\"></div><div class=\"tabs\"><button onclick=\"show('games')\">Games</button><button onclick=\"show('props')\">Props</button><button onclick=\"show('bets')\">Best Bets</button><button onclick=\"show('tracking')\">Model Tracking</button></div><div id=\"view\" class=\"panel\"></div></div><script>const safe=(v,d='—')=>v===null||v===undefined||v===''?d:v;function health(){{const h=DATA.data_health||{{}};document.getElementById('date').textContent=DATA.date||'';document.getElementById('health').innerHTML=[['Odds',h.odds||'missing'],['Props',h.player_points||h.props||'missing'],['Games',(DATA.games||[]).length],['Markets',h.sportsbook_markets||h.line_shopping_rows||0]].map(x=>`<div class=\"card\"><div>${{x[0]}}</div><div class=\"value ${{String(x[1]).includes('missing')?'bad':''}}\">${{x[1]}}</div></div>`).join('')}}function show(tab){{let out=''; if(tab==='games')out=(DATA.games||[]).map(g=>`<div class=\"row\"><b>${{safe(g.away?.name||g.away_team)}} @ ${{safe(g.home?.name||g.home_team)}}</b><br>${{safe(g.tip||g.date)}}</div>`).join('')||'No games.'; if(tab==='props')out=(DATA.props||DATA.player_points||[]).slice(0,80).map(p=>`<div class=\"row\"><b>${{safe(p.player)}}</b> ${{safe(p.stat)}} ${{safe(p.signal)}}<br>Line ${{safe(p.line)}} · Projection ${{safe(p.pred)}} · EV ${{safe(p.ev_pct)}}%</div>`).join('')||'No props.'; if(tab==='bets')out=(DATA.best_bets||[]).map(b=>`<div class=\"row\"><b>${{safe(b.play)}}</b><br>${{safe(b.game)}} · EV ${{safe(b.ev_pct)}}%</div>`).join('')||'No best bets.'; if(tab==='tracking')out=`<pre>${{JSON.stringify(DATA.tracking||DATA.model_tracking||{{}},null,2)}}</pre>`; document.getElementById('view').innerHTML=out}}health();show('games');</script></body></html>"""


def inject_data_script(html: str, data_json: str) -> str:
    html = re.sub(r"<script id=[\"']dashboard-data[\"']>.*?</script>\s*", "", html, flags=re.DOTALL)
    patterns = [r"const\s+DATA\s*=\s*.*?;\s*(?=\n\s*const|\n\s*let|\n\s*function|\n\s*window\.|</script>)", r"window\.DATA\s*=\s*.*?;\s*(?=\n|</script>)"]
    replacement = f"const DATA = {data_json}; window.DATA = DATA;\n"
    for pattern in patterns:
        new_html, n = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
        if n: return new_html
    block = f"<script id=\"dashboard-data\">const DATA = {data_json}; window.DATA = DATA;</script>\n"
    if "</head>" in html: return html.replace("</head>", block + "</head>", 1)
    if "<body" in html: return re.sub(r"(<body[^>]*>)", r"\1\n" + block, html, count=1, flags=re.IGNORECASE)
    return block + html


def build_html(data: Dict[str, Any]) -> bool:
    data = enrich_data(data)
    data_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    if os.path.exists(OUTPUT_HTML):
        with open(OUTPUT_HTML, encoding="utf-8") as f: html = f.read()
        html = html.replace('>Stats</button>', '>Model Tracking</button>')
        html = inject_data_script(html, data_json)
    else:
        html = fallback_html(data_json)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f: f.write(html)
    return True


def main() -> None:
    print("\n═══ Building Dashboard ═══\n")
    data = find_predictions()
    build_html(data)
    h = data.get("data_health", {})
    print(f"  ✅ {OUTPUT_HTML} updated")
    print(f"     Target env: {target_today()}")
    print(f"     Date: {data.get('date')}")
    print(f"     Odds: {h.get('odds')} · Markets: {h.get('sportsbook_markets', h.get('line_shopping_rows',0))}")


if __name__ == "__main__": main()
