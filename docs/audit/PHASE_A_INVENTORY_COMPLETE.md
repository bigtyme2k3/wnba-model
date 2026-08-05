# Phase A — Repository Inventory Complete

Completed: 2026-08-05

## Scope completed

- Audited every tracked repository file.
- Recorded path, size, hash, duplicate relationship, workflow references, and Python references.
- Classified files into production, generated, archive, documentation, review, and duplicate-review groups.
- Published machine-readable CSV and JSON inventories plus a human-readable Markdown report.
- Performed no deletions or destructive moves.

## Inventory totals

- KEEP: 260
- GENERATED: 630
- ARCHIVE: 119
- DOC: 39
- REVIEW: 412
- REVIEW_DUPLICATE: 17
- TOTAL TRACKED FILES: 1,477

## Canonical Phase A artifacts

- `docs/audit/REPOSITORY_FILE_AUDIT.md`
- `docs/audit/repository_file_audit.csv`
- `docs/audit/repository_file_audit.json`
- `docs/audit/PHASE_A_INVENTORY_COMPLETE.md`

## Phase A findings

1. The repository contains a large production core, but also substantial technical debt.
2. The strongest cleanup pool is the 429 files marked `REVIEW` or `REVIEW_DUPLICATE`.
3. Generated data is the largest category and needs an explicit current/history/retention policy before cleanup.
4. Archived files are already isolated and should remain untouched during initial cleanup.
5. Historical ledgers and grading records must not be deleted merely because static reference scanning did not find an active importer.
6. Sprint-, phase-, patch-, repair-, and version-named scripts require ownership review before archive or deletion.

## Safety rules for Phase B

- Do not delete historical ledgers, model-performance records, grading data, or market snapshots without confirming retention requirements.
- Do not delete a file referenced by an active workflow or imported/invoked by a retained production script.
- Prefer archive-before-delete for uncertain scripts.
- Remove exact duplicates first, then orphaned workflows, then superseded scripts, then stale generated outputs.
- Validate the production refresh and dashboard after every cleanup batch.

## Next phase

Phase B will convert the broad audit labels into a reviewed cleanup manifest with four final dispositions:

- CORE — keep in production
- SUPPORT — keep as a required dependency
- ARCHIVE — preserve outside production paths
- DELETE — confirmed safe to remove

Phase A is complete and locked as the baseline inventory for repository cleanup.
