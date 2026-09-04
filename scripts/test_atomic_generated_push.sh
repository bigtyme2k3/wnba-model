#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
REMOTE="$TMP/origin.git"
WORK="$TMP/work"

git init --bare "$REMOTE" >/dev/null
git init -b main "$WORK" >/dev/null
cd "$WORK"
git config user.name 'V5 Publish Scope Test'
git config user.email 'test@example.com'
git remote add origin "$REMOTE"
mkdir -p scripts config data/dashboard
cp "$ROOT/scripts/atomic_generated_push.sh" scripts/atomic_generated_push.sh
chmod +x scripts/atomic_generated_push.sh
cat > config/v5_artifact_ownership.json <<'JSON'
{
  "schema_version": 1,
  "mode": "maintenance",
  "artifacts": [
    {
      "domain": "current_slate",
      "artifact": "data/dashboard/protected.json",
      "writer_workflow": ".github/workflows/wnba_daily_canonical_build.yml"
    },
    {
      "domain": "dashboard_freshness",
      "artifact": "data/dashboard/freshness.json",
      "writer_workflow": ".github/workflows/wnba_daily_slate_rollover.yml"
    }
  ]
}
JSON
printf 'old-protected\n' > data/dashboard/protected.json
printf 'old-freshness\n' > data/dashboard/freshness.json
printf 'old-derived\n' > data/dashboard/derived.json
git add .
git commit -m 'fixture baseline' >/dev/null
git push -u origin main >/dev/null

printf 'new-protected\n' > data/dashboard/protected.json
printf 'new-freshness\n' > data/dashboard/freshness.json
printf 'new-derived\n' > data/dashboard/derived.json

export GITHUB_REPOSITORY='bigtyme2k3/wnba-model'
export GITHUB_WORKFLOW='WNBA Daily Slate Rollover'
export GITHUB_WORKFLOW_REF='bigtyme2k3/wnba-model/.github/workflows/wnba_daily_slate_rollover.yml@refs/heads/main'

bash scripts/atomic_generated_push.sh 'scope guard integration test' data/dashboard

protected=$(git --git-dir="$REMOTE" show main:data/dashboard/protected.json)
freshness=$(git --git-dir="$REMOTE" show main:data/dashboard/freshness.json)
derived=$(git --git-dir="$REMOTE" show main:data/dashboard/derived.json)

[ "$protected" = 'old-protected' ] || {
  echo "Foreign-owned protected artifact was published: $protected" >&2
  exit 1
}
[ "$freshness" = 'new-freshness' ] || {
  echo "Owner-authorized protected artifact did not publish: $freshness" >&2
  exit 1
}
[ "$derived" = 'new-derived' ] || {
  echo "Changed derived artifact did not publish: $derived" >&2
  exit 1
}

changed=$(git --git-dir="$REMOTE" diff-tree --no-commit-id --name-only -r main)
if grep -Fxq 'data/dashboard/protected.json' <<< "$changed"; then
  echo 'Foreign-owned protected artifact appeared in publish commit' >&2
  exit 1
fi
if ! grep -Fxq 'data/dashboard/freshness.json' <<< "$changed"; then
  echo 'Owner-authorized protected artifact missing from publish commit' >&2
  exit 1
fi
if ! grep -Fxq 'data/dashboard/derived.json' <<< "$changed"; then
  echo 'Derived artifact missing from publish commit' >&2
  exit 1
fi

echo "{'status':'PASS','scope':'atomic_generated_push','foreign_protected_skipped':true,'owner_protected_published':true,'derived_published':true}"
