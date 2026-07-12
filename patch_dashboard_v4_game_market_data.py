from __future__ import annotations

import json
from pathlib import Path

HTML = Path("docs/index.html")
DATA = Path("data/dashboard/wnba_game_market_model.json")
MARKER_START = '<script id="v4-game-market-data">'
MARKER_END = '</script>'


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")
    payload = {}
    try:
        payload = json.load(DATA.open(encoding="utf-8")) if DATA.exists() else {}
    except Exception:
        payload = {}
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    script = (
        f"window.GAME_MARKET={encoded};"
        "DATA.game_market=window.GAME_MARKET;"
        "DATA.projection=Object.assign({},DATA.projection||{},"
        "{games:[...((DATA.projection||{}).games||[]),...((window.GAME_MARKET||{}).games||[])]});"
    )
    block = f"{MARKER_START}{script}{MARKER_END}"
    html = HTML.read_text(encoding="utf-8")
    start = html.find(MARKER_START)
    if start >= 0:
        end = html.find(MARKER_END, start)
        if end >= 0:
            html = html[:start] + block + html[end + len(MARKER_END):]
    else:
        html = html.replace("</body>", block + "</body>")
    HTML.write_text(html, encoding="utf-8")
    print(f"Injected {len(payload.get('games', [])) if isinstance(payload, dict) else 0} game market projections")


if __name__ == "__main__":
    main()
