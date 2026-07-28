# Sprint 22 Phase 2.2 final QA fix

This patch fixes two final integration issues found during the full historical player backfill.

- The player warehouse now discovers normalized `player_profiles_<season>.csv` files.
- The historical backfill audit writes its catalog to the caller-provided output directory instead of the module-level production path.

These changes preserve the existing verification gate: profiles, game logs, and rolling metrics must all be populated before the workflow passes.
