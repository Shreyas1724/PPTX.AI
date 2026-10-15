# PPTX.AI — Projects Studio Integration Report

## What's delivered

The new **Projects** workspace is built inside the existing React/Vite + FastAPI product. Existing presentation folders, generated presentations, edit history, authentication, ledger, and rendering code are retained. `ProjectBlueprint` extends the existing `Project` model instead of replacing it.

New capabilities include creating and searching ideas, optional constraints, editing blueprint sections, innovation decisions, roadmap task status, archival and safe deletion, revision snapshots and restoration, optional evidence-linked Brave Search, provider-backed LLM analysis, and a handoff into the **existing** presentation generation and credit queue.

The UI includes a Projects dashboard and an information-dense nine-section workspace with restrained motion, section editing, project history, interactive innovation decisions, roadmap task selectors, research status and presentation format selection. The Projects link is in the authenticated site navigation.

## Files added

- `backend/app/project_models.py` — additive SQLAlchemy tables for blueprint, snapshot, and queued analysis.
- `backend/app/project_routes.py` — real secured JSON APIs.
- `backend/app/project_ai.py` — LLM schema and optional fixed-endpoint Brave Search retrieval.
- `backend/app/project_worker.py` — queued analysis processing, retries through the existing LLM adapter, refund on failure and version-conflict protection.
- `backend/app/migrations/projects_20261015.py` — forward-only, re-runnable migration.
- `frontend/src/ProjectsStudio.tsx` — projects UI and integration with API.
- `frontend/src/projects.css` — accessible responsive styling.
- `backend/tests/test_project_studio.py` — full API integration tests.

Modified: `backend/app/main.py`, `backend/app/worker.py`, `backend/app/documents.py` (increased subprocess virtual-memory limit from 384 MB to 768 MB to fix failure in installed Python 3.13 environment while keeping an OS-enforced bound), `frontend/src/main.tsx`, `.env.example`, `docker-compose.yml`, `README.md`.

## Database schema and migration

New tables: `project_blueprints`, `project_blueprint_versions`, `project_analysis_jobs`. Each blueprint points to an existing `projects.id` owned by a user; existing IDs, decks, documents and credit records are unmodified. Analysis jobs have owner-scoped idempotency keys and background status fields. The app's existing `Base.metadata.create_all()` creates new tables at startup. To apply explicitly before rollout:

```sh
cd backend
python -m app.migrations.projects_20261015
```

**Back up PostgreSQL first.** This does not drop or rename tables. Rollback is by restoring the previous app release while leaving additive tables in place; deletion of project data requires separate retention and backup procedures.

## Configuration and runtime

Copy `.env.example`, then configure `DATABASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` (HTTPS only), and optionally `PROJECT_RESEARCH_BRAVE_API_KEY`. `PROJECT_ANALYSIS_COST=0` by default (free until pricing is approved). Handoff uses the existing `GENERATION_COST` and credit reservation.

Start the existing API and **worker**. The backend must run the original `python -m app.worker`, now also polling the project-analysis table. Docker Compose passes the new provider variables to backend and worker. The UI shows **configuration required** rather than fake AI results if no LLM key is present. Without Brave, research is marked **not configured**. Public search snippets are leads for verification, not proof of originality.

## API routes

All require the existing login/session and CSRF middleware for state changes:

| Method | Endpoint | Function |
|---|---|---|
| GET | `/api/v1/idea-projects/capabilities` | Provider and pricing status |
| GET, POST | `/api/v1/idea-projects` | Paginated list / create |
| GET, PATCH, DELETE | `/api/v1/idea-projects/{pid}` | Read / edit / safe delete |
| PATCH | `/api/v1/idea-projects/{pid}/sections/{section}` | Update one section |
| POST | `/api/v1/idea-projects/{pid}/duplicate` | Duplicate an idea blueprint without duplicating user decks |
| POST | `/api/v1/idea-projects/{pid}/innovations` | Create an innovation |
| POST | `/api/v1/idea-projects/{pid}/innovations/{iid}/decision` | Accept, reject or save |
| PATCH | `/api/v1/idea-projects/{pid}/roadmap/tasks/{tid}` | Persist task status |
| GET | `/api/v1/idea-projects/{pid}/versions` | List revisions |
| POST | `/api/v1/idea-projects/{pid}/versions/restore` | Restore as new revision |
| POST | `/api/v1/idea-projects/{pid}/analysis` | Queue AI analysis / section regeneration |
| GET | `/api/v1/idea-projects/{pid}/analysis/jobs/{jid}` | Poll async result |
| POST | `/api/v1/idea-projects/{pid}/analysis/jobs/{jid}/cancel` | Cancel queued/running analysis and refund if charged |
| POST | `/api/v1/idea-projects/{pid}/handoff` | Create actual presentation in existing queue |

For analysis/handoff POST requests, include an `Idempotency-Key` HTTP header. Revision numbers protect against stale edit submissions. A project with linked presentations cannot be deleted; archive instead.

## Testing and verification

Executed: `PYTHONPATH=backend pytest -q backend/tests` — **27 passed** in the supplied environment. New tests cover authentication and ownership, creation and archival, history restoration, innovation decisions and roadmap persistence, missing-provider behavior, idempotency, refunded AI failures, successful generated report persistence (with a test-only provider stub), and handoff to existing presentation worker. Python modules compile. TypeScript/TSX **syntax parsing** passed using the globally installed TypeScript transpiler. `npm ci --offline` failed due uncached `zustand` package, so **the complete TypeScript typecheck and Vite production build were not run successfully**. Do not call the frontend production build verified.

Live LLM API calls, live Brave Search, Docker/PostgreSQL, full browser QA, and deployment were not exercised; they still need configured credentials and environment-specific verification.

## Important limits / known work

- This is a real saved Projects extension, but its AI planning is currently a single schema-validated provider call with optional bounded lexical document retrieval and web snippets, **not** a separately deployed multi-agent research system or a proof of global originality.
- The AI must be configured. No fake analyses are returned when it is absent. Without an LLM, manual project editing and saving still work.
- Section editing is presently structured JSON editing in the workspace, not a fully bespoke rich-text field editor. Architectures are stored with optional Mermaid text, not an interactive graphics editor.
- Research citations are search links/snippets only; primary-page verification, patent checks, and academic indexes still require additional integrations.
- Long-running AI work requires a running background worker. Existing queue timeouts and refund controls apply to paid actions.
- Full deployment and production validation require actual server credentials and front-end npm build in a networked environment.

## Local commands

```sh
# from project root
cp .env.example .env
# configure secrets appropriately
cd frontend && npm ci && npm run build
cd ../backend && python -m app.migrations.projects_20261015
PYTHONPATH=. python -m pytest -q tests
# alternative full services: from project root run docker compose up --build
```

## Repository integration validation

After integrating the complete frontend source, the TypeScript check and Vite production build passed. The complete backend suite passed with 36 tests on Python 3.12. Docker Compose configuration validates. The frontend dependency audit reports zero vulnerabilities. This supersedes the earlier build limitation above; live provider, browser and full-stack deployment checks remain unverified.
