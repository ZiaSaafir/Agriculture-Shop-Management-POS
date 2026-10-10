import { useEffect, useMemo, useRef, useState } from 'react'
import {
  formatMoneyCents,
  formatQuantityMicros,
  parseMoneyCents,
  parseQuantityMicros,
  quantityStep,
} from '../pos/money.js'
import {
  createPurchaseReturnDraft,
  getPurchase,
  listPurchaseReturns,
  listPurchases,
  postPurchaseReturn,
  updatePurchaseReturnDraft,
} from '../../services/procurementApi.js'

function localDate() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function quantitiesReturned(returns) {
  const totals = new Map()
  returns
    .filter((purchaseReturn) => purchaseReturn.status === 'posted')
    .flatMap((purchaseReturn) => purchaseReturn.items)
    .forEach((item) => {
      const key = String(item.purchase_line)
      const quantity = parseQuantityMicros(item.quantity, 6)
      if (quantity !== null) {
        totals.set(key, (totals.get(key) ?? 0n) + quantity)
      }
    })
  return totals
}

function blankItems(purchase, returns) {
  const returned = quantitiesReturned(returns)
  return purchase.items.map((line) => {
    const ordered = parseQuantityMicros(line.quantity, 6) ?? 0n
    const alreadyReturned = returned.get(String(line.id)) ?? 0n
    const remaining = ordered > alreadyReturned ? ordered - alreadyReturned : 0n
    return {
      purchase_line: line.id,
      product: line.product,
      product_name_snapshot: line.product_name_snapshot,
      unit_symbol_snapshot: line.unit_symbol_snapshot,
      remaining_quantity: formatQuantityMicros(remaining, 6),
      quantity: '',
      credit_amount: '',
    }
  })
}

function payloadFor(form, purchaseId) {
  return {
    purchase: Number(purchaseId),
    supplier_credit_note_reference: form.supplier_credit_note_reference,
    return_date: form.return_date,
    notes: form.notes,
    items: form.items
      .filter((item) => item.quantity && parseQuantityMicros(item.quantity, 6) > 0n)
      .map((item) => ({
        purchase_line: item.purchase_line,
        quantity: item.quantity,
        credit_amount: item.credit_amount,
      })),
  }
}

function formFromReturn(purchaseReturn, allItems) {
  const savedItems = new Map(
    purchaseReturn.items.map((item) => [String(item.purchase_line), item]),
  )
  return {
    supplier_credit_note_reference: purchaseReturn.supplier_credit_note_reference ?? '',
    return_date: purchaseReturn.return_date,
    notes: purchaseReturn.notes ?? '',
    items: allItems.map((item) => {
      const saved = savedItems.get(String(item.purchase_line))
      return saved
        ? { ...item, quantity: saved.quantity, credit_amount: saved.credit_amount }
        : item
    }),
  }
}

const emptyHeader = () => ({
  supplier_credit_note_reference: '',
  return_date: localDate(),
  notes: '',
  items: [],
})

export default function PurchaseReturnsTab({ branchId, products }) {
  const [purchases, setPurchases] = useState([])
  const [purchaseId, setPurchaseId] = useState('')
  const [purchase, setPurchase] = useState(null)
  const [purchaseReturns, setPurchaseReturns] = useState([])
  const [form, setForm] = useState(emptyHeader)
  const [activeReturn, setActiveReturn] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [draftDirty, setDraftDirty] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirmPost, setConfirmPost] = useState(false)
  const confirmationRef = useRef(null)

  useEffect(() => {
    if (confirmPost) confirmationRef.current?.focus()
  }, [confirmPost])

  useEffect(() => {
    let active = true
    setLoading(true)
    listPurchases(branchId, 'posted')
      .then((result) => {
        if (!active) return
        setPurchases(result)
        setLoading(false)
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message)
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [branchId])

  useEffect(() => {
    if (!purchaseId) {
      setPurchase(null)
      setPurchaseReturns([])
      setActiveReturn(null)
      setForm(emptyHeader())
      return undefined
    }
    let active = true
    setLoading(true)
    setError('')
    setNotice('')
    Promise.all([
      getPurchase(branchId, purchaseId),
      listPurchaseReturns(branchId, { purchase: purchaseId }),
    ])
      .then(([purchaseResult, returnResults]) => {
        if (!active) return
        setPurchase(purchaseResult)
        setPurchaseReturns(returnResults)
        const items = blankItems(purchaseResult, returnResults)
        setForm({ ...emptyHeader(), items })
        setActiveReturn(null)
        setDraftDirty(false)
        setLoading(false)
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message)
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [branchId, purchaseId])

  const productsById = useMemo(
    () => new Map(products.map((product) => [String(product.id), product])),
    [products],
  )
  const selectedReturnTotal = useMemo(
    () =>
      form.items.reduce((sum, item) => {
        if (!item.quantity) return sum
        const cents = parseMoneyCents(item.credit_amount)
        return cents === null ? sum : sum + cents
      }, 0n),
    [form.items],
  )
  const selectedLines = form.items.filter(
    (item) => item.quantity && parseQuantityMicros(item.quantity, 6) > 0n,
  )
  const canSave =
    Boolean(purchase) &&
    selectedLines.length > 0 &&
    selectedLines.every((item) => {
      const quantity = parseQuantityMicros(item.quantity, 6)
      const maximum = parseQuantityMicros(item.remaining_quantity, 6)
      const credit = parseMoneyCents(item.credit_amount)
      return (
        quantity !== null &&
        maximum !== null &&
        quantity > 0n &&
        quantity <= maximum &&
        credit !== null &&
        credit >= 1n
      )
    })

  async function reloadReturns() {
    if (!purchaseId) return
    const result = await listPurchaseReturns(branchId, { purchase: purchaseId })
    setPurchaseReturns(result)
  }

  function updateHeader(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    setNotice('')
    setDraftDirty(true)
  }

  function updateLine(lineId, field, value) {
    setForm((current) => ({
      ...current,
      items: current.items.map((item) =>
        item.purchase_line === lineId ? { ...item, [field]: value } : item,
      ),
    }))
    setNotice('')
    setDraftDirty(true)
  }

  function startNewReturn() {
    if (!purchase) return
    setActiveReturn(null)
    setForm({ ...emptyHeader(), items: blankItems(purchase, purchaseReturns) })
    setError('')
    setNotice('')
    setConfirmPost(false)
    setDraftDirty(false)
  }

  function openExistingReturn(purchaseReturn) {
    if (!purchase) return
    setActiveReturn(purchaseReturn)
    setForm(formFromReturn(purchaseReturn, blankItems(purchase, purchaseReturns)))
    setError('')
    setNotice('')
    setConfirmPost(false)
    setDraftDirty(false)
  }

  async function handleSave(event) {
    event.preventDefault()
    if (!canSave || (activeReturn && activeReturn.status !== 'draft')) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = payloadFor(form, purchaseId)
      const saved = activeReturn
        ? await updatePurchaseReturnDraft(branchId, activeReturn.id, {
            supplier_credit_note_reference: payload.supplier_credit_note_reference,
            return_date: payload.return_date,
            notes: payload.notes,
            items: payload.items,
          })
        : await createPurchaseReturnDraft(branchId, payload)
      setActiveReturn(saved)
      setDraftDirty(false)
      setNotice('Return saved as a draft. Stock and supplier balances have not changed.')
      try {
        await reloadReturns()
      } catch (refreshError) {
        setError(`The return draft was saved, but its history could not be refreshed: ${refreshError.message}`)
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  async function handlePost() {
    if (!activeReturn || activeReturn.status !== 'draft' || draftDirty) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const posted = await postPurchaseReturn(branchId, activeReturn.id)
      setActiveReturn(posted)
      setDraftDirty(false)
      setConfirmPost(false)
      setNotice('Supplier return posted. Branch stock and supplier account were updated.')
      try {
        await reloadReturns()
      } catch (refreshError) {
        setError(`The supplier return was posted, but its history could not be refreshed: ${refreshError.message}`)
      }
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  const canEdit = !activeReturn || activeReturn.status === 'draft'

  return (
    <>
      <section className="pos-panel catalog-form-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Supplier credit against a posted invoice</p>
            <h2>Create a purchase return</h2>
          </div>
        </div>
        <p className="checkout-hint">
          Enter quantities physically returned and the credit confirmed by the supplier.
          Posting permanently reduces stock and adjusts the supplier account.
        </p>
        <label className="branch-picker">
          Original posted purchase
          <select
            onChange={(event) => setPurchaseId(event.target.value)}
            value={purchaseId}
          >
            <option value="">Choose an invoice</option>
            {purchases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.purchase_number} — {item.supplier_name_snapshot} · {item.purchase_date}
              </option>
            ))}
          </select>
        </label>

        {loading && <p role="status">Loading posted purchases and return history…</p>}
        {purchase && (
          <>
            <div className="panel-heading return-heading">
              <div>
                <h3>{purchase.purchase_number} · {purchase.supplier_name_snapshot}</h3>
                <p>Invoice total {purchase.total} · dated {purchase.purchase_date}</p>
              </div>
              <button className="button-secondary" onClick={startNewReturn} type="button">
                New return draft
              </button>
            </div>
            {activeReturn && (
              <p className={activeReturn.status === 'posted' ? 'status-active' : 'status-inactive'}>
                {activeReturn.return_number} · {activeReturn.status === 'posted' ? 'Posted — read-only' : 'Draft'}
                {' · '}Supplier credit {activeReturn.credit_total}
              </p>
            )}
            <form className="product-form" onSubmit={handleSave}>
              <label>
                Supplier credit note reference
                <input
                  disabled={!canEdit || saving}
                  maxLength="100"
                  onChange={(event) => updateHeader('supplier_credit_note_reference', event.target.value)}
                  value={form.supplier_credit_note_reference}
                />
              </label>
              <label>
                Return date
                <input
                  disabled={!canEdit || saving}
                  onChange={(event) => updateHeader('return_date', event.target.value)}
                  required
                  type="date"
                  value={form.return_date}
                />
              </label>
              <label className="product-description">
                Notes
                <textarea
                  disabled={!canEdit || saving}
                  maxLength="500"
                  onChange={(event) => updateHeader('notes', event.target.value)}
                  rows="2"
                  value={form.notes}
                />
              </label>

              <div className="procurement-lines product-description">
                <h3>Original invoice lines</h3>
                {form.items.map((item) => {
                  const product = productsById.get(String(item.product))
                  const remaining = parseQuantityMicros(item.remaining_quantity, 6) ?? 0n
                  if (remaining <= 0n) return null
                  const precision = product?.quantity_decimal_places ?? 6
                  return (
                    <fieldset className="procurement-line return-line" key={item.purchase_line}>
                      <legend>{item.product_name_snapshot}</legend>
                      <p>
                        {item.unit_symbol_snapshot} · maximum available to return{' '}
                        {item.remaining_quantity}
                      </p>
                      <label>
                        Quantity returned ({item.unit_symbol_snapshot})
                        <input
                          disabled={!canEdit || saving}
                          max={formatQuantityMicros(remaining, precision)}
                          min={quantityStep(precision)}
                          onChange={(event) => updateLine(item.purchase_line, 'quantity', event.target.value)}
                          step={quantityStep(precision)}
                          type="number"
                          value={item.quantity}
                        />
                      </label>
                      <label>
                        Supplier-confirmed credit
                        <input
                          disabled={!canEdit || saving || !item.quantity}
                          min="0.01"
                          onChange={(event) => updateLine(item.purchase_line, 'credit_amount', event.target.value)}
                          step="0.01"
                          type="number"
                          value={item.credit_amount}
                        />
                      </label>
                    </fieldset>
                  )
                })}
              </div>
              <div className="procurement-total product-description">
                <span>Supplier credit requested</span>
                <strong>{formatMoneyCents(selectedReturnTotal)}</strong>
              </div>
              {error && <p className="pos-error product-description" role="alert">{error}</p>}
              {notice && <p className="success-message product-description" role="status">{notice}</p>}
              {canEdit && (
                <div className="product-form-actions">
                  <button disabled={saving || !canSave} type="submit">
                    {saving ? 'Saving…' : activeReturn ? 'Update return draft' : 'Save return draft'}
                  </button>
                </div>
              )}
            </form>
            {activeReturn?.status === 'draft' && (
              <div className="procurement-post-actions">
                {draftDirty && (
                  <p role="status">Save the draft changes before posting this return.</p>
                )}
                {!confirmPost ? (
                  <button
                    disabled={saving || draftDirty}
                    onClick={() => setConfirmPost(true)}
                    type="button"
                  >
                    Review and post supplier return
                  </button>
                ) : (
                  <div aria-labelledby="return-confirm-title" className="pos-notice" role="alertdialog">
                    <h3 id="return-confirm-title">Post this supplier return?</h3>
                    <p>
                      Posting will permanently record supplier credit of {activeReturn.credit_total},
                      reduce this branch’s stock for the returned quantities, and update the supplier
                      account. The return cannot be edited afterward. Confirm the goods and credit
                      note with the supplier before proceeding.
                    </p>
                    <div className="product-form-actions">
                      <button
                        className="button-secondary"
                        disabled={saving}
                        onClick={() => setConfirmPost(false)}
                        type="button"
                      >
                        Keep as draft
                      </button>
                      <button
                        disabled={saving}
                        onClick={handlePost}
                        ref={confirmationRef}
                        type="button"
                      >
                        {saving ? 'Posting…' : 'Confirm and post return'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
        {!loading && !purchases.length && (
          <p>No posted purchases are available to return.</p>
        )}
      </section>

      {purchaseId && purchaseReturns.length > 0 && (
        <section className="pos-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Original invoice</p>
              <h2>Supplier return history</h2>
            </div>
            <button
              className="button-secondary"
              onClick={() => reloadReturns().catch((requestError) => setError(requestError.message))}
              type="button"
            >
              Refresh
            </button>
          </div>
          <div className="procurement-list">
            {purchaseReturns.map((purchaseReturn) => (
              <article className="procurement-list-item" key={purchaseReturn.id}>
                <div>
                  <strong>{purchaseReturn.return_number}</strong>
                  <p>
                    {purchaseReturn.return_date}
                    {purchaseReturn.supplier_credit_note_reference
                      ? ` · Credit note ${purchaseReturn.supplier_credit_note_reference}`
                      : ''}
                    {' · '}{purchaseReturn.items.length} line(s)
                  </p>
                </div>
                <div className="procurement-list-actions">
                  <strong>{purchaseReturn.credit_total}</strong>
                  <span className={purchaseReturn.status === 'posted' ? 'status-active' : 'status-inactive'}>
                    {purchaseReturn.status === 'posted' ? 'Posted' : 'Draft'}
                  </span>
                  <button
                    className="button-secondary"
                    onClick={() => openExistingReturn(purchaseReturn)}
                    type="button"
                  >
                    {purchaseReturn.status === 'draft' ? 'Open draft' : 'View return'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  )
}
