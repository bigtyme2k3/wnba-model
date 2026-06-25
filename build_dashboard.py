"""
build_dashboard.py
------------------
Converts the React JSX dashboard into a standalone static HTML file
that works on any device — no Node.js, no build tools, no server.

The HTML file uses Babel standalone to transpile JSX in the browser,
and loads React/ReactDOM from CDN. Works on Android tablets with Chrome.

Output: docs/index.html  (served by GitHub Pages at your-username.github.io/wnba)
"""

import os, json, re
from datetime import date

DASHBOARD_JSX = "docs/index.jsx"
OUTPUT_HTML   = "docs/index.html"
PREDICTIONS   = f"predictions/predictions_{date.today()}.json"

# Fall back to latest prediction file if today's not found
if not os.path.exists(PREDICTIONS):
    pred_files = sorted([
        f for f in os.listdir("predictions")
        if f.startswith("predictions_") and f.endswith(".json")
    ])
    if pred_files:
        PREDICTIONS = f"predictions/{pred_files[-1]}"

os.makedirs("docs", exist_ok=True)

# Load latest predictions JSON
with open(PREDICTIONS) as f:
    pipeline_data = json.load(f)

# Load JSX source
if os.path.exists(DASHBOARD_JSX):
    with open(DASHBOARD_JSX) as f:
        jsx_content = f.read()
else:
    jsx_content = "// Dashboard JSX not found"

# Inject latest pipeline data into JSX
new_json = json.dumps(pipeline_data, separators=(",", ":"))
jsx_content = re.sub(
    r'(const PIPELINE_DATA\s*=\s*)(\{.*?\});',
    rf'\g<1>{new_json};',
    jsx_content, flags=re.DOTALL
)

# Remove import statements (not needed with CDN React)
jsx_content = re.sub(r'^import.*?;?\s*$', '', jsx_content, flags=re.MULTILINE)
# Remove export default, replace with ReactDOM.render
jsx_content = jsx_content.replace("export default function App()", "function App()")
jsx_content = jsx_content.replace("export default App", "")

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <meta name="theme-color" content="#07080f">
  <title>WNBA Model — {pipeline_data['date']}</title>

  <!-- Preconnect for speed on mobile -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://unpkg.com">

  <!-- React + Babel (CDN, no build step needed) -->
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>

  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ background: #07080f; color: #e2e8f0; height: 100%; }}
    body {{ font-family: 'DM Mono', 'Fira Code', 'Courier New', monospace; }}
    /* Mobile tap targets */
    button {{ min-height: 40px; }}
    /* Scrollbar */
    ::-webkit-scrollbar {{ width: 4px; }}
    ::-webkit-scrollbar-track {{ background: #0d0f1a; }}
    ::-webkit-scrollbar-thumb {{ background: #1e2235; border-radius: 2px; }}
  </style>
</head>
<body>
  <div id="root"></div>

  <script type="text/babel" data-presets="react">
    const {{ useState, useEffect }} = React;

    {jsx_content}

    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(React.createElement(App));
  </script>
</body>
</html>"""

with open(OUTPUT_HTML, "w") as f:
    f.write(HTML)

print(f"✅ Dashboard built → {OUTPUT_HTML}")
print(f"   Data date: {pipeline_data['date']}")
print(f"   Games: {len(pipeline_data['games'])} | Best bets: {len(pipeline_data['best_bets'])}")
print(f"\n   View at: https://YOUR-USERNAME.github.io/wnba-model")
