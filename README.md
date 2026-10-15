# PPTX.AI — Studio v3

An AI presentation workspace with a cinematic React interface, FastAPI services, verified registration, a transaction-safe credit wallet, durable background jobs, versioned editing, and real PPTX export.

See **PRESENTATION-QUALITY-UPGRADE.md** for the newly integrated SlideSpec/native-layout engine, quality checks, editable chart support, benchmark fixtures, remaining limitations, and optional LibreOffice worker verification.

## Start locally

1. Copy `.env.example` to `.env` and choose a strong PostgreSQL password.
2. Configure email/SMS verification for new signup. Google sign-in and paid credit purchases are optional integrations.
3. Add your LLM_API_KEY and model settings for AI generation and advanced editing. Without a key, the product explicitly identifies itself as Outline studio; basic outline generation and deterministic edit commands still work.
4. Run `docker compose up --build -d`.
5. Open `http://localhost:3000`. Development API docs: `http://localhost:3000/api/docs`.

Read **SECURITY-CREDITS-V3.md** before upgrading an existing installation. It covers credit invariants, queue recovery, payment setup, production settings, verification, and remaining limitations. Signup and Google configuration are also described in **UPGRADE-AUTH-HISTORY.md**, with v3 changes taking precedence.

## Product flow

Sign up → verify email and mobile → open your workspace → define a presentation → review the brief and credit cost → generate → edit manually or through the assistant → export PPTX.

The workspace includes search, starter prompts, recent activity, and real credit data. The wallet shows available, reserved, and spent credits, a paginated ledger, and recent operation states. History retains the last 100 days of task activity. From any real presentation viewer, **Mobile Control** creates a two-minute, single-use invitation. Scan it on a phone to open the mobile remote; the desktop viewer remains authoritative and receives typed, acknowledged WebSocket commands. Sessions, devices, replay protection, revocation, and audit events are persisted in additive control tables. Set `FRONTEND_URL` to the public HTTPS origin in production so pairing fragments never leave your site.

## Architecture

- `frontend/src/Workspace.tsx`, `CreateStudio.tsx`, `WalletPage.tsx`: workspace, creation review, and credit wallet.
- `frontend/src/AuthPage.tsx`, `HistoryPage.tsx`: verified registration, Google sign-in, and activity history.
- `frontend/src/EntryPage.tsx`, `appearance.tsx`: interactive eight-theme ring and persistent screen appearance.
- `frontend/src/FluxoraHome.tsx`, `fluxora/`: signed-in Fluxora video hero, feature navigation, and presentation library.
- `backend/app/auth.py`: Google identity verification, dual OTP onboarding, rate limits, secure sessions.
- `backend/app/credits.py`: atomic reservations, idempotency fingerprints, refunds, and wallet aggregation.
- `backend/app/worker.py`: durable database queue, atomic claims, fenced commits, timeouts, and recovery.
- `backend/app/intelligence.py`: validated AI generation/editing, limited retries, and reference retrieval.
- `backend/app/billing.py`: Stripe Checkout, signature verification, and one-time credit fulfillment.
- `backend/app/security.py`: CSRF token derivation, request limits, and production configuration checks.
- `backend/app/documents.py`: isolated parsing of untrusted documents under CPU/memory/time limits.
- `backend/app/manage.py`: trusted-operator credit grants, ledger reconciliation, and legacy job recovery.
- `backend/app/activity.py`: 100-day history cleanup and expired-job refunds.
- `backend/app/control.py`: short-lived QR pairing, scoped controller tokens, WebSocket state/ack protocol, revoke/end APIs, and audit records.
- `backend/app/core.py`: SQLAlchemy entities. New tables are additive to the previous schema.

PostgreSQL holds permanent state. The v3 queue deliberately uses database reservations as its authoritative durable job source. Redis remains available in Compose for future caching; v3 generation correctness does not depend on Redis or RQ. The HTTP API never silently executes paid jobs inline when a queue is unavailable.

## Credits

Default generation cost: 2 credits. Default assistant edit cost: 1 credit. Manual edits and export: included. Both paid costs are environment-configurable and displayed from the server. Signup grants 30 credits after both contacts are verified.

A request reserves credits atomically. Success settles that reservation; failure refunds it once. An idempotency key reused with the same payload returns the original job, while a changed payload is rejected. Concurrent requests cannot spend the same remaining credits twice. Concurrent edits use version checks so a background task cannot overwrite a newer deck version.

Paid top-ups require explicit Stripe configuration and a server-selected price. No balance is increased based on a frontend success page. Only a valid, paid, matching webhook fulfills an order.

## Development and tests

Backend (Python 3.12, matching Docker and CI):

```sh
cd backend
python3.12 -m venv .venv
# Activate .venv using the command appropriate to your shell.
pip install -r requirements-lock.txt
uvicorn app.main:app --reload
# In another terminal, with the same database environment:
python -m app.worker
# Also run hourly retention/recovery maintenance:
python -m app.activity
python -m pytest -q -W error
```

For the browser UI, keep `/api` proxied through the same origin. Set `CORS_ORIGINS` and `FRONTEND_URL` to the Vite origin (development uses port 5173; `npm run preview` uses port 4173). Use an origin reachable from your phone for mobile pairing. Docker uses port 3000.

Frontend:

```sh
cd frontend
npm ci
npm run dev
npm run build
```

Production document parsing is designed for the supplied Linux container. The parser uses Linux resource limits. Native Windows backend users should use Docker or WSL.

## Validation

The latest error audit includes strict TypeScript/production builds, Python tests with warnings treated as errors, dependency audits, and container/browser integration checks. Details, repaired failure cases, repeatable commands, and verification limits are recorded in [docs/ERROR-AUDIT.md](docs/ERROR-AUDIT.md).

## Local demo account

For a real password login without configuring OTP delivery, follow [the isolated local demo setup](docs/LOCAL-DEMO.md). The operator command creates a local SQLite test account and prints a random password once; no shared credentials are built into the application.

## External services and remaining scope

Live LLM, Google login, OTP delivery, and Stripe payments need your credentials and provider-side setup. Tests use mocks for external identity/payment delivery and local outline generation for the browser end-to-end test. The local audit exercises Docker/PostgreSQL with isolated fixtures; live provider integrations and paid transactions still need provider-side verification.

Advanced visual PowerPoint QA, PDF export, image generation, cloud object storage, OCR, team collaboration, subscriptions, automatic payment refund/dispute reconciliation, and web research remain outside this release. The assistant can rewrite, translate, or combine slide edits when an LLM is configured, but it does not execute arbitrary tools, invent chart data, or generate image assets.

## Projects Studio extension

The authenticated navbar now includes **Projects** (`/projects`). Save a project idea, optionally configure analysis constraints, run an actual provider-backed AI analysis, review/accept/reject innovations, edit sections, track development tasks, and create a deck using **Generate Presentation from Project**. Stored project revisions and generated presentation links remain accessible.

Use `PROJECT_ANALYSIS_COST` (default `0`) to configure a price for project analysis. Optional `PROJECT_RESEARCH_BRAVE_API_KEY` enables public search snippets with source links. Without `LLM_API_KEY`, AI analysis is explicitly unavailable; there are no fake successes. Run the existing worker process for queued analysis. The additive migration is `python -m app.migrations.projects_20261015`. See **PROJECTS-STUDIO-IMPLEMENTATION.md** for routes, limitations, and test results.
