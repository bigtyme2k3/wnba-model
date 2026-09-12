"""Install a fail-closed WNBA break state in the deployed dashboard.

The committed dashboard may contain historical/current-slate payloads from the
last game day. During a schedule-confirmed break, this final runtime wrapper
keeps archive and health views available while replacing every live betting
view with an explicit no-current-data state.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

HTML = Path("docs/index.html")
STYLE_ID = "wnba-break-state-style"
SCRIPT_ID = "wnba-break-state-script"

STYLE = r'''<style id="wnba-break-state-style">
.wnbaBreakBanner{margin:14px 0;padding:14px 16px;border:1px solid #75601d;border-radius:16px;background:linear-gradient(135deg,#2c2409,#111827 62%);box-shadow:0 10px 30px rgba(0,0,0,.22)}
.wnbaBreakTop{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.wnbaBreakTitle{font-size:18px;font-weight:950;color:#ffe082}.wnbaBreakBadge{display:inline-flex;align-items:center;border:1px solid #8c7424;border-radius:999px;padding:5px 9px;color:#ffe082;font-size:11px;font-weight:900;letter-spacing:.08em}.wnbaBreakText{margin-top:7px;color:#bdc8dc;font-size:12px;line-height:1.5}.wnbaBreakFacts{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px;margin-top:12px}.wnbaBreakFact{border:1px solid #34415a;border-radius:11px;background:#0b1220;padding:9px 10px;color:#91a0b9;font-size:11px}.wnbaBreakFact b{display:block;color:#eef3ff;font-size:13px;margin-top:3px}.wnbaBreakView{padding:18px;border:1px solid #34415a;border-radius:16px;background:linear-gradient(180deg,#101827,#0a0f1d)}.wnbaBreakView h2{margin:9px 0}.wnbaBreakNotice{margin-top:12px;padding:12px;border:1px solid #75601d;border-radius:12px;background:#211b08;color:#ffe082}.wnbaBreakAvailable{margin-top:12px;color:#91a0b9;font-size:11px}.tab[data-break-current="true"]{color:#78859a}.tab[data-break-current="true"]::after{content:' · PAUSED';font-size:8px;color:#d9b84c}
@media(max-width:620px){.wnbaBreakBanner{padding:12px}.wnbaBreakTitle{font-size:16px}.wnbaBreakFacts{grid-template-columns:1fr 1fr}}
</style>'''

SCRIPT_TEMPLATE = r'''<script id="wnba-break-state-script">
(function(){
const CONTEXT=__PAYLOAD__;
const CURRENT_VIEWS=new Set(['games','matchups','props','alt-props','alt','altstreaks','sportsbooks','books','best','ai','live','portfolio','today']);
const ALIASES={today:'games',alt:'alt-props',altstreaks:'alt-props',books:'sportsbooks'};
const esc=value=>String(value??'—').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const pretty=value=>{if(!value)return'Not scheduled';const parsed=new Date(value+'T12:00:00');return Number.isNaN(parsed.getTime())?value:parsed.toLocaleDateString(undefined,{weekday:'long',month:'long',day:'numeric'})};
const root=()=>document.getElementById('root')||document.getElementById('content');
const nextLabel=()=>CONTEXT.next_slate_date?pretty(CONTEXT.next_slate_date):'Not yet scheduled';
function copy(view){
 if(view==='games')return `There are no WNBA games today. The next confirmed slate is ${nextLabel()}. Early game lines may be visible at sportsbooks, but the model has no current slate to score.`;
 if(view==='props')return 'Player props have not been posted for the next WNBA slate. No prior-slate lines or projections are being reused.';
 if(view==='alt-props')return 'Verified alternate player markets are not available yet. The paid ALT refresh remains paused to protect API quota.';
 if(view==='sportsbooks')return 'Only limited early game markets may be available. Current sportsbook rows will appear after the canonical slate refresh.';
 if(view==='best'||view==='portfolio')return 'No bets or stakes are issued during the break. Recommendations remain withheld until current markets and source checks are available.';
 if(view==='live')return 'No WNBA game is live during the confirmed schedule break.';
 return 'This current-slate view is paused until the next WNBA game day has verified canonical data.';
}
function maintenanceView(view){return `<div class="section wnbaBreakView"><span class="wnbaBreakBadge">BREAK MODE · FAIL CLOSED</span><h2 class="mono">${esc(view==='alt-props'?'ALT Props':view==='props'?'Player Props':view==='best'?'Best Bets':view==='portfolio'?'Portfolio':view==='sportsbooks'?'Sportsbooks':view==='live'?'Live':view==='matchups'?'Matchups':'WNBA Slate')}</h2><div class="wnbaBreakText">${esc(copy(view))}</div><div class="wnbaBreakNotice mono">No prior-slate data is actionable. No Odds API refresh was called for this maintenance deployment.</div><div class="wnbaBreakAvailable mono">Results, Game Performance, Remaining Season, and Data Health remain available from the navigation.</div></div>`}
function syncTabs(view){const tabs=document.getElementById('tabs');if(!tabs)return;tabs.querySelectorAll('.tab').forEach(button=>{const id=button.getAttribute('data-view')||'';button.classList.toggle('a',id===view);const current=CURRENT_VIEWS.has(ALIASES[id]||id);button.dataset.breakCurrent=current?'true':'false';if(current)button.title='Paused until current WNBA slate data is available'});}
function banner(){
 let element=document.getElementById('wnba-break-state-banner');
 if(element)return element;
 element=document.createElement('section');element.id='wnba-break-state-banner';element.className='wnbaBreakBanner';
 element.innerHTML=`<div class="wnbaBreakTop"><div><div class="wnbaBreakTitle mono">WNBA schedule break</div><div class="wnbaBreakText">Today is ${esc(CONTEXT.current_date)}. ${CONTEXT.next_slate_date?`The next confirmed game date is ${esc(nextLabel())}.`:'No future slate is confirmed in the cached schedule.'}</div></div><span class="wnbaBreakBadge">HEALTHY MAINTENANCE</span></div><div class="wnbaBreakFacts"><div class="wnbaBreakFact">Next slate<b>${esc(CONTEXT.next_slate_date||'Not scheduled')}</b></div><div class="wnbaBreakFact">Player props<b>Not available</b></div><div class="wnbaBreakFact">ALT markets<b>Refresh paused</b></div><div class="wnbaBreakFact">Model decisions<b>Withheld</b></div></div>`;
 const tabs=document.getElementById('tabs');const app=document.querySelector('.app')||document.body;if(tabs&&tabs.parentNode)tabs.parentNode.insertBefore(element,tabs);else app.insertBefore(element,app.firstChild);
 return element;
}
function syncChrome(){
 document.body.classList.add('wnba-break-mode');banner();
 const sub=document.getElementById('sub');if(sub)sub.textContent=`Break ${CONTEXT.current_date} · Next slate ${CONTEXT.next_slate_date||'not scheduled'}`;
 const pill=document.getElementById('pill');if(pill)pill.textContent='Current markets unavailable';
 const active=document.querySelector('.tab.a');syncTabs(active?.getAttribute('data-view')||'');
}
function install(){
 if(window.render&&window.render.__wnbaBreakState)return true;
 if(typeof window.render!=='function')return false;
 const prior=window.render;
 const wrapped=function(view='games'){
   const resolved=ALIASES[view]||view;
   if(CURRENT_VIEWS.has(resolved)){
     syncTabs(resolved);const target=root();if(target)target.innerHTML=maintenanceView(resolved);
     try{history.replaceState(null,'','#'+resolved)}catch(_){}
     syncChrome();window.scrollTo(0,0);return;
   }
   const result=prior.apply(this,arguments);setTimeout(syncChrome,0);return result;
 };
 wrapped.__wnbaBreakState=true;window.render=wrapped;syncChrome();window.render((location.hash||'#games').slice(1)||'games');return true;
}
window.WNBA_SLATE_CONTEXT=CONTEXT;
if(!install()){let attempts=0;const timer=setInterval(()=>{attempts+=1;if(install()||attempts>=30)clearInterval(timer)},100)}
})();
</script>'''


def replace_element(html: str, tag: str, element_id: str, replacement: str) -> str:
    pattern = rf'<{tag} id="{re.escape(element_id)}">.*?</{tag}>'
    html, count = re.subn(pattern, replacement, html, count=1, flags=re.S)
    if count:
        return html
    anchor = "</head>" if tag == "style" else "</body>"
    if anchor not in html:
        raise SystemExit(f"Dashboard shell missing {anchor}")
    return html.replace(anchor, replacement + "\n" + anchor, 1)


def install_break_state(html_path: Path, context: dict[str, Any]) -> dict[str, Any]:
    mode = str(context.get("mode") or "")
    current = str(context.get("current_date") or "")
    next_slate = str(context.get("next_slate_date") or "") or None
    if mode not in {"break", "offseason"}:
        raise SystemExit(f"Break-state patch requires break/offseason mode, received {mode or 'missing'}")
    date.fromisoformat(current)
    if mode == "break" and not next_slate:
        raise SystemExit("Confirmed break mode requires next_slate_date")
    if next_slate:
        date.fromisoformat(next_slate)

    payload = {
        "schema_version": "wnba-break-dashboard-v1",
        "mode": mode,
        "current_date": current,
        "next_slate_date": next_slate,
        "days_until_slate": context.get("days_until_slate"),
        "schedule_source": context.get("schedule_source"),
        "maintenance_deploy_safe": True,
        "current_market_data_allowed": False,
        "paid_api_called": False,
        "stale_predictions_actionable": False,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    script = SCRIPT_TEMPLATE.replace("__PAYLOAD__", raw)
    html = html_path.read_text(encoding="utf-8")
    html = replace_element(html, "style", STYLE_ID, STYLE)
    html = replace_element(html, "script", SCRIPT_ID, script)
    html_path.write_text(html, encoding="utf-8")

    final = html_path.read_text(encoding="utf-8")
    if final.count(f'id="{STYLE_ID}"') != 1 or final.count(f'id="{SCRIPT_ID}"') != 1:
        raise SystemExit("Break-state dashboard markers are duplicated or missing")
    required = [
        "WNBA_SLATE_CONTEXT",
        '"maintenance_deploy_safe":true',
        '"current_market_data_allowed":false',
        "No prior-slate data is actionable",
        "Results, Game Performance, Remaining Season, and Data Health",
    ]
    missing = [marker for marker in required if marker not in final]
    if missing:
        raise SystemExit(f"Break-state dashboard verification failed: {missing}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", default=str(HTML))
    parser.add_argument("--mode", choices=("break", "offseason"), required=True)
    parser.add_argument("--current-date", required=True)
    parser.add_argument("--next-slate-date", default="")
    parser.add_argument("--days-until-slate", type=int)
    parser.add_argument("--schedule-source", default="")
    args = parser.parse_args()
    payload = install_break_state(
        Path(args.html),
        {
            "mode": args.mode,
            "current_date": args.current_date,
            "next_slate_date": args.next_slate_date or None,
            "days_until_slate": args.days_until_slate,
            "schedule_source": args.schedule_source or None,
        },
    )
    print({"status": "PASS", **payload})


if __name__ == "__main__":
    main()
