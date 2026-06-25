"""
setup.py
--------
One-time setup: installs dependencies, validates environment,
creates .env template, and verifies the model files are present.

Run once on a new machine:
    python setup.py
"""

import os, sys, subprocess, json
from pathlib import Path

BASE = Path(__file__).parent
REQUIRED_DIRS  = ["data/raw","data/processed","models","predictions","logs"]
REQUIRED_FILES = ["spread_model.py","totals_model.py","props_model.py",
                  "daily_runner.py","collect_stats.py","collect_odds.py",
                  "merge_data.py","feature_fixes.py","update_dashboard.py",
                  "run_pipeline.sh"]
PACKAGES = ["requests","pandas","numpy","beautifulsoup4","lxml",
            "python-dotenv","tqdm","scikit-learn","scipy","matplotlib"]

print("\n═══ WNBA MODEL — SETUP ═══\n")

# ── Directories ────────────────────────────────────────────────────
print("1. Creating directories...")
for d in REQUIRED_DIRS:
    Path(BASE / d).mkdir(parents=True, exist_ok=True)
    print(f"   ✅ {d}/")

# ── Install packages ───────────────────────────────────────────────
print("\n2. Installing Python packages...")
for pkg in PACKAGES:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "-q"],
        capture_output=True
    )
    status = "✅" if result.returncode == 0 else "❌"
    print(f"   {status} {pkg}")

# ── .env template ──────────────────────────────────────────────────
env_path = BASE / ".env"
if not env_path.exists():
    print("\n3. Creating .env template...")
    env_path.write_text(
        "# The Odds API — get your free key at https://the-odds-api.com\n"
        "ODDS_API_KEY=your_key_here\n"
        "\n"
        "# Optional: email alerts when HIGH confidence plays appear\n"
        "ALERT_EMAIL=\n"
        "SMTP_HOST=\n"
        "SMTP_PORT=587\n"
        "SMTP_USER=\n"
        "SMTP_PASS=\n"
    )
    print(f"   ✅ .env created — add your ODDS_API_KEY")
else:
    from dotenv import load_dotenv
    load_dotenv(env_path)
    key = os.getenv("ODDS_API_KEY","")
    if key and key != "your_key_here":
        print(f"\n3. .env found — ODDS_API_KEY set ✅")
    else:
        print(f"\n3. .env found — ⚠️  ODDS_API_KEY not set yet")

# ── Verify model files ─────────────────────────────────────────────
print("\n4. Checking model files...")
model_dir = BASE / "models"
for m in ["spread_model_v2.pkl","totals_model.pkl","props_models.pkl"]:
    p = model_dir / m
    status = "✅" if p.exists() else "⚠️  (run training scripts first)"
    print(f"   {status} {m}")

# ── Verify scripts ─────────────────────────────────────────────────
print("\n5. Checking pipeline scripts...")
for f in REQUIRED_FILES:
    p = BASE / f
    status = "✅" if p.exists() else "❌ MISSING"
    print(f"   {status} {f}")

# ── Cron suggestion ────────────────────────────────────────────────
print(f"""
═══ SETUP COMPLETE ═══

Next steps:
  1. Add your ODDS_API_KEY to .env
  2. Run the full pipeline once manually:
       ./run_pipeline.sh

  3. Set up daily cron (9 AM):
       crontab -e
       Add: 0 9 * * * cd {BASE} && ./run_pipeline.sh

  4. Models retrain automatically every Monday.

  5. After each run, update the dashboard:
       python update_dashboard.py --dashboard /path/to/wnba_dashboard.jsx

Quick test (no internet needed):
       python daily_runner.py --date 2026-05-12
""")
