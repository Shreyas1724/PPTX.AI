# Project error audit

This audit covers the executable application source, dependencies, automated tests,
container builds, and local browser/API/worker integration. Archived source ZIPs
and historical screenshots/reports describe previous versions.

## Repairs

- Mobile control now submits supported commands, tracks the current host slide,
  updates the slide count, stops reconnecting after termination, and closes revoked
  or ended sockets. nginx and Vite forward WebSocket upgrades.
- Late presentation and project responses cannot replace another open document.
  Failed workspace-list requests preserve the authenticated session. Slide editing
  rejects excess body points instead of silently discarding text.
- Phone validation works with current browser regular-expression rules. Google
  callbacks respect page lifecycle; form limits match the API.
- Project input and section structures are validated before storage. Revision
  checks and queue/handoff claims protect concurrent requests. Restored analysis
  snapshots preserve project titles, and credit totals include project analysis.
- Pairing invitations are claimed atomically. Concurrent presentation edits return
  a conflict instead of corrupting version history. Activity-journal failures cannot
  mask an already-committed successful request.
- Project and presentation deletion respects dependent records and active sessions.
  Foreign-key enforcement is included in regression validation.
- Signed malformed payment events return validation errors. Malformed AI provider
  payloads use the existing bounded validation retry policy.
- Document parsing works independently of the process working directory. Orphaned
  generation jobs refund reservations exactly once.
- Presentation planning recognizes comparison and reference titles. Quality checks
  inspect inherited fonts and independent rendering failures. Sources remain in
  notes, and process/chart/KPI text avoids the reproduced readability defects.
- The test HTTP adapter is pinned to the supported version; CI treats Python
  warnings as errors. The preview command serves the production build.

## Automated results

- 80 backend tests passed with warnings treated as errors and SQLite foreign keys enabled.
- Strict TypeScript and Vite production builds passed locally and inside Docker.
- Backend dependency audit: 54 pinned packages, no known vulnerabilities.
- Frontend dependency audit: no known vulnerabilities.
- nginx syntax, Compose configuration, installed Python dependency consistency, and Git whitespace checks passed.
- Browser regressions passed: real mobile pairing, repeated commands, manual host synchronization, dynamic slide counts, session termination, content preservation, stale-response protection, and fixture cleanup.
- Desktop (1440 px) and mobile (390 px) landing/wheel checks passed without overflow or unhandled browser errors.
- The isolated nginx/PostgreSQL stack passed document extraction, durable worker generation, assistant editing, credit settlement, editable PPTX reopening, expected missing-provider behavior, and foreign-key cleanup.
- Three-theme presentation fixtures exported with zero critical findings and zero readability warnings.

## Repeatable checks

```sh
cd backend
python -m pip install -r requirements-lock.txt
python -m pip check
python -m pytest -q -W error

cd ../frontend
npm ci
npm run build
npm audit
npx playwright install chromium
```

The browser regression runner requires an isolated running installation and a
verified test account. Set `PPTX_TEST_URL`, `PPTX_TEST_EMAIL`, and
`PPTX_TEST_PASSWORD`, then run `npm run test:browser` in `frontend`. It creates and
deletes its own presentation/project fixtures. It exercises manual slides, real
mobile pairing, slide synchronization, and delayed/failing API requests; the AI
analysis race check uses intercepted test responses without a live provider.

## Verification boundary

Live LLM, Google identity, email/SMS delivery, Brave research, and Stripe payments
require provider configuration and were not exercised against real accounts.
LibreOffice rendering remains optional. Automated structure/readability checks do
not establish factual accuracy or human visual approval.

The container integration run uses an isolated database and test account. This
workspace's Docker bridge cannot route traffic between containers, so integration
uses a temporary loopback-only host-network override. The application’s default
Compose configuration remains unchanged and validates independently.
