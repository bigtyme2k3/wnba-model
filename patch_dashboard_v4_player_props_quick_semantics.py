from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)

    html = DASHBOARD.read_text(encoding="utf-8")

    old_setter = "window.setPropsQuick=q=>{state.quick=state.quick===q?'':q;window.props()}"
    new_setter = "window.setPropsQuick=q=>{state.quick=state.quick===q?'':q;if(state.quick==='edge'||state.quick==='ev'){state.sort='edge';state.dir=-1}else if(state.quick==='hit'){state.sort='hit';state.dir=-1}else{state.sort='score';state.dir=-1}window.props()}"

    old_ev = "(state.quick==='ev'&&(num(r.ev??r.expected_value)??-99)>0)"
    new_ev = "(state.quick==='ev'&&((num(r.ev??r.expected_value)!==null&&(num(r.ev??r.expected_value)??-99)>0)||(num(r.ev??r.expected_value)===null&&(edge(r)??-99)>0)))"

    old_clv = "(state.quick==='clv'&&(num(r.clv??r.closing_line_value)??-99)>0)"
    new_clv = "(state.quick==='clv'&&((num(r.clv??r.closing_line_value)!==null&&(num(r.clv??r.closing_line_value)??-99)>0)||(num(r.clv??r.closing_line_value)===null&&score(r)>=65&&(edge(r)??-99)>0)))"

    replacements = [(old_setter, new_setter), (old_ev, new_ev), (old_clv, new_clv)]
    missing = []
    for old, new in replacements:
        if old in html:
            html = html.replace(old, new)
        elif new not in html:
            missing.append(old[:60])

    if missing:
        raise RuntimeError(f"Player Props quick-filter markers missing: {missing}")

    marker = "window.PLAYER_PROPS_UX={version:'2.0'}"
    if marker in html:
        html = html.replace(marker, "window.PLAYER_PROPS_UX={version:'2.1',quick_filter_semantics:'data-aware'}")

    DASHBOARD.write_text(html, encoding="utf-8")
    print("Player Props quick filters now use real metrics when present and safe proxies otherwise")


if __name__ == "__main__":
    main()
