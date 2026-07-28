# Sprint 24 Phase 3 Hotfix

The official WNBA injury PDF was discovered successfully, but `pdfplumber.extract_tables()` returned no usable rows for the live report layout.

This hotfix adds coordinate-based word parsing as a fallback while retaining the existing table parser. It normalizes the official report into the current injury schema and keeps ESPN/manual collection as a final fallback.
