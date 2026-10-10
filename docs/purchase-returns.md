# Supplier purchase returns

## Return workflow

A return references one posted purchase invoice and its original purchase lines.
Create it as a draft, enter the products and quantities being returned, and
record the supplier-confirmed credit-note amount for each line. Drafts do not
affect stock or supplier balances and can be edited before posting.

Posting is atomic: it reduces branch stock with immutable `supplier_return`
movements, records one supplier-ledger return credit for the total confirmed
credit-note amount, and marks the return posted. If stock is insufficient or
any part fails, the entire operation rolls back. A product cannot be returned
more than its received quantity less earlier posted returns.

The credit amount is entered from the supplier's confirmation. The system does
not infer tax/discount proration or a refund from original purchase costs.
Posted returns and their lines cannot be edited or deleted.

The React procurement workspace at `/procurement` supports selecting a posted
invoice, entering return quantities and supplier-confirmed credits, saving an
editable draft, and reviewing a separate confirmation before posting.
Insufficient-stock errors leave the draft available for correction; the UI does
not treat a failed post as successful.

## Invoice settlement

Posted return credits reduce the invoice's net total for outstanding reports.
Original payment allocations remain immutable:

`net invoice total = max(0, purchase total - posted return credits)`

`outstanding = max(0, net invoice total - allocated payments)`

If the invoice was partly or fully paid before the return, the prior allocation
is kept. Any value beyond the remaining invoice amount stays as supplier
credit/advance on the supplier-wide ledger. It is not automatically refunded
or reallocated to another invoice.

## API

Admin, Manager, and Inventory/Store Staff users need membership in the exact
active branch.

- `GET /api/purchases/branches/{branch_id}/returns/?purchase={id}&status=draft`
- `POST /api/purchases/branches/{branch_id}/returns/` — create a draft:

  ```json
  {
    "purchase": 31,
    "supplier_credit_note_reference": "CREDIT-44",
    "return_date": "2026-10-07",
    "notes": "",
    "items": [
      {"purchase_line": 88, "quantity": "2.000", "credit_amount": "18.00"}
    ]
  }
  ```

- `GET /api/purchases/branches/{branch_id}/returns/{return_id}/`
- `PATCH /api/purchases/branches/{branch_id}/returns/{return_id}/` — draft
  header update; supplying `items` replaces draft lines
- `POST /api/purchases/branches/{branch_id}/returns/{return_id}/post/` — post
  stock return and supplier credit once; insufficient stock returns HTTP 409

Purchase return refunds, a supplier-initiated exchange, editing historical
payments, and automatic credit reallocation are not implemented.
