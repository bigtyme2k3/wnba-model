from __future__ import annotations

from pathlib import Path

HTML = Path("docs/index.html")

CSS = r'''
<style id="v4-alt-clv-style">
.altClvGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}
.altClvCard{border:1px solid #21314b;border-radius:14px;padding:14px;background:#0a1322}
.altClvValue{font-size:24px;font-weight:950}
.altClvNote{font-size:11px;color:#8090aa;margin-top:10px}
</style>
'''

SCRIPT = r'''
<script id="v4-alt-clv-script">
(function(){
  function pct(v){return v===null||v===undefined?'—':(Number(v)*100).toFixed(1)+'%'}
  function signed(v,d=3){return v===null||v===undefined?'—':`${Number(v)>=0?'+':''}${Number(v).toFixed(d)}`}
  const previous=window.altPerformance;
  window.altPerformance=function(){
    const base=typeof previous==='function'?previous():'';
    const payload=DATA.alt_performance||{};
    const c=payload.clv?.summary||{};
    const block=`<div class="section"><h3 class="mono">Closing-Line Value</h3><div class="small mono">Certified pregame snapshots only. Post-start lines are excluded.</div><div class="altClvGrid"><div class="altClvCard"><div class="small">Certified</div><div class="altClvValue">${c.certified??0}</div></div><div class="altClvCard"><div class="small">Positive CLV</div><div class="altClvValue">${c.positive??0}</div></div><div class="altClvCard"><div class="small">Positive Rate</div><div class="altClvValue">${pct(c.positive_rate)}</div></div><div class="altClvCard"><div class="small">Avg Line CLV</div><div class="altClvValue">${signed(c.average_line_clv)}</div></div><div class="altClvCard"><div class="small">Avg Price CLV</div><div class="altClvValue">${signed(c.average_price_clv,4)}</div></div></div><div class="altClvNote mono">A closing value is shown only when the game start time is verified and the market snapshot was captured before tipoff.</div></div>`;
    return base+block;
  };
})();
</script>
'''


def replace_block(html: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = html.find(start_marker)
    if start < 0:
        return html
    end = html.find(end_marker, start)
    if end < 0:
        return html
    return html[:start] + replacement.strip() + html[end + len(end_marker):]


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    html = HTML.read_text(encoding="utf-8")
    html = replace_block(html, '<style id="v4-alt-clv-style">', '</style>', CSS) if 'id="v4-alt-clv-style"' in html else html.replace("</head>", CSS + "</head>")
    html = replace_block(html, '<script id="v4-alt-clv-script">', '</script>', SCRIPT) if 'id="v4-alt-clv-script"' in html else html.replace("</body>", SCRIPT + "</body>")
    HTML.write_text(html, encoding="utf-8")
    print("Certified ALT CLV metrics added to Performance")


if __name__ == "__main__":
    main()
