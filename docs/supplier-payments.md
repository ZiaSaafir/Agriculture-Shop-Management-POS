# Supplier payments and invoice settlement

## Payment behavior

Record a payment only after the real payment has been made. A payment is
immutable and reduces the supplier's branch ledger by its full amount.
`payment_method` and `reference` are descriptive records; the application does
not move money or verify bank, wallet, cheque, or cash transactions.

A payment may be allocated to one or more posted purchase invoices. An invoice
can also be settled through multiple partial payments. The service locks the
invoice rows while checking balances so concurrent payments cannot over-allocate
the same invoice. Allocation totals cannot exceed either the payment amount or
the invoice's remaining due.

The unallocated payment amount is recorded as a supplier advance. It reduces
the supplier's overall payable balance but does not silently close any invoice.
The invoice balance is:

`max(0, posted purchase total - posted supplier return credits - allocations)`

Posted returns do not rewrite prior payment allocations. A return that follows
a partial/full payment can reduce invoice outstanding to zero; any excess
payment/return credit remains on the supplier-wide ledger as an advance.

The supplier-wide ledger balance remains the sum of all payable increases and
decreases in that branch, including payments that are not allocated to an
invoice.

Payment, allocations, and the supplier-ledger entry are saved in one database
transaction. A failure leaves none of those records behind. Corrections,
refunds, and reversals are not implemented; they must be represented by future
compensating workflows, not by editing the payment history.

## API

Admin, Manager, and Inventory/Store Staff users must belong to the exact active
branch.

- `GET /api/purchases/branches/{branch_id}/outstanding/?supplier={id}` —
  posted invoice totals, allocated amounts, and outstanding balances
- `GET /api/purchases/branches/{branch_id}/payments/?supplier={id}` — payment
  history
- `POST /api/purchases/branches/{branch_id}/payments/` — record a payment:

  ```json
  {
    "supplier": 12,
    "amount": "120.00",
    "payment_date": "2026-10-07",
    "payment_method": "Bank transfer",
    "reference": "BANK-REF-77",
    "notes": "",
    "allocations": [
      {"purchase": 31, "amount": "100.00"}
    ]
  }
  ```

  The example leaves `20.00` as supplier advance.

- `GET /api/purchases/branches/{branch_id}/payments/{payment_id}/` — immutable
  payment and invoice allocation detail

No allocation is required when the payment is an advance or not assigned to
invoices yet. The React procurement workspace at `/procurement` shows invoice
balances, previews allocated and unallocated totals, and labels the unallocated
amount as supplier advance before recording the entry.
