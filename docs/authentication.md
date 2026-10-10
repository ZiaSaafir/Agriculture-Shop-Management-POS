# Authentication and roles

## Authentication method

The browser uses Django session authentication through same-origin `/api`
requests. In development, Vite proxies `/api` to Django. The session cookie is
HTTP-only and SameSite=Lax; unsafe requests include the CSRF token from Django's
CSRF cookie in the `X-CSRFToken` header. Login is explicitly CSRF-protected, and
logout requires an authenticated session and a valid CSRF token.

The session cookie is marked Secure automatically when `DEBUG=False`, unless
`SESSION_COOKIE_SECURE` overrides it. The CSRF cookie follows the same default
with `CSRF_COOKIE_SECURE`. Production must use HTTPS.

## Endpoints

- `GET /api/auth/csrf/` — initializes the CSRF cookie.
- `POST /api/auth/login/` — accepts JSON `username` and `password`; returns a
  limited user profile and establishes a session. Invalid credentials receive
  a generic error. Anonymous login attempts are throttled to five per minute.
- `POST /api/auth/logout/` — ends the current session; requires authentication
  and CSRF.
- `GET /api/auth/me/` — returns the current limited profile, or 401 when
  anonymous.

The profile contains only the user ID, username, first/last name, and assigned
role names. Passwords, password hashes, email addresses, and session values are
not returned.

## Roles

The initial role names are Django Groups: `Admin`, `Manager`, `Cashier`, and
`Inventory/Store Staff`. A user receives a role for a branch through
`BranchMembership`; assigning a Group directly to a user's global `groups`
does not grant shop API access. Create organizations, branches, and memberships
through Django admin in this order: create the organization, create its branch,
then create a membership selecting a user, that branch, and one of the four
configured roles. The `HasAnyRole` permission checks active branch
membership on every protected request. Django superusers bypass role checks.

Example-only endpoints demonstrate policy and return no business data:

- `GET /api/auth/protected/dashboard/` — Admin or Manager.
- `GET /api/auth/protected/sales/` — Admin, Manager, or Cashier.
- `GET /api/auth/protected/inventory/` — Admin, Manager, or Inventory/Store
  Staff.

These endpoints are authorization examples, not implemented business APIs.
They currently check for a matching role in any active branch because no active
branch selector exists yet. Future views must enforce membership for the
specific branch being accessed, in addition to declaring role requirements.

## Testing limitation

Backend authentication tests are included, but the application database role
does not have permission to create a separate Django test database. No
`CREATEDB` grant has been made. Avoid running the database-backed Django test
suite until an administrator provisions an isolated test database. Stage 4
runtime checks use rollback-only transactions against the configured database.
