from __future__ import annotations

from pathlib import Path

HTML = Path("docs/index.html")


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html missing")

    html = HTML.read_text(encoding="utf-8")

    # Remove the base-dashboard Sportsbooks navigation entry while preserving
    # sportsbook data and best-price fields used by Props, Best Bets, ALT
    # Streaks, ALT Performance, Portfolio, and Results.
    replacements = (
        ("['books','Sportsbooks'],", ""),
        (',\'books\':books', ''),
        (',books,', ','),
    )
    for old, new in replacements:
        html = html.replace(old, new)

    # The current base renderer uses an object literal. Remove its books route
    # without deleting the internal books() function or sportsbook payload.
    html = html.replace("{games,props,books,best,portfolio,ai,results,health}",
                        "{games,props,best,portfolio,ai,results,health}")

    HTML.write_text(html, encoding="utf-8")
    print("Standalone Sportsbooks tab removed; sportsbook data retained in contextual views")


if __name__ == "__main__":
    main()
