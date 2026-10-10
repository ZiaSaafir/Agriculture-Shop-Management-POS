# Inventory foundation

## Source of truth and branch stock

Stock belongs to a `(branch, product)` pair. Product definitions are shared
within an organization; stock is not. Every balance and movement must reference
a branch and a product from the same organization.
Movement quantities use the product's base unit and cannot exceed that unit's
configured decimal precision (up to six places).

`StockMovement` is the append-only explanation of each quantity change.
Movements have a positive decimal quantity plus a direction-bearing type. The
movement ledger is canonical. `StockBalance.on_hand` is a transactionally
maintained projection used for fast reads and row locking; it can be checked
against `ledger_quantity()` and must only be changed via
`record_stock_movement()`.
Movement creation, update, bulk update, and deletion are restricted at the
model/queryset layer so normal ORM usage cannot bypass the service or rewrite
history.

The service locks the balance row, checks the resulting quantity, inserts the
movement, and updates the balance inside one PostgreSQL transaction. Concurrent
changes to the same branch/product serialize on that lock. Decreases that would
result in negative stock are rejected.

Movements preserve the product name and unit symbol used when recorded. They
cannot be changed or deleted; corrections must be represented by a new
compensating movement.

## Movement types

The model defines the future vocabulary: opening stock, purchase, sale,
customer return, supplier return, damage, loss, adjustment in/out, and transfer
in/out. In Stage 7's manual API, only opening stock, damage, loss, and
adjustments are accepted. Purchase, sale, returns, and transfers must later be
created by their own atomic business workflows, not entered through the manual
endpoint.

Every movement requires the responsible user and a reason. Manual stock
operations are restricted to Admin, Manager, or Inventory/Store Staff
membership in the exact branch. Cashiers can read stock for POS checkout but
cannot post manual movements. The current API does not allow a user with
membership in one branch to see or change another branch's stock.

## API

- `GET /api/inventory/branches/{branch_id}/stock/`
- `GET /api/inventory/branches/{branch_id}/movements/`
- `POST /api/inventory/branches/{branch_id}/movements/`

The manual POST body uses `product`, `movement_type`, positive decimal
`quantity`, `reason`, and optional `reference`. An insufficient-stock request
returns HTTP 409 and leaves both the ledger and balance unchanged.
The stock listing includes every product in the branch's organization,
including products with no movement yet (shown with zero stock) and inactive
products whose remaining stock may still need reconciliation. It returns the
unit symbol, allowed quantity precision, selling price, and low-stock
threshold. Cashier accounts may read stock balances for POS but cannot access
the manual movement endpoint.
Deactivating a catalog item does not erase its stock history.

Supplier purchase receiving is implemented in the separate
[purchases module](purchases.md), not through the manual movement endpoint.
Batch/expiry tracking, locations, product package conversion, POS returns,
transfers, and detailed inventory valuation are deferred. The React inventory
screen supports branch stock lookup, low-stock cues, manual movement entry for
authorized staff, and recent movement history.
