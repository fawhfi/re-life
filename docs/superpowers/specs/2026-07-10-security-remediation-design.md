# Re-Life Security Remediation Design

**Date:** 2026-07-10

**Status:** Approved design awaiting written-spec review

## Objective

Close the application's broken authentication and authorization boundary while preserving the current `app_users` account system. The remediation also hardens email verification, password reset, file uploads, AI result handling, Supabase access, browser security controls, and production failure behavior.

The rewards and points logic remains a simulation. Its product rules will not change, but every operation must be bound to the authenticated account so one user cannot affect another user.

## Confirmed Product Decisions

- Keep the existing custom `app_users` account system instead of migrating to Supabase Auth.
- Add server-side, database-backed sessions.
- Force all existing users to log in again after deployment. Existing `localStorage` identity data is not trusted or migrated.
- Add security-related Supabase tables and schema changes.
- Remove the passwordless user picker and all public account lookup behavior.
- Do not provide public user profiles or user search.
- Require authentication for image scanning, records, account changes, and reward redemption.
- Require verified email before account creation.
- Return development verification codes only when both `APP_ENV=development` and `ALLOW_DEV_AUTH_CODES=true` are configured.
- Expire sessions after 30 consecutive days without activity. Logout revokes the current session; password reset revokes every session for the account.
- Serve the production frontend and API from the same origin.
- In production, fail closed when Supabase, session storage, verification-code storage, email delivery, or the configured rate limiter is unavailable.
- Preserve the current simulated points and rewards rules.

## Current Vulnerable Paths

### Client-controlled identity

Login and registration write a user name and identifiers to `localStorage`. Subsequent API calls submit those identifiers as `user_id`, `display_name`, or `user_key`, and the backend treats them as the resource owner. An attacker can therefore select another account identifier and read, create, modify, or delete data as that account.

### Passwordless account switching

`GET /api/users` exposes the account list, and the homepage user picker calls `loginAs()` without a password. This provides a direct account takeover path.

### Missing object authorization

Record lookup, creation, clearing, image upload, and deletion do not bind the operation to an authenticated principal. In particular, deletion by record ID does not verify ownership.

### Registration verification bypass

Email-code verification and account creation are separate operations. The registration endpoint itself does not require proof of a successfully verified code and marks any supplied email as verified.

### Unsafe trust boundaries

Upload validation trusts declared MIME types, account profile data accepts arbitrary avatar strings, AI output is not fully schema-validated, and production dependencies can silently fall back to process memory.

## Security Invariants

1. The authenticated principal is derived only from a valid server-issued session cookie.
2. Client-submitted account identifiers never determine ownership or authorization.
3. A user can read or mutate only their own account and records.
4. Account creation is impossible without consuming a valid, unexpired email-verification code.
5. Raw session tokens, passwords, verification codes, reset codes, API keys, and service-role keys are never persisted in logs or returned to production clients.
6. Production authentication fails closed when a required security dependency is unavailable.
7. Uploaded images and AI results are validated at the server boundary before use or persistence.
8. State-changing browser requests are same-origin and protected against CSRF.

## 1. Database-backed Session Architecture

Add an `app_sessions` table containing:

- a generated session ID;
- `user_id`, referencing `app_users` with cascade deletion;
- a unique SHA-256 hash of the random session token;
- `created_at` and `last_seen_at` timestamps;
- nullable `revoked_at`;
- bounded user-agent and request metadata suitable for audit and support without storing secrets.

After a successful login or registration, the server generates a 256-bit token using a cryptographically secure random source. Only its SHA-256 hash is stored. The original token is returned in a `rel_session` cookie with `HttpOnly`, `SameSite=Lax`, and `Path=/`; production adds `Secure`.

For every protected request, the server hashes the cookie token, resolves a non-revoked session and its user, and rejects sessions whose `last_seen_at` is at least 30 days old. Accepted sessions refresh their activity timestamp and cookie lifetime. Activity updates may be coalesced over a short interval to avoid a database write on every asset or API request, but an accepted request near the expiry boundary must refresh the session.

Logout sets `revoked_at` for the current session and clears the cookie. Password reset revokes all sessions belonging to the user. Session comparison uses constant-time primitives where applicable, and raw tokens are never logged.

Add these endpoints:

- `GET /api/auth/me`: return the current normalized user or `401`.
- `POST /api/auth/logout`: revoke the current session and clear the cookie.

Successful login and registration responses also set the session cookie. Production session operations return `503` when Supabase is unavailable; memory sessions are permitted only in explicitly configured development mode.

## 2. Authorization and API Surface

The FastAPI dependency that resolves the current session becomes the single enforcement boundary for protected routes.

### Protected resources

- `/` redirects unauthenticated users to `/login`.
- `/api/scan/ai` requires a valid session.
- all `/api/records` operations and record-image uploads require a valid session.
- `/api/rewards/redeem` requires a valid session while retaining simulated reward rules.
- account read and update operations use `/api/users/me` and act only on the session user.

### Removed account-discovery routes

Remove:

- `GET /api/users`
- `GET /api/users/by-name/{display_name}`
- `GET /api/users/by-email/{email}`
- `GET /api/users/by-id/{identifier}`
- `PATCH /api/users/{identifier}`

Replace required self-service behavior with:

- `GET /api/users/me`
- `PATCH /api/users/me`

### Record ownership

Record APIs no longer accept `user_id`, `display_name`, or `user_key` as authorization inputs. The backend supplies the session user's database ID when creating, listing, clearing, or uploading images for records.

Record deletion filters by both record ID and session user ID. A missing record and a record owned by another user both return `404`, preventing resource-existence disclosure. Storage paths are partitioned by a server-derived account identifier.

### Frontend identity

Remove `showUserPicker()` and `loginAs()`. Remove identity restoration from `RE_LIFE_CURRENT_USER`, `RE_LIFE_CURRENT_USER_ID`, and `RE_LIFE_CURRENT_USER_KEY`. On page startup, the frontend calls `/api/auth/me`; a `401` redirects to `/login`.

`localStorage` remains available only for non-security preferences such as language, theme, and sound.

## 3. Registration, Login, and Password Reset

### Registration

`POST /api/send-verification` creates a six-digit code using a cryptographically secure random source. The database stores only an HMAC digest using a dedicated production secret, together with purpose, normalized email, expiry, attempts, and consumption state. Codes expire after ten minutes. Resending invalidates the previous code.

The frontend's verification submission calls `POST /api/auth/register` with display name, email, password, and code in one operation. The backend validates and consumes the code before creating the user, then creates a session. The standalone `/api/verify-code` endpoint is removed.

A code becomes unusable after five failed attempts. Account creation enforces unique normalized email and display name and a minimum password length of eight characters.

### Login

Unknown users and incorrect passwords return the same `INVALID_CREDENTIALS` result. Authentication rate limits combine request IP with a normalized account key. Successful Argon2 verification rehashes passwords when current Argon2 parameters require an upgrade.

### Password reset

Forgot-password responses do not disclose whether an email is registered. Reset codes use the same expiry, hashing, attempt, resend, and development-mode rules as verification codes. A successful reset updates the Argon2 hash, consumes the code, and revokes all sessions for the account.

### Development codes and dependency failure

`dev_code` is returned only when both `APP_ENV=development` and `ALLOW_DEV_AUTH_CODES=true`. In every other environment, email-delivery failure returns a generic service error and never exposes the code.

Production refuses to start without the required verification-code secret and mail configuration. Authentication endpoints return `503` if their configured distributed rate limiter or persistent code/session store is unavailable.

## 4. File Upload, Avatar, and AI Validation

Create one reusable image-validation boundary for scan images, record images, and avatars:

- enforce the byte limit while reading the request rather than after accepting an unbounded body;
- ignore the claimed MIME type and extension when determining format;
- decode with Pillow and accept only JPEG, PNG, or WebP;
- reject malformed images, decompression bombs, and unreasonable dimensions;
- re-encode accepted images before forwarding or storing them, stripping EXIF and embedded payloads;
- use server-generated names and session-derived storage prefixes.

The `scan-images` bucket becomes private. Application-generated proxy URLs remain time-limited and must not expose the service-role key.

Profile updates no longer accept arbitrary `photoUrl` or data URLs. Emoji avatars are limited to a server-defined allowlist. Image avatars use a protected multipart upload endpoint and the same decode-and-re-encode pipeline. Frontend rendering uses DOM properties such as `textContent` and `src` rather than concatenating untrusted strings into `innerHTML`.

Define Pydantic request and response models for authentication, account updates, records, scans, and rewards. Enforce bounded strings, normalized email, supported language values, fixed enums, and bounded integer/list fields.

AI results are normalized and validated before scoring or persistence. Material, mode, grade, and other categorical values must belong to supported enums; scores must be finite and inside their documented ranges; text and list values have length and count limits. Invalid provider output triggers the existing safe fallback or a controlled error rather than database persistence.

Production custom AI endpoints must use HTTPS. Outbound calls retain strict timeouts, bound response sizes, and expose only generic upstream errors to clients.

## 5. Supabase and Browser Hardening

Enable RLS on `app_users`, `app_sessions`, `auth_codes`, and `scan_records`. Revoke direct data privileges from `anon` and `authenticated`; no browser client receives the service-role key. FastAPI remains the only data-access authority for these custom-account tables.

Make the `scan-images` bucket private and preserve a service-role-only storage policy. Remove the unused `admin_users` and `my_records` Edge Functions and their configuration because they expose a second, inconsistent authentication model that is not used by the product.

Load `.env` before importing modules that read configuration. Production startup validates:

- Supabase URL and service-role key;
- application environment;
- allowed origins and hosts;
- verification-code secret;
- email provider configuration;
- distributed rate-limiter configuration;
- session and upload security settings.

Public configuration responses use an explicit allowlist and never serialize arbitrary environment data.

Add `TrustedHostMiddleware`, an explicit CORS origin list, credential support only for configured local-development origins, and same-origin validation for unsafe methods. Requests with an invalid origin return `403` before state changes occur.

Preserve `X-Content-Type-Options`, HSTS in HTTPS production, Referrer Policy, frame denial, and Permissions Policy. Add a Content Security Policy restricting scripts, styles, images, connections, objects, frames, base URLs, and form destinations. Inline identity-switching handlers are removed; remaining inline handlers and scripts are migrated to registered event listeners so the policy does not depend on unrestricted inline script execution.

## 6. Error Handling and Security Logging

Use consistent status semantics:

- `401` for missing, expired, or revoked authentication;
- `403` for authenticated requests that violate an origin or security policy;
- `404` for absent resources and resources not owned by the current user;
- `422` for structured input-validation failures;
- `429` for rate limits;
- `503` for unavailable mandatory security dependencies.

Client responses remain generic where detail could reveal accounts, records, provider configuration, or internal infrastructure.

Security logs include a generated request ID, event category, route, result, and internal account ID when available. They exclude passwords, codes, reset material, cookies, raw session tokens, API keys, service-role keys, complete request bodies, and full email addresses.

## 7. Test Strategy

Every production change follows a red-green-refactor cycle. The regression test must first demonstrate the unsafe behavior through the real FastAPI or helper boundary and fail for the expected security reason.

Required regression coverage includes:

- protected endpoints reject unauthenticated requests;
- login and verified registration issue a secure session cookie;
- forged account identifiers do not influence ownership;
- users cannot read, modify, clear, or delete another user's records;
- passwordless account listing and switching no longer exist;
- logout, reset, revocation, and 30 days of inactivity invalidate sessions;
- session storage contains only token hashes;
- invalid, expired, reused, and over-attempt verification codes cannot create accounts;
- production never returns development codes or uses memory authentication fallback;
- reset responses do not enumerate accounts and reset revokes all sessions;
- CSRF attempts and invalid origins fail before mutation;
- forged MIME types, oversized images, corrupt files, decompression bombs, and unreasonable dimensions are rejected;
- accepted images are re-encoded and stripped of metadata;
- invalid AI enums, non-finite or out-of-range scores, and oversized output are rejected or safely handled;
- RLS, private storage, removed Edge Functions, security headers, CORS, and startup validation match the design.

Positive controls cover legitimate login, session restoration, self-profile updates, scans, record CRUD, avatar updates, password reset, and simulated reward use.

The existing unrelated weather UI assertion is recorded as a baseline failure and is not changed as part of this security work. Focused security tests and the full suite are both run at each stage; unrelated baseline behavior is reported separately rather than hidden.

## 8. Delivery Phases

### Phase 1: Sessions and authentication

Add the session schema, session service, login cookie, `/api/auth/me`, logout, inactivity expiry, revocation, production fail-closed behavior, and focused tests.

### Phase 2: Account and record authorization

Replace public account endpoints with `/api/users/me`, bind all record operations to the session user, remove the user picker and client-controlled identity, and add cross-account exploit tests.

### Phase 3: Verification and password reset

Make registration consume the verification code, enforce code attempts and production delivery rules, unify credential errors, rehash Argon2 passwords when required, revoke sessions on reset, and add regression tests.

### Phase 4: Upload and AI validation

Add shared image validation and re-encoding, protected avatar upload, private storage, Pydantic request models, validated AI output, outbound endpoint restrictions, and adversarial input tests.

### Phase 5: Platform hardening

Apply RLS and grants, remove unused Edge Functions, correct environment loading, add startup validation, enforce CORS/host/origin rules, strengthen headers and CSP, and complete the security verification matrix.

Each phase must leave the application in a working, testable state. Schema changes are deployed before the code that requires them. Because existing browser identities are deliberately not migrated, deployment naturally forces a safe re-login.

## Success Criteria

The remediation is complete only when:

- the original passwordless and identifier-forging paths no longer reproduce;
- every protected operation derives ownership from a valid database-backed session;
- legitimate users can register, log in, resume a session, manage only their own data, reset a password, and log out;
- all focused security tests pass;
- relevant existing tests preserve their baseline or improve;
- database and storage policies match the backend-only access model;
- production configuration fails closed without leaking secrets or development codes;
- remaining limitations and any unavailable integration validation are explicitly documented.
