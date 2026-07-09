from __future__ import annotations

from pathlib import Path

DOC = Path("docs/index.html")


def main() -> None:
    if not DOC.exists():
        raise SystemExit("docs/index.html missing")
    html = DOC.read_text(encoding="utf-8")

    # The prop header was sticky inside the table and floated over the first row on tablets.
    # Make it a normal header row with a little bottom spacing.
    html = html.replace(
        ".propHead{color:#66748d;text-transform:uppercase;font-size:12px;letter-spacing:.1em;padding:15px 16px;background:#070b13;position:sticky;top:58px;z-index:3}",
        ".propHead{color:#66748d;text-transform:uppercase;font-size:12px;letter-spacing:.1em;padding:15px 16px;background:#070b13;position:relative;z-index:1;border-bottom:1px solid var(--line)}"
    )
    html = html.replace(
        ".propRow{padding:16px;border-top:1px solid #151f31;min-height:94px}",
        ".propRow{padding:16px;border-top:1px solid #151f31;min-height:94px;background:#0b1220}"
    )
    html = html.replace(
        ".propScroll{overflow:auto;border:1px solid var(--line);border-radius:18px;width:100%}",
        ".propScroll{overflow:auto;border:1px solid var(--line);border-radius:18px;width:100%;background:#08101c}"
    )

    DOC.write_text(html, encoding="utf-8")
    print("Dashboard V4 prop header overlap fixed")


if __name__ == "__main__":
    main()
