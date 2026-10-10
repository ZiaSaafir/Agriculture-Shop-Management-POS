# Business rules

# Business rules

Confirmed rules are recorded with their domain documentation and tests. Do not
infer rules for a new workflow from a neighboring module; agree on material
financial and operational behavior before implementing it.

## Implemented foundations

- Inventory movements cannot reduce branch stock below zero. See
  [inventory.md](inventory.md).
- Customer overpayments are retained as customer advances; no credit limit is
  enforced yet. See [customer-ledger.md](customer-ledger.md).
- Supplier overpayments are retained as supplier advances. See
  [supplier-ledger.md](supplier-ledger.md).
- Purchases are drafted first and explicitly received/posted. Receiving
  atomically increases stock and supplier payable.
- Purchase quantities use the product's base unit and configured precision;
  no package conversions are assumed.
- Purchase tax and discount are entered as per-line currency amounts and
  become immutable with the posted invoice. They are not calculated from
  percentage rates. See [purchases.md](purchases.md).
- Supplier payments can be partially allocated across posted invoices. Any
  unallocated portion remains a supplier advance; it does not automatically
  reduce invoice-level outstanding amounts. See
  [supplier-payments.md](supplier-payments.md).
- Purchase returns reference the original posted invoice, record the
  supplier-confirmed credit amount per line, and remain draft until posted.
  Posting reduces stock and supplier payable atomically. Return credits reduce
  invoice net outstanding without changing prior payment allocations; excess
  credit remains on the supplier account. See [purchases.md](purchases.md).
- POS sales use an editable draft followed by explicit checkout. Checkout
  atomically reduces stock and records customer ledger entries. Walk-in sales
  must be paid in full and over-tender is change; registered customer
  overpayment is an account advance. Sale tax/discount are fixed per-line
  amounts, and one tender method is stored. See [sales.md](sales.md).

## Decisions still needed

Payment reversals/refunds, costing/valuation, batch and expiry tracking, and
product package conversions need business confirmation before implementation.
Supplier settlement details are documented in [supplier-payments.md](supplier-payments.md).
