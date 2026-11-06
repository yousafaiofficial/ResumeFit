# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Modular architecture with `core`, `models`, `schemas`, `services`, and `routers` packages.
- Strict Pydantic Settings management with environment-specific profiles (`dev`, `test`, `staging`, `prod`).
- Secret key validation at startup preventing startup in production with insecure defaults.
- Key-rotatable JWT authentication with `kid` header support.
- Secure HTTP-only cookie authentication with CSRF token protection.
- Hard input caps on resume, job description, PDF page limits (max 10 pages), and file size (5MB).
- Non-blocking threadpool offloading for CPU-intensive PDF parsing and embedding inference.
- Content hash caching (SHA256) for deduplicating identical resume + job description analyses.
- Paginated history endpoint with limit and cursor controls.
- Production security middleware with strict CSP, HSTS, X-Content-Type-Options, Referrer-Policy, and Permissions-Policy.
- Healthcheck endpoints `/healthz` (liveness) and `/readyz` (readiness for DB and NLP models).
- Database migrations with Alembic and composite indexing on `analyses(user_id, created_at)`.
- Multi-stage Dockerfile and Docker Compose environment with PostgreSQL and Redis.
- Unit and authorization test suites with pytest.

## [0.1.0] - 2026-11-06
### Added
- Initial prototype featuring basic FastAPI backend, SQLite database, simple JWT auth, and frontend UI.
