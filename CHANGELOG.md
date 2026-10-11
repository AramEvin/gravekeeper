# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-10-11

### Fixed
- A single dashboard visit was counted more than once, because sub-requests such as `/api/dashboards/uid/<uid>/public-dashboards` matched the view query. Only the dashboard request itself is counted now.

### Added
- Community files, CI with linting, release workflow, docs and screenshots.

## 0.1.0 - 2026-10-11 (not tagged)

### Added
- Read-only scan of Grafana dashboards and datasources.
- Causes of death: C01 abandoned (views from Loki), C02 stale, C03 orphaned datasource, C04 broken datasource, C07 legacy Angular panels, C08 duplicates, C09 ownerless, C10 empty shell.
- Health score and status bands (Healthy, At Risk, Terminal, Deceased).
- Estate Health Report and Death Certificate DOCX templates.
- Docker demo stack (Grafana 12, Prometheus, Loki, Alloy) with seeded zombie dashboards.
- Verified against Grafana 12.1.1 and Loki 3.5.3.

[Unreleased]: https://github.com/AramEvin/gravekeeper/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/AramEvin/gravekeeper/releases/tag/v0.1.1
