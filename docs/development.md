# Development

Follow the root [README](../README.md) to prepare the Python environment,
configure PostgreSQL, install dependencies, run tests, and start the backend
and frontend.

Backend checks and tests:

```powershell
python backend\manage.py check
python backend\manage.py makemigrations --check --dry-run
python backend\manage.py migrate
```

Database-backed Django tests exist, including supplier ledger/API coverage,
but are not currently run because the project intentionally has no separate
test database. Do not grant `CREATEDB` to the application role. Once an
administrator provisions an isolated test database, run:

```powershell
python backend\manage.py test
```

Until then, validate database-dependent changes with deliberate rollback-only
smoke checks so temporary records do not persist. No example organization,
branch, or supplier data is seeded.

## First organization setup

Create an administrator after migrations:

```powershell
python backend\manage.py createsuperuser
```

Sign in at `/admin/`, create the real Organization, create its first Branch,
then add BranchMembership records for staff, selecting a configured role. No
client/business name or branch is seeded automatically.

Frontend checks:

```powershell
cd frontend
npm test
npm run build
```

Add business behavior together with tests. The custom user model is already
included in the initial migration; do not switch `AUTH_USER_MODEL` afterward.
