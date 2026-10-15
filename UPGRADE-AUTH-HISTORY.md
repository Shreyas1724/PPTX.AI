# Identity and history upgrade

**v3 update:** Read `SECURITY-CREDITS-V3.md` first. It supersedes the older test counts, browser-verification status, session CSRF handling, credit/job implementation, and payment limitations described below.

## What changed

- Redesigned `/signup` and `/login`: layered presentation visual, responsive forms, accessible labels, role cards, show/hide password, and clearer error states.
- Signup collects full name, international mobile number, email (Gmail or another provider), password (10+ characters), and Student / Professional / Faculty / Entrepreneur / Other.
- Signup is pending until **both** the email and mobile OTP are verified. Each channel uses a separate random six-digit code, HMAC-protected storage, a shared 15-minute signup expiry, 60-second resend cooldown, and five failed guesses per channel. Resending invalidates the old code and does not reset the failure counter. Codes and passwords never appear in API responses or logs.
- Login asks only for the registered email and password. Sessions use HttpOnly SameSite=Lax cookies. Production HTTPS requires COOKIE_SECURE=true. Browsers no longer store session tokens in localStorage.
- Google Identity Services button verifies signed tokens on the backend, including audience, issuer, expiration (Google's library), verified email, and a one-time nonce. First-time Google users complete profile/password collection and BOTH OTP checks. Future Google logins use the stored Google subject.
- Existing password accounts do not silently link to a Google identity. They remain available through email/password. Google account linking for those accounts is not exposed in this version.
- `/history` shows task activity for the last 100 days with search, category filters, pagination, date/time, and outcomes. It records project/deck/slide operations, reference uploads, export, assistant requests, generation completion/failure, and successful authentication events.
- History is account-scoped. Records outside the rolling 100-day window are excluded immediately. A maintenance process removes expired records hourly. It does not delete saved presentations, presentation versions, or accounting entries. This is an activity journal, not model training or automatic conversational recall. It begins recording when this upgrade is installed; prior activity cannot be reconstructed.
- Landing-page WebGL is lazy-loaded, supports a static fallback, and respects reduced-motion settings. The creation job polling ID has also been corrected.

## Quick start

1. Back up the existing database and project files.
2. Replace the application source with this package. Preserve your `.env` and database volume, then merge the new settings from `.env.example`.
3. Generate a unique OTP secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Configure SMTP, Twilio, and (optionally) Google as below.
5. Run `docker compose up --build -d`. Open `http://localhost:3000`.

Database changes are additive: profiles, registrations, google_tickets, rate_buckets, and activities are new tables created at backend startup. Existing users/decks/credits remain intact. Legacy accounts without profile records can still log in but display unverified/missing profile details; this update does not falsely mark them verified. There is no automatic migration that knows old users' names or mobile numbers.

## Email delivery

Set SMTP_HOST, SMTP_PORT (587), SMTP_SECURITY (starttls), SMTP_FROM, SMTP_USER, and SMTP_PASSWORD. SSL SMTP uses SMTP_SECURITY=ssl and port 465. Plain unauthenticated SMTP delivery is not supported; STARTTLS or SSL is used. A transactional email provider is suitable. For Gmail SMTP, use an appropriately configured account/app password, not the user's normal signup password. Configure your sending domain and test inbox delivery.

## Mobile delivery

Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM to a permitted SMS sender. Enable destination-country delivery in your provider account and complete any required sender registration. Phone numbers must use international format, e.g. +919876543210. The service calls Twilio's Messages API. API acceptance is not proof of handset delivery; test a real number in each supported country. This package does not configure your provider account or use the ChatGPT connection to send OTPs.

## Continue with Google

Create a Google web OAuth client, configure the consent screen, and add your exact JavaScript origins (e.g. http://localhost:3000 and https://your-domain.example). Set GOOGLE_CLIENT_ID on the backend. This is Google Identity Services' credential callback flow; no Google client secret or redirect URL is required by this implementation. The button loads Google's official script, sends its ID token to the backend, and then creates a normal local session or a pending onboarding ticket. For Google test-mode projects, add test users. Gmail and Google Workspace accounts are supported; every new account still verifies both contact channels.

Official implementation references:
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
- https://developers.google.com/identity/gsi/web/reference/js-reference
- https://www.twilio.com/docs/messaging/api/message-resource

## Production settings

Set COOKIE_SECURE=true, serve the frontend over HTTPS, and set CORS_ORIGINS to the exact public origin. Keep `/api` behind the same origin as the UI so SameSite cookies work. For separate hosting, proxy `/api` through the frontend domain rather than sending cross-site cookies. API secrets remain backend-only. Never add secrets to VITE_* variables.

Rate limits use database-backed atomic buckets. With default Docker networking the proxy address may be shared, so IP limits can apply to multiple users. Configure Uvicorn's FORWARDED_ALLOW_IPS to the exact trusted reverse proxy address/network if per-client IP limits are needed. Do not blindly trust forwarded headers on a publicly reachable backend. Email and phone limits operate independently of IP limits.

`maintenance` starts after backend readiness and runs hourly. If running without Docker, also run `python -m app.activity` as a supervised process. Expired history is filtered on every read even if maintenance is delayed. Backups need their own retention policy if the same 100-day deletion policy must apply to backup copies.

No OTP development bypass is shipped. Missing provider settings return a clear 503 and prevent new registrations. Existing password accounts can still log in. Without GOOGLE_CLIENT_ID the Google option is labeled unavailable. Provider outage errors leave a pending signup session that can be retried with Resend.

## API additions

- GET /api/v1/auth/config
- POST /api/v1/auth/register — {name,email,mobile,password,role,google_ticket?}
- POST /api/v1/auth/register/verify — {challenge_id,channel:email|mobile,code}
- POST /api/v1/auth/register/resend — {challenge_id,channel}
- POST /api/v1/auth/register/complete — {challenge_id}
- POST /api/v1/auth/google/start
- POST /api/v1/auth/google — {ticket,credential}
- GET /api/v1/history?q=&category=&offset=0&limit=30

Existing auth endpoints now set HttpOnly cookies rather than returning browser bearer tokens. API clients may use a cookie jar. Existing bearer sessions are accepted until expiry for compatibility.

## Verification performed

- Frontend TypeScript and production build: passed.
- Backend: eight tests passed, covering real database/API flows for both OTP gates, resend cooldown/invalidation, wrong-code lockout, expiry, missing configuration, cookie auth/logout/login, Google onboarding/nonce/replay, ownership isolation, task activity capture, history pagination/filtering, retention deletion, cross-origin rejection, login rate limits, and PPTX export.
- Email/SMS transports and Google signature verification are mocked in tests; real delivery and real Google OAuth require your accounts/credentials and have not been tested here.
- Browser screenshot testing could not run because the browser download returned invalid archives. The build is checked, but a live visual/browser smoke test remains necessary.
- Full Docker/PostgreSQL deployment was not run in this environment; tests use SQLite. Existing unrelated production limitations (billing, cloud storage, full visual PowerPoint QA, advanced agents) remain as described in README.md.
