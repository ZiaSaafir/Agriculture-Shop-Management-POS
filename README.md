# Agriculture POS

A local-first agriculture shop management system, built as a Django REST
Framework API and a React frontend. PostgreSQL is the database from the start.
The modular monolith and organization/branch-ready design leave room for future
cloud and multi-branch operation without implementing SaaS features now.

## Requirements

- Python 3.12 or newer
- Node.js 20.19 or newer
- PostgreSQL 16 or newer

## Local development setup

1. Create and activate a Python virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install backend dependencies:

   ```powershell
   python -m pip install -r backend\requirements.txt
   ```

3. Create a PostgreSQL login and database using PostgreSQL/pgAdmin as an
   administrator. Choose your own password and do not put it in source control.
   For example, run these SQL statements after replacing the password:

   ```sql
   CREATE ROLE agriculture_pos_user LOGIN PASSWORD 'choose-a-local-password';
   CREATE DATABASE agriculture_pos OWNER agriculture_pos_user;
   ```

   Do not grant `CREATEDB` to the application role. A separate test database
   has intentionally not been set up yet.

4. Copy the environment template:

   ```powershell
   Copy-Item .env.example .env
   ```

   Edit `.env`: set a unique `SECRET_KEY` and set `DATABASE_URL` to match the
   PostgreSQL role/database you created. Keep `.env` private; it is ignored by
   Git. To generate a secret key, run:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```

5. Run backend checks and apply migrations:

   ```powershell
   python backend\manage.py check
   python backend\manage.py migrate
   ```

   This creates Django's authentication tables and the project's custom user
   table. Do not replace `AUTH_USER_MODEL` after this initial migration.

   Database-backed Django tests are present but are not currently run because
   the project intentionally has no separate test database. Do not grant
   `CREATEDB` to the application role; provision an isolated test database
   explicitly before running `python backend\manage.py test`.

7. Start the Django API in one terminal:

   ```powershell
   python backend\manage.py runserver 127.0.0.1:8000
   ```

8. In another terminal, install frontend dependencies and start Vite:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

   Open <http://127.0.0.1:5173>. The Vite development server proxies `/api`
   requests to Django at `127.0.0.1:8000`. The initial API health endpoint is
   <http://127.0.0.1:8000/api/health/>.

9. Run frontend tests/build from `frontend`:

   ```powershell
   cd frontend
   npm test
   npm run build
   ```

## Configuration and security notes

- `DATABASE_URL` is required; there is no SQLite fallback.
- Django reads `.env` at the project root for local development and reads
  environment variables directly in deployment.
- `DEBUG` defaults to false. Set it explicitly for local development.
- The frontend uses a same-origin `/api` proxy in development. CORS is therefore
  not enabled or needed. Django CSRF middleware remains enabled; trusted origins
  are configurable with `CSRF_TRUSTED_ORIGINS`.
- The custom user model is configured in `apps.accounts.User` and is included
  in the initial migration. Organization/branch foundations, product catalog,
  inventory, customer ledger, and supplier ledger foundations are implemented.

## Project documentation

See [docs/architecture.md](docs/architecture.md),
[docs/development.md](docs/development.md), and
[docs/local-deployment.md](docs/local-deployment.md) for the current foundation
and next steps.

For session authentication, CSRF behavior, and role examples, see
[docs/authentication.md](docs/authentication.md).

For the product catalog and unit model, see
[docs/product-catalog.md](docs/product-catalog.md).

For stock movement rules and inventory endpoints, see
[docs/inventory.md](docs/inventory.md).

For customer profiles and ledger behavior, see
[docs/customer-ledger.md](docs/customer-ledger.md).

For supplier profiles and payable-ledger behavior, see
[docs/supplier-ledger.md](docs/supplier-ledger.md).

For purchase invoices, receiving, and the resulting stock/payable entries, see
[docs/purchases.md](docs/purchases.md).

For supplier payment allocation and invoice balances, see
[docs/supplier-payments.md](docs/supplier-payments.md).

For supplier purchase returns and credit-note handling, see
[docs/purchase-returns.md](docs/purchase-returns.md).

For POS sale carts, checkout, and customer balance behavior, see
[docs/sales.md](docs/sales.md).

For the branch operations dashboard metrics and limitations, see
[docs/dashboard.md](docs/dashboard.md).

For date-filtered operational reports and available/unsupported measures, see
[docs/reports.md](docs/reports.md).

For Google Drive setup, manual USB downloads, Task Scheduler configuration, and
restore safety, see [docs/backups.md](docs/backups.md).

For the PKR demo catalog entries and the estimates' market references, see
[docs/pakistan-demo-catalog.md](docs/pakistan-demo-catalog.md).

The authenticated React application includes role-aware POS checkout, product
catalog, inventory, customer/supplier workspaces, purchasing, supplier
payments/returns, sales history/returns, operational reports, and dashboard
workflows. Organization/branch administration, complete accounting and cash
management, and production deployment hardening are still needed before it
can be considered a complete shop-management system.
