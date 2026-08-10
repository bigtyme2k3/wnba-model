# Stale dashboard shell repair

The canonical runtime now rewrites all generated `Slate YYYY-MM-DD` labels to the canonical target during the build and stamps `canonical-build-target-v1:<target>` into `docs/index.html`.

The Pages workflow now has a pre-upload hard gate that refuses deployment when:
- the canonical build marker does not match `TARGET`;
- any stale Slate date remains in the generated HTML;
- the current target Slate label is absent; or
- any Sprint 19 M02-M06 audit is not READY for the same target.

This prevents a previously committed dashboard shell (for example 2026-08-05) from being published as the current slate.
