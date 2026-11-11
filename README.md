# ResumeFit: Production-Grade Resume & Job Match Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-63%20Passed-brightgreen.svg)](tests/)

ResumeFit transforms resumes from generic self-descriptions into quantified, ATS-optimized assets targeted directly at specific job postings. It blends transformer embeddings, skill coverage taxonomies with alias mapping, defensive parsing, and rule/LLM rewrite engines.

---

## Architecture & Data Flow

```mermaid
flowchart TD
    Client["Web Client / SPA"] -->|"HTTPS / Secure httpOnly Cookie & CSRF"| Proxy["Reverse Proxy / CDN / Cloudflare"]
    Proxy -->|"Port 8000"| App["FastAPI Application"]

    subgraph Security_Layer["Security & Gateway Layer"]
        App --> MW["Security Headers & Request ID Middleware"]
        MW --> RL["SlowAPI Rate Limiter (in-memory, per process)"]
        RL --> Router["APIRouter (/api/v1)"]
    end

    subgraph Core_Services["Core Application Services"]
        Router -->|"POST /analyze"| ThreadPool["ThreadPool Offload (run_in_threadpool)"]
        ThreadPool --> PDFService["PDF Service (Magic bytes, max 10 pages)"]
        ThreadPool --> NLPService["NLP Service (Embeddings + Taxonomy + Aliases)"]
        Router --> HashCache{"SHA256 Content-Hash Check"}
    end

    subgraph Storage_Layer["Persistent Storage"]
        HashCache -->|"Cache Hit"| DB[(PostgreSQL Database)]
        NLPService -->|"Cache Miss / Write"| DB
        App -.-> Alembic["Alembic Migrations"]
    end
```

---

## Key Features

1. **Enterprise Packaging & Architecture**: Clean separation into `core/`, `models/`, `schemas/`, `services/`, and `routers/api_v1/`.
2. **Defensive PDF Extraction**: Hard caps on file size (5MB), page limits (max 10 pages), magic byte checks (`%PDF`), and scanned PDF detection.
3. **Non-Blocking Threadpool Offload**: All CPU-intensive embedding and parsing workloads run via `run_in_threadpool`, keeping the async event loop responsive.
4. **Deterministic Content-Hash Caching**: SHA256 hashing of (resume + job description) prevents redundant inference and database costs.
5. **Hardened Security & Auth**:
   - `httpOnly`, `Secure`, `SameSite=lax` session cookies.
   - Dual-layer CSRF protection for state-changing endpoints.
   - Opaque, database-backed sessions; the signing secret is used for pre-authentication CSRF tokens.
   - Minimum 10-character password enforcement with bcrypt hashing.
   - Strict Content Security Policy (CSP), HSTS, frame-ancestors, and X-Content-Type-Options headers.
6. **Skill Taxonomy & Aliases**: Normalized mapping of 25+ real-world aliases (e.g. `k8s` → `kubernetes`, `postgres` → `postgresql`, `js` → `javascript`).
7. **Production Observability & Probes**: Standard liveness (`/healthz`) and readiness (`/readyz`) health checks inspecting database and ML engine status.
8. **Container Ready**: Multi-stage, non-root `Dockerfile` and Compose setup with PostgreSQL 16 and a one-shot, serialized migration step.

---

## Quickstart

### Option 1: Local Development (Python)

```bash
# 1. Clone repository
git clone https://github.com/your-username/resumefit.git
cd resumefit

# 2. Create virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Generate a random secret with: python -c "import secrets; print(secrets.token_urlsafe(48))"
# Put the generated value in SECRET_KEY in .env before starting the application.

# 5. Run database migrations (the app only creates tables automatically for SQLite)
alembic upgrade head

# 6. Start the server
uvicorn app.main:app --reload --port 8000
```
Open **http://127.0.0.1:8000** in your browser.

---

### Option 2: Docker Compose (PostgreSQL)

```bash
docker compose up --build -d
```
This starts the API on `127.0.0.1:8000`, a PostgreSQL 16 database with a
persistent named volume, and a one-shot Alembic migration service. The database
port is not published to the host. The API starts only after the database is
healthy and the migration service succeeds.

Copy `.env.example` to `.env`, then set `SECRET_KEY` and a URL-safe
`POSTGRES_PASSWORD` (generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
For local HTTP Compose development, set `APP_ENV=dev`; the example localhost
origins and hosts are intended for this mode. Production Compose defaults to
`APP_ENV=prod` and requires explicit HTTPS `ALLOWED_ORIGINS` and exact
`ALLOWED_HOSTS`. Include `127.0.0.1` in `ALLOWED_HOSTS` for the container's
readiness probe. Compose does not provide TLS termination: expose the service
through a separately configured HTTPS reverse proxy, and trust only the proxy's
actual IPs in `FORWARDED_ALLOW_IPS`.

Verify startup with `docker compose ps`, `docker compose logs migrate`, and:

```bash
curl -f http://127.0.0.1:8000/healthz
curl -f http://127.0.0.1:8000/readyz
```

The Docker health check calls `/readyz`, which verifies database and NLP
readiness. `/healthz` is a lightweight process liveness check.

---

## Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `APP_ENV` | `dev` (Uvicorn); `prod` (Compose) | Environment mode: `dev`, `test`, `staging`, or `prod` |
| `SECRET_KEY` | Required | Explicit signing secret (minimum 32 characters) |
| `DATABASE_URL` | `sqlite:///./app.db` (Uvicorn) | Compose configures its PostgreSQL service |
| `POSTGRES_PASSWORD` | Required for Compose | PostgreSQL password |
| `ALLOWED_ORIGINS` | Localhost origins | Explicit HTTPS origins required in production |
| `ALLOWED_HOSTS` | Localhost hosts | Explicit trusted hosts required in production |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Exact proxy IPs trusted for forwarded headers; wildcards rejected |
| `DB_POOL_SIZE` | `5` | PostgreSQL connections retained per app process |
| `DB_MAX_OVERFLOW` | `10` | Temporary connections above the pool size |
| `DB_POOL_PRE_PING` | `true` | Test pooled connections before checkout |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a pooled connection |
| `DB_POOL_RECYCLE` | `1800` | Recycle connections after this many seconds |
| `DB_CONNECT_TIMEOUT` | `10` | PostgreSQL connection establishment timeout |
| `COOKIE_SECURE` | `false` in development | Production cookies are always Secure |
| `MAX_PDF_PAGES` | `10` | Hard cap on uploaded PDF pages |
| `MAX_PDF_BYTES` | `5242880` | Hard cap on file upload size (5MB) |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model identifier |
| `ANTHROPIC_API_KEY` | *None* | Optional Anthropic API key for AI rewrites |

Pool capacity is per process: maximum possible connections are
`(DB_POOL_SIZE + DB_MAX_OVERFLOW) × app workers × app instances`. Size this
against the PostgreSQL server's connection limit. The current limiter uses
in-memory storage per process; do not rely on globally coordinated rate limits
when scaling horizontally.
The runtime image installs only `requirements.lock`. CI installs
`requirements-dev.lock`, which includes runtime and development dependencies
with hashes for Linux/Python 3.11. Refresh these locks from their input files:

```bash
uv pip compile --python-version 3.11 --python-platform linux --generate-hashes \
  --output-file requirements.lock requirements.txt
uv pip compile --python-version 3.11 --python-platform linux --generate-hashes \
  --output-file requirements-dev.lock requirements-dev.txt
```

### Migration and operations

Compose runs `alembic upgrade head` once in the `migrate` service before
starting the API. A migration failure leaves the API stopped; inspect
`docker compose logs migrate` and the database logs before retrying. Back up
PostgreSQL before schema changes. The session-table downgrade removes session
records, and downgrading the initial revision drops user and analysis tables;
do not use `alembic downgrade` as a routine rollback. Prefer restoring a verified
backup or applying a forward migration.

The PostgreSQL image uses a persistent Compose volume. A basic dump can be
written to a local file with:

```bash
docker compose exec -T db pg_dump -U resumefit -d resumefit -Fc > resumefit.dump
```

Keep backups outside the repository, restrict access, and periodically test
restore into a separate disposable database. Compose stores the database
password in the container environment; use a secret manager for production
deployments and protect the Compose `.env` file.

---

## Running the Automated Test Suite

```bash
python -m pytest -v
```

Test coverage includes:
- **`tests/test_nlp.py`**: Semantic similarity scoring, canonical skills, skill alias resolution, bullet detection, and rule rewrites.
- **`tests/test_authorization.py`**: Tenant isolation verification (User B cannot read, list, or delete User A's data).
- **`tests/test_auth.py`**: Password policy checks, CSRF issuance, registration, and login.
- **`tests/test_analyze.py`**: Input character thresholds, PDF page limits, and content-hash caching.
- **`tests/test_health.py`**: `/healthz` liveness and `/readyz` readiness endpoints.

---

## Architecture Decision Records (ADRs)

1. **Embeddings vs TF-IDF**: Uses Sentence Transformers (`all-MiniLM-L6-v2`) for semantic nuance with automatic TF-IDF fallback for minimal-dependency environments.
2. **Cookies vs LocalStorage**: Implemented `httpOnly` secure cookies with double-submit / header CSRF tokens to safeguard against XSS token harvesting.
3. **Event Loop Non-Blocking**: Heavy CPU workloads (PDF text extraction and neural embeddings) are offloaded to `run_in_threadpool` worker threads to preserve FastAPI event loop latency.

---

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
