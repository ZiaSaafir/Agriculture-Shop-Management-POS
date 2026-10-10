# Architecture

## Current foundation

The project is a modular monolith: a Django/DRF backend and a React frontend.
PostgreSQL is the only configured database. Business features will be grouped by
domain as they are introduced; this setup deliberately does not create empty
business apps or SaaS infrastructure.

The database foundation now has organizations, branches, and user role
memberships scoped to a branch. Branch-sensitive transactions and inventory
will be associated with a branch. All future tenant-owned queries must scope
records to the active organization/branch rather than relying on frontend
filtering.

## Local request flow

The React development server runs at `127.0.0.1:5173` and proxies `/api` to
Django at `127.0.0.1:8000`. This keeps browser API requests same-origin and
avoids a CORS dependency in local development. Django's CSRF middleware remains
enabled, and its trusted origins are environment-configured for future
cookie-authenticated writes.

## Authentication decision

A custom `apps.accounts.User` model extends Django's `AbstractUser` and is
configured as `AUTH_USER_MODEL`. It is included in the initial migration.
Branch membership associates a user, branch, and configured Django role group.
Session/cookie authentication uses Django sessions and CSRF protection.
Authentication and role checks are documented in [authentication.md](authentication.md).
