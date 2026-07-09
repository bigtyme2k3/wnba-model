from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MASTER_PATHS = [Path("data/dashboard/wnba_master.json"), Path("data/master/wnba_master.json")]
SPORTSBOOK = Path("data/dashboard/wnba_sportsbook_consensus.json")
PLAYERS = Path("data/raw/wnba_players_live.json")


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.load(path.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def as_float(v: Any, default: float | None = None) -> float | None:
    try:
        if v in (None, ""):
            return default
        return float(v)
    except Exception:
        return default


def projection(player: dict[str, Any], stat: str) -> float | str:
    stat = (stat or "").upper()
    pts = as_float(player.get("roll5_pts"), as_float(player.get("ppg"), 0)) or 0
    reb = as_float(player.get("roll5_reb"), as_float(player.get("reb"), 0)) or 0
    ast = as_float(player.get("roll5_ast"), as_float(player.get("ast"), 0)) or 0
    threes = as_float(player.get("roll5_threes"), 0) or 0
    if stat == "PTS":
        return round(pts, 1)
    if stat == "REB":
        return round(reb, 1)
    if stat == "AST":
        return round(ast, 1)
    if stat == "PRA":
        return round(pts + reb + ast, 1)
    if stat == "PR":
        return round(pts + reb, 1)
    if stat == "PA":
        return round(pts + ast, 1)
    if stat == "RA":
        return round(reb + ast, 1)
    if stat in ("3PM", "FG3M"):
        return round(threes, 1)
    return ""


def reverse_game(game: str) -> str:
    if " @ " not in game:
        return game
    a, h = game.split(" @ ", 1)
    return f"{h} @ {a}"


def build_prop(m: dict[str, Any], players: dict[str, dict[str, Any]], game_override: str | None = None) -> dict[str, Any]:
    prow = players.get(str(m.get("player", "")).lower(), {})
    line = as_float(m.get("consensus_line"))
    proj = projection(prow, m.get("stat", "")) if prow else ""
    edge = round((as_float(proj, 0) or 0) - line, 2) if proj != "" and line is not None else ""
    side = "OVER" if edge != "" and edge > 0.25 else "UNDER" if edge != "" and edge < -0.25 else "PASS"
    confidence = 0
    if edge != "" and line:
        confidence = min(99, round(50 + abs(edge) * 8 + min(int(m.get("book_count", 0) or 0) * 3, 12), 1))
    best_book = m.get("best_over_book") if side == "OVER" else m.get("best_under_book") if side == "UNDER" else (m.get("best_over_book") or m.get("best_under_book"))
    return {
        "player": m.get("player", ""),
        "game": game_override or m.get("game", ""),
        "stat": m.get("stat", ""),
        "line": m.get("consensus_line"),
        "projection": proj,
        "pred": proj,
        "edge": edge,
        "signal": side,
        "side": side,
        "confidence": confidence,
        "book": best_book,
        "best_book": best_book,
        "best_over_book": m.get("best_over_book"),
        "best_over_price": m.get("best_over_price"),
        "best_under_book": m.get("best_under_book"),
        "best_under_price": m.get("best_under_price"),
        "book_count": m.get("book_count", 0),
        "books": m.get("books", []),
        "market_status": m.get("status"),
        "source": "v4_props_guard",
    }


def best_bets(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plays = []
    for p in props:
        if p.get("signal") in ("OVER", "UNDER") and (as_float(p.get("confidence"), 0) or 0) >= 60:
            plays.append({**p, "final_action": "BET" if (as_float(p.get("confidence"), 0) or 0) >= 80 else "LEAN", "final_score": p.get("confidence")})
    return sorted(plays, key=lambda x: as_float(x.get("final_score"), 0) or 0, reverse=True)[:30]


def main() -> None:
    sb = load_json(SPORTSBOOK, {})
    markets = sb.get("markets", []) if isinstance(sb, dict) else []
    players_raw = load_json(PLAYERS, {})
    players = {str((v.get("player") if isinstance(v, dict) else k) or k).lower(): v for k, v in players_raw.items()} if isinstance(players_raw, dict) else {}
    for path in MASTER_PATHS:
        master = load_json(path, {})
        if not isinstance(master, dict) or not master:
            continue
        current = master.get("props", []) if isinstance(master.get("props"), list) else []
        today_games = [g.get("game") for g in master.get("games", []) if g.get("bucket") == "today" and g.get("game")]
        allowed = set(today_games) | {reverse_game(g) for g in today_games}
        matched = [m for m in markets if m.get("game") in allowed]
        source = matched
        stale = False
        if not source:
            source = markets
            stale = True
        if not current and source:
            props = []
            for m in source:
                g = m.get("game", "")
                if g in allowed:
                    override = reverse_game(g) if reverse_game(g) in today_games else g
                else:
                    override = None
                props.append(build_prop(m, players, override))
            master["props"] = props
            master["best_bets"] = best_bets(props)
            master.setdefault("summary", {})["props"] = len(props)
            master.setdefault("summary", {})["best_bets"] = len(master["best_bets"])
            master.setdefault("summary", {})["props_guard_applied"] = True
            master.setdefault("summary", {})["props_guard_stale_fallback"] = stale
            master["props_guard"] = {
                "applied_at_utc": datetime.now(timezone.utc).isoformat(),
                "reason": "master props were empty",
                "matched_today_markets": len(matched),
                "source_markets_used": len(source),
                "stale_fallback_used": stale,
            }
            path.write_text(json.dumps(master, indent=2), encoding="utf-8")
            print(f"V4 props guard populated {len(props)} props in {path}; stale_fallback={stale}")
        else:
            print(f"V4 props guard no-op for {path}; current_props={len(current)} markets={len(markets)}")


if __name__ == "__main__":
    main()
