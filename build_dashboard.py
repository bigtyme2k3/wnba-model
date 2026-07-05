"""
build_dashboard.py
------------------
Reads the latest predictions JSON and bakes it into docs/index.html.
Also injects model tracking data and overrides the Stats tab into Model Tracking.
"""

import glob, json, os, re
from datetime import date
import pandas as pd

PREDICTIONS_DIR = "predictions"
RAW_DIR = "data/raw"
TRACKING_JSON = "data/tracking/model_tracking.json"
OUTPUT_HTML = "docs/index.html"


def empty_tracking():
    return {"overall":"0-0-0","wins":0,"losses":0,"pushes":0,"win_pct":0,"roi":0,"profit_units":0,"clv_avg":0,"by_type":{},"by_conf":{},"recent_10":[]}


def empty_dashboard_data():
    today = str(date.today())
    return {"date":today,"generated":None,"games":[],"best_bets":[],"props":[],"player_points":[],"props_board":[],"tracking":empty_tracking(),"model_tracking":empty_tracking(),"data_health":{"odds":"missing","props":"missing","player_points":"missing","spreads_found":0,"totals_found":0,"props_found":0,"player_points_found":0,"games":0,"actionable_bets":0,"high_bets":0,"last_updated_utc":None},"model_stats":{"spread":{"algo":"Ridge v2","cv_mae":9.72,"dir_acc":0.716,"strong_ats":0.815,"n":0},"totals":{"algo":"Random Forest","cv_mae":6.77,"ou_acc":0.542,"strong_ou":0.554,"n":0},"props":{"algo":"Ridge","cv_mae":6.00,"hit_rate":0.721,"strong_hr":0.754,"n":0}}}


def find_predictions():
    today = str(date.today())
    candidates = [os.path.join(PREDICTIONS_DIR, f"predictions_{today}.json")] + sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")), reverse=True)
    seen = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            print(f"  Loaded: {path} ({len(data.get('games', []))} games)")
            return data
    print("  [WARN] No predictions file found — using empty data")
    return empty_dashboard_data()


def csv_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def load_player_points_for_date(target_date):
    for path in [os.path.join(RAW_DIR, f"player_points_{target_date}.csv"), os.path.join(RAW_DIR, "player_points_today.csv")]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                print(f"  Loaded player points: {path} ({len(df)} rows)")
                return [{k: csv_value(v) for k, v in row.to_dict().items()} for _, row in df.iterrows()]
            except Exception as exc:
                print(f"  [WARN] Could not load player points from {path}: {exc}")
    return []


def load_tracking():
    if os.path.exists(TRACKING_JSON):
        try:
            with open(TRACKING_JSON) as f:
                return json.load(f)
        except Exception as exc:
            print(f"  [WARN] Could not read model tracking: {exc}")
    return empty_tracking()


def enrich_data(data):
    target_date = data.get("date") or str(date.today())
    points = data.get("props") or data.get("player_points") or load_player_points_for_date(target_date)
    if points:
        data["props"] = points
        data["player_points"] = points
        data["props_board"] = data.get("props_board") or points
        h = data.setdefault("data_health", {})
        h["player_points"] = "loaded"
        h["player_points_found"] = len(points)
        h["props_found"] = max(int(h.get("props_found", 0) or 0), len(points))
    else:
        data.setdefault("props", [])
        data.setdefault("player_points", [])
        data.setdefault("props_board", [])
    tracking = data.get("tracking") or data.get("model_tracking") or load_tracking()
    data["tracking"] = tracking
    data["model_tracking"] = tracking
    return data


def dashboard_override_script():
    return r'''
<script id="model-tracking-override">
(function(){
  const tabs=document.querySelectorAll('.tab');
  tabs.forEach(t=>{ if(t.textContent.trim()==='Stats') t.textContent='Model Tracking'; });
  window.renderStats=function(){
    const t=DATA.tracking||DATA.model_tracking||{};
    const byType=t.by_type||{}, byConf=t.by_conf||{};
    const fmtPct=v=>typeof v==='number'?Math.round(v*1000)/10+'%':'—';
    const safe=(v,d='—')=>v===null||v===undefined||v===''?d:v;
    const statCard=(title,rows)=>`<article class="stat-card"><div class="stat-title">${title}</div>${rows.map(r=>`<div class="stat-line"><span>${r[0]}</span><span>${safe(r[1])}</span></div>`).join('')}</article>`;
    const typeRows=Object.keys(byType).length?Object.entries(byType).map(([k,v])=>`<article class="board-row"><div><div class="board-main">${k}</div><div class="board-sub">${v.bets||0} tracked bets</div></div><div><div class="board-label">Record</div><div class="board-value">${safe(v.record)}</div></div><div><div class="board-label">Win %</div><div class="board-value">${fmtPct(v.win_pct)}</div></div><div></div><div></div></article>`).join(''):'<div class="empty">No graded bets yet. Tracking starts once games finish.</div>';
    const confRows=Object.keys(byConf).length?Object.entries(byConf).map(([k,v])=>`<article class="board-row"><div><div class="board-main">${k}</div><div class="board-sub">Confidence bucket</div></div><div><div class="board-label">Record</div><div class="board-value">${safe(v.record)}</div></div><div><div class="board-label">Win %</div><div class="board-value">${fmtPct(v.win_pct)}</div></div><div></div><div></div></article>`).join(''):'<div class="note">Confidence tracking appears after bets are graded.</div>';
    const recent=(t.recent_10||[]).slice(-10).map(b=>`<article class="board-row"><div><div class="board-main">${safe(b.play)}</div><div class="board-sub">${safe(b.date)} · ${safe(b.game)}</div></div><div><div class="board-label">Type</div><div class="board-value">${safe(b.type)}</div></div><div><div class="board-label">Result</div><div class="board-value ${b.result==='WIN'?'good':b.result==='LOSS'?'bad':'warn'}">${safe(b.result)}</div></div><div><div class="board-label">Units</div><div class="board-value">${safe(b.profit_units)}</div></div><div></div></article>`).join('')||'<div class="empty">No recent graded bets yet.</div>';
    document.getElementById('tab-stats').innerHTML=`<div class="section-title">Model Tracking</div><section class="stats-grid">${statCard('Overall',[['Record',t.overall||'0-0-0'],['Win %',fmtPct(t.win_pct)],['ROI',fmtPct(t.roi)],['Units',safe(t.profit_units,0)],['Avg CLV',safe(t.clv_avg,0)]])}${statCard('Automation',[['Odds',safe((DATA.data_health||{}).odds)],['Props',safe((DATA.data_health||{}).props)],['Games',safe((DATA.data_health||{}).games,0)],['Best Bets',(DATA.best_bets||[]).length]])}${statCard('EV Engine',[['A/B Bets',(DATA.best_bets||[]).filter(b=>['A','B'].includes(b.grade)).length],['Top EV',(DATA.best_bets||[])[0]?.ev_pct?((DATA.best_bets||[])[0].ev_pct+'%'):'—'],['Top Grade',(DATA.best_bets||[])[0]?.grade||'—'],['Kelly Units',(DATA.best_bets||[])[0]?.units||'—']])}${statCard('Model Counts',[['Spreads',(DATA.data_health||{}).spreads_found||0],['Totals',(DATA.data_health||{}).totals_found||0],['Props',(DATA.data_health||{}).props_found||0],['High Bets',(DATA.data_health||{}).high_bets||0]])}</section><div class="section-title">Performance by Market</div><div class="board">${typeRows}</div><div class="section-title">Confidence Breakdown</div><div class="board">${confRows}</div><div class="section-title">Recent Graded Bets</div><div class="board">${recent}</div>`;
  };
})();
</script>
'''


def build_html(data):
    data = enrich_data(data)
    data_json = json.dumps(data, separators=(",", ":"))
    with open(OUTPUT_HTML) as f:
        html = f.read()
    html = html.replace('>Stats</button>', '>Model Tracking</button>')
    html = re.sub(r"<script id=\"model-tracking-override\">.*?</script>", "", html, flags=re.DOTALL)
    pattern = r"const\s+DATA\s*=\s*.*?;\s*(?=\n\s*const|\n\s*let|\n\s*function|\n\s*window\.)"
    replacement = f"const DATA = {data_json};\n"
    new_html = re.sub(pattern, lambda _: replacement, html, flags=re.DOTALL)
    if new_html == html:
        print("  [WARN] Could not find DATA constant to replace — check docs/index.html")
        return False
    new_html = new_html.replace("</body>", dashboard_override_script() + "\n</body>")
    with open(OUTPUT_HTML, "w") as f:
        f.write(new_html)
    return True


def main():
    print("\n═══ Building Dashboard ═══\n")
    os.makedirs("docs", exist_ok=True)
    data = find_predictions()
    success = build_html(data)
    if success:
        h = data.get("data_health", {})
        print(f"  ✅ {OUTPUT_HTML} updated")
        print(f"     Date: {data.get('date')}")
        print(f"     Games: {len(data.get('games', []))}")
        print(f"     Best bets: {len(data.get('best_bets', []))}")
        print(f"     Props: {len(data.get('props', []))}")
        print(f"     Odds: {h.get('odds', 'unknown')}")
    else:
        raise SystemExit("  ❌ Build failed")


if __name__ == "__main__":
    main()
