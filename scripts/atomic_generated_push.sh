#!/usr/bin/env bash
set -euo pipefail

MESSAGE=${1:?commit message required}
shift
FILES=("$@")

# Only the canonical dashboard builder may publish docs/index.html. Other
# workflows can continue publishing their generated JSON/CSV outputs without
# overwriting the live dashboard. Local/manual callers may opt in explicitly.
CANONICAL_DASHBOARD_WORKFLOW="WNBA V4 Player Props Polish"
ALLOW_DASHBOARD_WRITE=${ALLOW_DASHBOARD_WRITE:-0}
CURRENT_WORKFLOW=${GITHUB_WORKFLOW:-local}
FILTERED_FILES=()
for supplied in "${FILES[@]}"; do
  if [ "$supplied" = "docs/index.html" ] \
     && [ "$ALLOW_DASHBOARD_WRITE" != "1" ] \
     && [ "$CURRENT_WORKFLOW" != "$CANONICAL_DASHBOARD_WORKFLOW" ]; then
    echo "Skipping protected dashboard output from non-canonical workflow: $CURRENT_WORKFLOW"
    continue
  fi
  FILTERED_FILES+=("$supplied")
done
FILES=("${FILTERED_FILES[@]}")

# Persistent generated histories used by downstream grading and CLV. Add them
# automatically when present so callers cannot accidentally drop state.
PERSISTENT_OUTPUTS=(
  data/history/wnba_alt_market_snapshots.jsonl
)

# A manual canonical dashboard run may advance the active slate before the
# scheduled Version 4 Status workflow has published its dependent model files.
# Mission Control performs a bounded self-heal in that case. Persist those
# refreshed outputs with the dashboard so the next run does not fall back to
# stale projection state.
if [ "$CURRENT_WORKFLOW" = "$CANONICAL_DASHBOARD_WORKFLOW" ]; then
  PERSISTENT_OUTPUTS+=(
    data/dashboard/wnba_minutes_projection_v2.json
    data/dashboard/wnba_points_projection_v2.json
    data/dashboard/wnba_rebounds_assists_projection_v2.json
    data/dashboard/wnba_ancillary_projection_v2.json
    data/dashboard/wnba_unified_player_simulation_v2.json
    data/dashboard/wnba_cross_market_top_plays.json
    data/dashboard/wnba_model_explainability.json
    data/dashboard/wnba_mission_control_acceptance.json
  )
fi

for persistent in "${PERSISTENT_OUTPUTS[@]}"; do
  if [ -e "$persistent" ]; then
    found=false
    for supplied in "${FILES[@]}"; do
      if [ "$supplied" = "$persistent" ]; then found=true; break; fi
    done
    if [ "$found" = false ]; then FILES+=("$persistent"); fi
  fi
done

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No generated paths supplied after publish guard filtering"
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Resolve optional globs before resetting the repository. Several pipelines pass
# dated output patterns that legitimately have no match on quiet/no-game runs.
# Git rejects unmatched pathspecs, so only concrete files are carried forward.
EXPANDED_FILES=()
for path in "${FILES[@]}"; do
  if compgen -G "$path" > /dev/null; then
    while IFS= read -r file; do
      [ -f "$file" ] || continue
      EXPANDED_FILES+=("$file")
      mkdir -p "$TMP/$(dirname "$file")"
      cp -p "$file" "$TMP/$file"
    done < <(compgen -G "$path")
  else
    echo "Optional generated path had no matches: $path"
  fi
done

if [ ${#EXPANDED_FILES[@]} -eq 0 ]; then
  echo "No generated files were produced; nothing to publish"
  exit 0
fi

# De-duplicate concrete paths while preserving order.
UNIQUE_FILES=()
declare -A SEEN=()
for file in "${EXPANDED_FILES[@]}"; do
  if [ -z "${SEEN[$file]+x}" ]; then
    UNIQUE_FILES+=("$file")
    SEEN[$file]=1
  fi
done

for attempt in 1 2 3 4; do
  echo "Atomic push attempt $attempt"
  git rebase --abort 2>/dev/null || true
  git fetch origin main
  git reset --hard origin/main

  cp -a "$TMP/." .

  git add -- "${UNIQUE_FILES[@]}"
  if git diff --cached --quiet; then
    echo "No generated changes after syncing main"
    exit 0
  fi

  git commit -m "$MESSAGE"
  if git push origin HEAD:main; then
    echo "Generated outputs pushed successfully"
    exit 0
  fi

  echo "Remote changed during push; retrying from latest main"
  sleep $((attempt * 2))
done

echo "Unable to push generated outputs after 4 attempts" >&2
exit 1
