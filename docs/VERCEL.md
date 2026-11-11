# Vercel and Supabase deployment

Deploy the existing FastAPI application, including its same-origin static UI.
Vercel uses Python 3.12 and the hash-locked runtime dependencies. Docker remains
available for other hosts. Do not put migrations in a request handler, startup
hook, or Vercel build command: preview builds must not migrate production.

## Production environment

Set these only for the Production environment; do not share the production
database credentials with Preview deployments:

- `APP_ENV=prod`
- `SECRET_KEY`: a privately generated random value of at least 32 characters
- `DATABASE_URL`: Supabase session pooler on port 5432, with the
  `postgresql+psycopg` driver and `?sslmode=require`; encode the password
- `ALLOWED_ORIGINS`: JSON array containing the exact production HTTPS origin
- `ALLOWED_HOSTS`: JSON array containing the exact production hostname
- `DB_POOL_SIZE=1`
- `DB_MAX_OVERFLOW=0`
- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`

Optional Anthropic and sentence-transformers dependencies are not required.
Core matching uses the existing TF-IDF fallback. PDF uploads are capped at
4 MiB to leave space below Vercel's total request limit for multipart fields.
Rate limiting is process-local; it is not a global limit across serverless
instances. Monitor usage and add shared limiting before increasing traffic.

## Database provisioning and migrations

Before creating application tables, disable the Supabase Data API if it is not
used by any other application. ResumeFit accesses PostgreSQL through SQLAlchemy;
its users, password hashes, sessions, and resumes must not be exposed through
Supabase's public REST/GraphQL APIs. Keep existing application authentication.

Use a dedicated empty project. For an existing database, take and verify a
backup first. Inject the production variables privately into a trusted migration
environment. Inspect the target host/database and `alembic current` before
running `alembic upgrade head`, then verify `alembic current` again. Prefer a
direct database connection for migrations where IPv6 is available; the session
pooler is the IPv4 alternative. Do not use the transaction pooler because the
migration runner holds a session-level advisory lock.

## Release verification

Deploy only a reviewed source revision with green CI. Confirm dependency bundle
size during the Vercel build; local unit tests do not validate Vercel packaging.
Disable deployment protection for the production portfolio URL if it would
require visitors to sign in to Vercel. Keep preview protection enabled.

Check `/`, `/static/app.js`, `/healthz`, and `/readyz` over HTTPS. Test the
synthetic demo without signing in, then registration, login, CSRF rejection,
analysis, history isolation, and logout with a disposable test account. Check
secure cookies and inspect logs without printing secrets or resume contents.
