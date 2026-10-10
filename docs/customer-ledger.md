# Customers and customer ledger

## Customer scope

A `Customer` belongs to one organization and can be looked up from any active
branch in that organization. Customer profiles do not require a phone number,
so walk-in/anonymous POS sales remain possible later without creating fake
customer records. Customer profiles are deactivated rather than deleted.

Authorized Admin, Manager, and Cashier users can list/search, create, and update
customers through a branch-scoped API. The API only exposes profiles in that
branch's organization. Deactivated customers are omitted from the list but
remain readable by ID for historical reference.

## Ledger

`CustomerLedgerEntry` is the financial history; a stored mutable balance is
deliberately not the source of truth. Entries use a positive `DecimalField`
amount and a type that defines direction:

- Debit/increases amount owed: sale, opening debit, debit adjustment.
- Credit/decreases amount owed: payment, return, opening credit, credit
  adjustment.

The balance helper sums signed entries for one customer and one branch. A
negative balance represents an advance/credit held for the customer; the
selected business rule permits this. Credit sales are uncapped for now.

Each entry records organization, customer, branch, author, reason, reference,
and timestamp. Customer name is snapshotted so later profile changes do not
rewrite past ledger descriptions. The entry is immutable; corrections must be
new reversing/adjusting entries.

Entries are created through `post_customer_ledger_entry()` inside a database
transaction. There is no public API or admin action to fabricate ledger
entries in this stage. Future sale, payment, return, and opening-balance
workflows should call this service as part of their own atomic operation.
POS checkout now creates the sale debit and any received payment credit through
this service in the same transaction as stock movements. Walk-in sales have no
customer ledger.

## API

- `GET /api/customers/branches/{branch_id}/?search=...`
- `POST /api/customers/branches/{branch_id}/`
- `GET /api/customers/branches/{branch_id}/{customer_id}/`
- `PATCH /api/customers/branches/{branch_id}/{customer_id}/`
- `GET /api/customers/branches/{branch_id}/{customer_id}/ledger/`

Append `include_inactive=true` to the list endpoint when an authorized user
needs to locate previously deactivated profiles.

Every endpoint requires authentication and an Admin, Manager, or Cashier
membership in that exact active branch. Ledger history and balance are scoped
to the branch, not aggregated across branches the caller may not be permitted
to access.

Sales/POS checkout is documented in [sales.md](sales.md). Separate customer
payments, customer returns, opening balances, ledger adjustments, receipts, and
customer payments and returns are not implemented yet. The React customer
workspace supports profile search/create/edit/deactivation and read-only
branch-ledger review.
