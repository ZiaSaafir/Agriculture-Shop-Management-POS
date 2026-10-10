# Sales and POS checkout

## Cart and checkout

Sales are created as editable drafts. Draft carts do not change stock or a
customer ledger. Cashier completes the sale explicitly at checkout. Completion
is atomic: it records one stock sale movement per line, records the registered
customer's sale debit and any amount received, and marks the sale completed. If
any line fails, no stock, ledger, or sale completion changes persist.

Only products in the branch's organization that are active at checkout may be
sold. The cashier chooses the base unit or another same-dimension unit with a
verified organization-level conversion factor. The sale snapshots the entered
quantity, unit, and conversion-to-base factor; inventory movement remains in
the product's immutable base unit. Fractional quantities are disabled by
default per product and still obey the chosen unit's configured precision.
The cashier may enter a unit-price override; the actual unit price, product
name, SKU, and unit are snapshotted on the sale line. Catalog changes therefore
do not rewrite completed receipt details.

Per-line discount and tax are fixed currency amounts, not inferred percentages:

`line total = (quantity × unit price) - discount amount + tax amount`

The subtotal is rounded to two decimal places using `ROUND_HALF_UP`. Header
totals sum the line amounts. Discount cannot exceed line subtotal, and a
zero-total sale cannot be completed.

## Customer, tender, and change

- A registered customer is optional; no fake customer profile is created for
  walk-in sales.
- A walk-in sale must be paid in full before checkout. Any tender above the
  total is reported as change due and is not recorded as a customer advance.
- A registered customer can pay partially, buy on credit, or overpay. The full
  sale is debited and the full amount received is credited to the customer
  ledger. Remaining debt increases the customer balance; an overpayment is a
  customer advance. The response reports these separately as amount due and
  customer advance, not as cash change.
- One descriptive payment method and optional payment reference are captured
  per sale. Split tenders and payment processing are not implemented; this API
  does not move or verify funds.

Customer balances use the existing branch-scoped immutable customer ledger.
Walk-in transactions have no customer-ledger entry.

Completed sales and their lines are immutable. A partial return is a separate
immutable record tied to original sale lines; it restores inventory, credits
the customer ledger where applicable, and cannot return more than the
unreturned quantity. The cashier must select debt reduction, store credit, or a
cash refund. Debt reduction is limited to the customer's current positive
branch balance. Walk-in sales can only receive a cash refund. For customer
cash refunds the ledger records both the return credit and an equal debit
adjustment so the customer balance reflects the actual cash paid out.

Cash refunds are not reconciled against a till/cashbook because the system has
no cash-management ledger. Cost of goods sold, margin, and profit are also
unavailable.

## API

Admin, Manager, and Cashier users need membership in the exact active branch.

- `GET /api/sales/branches/` — returns only active branches where the
  authenticated user has sales access; superusers receive all active branches.
- `GET /api/sales/branches/{branch_id}/?status=draft|completed&search=...`
- `POST /api/sales/branches/{branch_id}/` — create a draft with optional
  `customer` and one or more `items`
- `GET /api/sales/branches/{branch_id}/{sale_id}/`
- `PATCH /api/sales/branches/{branch_id}/{sale_id}/` — edit a draft; supplying
  `items` replaces the draft lines, and `customer: null` makes it a walk-in sale
- `POST /api/sales/branches/{branch_id}/{sale_id}/checkout/` — complete the
  sale with `amount_paid`, and optional `payment_method` and
  `payment_reference`
- `GET /api/sales/branches/{branch_id}/{sale_id}/returns/` — list posted
  returns for a completed sale
- `POST /api/sales/branches/{branch_id}/{sale_id}/returns/` — post an immutable
  return with a disposition and one or more `{sale_line, quantity}` items

Checkout returns HTTP 409 if stock is insufficient.

## Sales history

Admin, Manager, and Cashier users can open **Sales history** from the POS
navigation. The workspace selects an authorized branch, filters by status, and
searches customer name, product name, and SKU using the branch-scoped sales
list endpoint. Summary amounts use integer cents and describe only the
currently displayed results.

Opening a receipt reads the existing sale detail endpoint. Sale details are
read-only and use the saved customer/product/unit/price snapshots; the screen
distinguishes registered-customer balance/advance from walk-in change. Drafts
are labeled as drafts and excluded from completed-sales summary totals.

Completed receipts can be printed or saved as PDF through the browser print
dialog, and a WhatsApp share link opens a prefilled receipt message. The
administrator's Settings workspace selects a 58 mm or 80 mm thermal-paper
layout and receipt footer for the current browser. Choose the matching thermal
printer and roll size in the browser print dialog; printing depends on the
printer's Windows driver. The application does not send WhatsApp messages
itself. The sale detail screen records partial returns and shows posted return
history. The sales list
endpoint currently returns the branch's full matching result without
pagination, so high-volume branches will need server-side pagination before
scale.

## POS frontend

The authenticated React home page is a cashier-facing POS screen. It loads the
user's allowed branches, the selected branch's stock listing, and active
customers. The stock response includes the configured unit precision and
catalog selling price so the cart can display accurate quantities and initial
prices. Frontend money calculations use integer cents; Django remains the
authoritative validator and calculator at checkout.

The screen creates a server-side draft immediately before checkout. If checkout
fails, it retains the draft ID so retry updates that same draft instead of
creating another sale. Walk-in tender defaults to the total; registered
customers default to zero tender and can complete the sale on credit. Split
tender and barcode scanning are not included.
