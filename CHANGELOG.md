# Changelog

All notable changes to target-data-extractor will be documented in this file.

## [0.1.0] - 2026-06-15

### Added
- 7 platform extractors: HackerOne, Bugcrowd, Intigriti, Immunefi, YesWeHack, Bugrap, HackenProof
- Two-tier fetch strategy: API-first (HackerOne, Bugcrowd) → scrape fallback
- Bypass layer with auto-escalation: curl_cffi → cloudscraper → playwright
- Output formats: JSON, YAML, Markdown, self-contained HTML
- CLI: `tde extract/detect/platforms/list/version`
- Pydantic v2 normalized schema: `BountyProgram`, `ProgramScope`, `ScopeAsset`, `BountyRange`
- 49 tests passing (models, output, platform detection, base, bypass)
- MIT license, README, ETHICS doc, CONTRIBUTING
