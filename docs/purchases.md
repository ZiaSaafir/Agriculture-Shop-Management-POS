# Purchases and receiving

## Workflow

A purchase belongs to one organization branch and supplier. Create it as a
draft, then receive it explicitly:

1. A draft records the supplier invoice reference/date, products, quantities,
   base-unit purchase costs, and optional per-line discount and tax amounts.
2. Drafts do not change inventory or the supplier ledger. Draft lines may be
   replaced and header details edited.
3. Receiving/posting is atomic. It records a purchase stock movement for each
   line, posts one payable entry for the invoice total, and marks the purchase
   posted. If any operation fails, none of those effects persist.
4. Posted purchases and their lines are immutable. A future return or
   correction workflow must record compensating transactions rather than
   silently rewriting history.

The invoice subtotal per line is quantity multiplied by unit purchase cost,
rounded to two decimal places using `ROUND_HALF_UP`. The line total is
`subtotal - discount_amount + tax_amount`. Header totals are the sum of the
line values. Tax and discount are entered as amounts per line; the system does
not assume or calculate jurisdiction-specific rates.

Quantities use the product's configured base unit and precision. Packaging
conversions are not performed. For example, an item whose base unit is `kg`
must be entered in kilograms, not an assumed bag size.

The purchase line preserves product name, SKU, unit symbol, quantity, unit
cost, discount, tax, and totals. The header preserves the supplier name and
invoice reference. Later catalog edits therefore do not rewrite a posted
invoice. The purchase workflow does not automatically change the product's
catalog `purchase_price`; the line is the historical actual cost, while any
average-cost or stock-valuation policy remains future work.

The full posted invoice total, including entered tax less entered discounts,
increases the supplier payable. Supplier payments are separate immutable
transactions. One payment can be allocated across one or more posted invoices,
and a posted invoice may be paid in partial amounts over multiple payments.
The total allocated to an invoice cannot exceed its outstanding balance.
Payment amount not allocated to invoices remains a supplier advance, which can
make the overall supplier balance negative.

Payments reduce the supplier ledger by the full cash/payment amount whether or
not the amount is allocated to invoices. Invoice outstanding amounts come from
the immutable payment allocations; a supplier advance does not silently close
an invoice. Payment method is recorded as a descriptive value only; the system
does not initiate or verify bank, mobile wallet, or cash transactions. See the
[supplier settlement guide](supplier-payments.md) for payment API and
allocation details.

## Access and API

Admin, Manager, and Inventory/Store Staff users need membership in the exact
active branch.

- `GET /api/purchases/branches/{branch_id}/`
- `POST /api/purchases/branches/{branch_id}/` — create a draft with items
- `GET /api/purchases/branches/{branch_id}/{purchase_id}/`
- `PATCH /api/purchases/branches/{branch_id}/{purchase_id}/` — draft only;
  supplying `items` replaces all draft lines
- `POST /api/purchases/branches/{branch_id}/{purchase_id}/receive/` — post and
  receive once
- `GET /api/purchases/branches/{branch_id}/outstanding/?supplier={id}` — list
  posted invoices and their paid/outstanding amounts
- `GET /api/purchases/branches/{branch_id}/payments/?supplier={id}` — payment
  history
- `POST /api/purchases/branches/{branch_id}/payments/` — record a payment with
  optional allocations of `purchase` and `amount`
- `GET /api/purchases/branches/{branch_id}/payments/{payment_id}/` — payment
  and invoice allocation detail

The list supports `status=draft|posted`, `supplier={id}`, and
`search={supplier name or supplier invoice number}`.

Purchase returns are recorded against the original posted purchase, with a
confirmed supplier credit amount per returned product line. The return remains
a draft until posted. Posting reduces stock and supplier payable atomically;
the inventory service rejects a return that would create negative stock.
Posted return credits reduce invoice net outstanding while original payment
allocations remain immutable. Any excess credit or prior payment remains a
supplier advance.
For return endpoints and an example payload, see
[purchase-returns.md](purchase-returns.md).

## Procurement workspace

The React workspace is available at `/procurement` to Admin, Manager, and
Inventory/Store Staff users. It supports:

- Creating and editing purchase drafts, then separately reviewing and
  confirming receipt. Drafts do not change stock or balances; posting is
  irreversible and updates both.
- Recording supplier payments, allocating them to posted invoices, and
  previewing the amount that remains a supplier advance. The entry records a
  payment already made; it does not initiate a bank, wallet, cheque, or cash
  transaction.
- Preparing supplier return drafts against posted purchase lines, reviewing
  the supplier-confirmed credit, and separately confirming the irreversible
  stock and ledger update.

The workspace displays current supplier and product records; no sample
suppliers, invoices, payments, or returns are seeded. Payment
reversals/refunds, batch/expiry data, package conversion, tax-rate calculation,
and cost-of-goods valuation remain future work.
