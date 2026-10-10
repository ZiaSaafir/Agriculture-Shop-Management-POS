# Suppliers and supplier ledger

## Supplier scope

A `Supplier` belongs to one organization and is shared across that
organization's branches. It stores contact/address information, an optional
account reference, notes, active status, and timestamps. Supplier profiles are
deactivated rather than deleted.

Admin, Manager, and Inventory/Store Staff users with membership in the exact
active branch can search, create, and update suppliers. The API limits records
to the branch's organization.

## Ledger

`SupplierLedgerEntry` is the payable history; a mutable supplier balance is
not stored as the source of truth. Entries use a positive Decimal amount with
an explicit type:

- Increases payable: purchase, opening payable, payable adjustment.
- Decreases payable: payment, supplier return, opening advance, advance
  adjustment.

The balance helper sums signed entries for one supplier in one branch. A
negative balance means the shop has an advance/prepayment with the supplier;
the selected business rule permits this.

Each entry records organization, supplier, branch, author, reason, reference,
and timestamp. Supplier name is snapshotted so profile changes do not rewrite
history. Entries are immutable, and the service locks the supplier row while
posting so concurrent ledger changes to that supplier serialize.

Only the internal `post_supplier_ledger_entry()` service can create ledger
entries. There is no public API or admin action to fabricate purchase/payment
history. The purchase receiving workflow calls this service in the same
transaction that records stock movements. Payment, return, and opening-balance
workflows should call it as part of their own atomic business transactions.
Supplier payments are recorded through the purchase/settlement service, which
also creates invoice allocations and this payment ledger entry atomically.
Purchase returns post a `return` debit to this ledger at the time the confirmed
return is recorded; see [purchases.md](purchases.md).

## API

- `GET /api/suppliers/branches/{branch_id}/?search=...`
- `POST /api/suppliers/branches/{branch_id}/`
- `GET /api/suppliers/branches/{branch_id}/{supplier_id}/`
- `PATCH /api/suppliers/branches/{branch_id}/{supplier_id}/`
- `GET /api/suppliers/branches/{branch_id}/{supplier_id}/ledger/`

Append `include_inactive=true` to the list endpoint when an authorized user
needs to locate previously deactivated suppliers.

All endpoints require authentication and Admin, Manager, or Inventory/Store
Staff membership in the specific active branch. Ledger responses are scoped to
that branch.

Purchases, supplier payments, and purchase returns are documented in the
[purchases guide](purchases.md). The React supplier workspace supports
profile search/create/edit/deactivation and read-only branch-ledger review.
Opening-balance import, ledger adjustments, and settlement workflows beyond
the existing supplier-payment API are not part of this workspace.
