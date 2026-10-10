# Database

PostgreSQL is required from the initial setup. Set `DATABASE_URL` in the
project-root `.env` for local development, or as a deployment environment
variable. SQLite fallback is intentionally not configured.

The initial migration creates Django's built-in auth tables and the project's
custom user table (`apps.accounts.User`). Stage 5 adds organization, branch, and
branch membership tables. Stage 6 adds the organization-scoped product catalog,
categories, brands, varieties, and units. Stage 7 adds branch/product stock
balances and immutable stock movements. Stage 8 adds organization-scoped
customer profiles and a branch-attributed customer ledger. Stage 9 adds
organization-scoped supplier profiles and a branch-attributed supplier ledger.
Stage 10 adds branch-scoped draft purchases and immutable posted purchase
records that create inventory and supplier-ledger entries atomically. Stage 11
adds immutable supplier payments and allocations to posted purchase invoices.
Stage 12 adds draft and posted supplier purchase returns with atomic stock and
supplier-credit effects. Apply new migrations with
`python backend\manage.py migrate` after configuring `.env`. Stage 13 adds
branch-scoped sales and explicit POS checkout, which atomically reduces stock
and updates a registered customer's ledger. Refunds, payment reversals, and
unit conversions remain deferred.

Create the real business and first branch through Django admin; Stage 5 does
not insert a guessed client name. Each branch belongs to exactly one
organization. Branch names and codes are unique within that organization, not
globally. A branch membership joins one user, one branch, and one configured
role group; a user can have multiple roles or work at multiple branches.

To start, run `python backend\manage.py createsuperuser`, sign into Django
admin, then create the Organization, Branch, and staff BranchMembership
records. No business records are seeded by the migration.

Organization and branch records are deactivated rather than cascaded away.
Foreign-key protections prevent deleting organizations that still have
branches or branches that still have memberships. Future financial/history
records should likewise be preserved through explicit lifecycle rules.
