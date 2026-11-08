# ResumeFit: Production Operations Runbook

This runbook outlines operational procedures and disaster recovery protocols. All operational drills should be executable in under 10 minutes.

---

## 1. Service Restart (Graceful Shutdown)

To restart the application without dropping in-flight HTTP requests:

### Docker / Containerized
```bash
# Gracefully restarts uvicorn/gunicorn workers
docker-compose restart app
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

---

## 2. Fast Rollback Procedure (< 10 Minutes Target)

If a new deployment causes errors or fails health checks:

### Step 1: Revert Code to Last Stable Release
```bash
# Identify previous release tag or green commit
git log --oneline -n 5

# Check out previous tag or stable commit
git checkout v0.1.0
```

### Step 2: Rollback Database Migrations (If Needed)
```bash
# Check current migration revision
alembic current

# Revert to previous revision
alembic downgrade -1
```

### Step 3: Rebuild and Restart Application
```bash
docker-compose up --build -d app
# Or redeploy via platform CLI:
# flyctl deploy --image <previous-image>
# render rollback
```

### Step 4: Verify Health and Probes
```bash
curl -I https://your-domain.com/healthz
curl -I https://your-domain.com/readyz
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

## 4. Disaster Recovery & Backup Restore Drill

Automated backup and restore verification is packaged in [scripts/backup_restore.py](file:///C:/Users/Samia/Videos/resumefit/scripts/backup_restore.py).

### Manual Restore Procedure (PostgreSQL)
```bash
# 1. Download latest dump from object store / backup provider
aws s3 cp s3://resumefit-backups/latest.dump ./latest.dump

# 2. Restore into target database
pg_restore --clean --if-exists -h $DB_HOST -U $DB_USER -d $DB_NAME ./latest.dump

# 3. Verify record counts
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT count(*) FROM users; SELECT count(*) FROM analyses;"
```

---

## 5. Operations Drills

### 5.1 Sentry Verification Drill
To verify error alerting in Sentry:
1. Trigger a test exception on a non-production test route:
   ```bash
   curl -H "Authorization: Bearer <TOKEN>" https://your-domain.com/api/v1/test-error
   ```
2. Confirm the exception surfaces in your Sentry dashboard within 60 seconds with PII scrubbed.

### 5.2 Uptime Alerting Drill
1. Temporarily pause or stop container:
   ```bash
   docker-compose stop app
   ```
2. Confirm notification is received via your uptime monitor (Better Stack / UptimeRobot) within 3 minutes.
3. Restart container:
   ```bash
   docker-compose start app
   ```

### 5.3 Privacy & PII Log Inspection
Ensure server logs do not contain resume text:
```bash
# Search recent container logs for common resume keywords
docker-compose logs app | grep -E "Summary:|Experience:|GPA|phone"
# Result must be empty.
```
