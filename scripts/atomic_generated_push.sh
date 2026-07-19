#!/usr/bin/env bash
set -euo pipefail

MESSAGE=${1:?commit message required}
shift
FILES=("$@")

# Persistent generated histories used by downstream grading and CLV. Add them
# automatically when present so callers cannot accidentally drop state.
for persistent in \
  data/history/wnba_alt_market_snapshots.jsonl
do
  if [ -e "$persistent" ]; then
    found=false
    for supplied in "${FILES[@]}"; do
      if [ "$supplied" = "$persistent" ]; then found=true; break; fi
    done
    if [ "$found" = false ]; then FILES+=("$persistent"); fi
  fi
done

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No generated paths supplied"
  exit 2
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
