# ResumeFit: Production Operations Runbook

This runbook covers local Compose operations and recovery guidance. Compose is
not a public HTTPS ingress or a managed secret/backup service.

---

## 1. Service Restart (Graceful Shutdown)

To restart the application without dropping in-flight HTTP requests:

### Docker Compose
```bash
# Recreate the application from the current image
docker compose up --build -d app
docker compose ps
docker compose logs --tail=100 app
```

### Systemd / Bare Metal (VPS)
```bash
sudo systemctl reload resumefit
# Or graceful restart:
sudo systemctl restart resumefit
```

Verification:
```bash
curl -f http://127.0.0.1:8000/healthz
curl -f http://127.0.0.1:8000/readyz
```
`/healthz` is a liveness probe. `/readyz` checks database and NLP readiness;
the container health check uses `/readyz`. A running container is not ready if
the database is unavailable or model initialization failed.

Compose exposes the API only on host loopback and does not publish PostgreSQL.
For production, place an HTTPS reverse proxy in front of the API, configure
explicit HTTPS origins and exact trusted hosts, include `127.0.0.1` for the
container health probe, and set `FORWARDED_ALLOW_IPS` to the proxy addresses
that actually connect to Uvicorn. Never trust arbitrary forwarded headers.

---

## 2. Migration and Application Recovery

Compose orders startup as database health, one-shot migration, then API. A
failed migration exits nonzero and prevents the API from starting.

### Inspect failure
```bash
docker compose ps -a
docker compose logs --tail=200 db migrate
```

Correct the configuration or migration issue, take/verify a database backup,
then retry the migration service:

```bash
docker compose run --rm migrate
docker compose up -d app
```

Do not routinely downgrade a deployed database to roll back application code.
The session migration's downgrade deletes session records; the initial
migration's downgrade deletes user and analysis tables. Prefer rolling back the
application image only when it remains compatible with the current schema, or
restore a verified backup to a separate database and follow an explicit
recovery plan. Never run migrations against an existing database as a
verification step.

### Verify
```bash
docker compose ps
curl -f http://127.0.0.1:8000/healthz
curl -f http://127.0.0.1:8000/readyz
```

---

## 3. Authentication Sessions and Secret Rotation

Browser authentication uses opaque, random session values stored only as SHA-256
hashes in the database. Session records expire after `SESSION_EXPIRE_DAYS` and
logout revokes the current record. Deploy the new `user_sessions` table using
`alembic upgrade head` before starting the new application version. Do not edit
the already-applied initial migration.

The signing secret is used only for short-lived pre-authentication CSRF tokens.
Generate it with:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
Configure `SECRET_KEY`, HTTPS `ALLOWED_ORIGINS`, and exact `ALLOWED_HOSTS`
explicitly in production. Changing `SECRET_KEY` invalidates outstanding pre-auth
CSRF tokens but does not invalidate database-backed sessions.

The frontend requests `/api/v1/auth/csrf` before login or registration. It
keeps that token in memory and sends it in `X-CSRF-Token`; the server also
requires the matching HttpOnly pre-auth cookie and an allowed Origin or Referer.
After login, registration, or page reload, it obtains the session CSRF token
from the authentication response or `/api/v1/auth/csrf/session`. Tokens are
never written to browser storage. When deploying behind a proxy, set Uvicorn's
`FORWARDED_ALLOW_IPS` to the trusted proxy IPs only; never use `*`.

---

## 4. PostgreSQL Backup and Restore

Write a custom-format dump outside the repository:
```bash
docker compose exec -T db pg_dump -U resumefit -d resumefit -Fc > resumefit.dump
```

Restrict access to the dump and store it in an approved backup location. Before
restoring, verify the target is disposable or explicitly authorized. Restore
into an empty, separate database rather than overwriting the running volume:
```bash
docker compose exec -T db createdb -U resumefit resumefit_restore_check
docker compose exec -T db pg_restore -U resumefit -d resumefit_restore_check \
  < resumefit.dump
```

Verify the restored schema and representative records, then remove the
disposable restore database only after confirming its exact name and contents.
Do not use `docker compose down -v`; it deletes the persistent database volume.

For production backup retention, encryption, offsite storage, and recovery-time
targets, use a managed backup system or an explicitly designed operational
process. Compose does not provide these controls.
```

---

## 5. Operations Drills

### 5.1 Uptime Alerting Drill
1. Temporarily stop the application container:
   ```bash
   docker compose stop app
   ```
2. Confirm the configured external uptime monitor detects the outage.
3. Restore the application:
   ```bash
   docker compose start app
   ```

### 5.2 Privacy & PII Log Inspection
Check that recent logs do not contain resume text:
```bash
docker compose logs app | grep -E "Summary:|Experience:|GPA|phone"
```