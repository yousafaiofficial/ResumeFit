# Google sign-in and password reset

Both integrations are optional. Email/password login and the synthetic demo
continue working without provider credentials. Provider availability is exposed
through `/api/v1/auth/options`; the UI hides unconfigured controls.

## Rollout order

1. Review the source and run tests/CI. Keep provider credentials unset initially.
2. Back up an existing production database and verify the restore process.
3. In a trusted migration environment, confirm the target and run
   `alembic upgrade head`. Expected revision: `auth_recovery_google`.
4. Deploy the reviewed code, then configure production-only provider secrets.
5. Test real Google consent, email delivery, reset expiry, and session revocation.

This additive migration creates `google_identities` and `auth_challenges`; it does
not change existing users, passwords, sessions, or saved analyses. Do not downgrade
after users start using the new flows without planning for identity loss.

## Google OAuth client

Create a Google Cloud OAuth client of type **Web application**, configure the
consent screen, and register these exact authorized redirect URIs as needed:

- Production: `https://resumefit-iota.vercel.app/api/v1/auth/google/callback`
- Local: `http://localhost:8000/api/v1/auth/google/callback`

Set `PUBLIC_BASE_URL` to the corresponding exact origin, plus
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` privately. Use a separate OAuth client
for development if possible. While Google's consent app is in Testing mode,
add the intended testers; publish the consent app when ready for public use.
Do not register arbitrary Vercel preview URLs or share production secrets with
previews.

The backend uses the authorization-code flow with PKCE and expiring, browser-bound
state. State consumption is atomic and provider access tokens are never persisted
or returned to the browser. Identity comes from Google's fixed HTTPS UserInfo
endpoint using the server-exchanged access token, not an unverified browser JWT.
Google's stable `sub` is the identity key, and a verified email is required.
Existing email/password accounts are never automatically linked by matching email;
those users should continue using password login/recovery. Explicit authenticated
account linking is not implemented.

## Password recovery email

Configure `RESEND_API_KEY`, `EMAIL_FROM`, and `PUBLIC_BASE_URL`. A verified sender
domain is needed for public delivery; Resend's testing sender is restricted and
must not be represented as working for all users. Keep API keys server-side.

Reset tokens last 20 minutes, are stored only as SHA-256 hashes, and appear in the
email URL fragment. The frontend immediately removes the fragment from browser
history. Successful reset consumes all reset challenges for that account and
revokes all sessions; the user must sign in again. Reset endpoints require the
existing pre-auth CSRF protection and return a generic message for unknown or
inactive accounts and email-provider failures. No token is returned in API JSON.

Delivery runs as FastAPI background work after the generic response, within the
request lifecycle. There is no durable retry queue; check provider delivery logs
when diagnosing email issues. Logs must not contain passwords, reset links, OAuth
codes, tokens, or provider response bodies. IP rate limits are process-local on
serverless instances; the reset email cooldown also uses database challenges.
Expired challenges are cleaned during Google flow initiation; add scheduled
cleanup if recovery-only traffic grows. Use a shared limiter for high-volume use.
