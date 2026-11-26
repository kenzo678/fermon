# Fermon — agent guide

Fermon is a thesis project: a responsive web app that ingests, stores and monitors temperature, pressure
and alcohol readings from a microbrewery's fermentation tanks. The data sources come in three stages:
simulated sensors (done), homemade ESP32 sensors (planned), and the brewery's real sensors (later).

This file works with or without extra tooling. With plain Claude Code (or any agent), read it and the
files it points to. With gentle-ai, Engram and OpenSpec add memory and specs on top of it, but they hold
the same facts. The repository is the source of truth.

## Start here (resume on any machine)

1. Read `odd/ESTADO.md`. It is the current project status: what is built, what is pending, and the next
   step. It is written in Spanish.
2. Read the feature document of whatever you resume, under `odd/tasks/`. Every feature has one.
3. If gentle-ai / Engram is installed, run `engram sync --import` from the repository root to load the
   exported memories in `.engram/`. Then search the project `fermon`. Without Engram, skip this step;
   everything that matters is also in `odd/` and `openspec/`.
4. Bring the stack up: `docker compose up -d`. Then run `docker compose run --rm api uv run alembic
   upgrade head`, and create the first admin user (README, "Usuarios y sesiones").

Nothing has to be installed on the host except Docker (and `gh` for pull requests).

## Repository map

| Path | What it is |
| --- | --- |
| `backend/` | FastAPI API + MQTT ingestor (Python 3.12, uv). Hexagonal + screaming architecture: `src/fermon/{fermentation,identity}/{domain,application,infrastructure}`; the domain is pure. |
| `frontend/` | React 19 + TypeScript + Vite, TanStack Query, react-router, ECharts, Tailwind. Organized by feature (`src/features/*`, `src/shared`), container/presentational components. |
| `simulator/` | Separate Python project that publishes realistic sensor readings over MQTT. It is the reference for what a physical sensor must send. |
| `mosquitto/` | MQTT broker config (anonymous, development only). |
| `odd/` | Planning, in Spanish. `ESTADO.md` is the status; `tasks/*.md` holds one document per feature, with decisions, TDD evidence, review outcomes and known debt. |
| `openspec/` | `config.yaml` (stack, rules) and `specs/*/spec.md`: the specification of the behavior that is already built (RFC 2119 + Given/When/Then). |
| `.engram/` | Engram memory export (gentle-ai). Import it with `engram sync --import`. |
| `README.md` | Full user and developer documentation (Spanish): every endpoint, env var and command. |

## Commands (all through Docker Compose)

```sh
docker compose up -d                                       # stack: timescaledb, mosquitto, api, ingestor, frontend
docker compose --profile simulator up -d                   # + simulated sensors
docker compose run --rm api uv run pytest -q               # backend tests (unit + integration)
docker compose run --rm api uv run ruff check . && docker compose run --rm api uv run ruff format --check .
docker compose run --rm api uv run mypy src
docker compose run --rm --no-deps frontend npm test        # frontend unit tests
docker compose run --rm --no-deps frontend npm run lint    # also: typecheck, build
docker compose run --rm e2e                                # Playwright e2e (see README "Pruebas e2e" for setup)
docker compose --profile simulator --profile e2e down      # stop everything
```

Integration tests use the `fermon_test` database, which is created automatically.

## Conventions (follow them)

- **Language.** Code, identifiers, comments, UI copy, commit messages and specs are in English.
  Planning documents (`odd/`) and the README are in Spanish.
- **Workflow (ODD).** Explore first. For substantial work, create `odd/tasks/<feature>.md` with an
  objective, scope, a task checklist, acceptance criteria and a "Progreso" log before writing code.
  Update the log after each task.
- **Strict TDD.** Write a failing test first and observe RED, then GREEN, then REFACTOR. Record the
  evidence in the feature document.
- **Commits.** Use Conventional Commits, with no AI attribution or co-author lines. Make one commit per
  finished, reviewed and corrected task. Tests and docs travel with the behavior. Lockfile or dependency
  changes go in their own `build(...)` commit.
- **Branches and PRs.** Branch from `main` (`feat/...`, `chore/...`, `docs/...`). Push after review.
  Open the PR with `gh`. The human merges (`gh pr merge N --repo kenzo678/fermon --merge
  --delete-branch`).
- **Review (gentle-ai RDD).** When gentle-ai is present, review each commit on its own with
  `gentle-ai review assess --base-ref <previous reviewed commit> --committed-only`. A whole-branch
  review above ~3k changed lines fails with `lens_context_budget_exceeded`. Without gentle-ai, review
  the commit diff yourself before pushing.
- **Secrets.** Never read or commit `.env*` files. Passwords are never passed through argv.

## Contracts worth knowing before touching code

- **MQTT reading.** Topic `{prefix}/tanks/{tank_id}/readings` (prefix `fermon`), QoS 1. JSON payload
  `{"sensor_id", "measurement", "value", "unit", "recorded_at"}`. The measurements and units are
  `temperature`/`celsius` (−20..100), `pressure`/`bar` (0..10) and `alcohol`/`percent_abv` (0..20).
  `recorded_at` is ISO 8601 with a timezone. A tank registers itself on its first reading.
- **HTTP ingestion.** `POST /readings` with an `X-Device-Key` header. Keys are listed in `DEVICE_API_KEYS`.
- **Auth.**
  - Server-side sessions in an HttpOnly cookie (`fermon_session`, 8 h).
  - Roles: `admin`, `brewer`, `viewer`.
  - Every unsafe method needs `X-Requested-With: fermon`.
  - WebSockets close with 4401 when there is no session and 4403 for a bad origin.
- **Migrations.** Alembic, sequential (`0001`–`0009`). The next one is `0010` with `down_revision = "0009"`.
