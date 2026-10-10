import { useEffect, useMemo, useRef, useState } from 'react'
import {
  calculateCart,
  formatMoneyCents,
  quantityStep,
} from '../pos/money.js'
import {
  createPurchaseDraft,
  listPurchases,
  receivePurchase,
  updatePurchaseDraft,
} from '../../services/procurementApi.js'

function localDate() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function blankForm() {
  return {
    supplier: '',
    supplier_invoice_number: '',
    purchase_date: localDate(),
    notes: '',
    items: [],
  }
}

function formFromPurchase(purchase) {
  return {
    supplier: String(purchase.supplier),
    supplier_invoice_number: purchase.supplier_invoice_number,
    purchase_date: purchase.purchase_date,
    notes: purchase.notes,
    items: purchase.items.map((item) => ({
      product: String(item.product),
      quantity: item.quantity,
      unit_cost: item.unit_cost,
      discount_amount: item.discount_amount,
      tax_amount: item.tax_amount,
    })),
  }
}

function purchasePayload(form) {
  return {
    supplier: Number(form.supplier),
    supplier_invoice_number: form.supplier_invoice_number,
    purchase_date: form.purchase_date,
    notes: form.notes,
    items: form.items.map((item) => ({
      product: Number(item.product),
      quantity: item.quantity,
      unit_cost: item.unit_cost,
      discount_amount: item.discount_amount || '0.00',
      tax_amount: item.tax_amount || '0.00',
    })),
  }
}

export default function PurchasesTab({ branchId, products, suppliers }) {
  const [purchases, setPurchases] = useState([])
  const [form, setForm] = useState(blankForm)
  const [activePurchase, setActivePurchase] = useState(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [draftDirty, setDraftDirty] = useState(false)
  const [confirmReceive, setConfirmReceive] = useState(false)
  const confirmationRef = useRef(null)

  useEffect(() => {
    if (confirmReceive) confirmationRef.current?.focus()
  }, [confirmReceive])

  async function reloadPurchases() {
    const result = await listPurchases(branchId)
    setPurchases(result)
    return result
  }

  useEffect(() => {
    let active = true
    setStatus('loading')
    listPurchases(branchId)
      .then((result) => {
        if (!active) return
        setPurchases(result)
        setStatus('ready')
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message)
          setStatus('error')
        }
      })
    return () => {
      active = false
    }
  }, [branchId])

  const productsById = useMemo(
    () => new Map(products.map((product) => [String(product.id), product])),
    [products],
  )
  const totals = useMemo(
    () =>
      calculateCart(
        form.items.map((item) => ({
          ...item,
          product: productsById.get(item.product) ?? { quantity_decimal_places: 6 },
          unit_price: item.unit_cost,
        })),
      ),
    [form.items, productsById],
  )
  const canSave =
    Boolean(form.supplier) &&
    form.items.length > 0 &&
    totals.valid &&
    suppliers.some((supplier) => String(supplier.id) === form.supplier) &&
    form.items.every((item) => productsById.has(item.product))

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    setDraftDirty(true)
  }

  function updateLine(index, field, value) {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      ),
    }))
    setDraftDirty(true)
  }

  function addLine() {
    const firstProduct = products.find((product) => product.is_active)
    if (!firstProduct) return
    setForm((current) => ({
      ...current,
      items: [
        ...current.items,
        {
          product: String(firstProduct.id),
          quantity: '',
          unit_cost: firstProduct.purchase_price ?? '0.00',
          discount_amount: '0.00',
          tax_amount: '0.00',
        },
      ],
    }))
    setDraftDirty(true)
  }

  function startNewDraft() {
    setActivePurchase(null)
    setForm(blankForm())
    setError('')
    setNotice('')
    setConfirmReceive(false)
    setDraftDirty(false)
  }

  function openPurchase(purchase) {
    setActivePurchase(purchase)
    setForm(formFromPurchase(purchase))
    setError('')
    setNotice('')
    setConfirmReceive(false)
    setDraftDirty(false)
  }

  async function handleSave(event) {
    event.preventDefault()
    if (!canSave || (activePurchase && activePurchase.status !== 'draft')) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = purchasePayload(form)
      const saved = activePurchase
        ? await updatePurchaseDraft(branchId, activePurchase.id, payload)
        : await createPurchaseDraft(branchId, payload)
      setActivePurchase(saved)
      setForm(formFromPurchase(saved))
      setDraftDirty(false)
      setNotice('Purchase saved as a draft. Stock and supplier balances have not changed.')
      try {
        await reloadPurchases()
      } catch (refreshError) {
        setError(`The draft was saved, but the invoice list could not be refreshed: ${refreshError.message}`)
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleReceive() {
    if (!activePurchase || activePurchase.status !== 'draft' || draftDirty) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const posted = await receivePurchase(branchId, activePurchase.id)
      setActivePurchase(posted)
      setForm(formFromPurchase(posted))
      setDraftDirty(false)
      setConfirmReceive(false)
      setNotice('Purchase received. Stock and supplier payable were updated.')
      try {
        await reloadPurchases()
      } catch (refreshError) {
        setError(`The purchase was received, but the invoice list could not be refreshed: ${refreshError.message}`)
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  function removeLine(index) {
    setForm((current) => ({
      ...current,
      items: current.items.filter((_, itemIndex) => itemIndex !== index),
    }))
    setDraftDirty(true)
  }

  const canEdit = !activePurchase || activePurchase.status === 'draft'

  return (
    <>
      <section className="pos-panel catalog-form-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Supplier invoice entry</p>
            <h2>{activePurchase ? activePurchase.purchase_number : 'New purchase draft'}</h2>
          </div>
          <button className="button-secondary" onClick={startNewDraft} type="button">
            New draft
          </button>
        </div>
        {activePurchase && (
          <p className={activePurchase.status === 'posted' ? 'status-active' : 'status-inactive'}>
            {activePurchase.status === 'posted'
              ? 'Received and posted — invoice is read-only'
              : 'Draft — it has not changed stock or supplier balances'}
          </p>
        )}
        <form className="product-form" onSubmit={handleSave}>
          <label>
            Supplier
            <select
              disabled={!canEdit || saving}
              onChange={(event) => updateForm('supplier', event.target.value)}
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
            Supplier invoice reference
            <input
              disabled={!canEdit || saving}
              maxLength="100"
              onChange={(event) => updateForm('supplier_invoice_number', event.target.value)}
              value={form.supplier_invoice_number}
            />
          </label>
          <label>
            Invoice date
            <input
              disabled={!canEdit || saving}
              onChange={(event) => updateForm('purchase_date', event.target.value)}
              required
              type="date"
              value={form.purchase_date}
            />
          </label>
          <label className="product-description">
            Notes
            <textarea
              disabled={!canEdit || saving}
              maxLength="500"
              onChange={(event) => updateForm('notes', event.target.value)}
              rows="2"
              value={form.notes}
            />
          </label>

          <div className="procurement-lines product-description">
            <div className="panel-heading">
              <h3>Invoice lines</h3>
              {canEdit && (
                <button
                  className="button-secondary"
                  disabled={!products.some((product) => product.is_active)}
                  onClick={addLine}
                  type="button"
                >
                  Add product
                </button>
              )}
            </div>
            {!form.items.length && (
              <p className="checkout-hint">Add at least one product line to save this invoice.</p>
            )}
            {form.items.map((item, index) => {
              const product = productsById.get(item.product)
              return (
                <fieldset className="procurement-line" key={`${activePurchase?.id ?? 'new'}-${index}`}>
                  <legend>Line {index + 1}</legend>
                  <label>
                    Product
                    <select
                      disabled={!canEdit || saving}
                      onChange={(event) => {
                        const next = productsById.get(event.target.value)
                        updateLine(index, 'product', event.target.value)
                        if (next) updateLine(index, 'unit_cost', next.purchase_price)
                      }}
                      required
                      value={item.product}
                    >
                      {products.filter((choice) => choice.is_active || String(choice.id) === item.product).map((choice) => (
                        <option key={choice.id} value={choice.id}>
                          {choice.name} — {choice.sku} ({choice.unit ?? 'unit'})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Quantity ({product?.unit ?? 'unit'})
                    <input
                      disabled={!canEdit || saving}
                      min={quantityStep(product?.quantity_decimal_places ?? 6)}
                      onChange={(event) => updateLine(index, 'quantity', event.target.value)}
                      required
                      step={quantityStep(product?.quantity_decimal_places ?? 6)}
                      type="number"
                      value={item.quantity}
                    />
                  </label>
                  <label>
                    Unit cost
                    <input
                      disabled={!canEdit || saving}
                      min="0"
                      onChange={(event) => updateLine(index, 'unit_cost', event.target.value)}
                      required
                      step="0.01"
                      type="number"
                      value={item.unit_cost}
                    />
                  </label>
                  <label>
                    Line discount
                    <input
                      disabled={!canEdit || saving}
                      min="0"
                      onChange={(event) => updateLine(index, 'discount_amount', event.target.value)}
                      step="0.01"
                      type="number"
                      value={item.discount_amount}
                    />
                  </label>
                  <label>
                    Line tax
                    <input
                      disabled={!canEdit || saving}
                      min="0"
                      onChange={(event) => updateLine(index, 'tax_amount', event.target.value)}
                      step="0.01"
                      type="number"
                      value={item.tax_amount}
                    />
                  </label>
                  {canEdit && (
                    <button
                      className="button-secondary"
                      disabled={saving}
                      onClick={() => removeLine(index)}
                      type="button"
                    >
                      Remove line {index + 1}
                    </button>
                  )}
                </fieldset>
              )
            })}
          </div>

          <div className="procurement-total product-description">
            <span>Invoice total</span>
            <strong>
              {activePurchase && !draftDirty
                ? activePurchase.total
                : totals.valid
                  ? formatMoneyCents(totals.total)
                  : '—'}
            </strong>
            {!totals.valid && canEdit && (
              <span>Check each quantity, unit cost, discount, and tax amount.</span>
            )}
          </div>
          {error && <p className="pos-error product-description" role="alert">{error}</p>}
          {notice && <p className="success-message product-description" role="status">{notice}</p>}
          {canEdit && (
            <div className="product-form-actions">
              <button disabled={saving || !canSave} type="submit">
                {saving ? 'Saving…' : activePurchase ? 'Update draft' : 'Save purchase draft'}
              </button>
            </div>
          )}
        </form>
        {activePurchase?.status === 'draft' && (
          <div className="procurement-post-actions">
            {draftDirty && (
              <p role="status">Save the draft changes before receiving this invoice.</p>
            )}
            {!confirmReceive ? (
              <button
                disabled={saving || draftDirty}
                onClick={() => setConfirmReceive(true)}
                type="button"
              >
                Review and receive purchase
              </button>
            ) : (
              <div aria-labelledby="receive-confirm-title" className="pos-notice" role="alertdialog">
                <h3 id="receive-confirm-title">Post this supplier invoice?</h3>
                <p>
                  This permanently records {activePurchase.items.length} invoice line(s), adds
                  the received quantities to branch stock, and updates the supplier balance.
                  The purchase cannot be edited after posting.
                </p>
                <div className="product-form-actions">
                  <button
                    className="button-secondary"
                    disabled={saving}
                    onClick={() => setConfirmReceive(false)}
                    type="button"
                  >
                    Keep as draft
                  </button>
                  <button
                    disabled={saving}
                    onClick={handleReceive}
                    ref={confirmationRef}
                    type="button"
                  >
                    {saving ? 'Posting…' : 'Confirm and post purchase'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="pos-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Branch purchase history</p>
            <h2>Invoices</h2>
          </div>
          <button
            className="button-secondary"
            onClick={() => reloadPurchases().catch((requestError) => setError(requestError.message))}
            type="button"
          >
            Refresh
          </button>
        </div>
        {status === 'loading' && <p role="status">Loading purchase invoices…</p>}
        {status === 'error' && error && <p className="pos-error" role="alert">{error}</p>}
        {status === 'ready' && purchases.length === 0 && (
          <p>No supplier invoices have been entered for this branch.</p>
        )}
        {purchases.length > 0 && (
          <div className="procurement-list">
            {purchases.map((purchase) => (
              <article className="procurement-list-item" key={purchase.id}>
                <div>
                  <strong>{purchase.purchase_number}</strong>
                  <p>
                    {purchase.supplier_name_snapshot}
                    {purchase.supplier_invoice_number
                      ? ` · Supplier ref ${purchase.supplier_invoice_number}`
                      : ''}
                    {' · '}{purchase.purchase_date} · {purchase.items.length} line(s)
                  </p>
                </div>
                <div className="procurement-list-actions">
                  <strong>{purchase.total}</strong>
                  <span className={purchase.status === 'posted' ? 'status-active' : 'status-inactive'}>
                    {purchase.status === 'posted' ? 'Received' : 'Draft'}
                  </span>
                  <button
                    className="button-secondary"
                    onClick={() => openPurchase(purchase)}
                    type="button"
                  >
                    {purchase.status === 'draft' ? 'Open draft' : 'View invoice'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
