# Studio v3 — security, credits, intelligence, and operations

## Upgrade an existing installation

1. Back up PostgreSQL and keep your existing `.env` values.
2. Stop the old API and old RQ workers before replacing application files. Do not run old and new worker code against the same database during upgrade.
3. Merge the new settings in `.env.example`; install the new exact dependencies.
4. Start the new stack with `docker compose up --build -d`.
5. The API creates additive `operations` and `purchases` tables. Existing accounts, profiles, decks, history, and credit balances are retained.
6. Pending legacy jobs with a matching v2 debit are marked interrupted and refunded once. No completed historical debit is automatically reversed.
7. Log in again if an older browser session lacks the new CSRF cookie.
8. Check the wallet and run `docker compose exec backend python -m app.manage audit-credits`.

Schema creation remains an additive SQLAlchemy startup migration; this release does not introduce a full Alembic migration history. Subsequent destructive schema changes require explicit migrations. Keep a tested database backup/restore process.

## Credit invariants

- The backend is authoritative for price and balance. There is no public API to set a balance or award arbitrary credits.
- A conditional database UPDATE requires enough available credits and deducts the reservation. The job, operation, debit, and balance update commit together.
- `(user_id, request_key)` is unique. The operation stores a fingerprint containing the deck, operation kind, and payload. Different content cannot reuse a paid request key.
- Every reservation has a unique ledger key. Refunds change only `reserved`/`running` operations to `refunded`, then restore the balance and append a unique refund entry in one transaction.
- Success changes a running operation to settled and writes the new deck/version in one transaction. A version conflict rolls back settlement and refunds the reservation.
- A worker claims an operation through an atomic state transition. Duplicate workers cannot claim the same queued operation.
- Running tasks have a five-minute lease. Expired tasks cannot commit. The worker checks expired jobs each poll; maintenance also refunds expired jobs. Queued tasks older than 15 minutes are refunded.
- Maintenance polls hourly, so a full worker outage can delay a refund until the next maintenance run. Monitoring must alert if both worker and maintenance stop.
- A crashed job is not automatically re-run against the LLM; it is refunded. This avoids silently multiplying provider charges. Users may explicitly retry with a new request.

`available` is the spendable balance; `reserved` is already deducted from it; `spent` covers settled v3 operations. Legacy usage remains visible in the transaction ledger but cannot be retroactively classified into v3 operations.

Operator grants:

```sh
docker compose exec backend python -m app.manage grant-credits --email person@example.com --credits 100 --reference support-ticket-123
```

Run this only through trusted server access. A reference can be used once. Audit discrepancies are reported without silently rewriting balances.

## Stripe credit purchases

Set STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, PUBLIC_APP_URL, CREDIT_PACK_CREDITS, CREDIT_PACK_AMOUNT, and BILLING_CURRENCY. Supported currencies are INR, USD, EUR, and GBP. Amounts use the currency's smallest unit; zero leaves purchases disabled. No arbitrary default business price is imposed.

Register `/api/v1/billing/webhook` for `checkout.session.completed` and `checkout.session.async_payment_succeeded`. Use Stripe test mode first. The backend verifies the raw-body HMAC signature and timestamp, checks `payment_status=paid`, and compares amount, currency, session, and order identifiers. It credits the user once using an atomic order transition. Unpaid events and duplicate delivery do not award credits. A browser redirect never fulfills an order.

Provider setup and real transactions were not exercised here. Refunds, disputes, taxes, invoices, subscriptions, and merchant-account availability require a separate operational policy/integration before commercial launch. This package implements prepaid top-up fulfillment, not a complete accounting system.

Reference: https://docs.stripe.com/api/checkout/sessions

## Security protections

- Password hashing uses scrypt with random salts. Session tokens are random and stored only as hashes in the database.
- Browser sessions use HttpOnly SameSite cookies. A session-bound CSRF token is sent in a custom header for all cookie-authenticated writes. Cross-origin writes are rejected. API bearer compatibility does not bypass ownership checks.
- Registration verifies email and mobile. OTP retry, expiry, rate limiting, and single-use onboarding are retained.
- Login, OTP, generation, assistant edits, uploads, exports, and checkout have server-side limits for their expensive or sensitive actions.
- Paid operation IDs, projects, jobs, history, and presentations remain owner-scoped.
- Body limits cover requests without Content-Length. DOCX expanded sizes are checked; parsing runs in a subprocess capped at 384 MiB address space, eight CPU seconds, and a 12-second wall timeout. Parser subprocess failure is returned as a controlled error.
- Model text is validated against bounded Pydantic schemas. It cannot choose URLs, run code, access other users' documents, or execute arbitrary tools.
- Unexpected API errors return a generic message and request ID. Internal exception types are logged without the user's prompt, password, code, or provider credential.
- Production startup requires secure cookies, explicit HTTPS origins, a strong OTP secret, and PostgreSQL. Frontend Nginx sets CSP, clickjacking, and MIME headers; API adds request IDs and HTTPS HSTS in production.
- Backend and worker containers run as an unprivileged user with dropped capabilities, no privilege escalation, and a read-only root filesystem.
- Browser-based “sign out of all devices” UI is not included, but authenticated POST `/api/v1/auth/logout-all` revokes every session.

Production still needs TLS termination, secret management, infrastructure patching, monitoring, provider abuse controls, and a deployment-specific security review. No application can be declared invulnerable from these tests alone.

## AI workflow

## Mobile presentation control

Mobile control is additive and scoped to an owned presentation. A host creates a session; the server stores only hashes of the invitation and controller token. The invitation is returned once in a URL fragment, expires after `CONTROL_PAIRING_TTL` (default 120 seconds), and is atomically marked used. Regeneration revokes outstanding invitations. Controller commands carry a client request ID and are deduplicated by `(session_id, request_id)`. The host browser remains authoritative: it receives commands over `/api/v1/presentation-control/ws/{session_id}`, applies the bounded transition in the real viewer, and acknowledges the result. Deploy the frontend and API on the same HTTPS origin (WSS in production), set `FRONTEND_URL`, and keep `CORS_ORIGINS` exact. Revoke a device or end a session when a phone is lost.

Request → atomic reservation → durable queue → bounded reference retrieval → generation/editing → schema validation → PowerPoint render check → version-safe save → credit settlement.

Generation and editing use one provider gateway with bounded timeouts, retries for transient provider errors, and up to two schema-correction retries. Usage records retain model, token count, and attempt count. For failed/invalid output, the user is refunded; the provider may still bill the operator for API calls already made.

Reference retrieval ranks small text chunks by term overlap. This is lexical retrieval, not a vector database or web-research claim. Only the current project's uploaded documents are supplied. Retrieved text is clearly separated as untrusted data. Returned source metadata shows which chunks were supplied; it does not certify factual accuracy or claim citation-level grounding for every sentence.

Exact supported local commands (for example `make slide 1 shorter`) use deterministic transformations. Compound instructions go to the model rather than being reduced to a single keyword action. Without an LLM key, unsupported natural-language edits fail clearly and refund their reservation.

The renderer performs structural generation validation. Human fact checking and actual slide-image QA are still needed for high-stakes presentation content.

## Validation record

- 20 automated tests passed, including credit concurrency, simultaneous duplicate requests, overspending prevention, settlement, duplicate refunds, lease expiry, conflict preservation, CSRF, upload limits, signed payment replay, unpaid/mismatched payment rejection, legacy migration/refunds, OTP/Google flows, and history retention/isolation.
- Frontend build and TypeScript passed.
- Browser layouts checked at 1440-pixel desktop and 390-pixel mobile widths. Workspace, wallet, create, and signup had no horizontal overflow or runtime page errors.
- Real local browser/API/worker test: email login → generation → PPTX export → assistant edit. Credit balance: 30 → 28 → 27. No page errors.
- Dependency audit after patching: no known vulnerabilities reported for the audited packages at the time of the check.
- PostgreSQL/Docker deployment, live Google/OTP, live LLM responses, and real Stripe payments were not run here. SQLite concurrency tests do not replace a production PostgreSQL load test.
