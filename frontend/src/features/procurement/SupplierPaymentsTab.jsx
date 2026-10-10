import { useEffect, useMemo, useRef, useState } from 'react'
import {
  formatMoneyCents,
  parseMoneyCents,
} from '../pos/money.js'
import {
  createSupplierPayment,
  listSupplierInvoiceBalances,
  listSupplierPayments,
} from '../../services/procurementApi.js'

function localDate() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

const EMPTY_FORM = {
  supplier: '',
  amount: '',
  payment_date: localDate(),
  payment_method: '',
  reference: '',
  notes: '',
}

export default function SupplierPaymentsTab({ branchId, suppliers }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [allocations, setAllocations] = useState({})
  const [invoices, setInvoices] = useState([])
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [reviewPayment, setReviewPayment] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const confirmationRef = useRef(null)

  useEffect(() => {
    if (reviewPayment) confirmationRef.current?.focus()
  }, [reviewPayment])

  async function reloadData(supplierId = form.supplier) {
    const [invoiceResults, paymentResults] = await Promise.all([
      listSupplierInvoiceBalances(branchId, supplierId),
      listSupplierPayments(branchId, supplierId),
    ])
    setInvoices(invoiceResults)
    setPayments(paymentResults)
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setInvoices([])
    setPayments([])
    Promise.all([
      listSupplierInvoiceBalances(branchId, form.supplier),
      listSupplierPayments(branchId, form.supplier),
    ])
      .then(([invoiceResults, paymentResults]) => {
        if (!active) return
        setInvoices(invoiceResults)
        setPayments(paymentResults)
      })
      .catch((requestError) => {
        if (active) setError(requestError.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [branchId, form.supplier])

  const amountCents = parseMoneyCents(form.amount)
  const allocatedCents = useMemo(
    () =>
      Object.values(allocations).reduce((sum, value) => {
        const cents = parseMoneyCents(value)
        return cents === null ? sum : sum + cents
      }, 0n),
    [allocations],
  )
  const invalidAllocation = invoices.some((invoice) => {
    const amount = allocations[String(invoice.purchase_id)]
    if (!amount) return false
    const cents = parseMoneyCents(amount)
    const outstanding = parseMoneyCents(invoice.outstanding_amount)
    return cents === null || cents < 0n || outstanding === null || cents > outstanding
  })
  const unallocatedCents =
    amountCents === null || allocatedCents > amountCents
      ? null
      : amountCents - allocatedCents

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    setNotice('')
    setReviewPayment(false)
  }

  function updateAllocation(purchaseId, value) {
    setAllocations((current) => ({ ...current, [String(purchaseId)]: value }))
    setNotice('')
    setReviewPayment(false)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (
      !form.supplier ||
      amountCents === null ||
      amountCents <= 0n ||
      allocatedCents > amountCents ||
      invalidAllocation
    ) {
      return
    }
    if (!reviewPayment) {
      setReviewPayment(true)
      return
    }
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const result = await createSupplierPayment(branchId, {
        ...form,
        supplier: Number(form.supplier),
        allocations: invoices
          .filter(
            (invoice) =>
              (parseMoneyCents(allocations[String(invoice.purchase_id)] ?? '0') ?? 0n) > 0n,
          )
          .map((invoice) => ({
            purchase: invoice.purchase_id,
            amount: allocations[String(invoice.purchase_id)],
          })),
      })
      setNotice(
        `Payment ${result.payment.payment_number} recorded. ${result.payment.unallocated_amount} remains as supplier advance. The app records the entry; it does not move money.`,
      )
      setForm({ ...EMPTY_FORM, payment_date: localDate(), supplier: form.supplier })
      setAllocations({})
      setReviewPayment(false)
      try {
        await reloadData(form.supplier)
      } catch (refreshError) {
        setError(`The payment was recorded, but the payment and balance lists could not be refreshed: ${refreshError.message}`)
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  const selectedSupplier = suppliers.find(
    (supplier) => String(supplier.id) === form.supplier,
  )

  return (
    <>
      <section className="pos-panel catalog-form-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Supplier settlement</p>
            <h2>Record a supplier payment</h2>
          </div>
        </div>
        <p className="checkout-hint">
          Record payments already made outside this app. Allocate against posted invoices;
          any unallocated amount is recorded as supplier advance.
        </p>
        <form className="product-form" id="supplier-payment-form" onSubmit={handleSubmit}>
          <label>
            Supplier
            <select
              onChange={(event) => {
                setForm((current) => ({ ...current, supplier: event.target.value }))
                setAllocations({})
                setError('')
                setNotice('')
                setReviewPayment(false)
              }}
              required
              value={form.supplier}
            >
              <option value="">Choose supplier</option>
              {suppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>{supplier.name}</option>
              ))}
            </select>
          </label>
          <label>
            Amount paid
            <input
              min="0.01"
              onChange={(event) => updateForm('amount', event.target.value)}
              required
              step="0.01"
              type="number"
              value={form.amount}
            />
          </label>
          <label>
            Payment date
            <input
              onChange={(event) => updateForm('payment_date', event.target.value)}
              required
              type="date"
              value={form.payment_date}
            />
          </label>
          <label>
            Payment method (optional)
            <input
              maxLength="40"
              onChange={(event) => updateForm('payment_method', event.target.value)}
              value={form.payment_method}
            />
          </label>
          <label>
            Reference (optional)
            <input
              maxLength="100"
              onChange={(event) => updateForm('reference', event.target.value)}
              value={form.reference}
            />
          </label>
          <label>
            Notes (optional)
            <input
              maxLength="500"
              onChange={(event) => updateForm('notes', event.target.value)}
              value={form.notes}
            />
          </label>

          {form.supplier && (
            <div className="product-description">
              <h3>Invoice allocations</h3>
              {loading && <p role="status">Loading invoice balances…</p>}
              {!loading && invoices.length === 0 && (
                <p>{selectedSupplier?.name} has no outstanding posted invoices.</p>
              )}
              {!loading && invoices.length > 0 && (
                <div className="procurement-list">
                  {invoices.map((invoice) => (
                    <label className="allocation-row" key={invoice.purchase_id}>
                      <span>
                        <strong>{invoice.purchase_number}</strong>
                        <span>
                          {invoice.supplier_invoice_number || 'No supplier reference'}
                          {' · '}Outstanding {invoice.outstanding_amount}
                        </span>
                      </span>
                      <input
                        aria-label={`Allocate to invoice ${invoice.purchase_number}`}
                        max={invoice.outstanding_amount}
                        min="0"
                        onChange={(event) => updateAllocation(invoice.purchase_id, event.target.value)}
                        step="0.01"
                        type="number"
                        value={allocations[String(invoice.purchase_id)] ?? ''}
                      />
                    </label>
                  ))}
                </div>
              )}
              <div aria-live="polite" className="procurement-total">
                <span>Allocated to invoices</span>
                <strong>{formatMoneyCents(allocatedCents)}</strong>
                <span>Supplier advance from this payment</span>
                <strong>{unallocatedCents === null ? '—' : formatMoneyCents(unallocatedCents)}</strong>
              </div>
            </div>
          )}

          {error && <p className="pos-error product-description" role="alert">{error}</p>}
          {notice && <p className="success-message product-description" role="status">{notice}</p>}
          {!reviewPayment && (
            <div className="product-form-actions">
              <button
                disabled={
                  saving ||
                  loading ||
                  !form.supplier ||
                  amountCents === null ||
                  amountCents <= 0n ||
                  allocatedCents > amountCents ||
                  invalidAllocation
                }
                type="submit"
              >
                Review payment
              </button>
            </div>
          )}
        </form>
        {reviewPayment && unallocatedCents !== null && (
          <section
            aria-labelledby="payment-confirm-title"
            aria-modal="false"
            className="pos-notice payment-confirmation"
            role="alertdialog"
          >
            <h3 id="payment-confirm-title">Review this supplier payment</h3>
            <p>
              Record {form.amount} already paid to {selectedSupplier?.name}. This immutable
              entry will not move money. Allocated to invoices: {formatMoneyCents(allocatedCents)}.
              Supplier advance: {formatMoneyCents(unallocatedCents)}.
            </p>
            {Object.entries(allocations).some(([, value]) => value) && (
              <ul>
                {invoices
                  .filter((invoice) => allocations[String(invoice.purchase_id)])
                  .map((invoice) => (
                    <li key={invoice.purchase_id}>
                      {invoice.purchase_number}: {allocations[String(invoice.purchase_id)]}
                    </li>
                  ))}
              </ul>
            )}
            <div className="product-form-actions">
              <button
                className="button-secondary"
                disabled={saving}
                onClick={() => setReviewPayment(false)}
                type="button"
              >
                Edit payment
              </button>
              <button
                disabled={saving || loading}
                form="supplier-payment-form"
                ref={confirmationRef}
                type="submit"
              >
                {saving ? 'Recording…' : 'Confirm and record payment'}
              </button>
            </div>
          </section>
        )}
      </section>

      <section className="pos-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Immutable payment history</p>
            <h2>Supplier payments</h2>
          </div>
          <button
            className="button-secondary"
            disabled={loading}
            onClick={() => reloadData().catch((requestError) => setError(requestError.message))}
            type="button"
          >
            Refresh
          </button>
        </div>
        {loading && <p role="status">Loading supplier payments…</p>}
        {!loading && payments.length === 0 && <p>No supplier payments recorded for this selection.</p>}
        {!loading && payments.length > 0 && (
          <div className="procurement-list">
            {payments.map((payment) => (
              <article className="procurement-list-item" key={payment.id}>
                <div>
                  <strong>{payment.payment_number} · {payment.supplier_name_snapshot}</strong>
                  <p>
                    {payment.payment_date} · {payment.payment_method || 'Method not recorded'}
                    {payment.reference ? ` · Ref ${payment.reference}` : ''}
                  </p>
                  <p>
                    {payment.allocations.length
                      ? payment.allocations.map((allocation) =>
                          `${allocation.purchase_number_snapshot}: ${allocation.amount}`,
                        ).join(' · ')
                      : 'Unallocated advance'}
                  </p>
                </div>
                <div className="procurement-list-actions">
                  <strong>{payment.amount}</strong>
                  <span>Allocated {payment.allocated_amount}</span>
                  <span>Advance {payment.unallocated_amount}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
