# Sprint 18 — Production Hardening

## Objective

Move WNBA V4 from a functionally complete production build to a failure-transparent operating system. Sprint 18 prioritizes workflow reliability, explicit source health, and trustworthy dashboard artifacts.

## Phase 1: Multi-source ingestion hardening

- Keep `sportsdataverse/wehoop` as the required primary statistics source.
- Treat `sports-skills` as an optional supplemental source.
- Remove step-level `continue-on-error` masking from the multi-source workflow.
- Capture optional provider installation and fetch failures in structured JSON.
- Fail the workflow when the required primary source is unhealthy.
- Preserve empty supplemental files only with an accompanying reason/status record.

## Phase 2 backlog

1. Harden `.github/workflows/wnba_intelligence_foundation.yml` by separating required engines from advisory enrichment.
2. Replace unexplained empty dashboard JSON with explicit `status`, `reason`, `generated_at_utc`, and upstream dependency fields.
3. Extend V4 QA so expected off-slate emptiness is distinguished from pipeline failure.
4. Add a Sprint 18 smoke test that validates source health, JSON contracts, and critical workflow behavior.

## Acceptance criteria

- No critical ingestion step is hidden by `continue-on-error`.
- Primary-source failure stops the ingestion run.
- Supplemental-source failure does not invalidate healthy primary data.
- Every fallback artifact is accompanied by machine-readable failure context.
- V4 QA workflow-risk count decreases without weakening checks.
