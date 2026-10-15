# Local demo login

A trusted operator can create a synthetic account in an isolated local SQLite database without configuring email or SMS delivery. The account uses the ordinary password login and session cookies. No account is created at application startup, and registration still requires real email/mobile verification.

From `backend`, with backend dependencies installed:

```sh
export APP_ENV=development
export DATABASE_URL=sqlite:////tmp/pptx-ui-demo.db
export CORS_ORIGINS=http://localhost:5173
export FRONTEND_URL=http://localhost:5173
python -m app.manage create-demo-user
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The command prints `demo@pptx.test` and a randomly generated password once. Sign in through the frontend using those values. Keep the API and worker processes on the same `DATABASE_URL`; run `python -m app.worker` in another terminal to process generation tasks. Use the actual frontend origin if it differs from port 5173.

The account starts with 30 credits recorded in the credit ledger. Its synthetic contacts are correctly marked as unverified. Repeating the command fails without replacing a password or adding credits. For another account, provide a different reserved `.test` email and synthetic mobile number with `--email` and `--mobile`. `--credits` selects an initial balance between 1 and 100000.

To select a password, use `--password-stdin` with a secret manager or a hidden terminal prompt; passwords are never accepted as command-line arguments or saved to the repository. The supplied password must contain 10–128 characters.

This CLI refuses PostgreSQL and any `APP_ENV` other than `development`, `test`, or `local`. These credentials exist only in the selected local database; pushing or deploying the source does not create a login on a hosted installation. Hosted accounts continue to use verified registration.
