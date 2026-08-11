#!/usr/bin/env bash
set -euo pipefail

MESSAGE=${1:?commit message required}
shift
FILES=("$@")

DASHBOARD_DEPLOY_WORKFLOW="Deploy WNBA Dashboard"
CURRENT_WORKFLOW=${GITHUB_WORKFLOW:-local}
FILTERED_FILES=()
for supplied in "${FILES[@]}"; do
  if [ "$supplied" = "docs/index.html" ] \
     && [ "$CURRENT_WORKFLOW" != "$DASHBOARD_DEPLOY_WORKFLOW" ]; then
    echo "Skipping protected dashboard output from non-deploy workflow: $CURRENT_WORKFLOW"
    continue
  fi
  FILTERED_FILES+=("$supplied")
done
FILES=("${FILTERED_FILES[@]}")

# Publishable generated history only. Do not add docs/ or data/dashboard/ here:
# those paths can retrigger Deploy WNBA Dashboard from inside itself.
PERSISTENT_OUTPUTS=(
  data/history/wnba_alt_market_snapshots.jsonl
)

# A deploy may need to reset to origin/main while publishing history. Preserve
# the already-verified in-run artifact and grading state across that reset, but
# never stage these files implicitly. This avoids self-triggering deploy loops.
WORKSPACE_PRESERVE=()
if [ "$CURRENT_WORKFLOW" = "$DASHBOARD_DEPLOY_WORKFLOW" ]; then
  WORKSPACE_PRESERVE+=(
    docs/index.html
    data/history/wnba_game_predictions.jsonl
    data/warehouse/wnba_game_predictions_ledger.json
    data/dashboard/wnba_game_predictions_ledger.json
    data/warehouse/wnba_game_performance.json
    data/dashboard/wnba_game_performance.json
    data/dashboard/wnba_game_archive_backfill_audit.json
    data/raw/scores_historical.csv
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
PRESERVE_TMP=$(mktemp -d)
trap 'rm -rf "$TMP" "$PRESERVE_TMP"' EXIT

EXPANDED_FILES=()
copy_file() {
  local file=$1
  [ -f "$file" ] || return 0
  EXPANDED_FILES+=("$file")
  mkdir -p "$TMP/$(dirname "$file")"
  cp -p "$file" "$TMP/$file"
}

for path in "${FILES[@]}"; do
  if [ -d "$path" ]; then
    while IFS= read -r -d '' file; do
      copy_file "$file"
    done < <(find "$path" -type f -print0)
  elif [ -f "$path" ]; then
    copy_file "$path"
  elif compgen -G "$path" > /dev/null; then
    while IFS= read -r match; do
      if [ -d "$match" ]; then
        while IFS= read -r -d '' file; do
          copy_file "$file"
        done < <(find "$match" -type f -print0)
      else
        copy_file "$match"
      fi
    done < <(compgen -G "$path")
  else
    echo "Optional generated path had no matches: $path"
  fi
done

for file in "${WORKSPACE_PRESERVE[@]}"; do
  if [ -f "$file" ]; then
    mkdir -p "$PRESERVE_TMP/$(dirname "$file")"
    cp -p "$file" "$PRESERVE_TMP/$file"
  fi
done

if [ ${#EXPANDED_FILES[@]} -eq 0 ]; then
  echo "No generated files were produced; nothing to publish"
  exit 0
fi

UNIQUE_FILES=()
declare -A SEEN=()
for file in "${EXPANDED_FILES[@]}"; do
  if [ -z "${SEEN[$file]+x}" ]; then
    UNIQUE_FILES+=("$file")
    SEEN[$file]=1
  fi
done

restore_workspace() {
  if [ -d "$PRESERVE_TMP" ]; then cp -a "$PRESERVE_TMP/." .; fi
}

for attempt in 1 2 3 4; do
  echo "Atomic push attempt $attempt"
  git rebase --abort 2>/dev/null || true
  git fetch origin main
  git reset --hard origin/main

  cp -a "$TMP/." .
  restore_workspace

  git add -- "${UNIQUE_FILES[@]}"
  if git diff --cached --quiet; then
    echo "No generated changes after syncing main"
    exit 0
  fi

  git commit -m "$MESSAGE"
  if git push origin HEAD:main; then
    echo "Generated outputs pushed successfully"
    restore_workspace
    exit 0
  fi

  echo "Remote changed during push; retrying from latest main"
  sleep $((attempt * 2))
done

restore_workspace
echo "Unable to push generated outputs after 4 attempts" >&2
exit 1
