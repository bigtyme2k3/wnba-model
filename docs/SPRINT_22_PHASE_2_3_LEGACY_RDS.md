# Sprint 22 Phase 2.3 — Legacy RDS Reconstruction

Some SportsDataverse releases from 2015–2023 deserialize in native R but contain legacy data-frame/list-column structures that base `write.csv()` rejects as a corrupt data frame.

The compatibility collector now reconstructs a clean rectangular table before export:

- recursively locates the largest data-frame-like object;
- unwraps the underlying column list without trusting a damaged row-count attribute;
- determines the dominant row length;
- retains and repairs columns matching that length;
- recycles scalar columns;
- converts list columns to stable text values;
- fills empty columns with missing values;
- drops irreconcilable columns with an explicit warning.

This affects ingestion compatibility only. It does not change prediction or betting logic.
