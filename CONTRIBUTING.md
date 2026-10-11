# Contributing to Gravekeeper

Thanks for helping keep Grafana estates clean! All kinds of contributions are welcome: bug reports, new cause-of-death detectors, template designs, docs and translations.

## Quick start for developers

```bash
git clone https://github.com/AramEvin/gravekeeper.git
cd gravekeeper
python3 -m venv .venv && source .venv/bin/activate
make dev          # pip install -e ".[dev]" + pre-commit hooks
make test         # pytest
make lint         # ruff
```

You don't need Docker or Grafana to develop: the tests run against a mock Grafana API (`tests/mock_grafana.py`). To try changes against a real Grafana, use the demo stack:

```bash
make demo-up      # Grafana, Prometheus, Loki, Alloy
make seed         # creates the demo dashboards and prints a token
export GRAFANA_TOKEN=glsa_...
gravekeeper run -c demo/gravekeeper.demo.yaml
make demo-down
```

## Project layout

| Path | What it does |
|---|---|
| `gravekeeper/client.py` | Read-only Grafana API client |
| `gravekeeper/usage.py` | Dashboard view counts from Grafana's request logs in Loki |
| `gravekeeper/scanner.py` | Detectors (C01–C10) and scoring |
| `gravekeeper/render.py` | Fills the DOCX templates |
| `gravekeeper/build_templates.py` | Generates the DOCX templates |
| `demo/` | Docker demo stack and seed script |
| `tests/` | Mock Grafana and end-to-end tests |

## Adding a new cause of death

1. Pick the next free code (see [docs/causes.md](docs/causes.md)) and open an issue with the **New cause of death** template, so the idea can be discussed first.
2. Add the code and description to `CAUSES` in `gravekeeper/scanner.py`, and implement the check inside `scan()`.
3. Add a default weight in `gravekeeper/config.py` and `gravekeeper.example.yaml`.
4. Add a dashboard that triggers it to `demo/seed.py`; the mock Grafana picks it up automatically.
5. Add an assertion in `tests/test_end_to_end.py`, and document it in `docs/causes.md`.

## Ground rules

- **Read-only by default.** Anything that changes Grafana must be opt-in, dry-run first, and archive before it deletes.
- Never count Gravekeeper's own API requests as views.
- Keep dependencies small. Ask in an issue before adding a new one.
- Write tests for new behaviour. CI must be green before merge.

## Commits and pull requests

- Use clear commit messages, ideally [Conventional Commits](https://www.conventionalcommits.org/): `feat: add C05 erroring panels`, `fix: ...`, `docs: ...`.
- One topic per pull request. Fill in the PR template.
- Add a line to `CHANGELOG.md` under **Unreleased**.

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). Please be kind.
