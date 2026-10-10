import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import SaleReceipt from '../../components/SaleReceipt.jsx'
import {
  checkoutSale,
  createSaleDraft,
  listBranchCustomers,
  listBranchStock,
  listSalesBranches,
  updateSaleDraft,
} from '../../services/posApi.js'
import {
  calculateCart,
  convertUnitPriceCents,
  formatMoneyCents,
  lineSubtotalCents,
  parseMoneyCents,
  quantityStep,
} from './money.js'

function draftPayload(customerId, lines) {
  return {
    customer: customerId ? Number(customerId) : null,
    items: lines.map((line) => ({
      product: line.product.id,
      quantity: line.quantity,
      transaction_unit: Number(line.unit.id),
      unit_price: line.unit_price,
      discount_amount: line.discount_amount,
      tax_amount: line.tax_amount,
    })),
  }
}

export default function PosPage() {
  const { user, signOut } = useAuth()
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [products, setProducts] = useState([])
  const [customers, setCustomers] = useState([])
  const [cart, setCart] = useState([])
  const [customerId, setCustomerId] = useState('')
  const [amountPaid, setAmountPaid] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [draftId, setDraftId] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [signOutError, setSignOutError] = useState('')
  const nextLineId = useRef(1)

  useEffect(() => {
    let active = true
    listSalesBranches()
      .then((accessibleBranches) => {
        if (!active) return
        setBranches(accessibleBranches)
        setBranchId(accessibleBranches.length === 1 ? String(accessibleBranches[0].id) : '')
        setStatus(
          accessibleBranches.length === 1
            ? 'loading-branch'
            : accessibleBranches.length
              ? 'ready'
              : 'no-branches',
        )
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
  }, [])

  useEffect(() => {
    if (!branchId) {
      setProducts([])
      setCustomers([])
      return undefined
    }

    let active = true
    setStatus('loading-branch')
    setError('')
    setCart([])
    setDraftId(null)
    setReceipt(null)
    setCustomerId('')
    setAmountPaid('')

    Promise.all([listBranchStock(branchId), listBranchCustomers(branchId)])
      .then(([stock, branchCustomers]) => {
        if (!active) return
        setProducts(stock.filter((product) => product.is_active))
        setCustomers(branchCustomers)
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

  const totals = useMemo(() => calculateCart(cart), [cart])
  const filteredProducts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    if (!query) return products
    return products.filter(
      (product) =>
        product.name.toLocaleLowerCase().includes(query) ||
        product.sku.toLocaleLowerCase().includes(query),
    )
  }, [products, search])
  const currentCustomer = customers.find(
    (customer) => String(customer.id) === customerId,
  )
  const paidCents = parseMoneyCents(
    amountPaid || (currentCustomer ? '0.00' : formatMoneyCents(totals.total)),
  )
  const isWalkInUnderpaid =
    !currentCustomer && paidCents !== null && paidCents < totals.total
  const needsPaymentMethod =
    paidCents !== null && paidCents > 0n && !paymentMethod.trim()

  function addProduct(product) {
    setError('')
    setReceipt(null)
    const units = product.available_units?.length
      ? product.available_units
      : [{
          id: product.base_unit ?? product.id,
          name: product.unit,
          symbol: product.unit,
          decimal_places: product.quantity_decimal_places,
          base_multiplier: '1',
        }]
    const unit = units.find((option) => Number(option.id) === Number(product.base_unit)) ?? units[0]
    setCart((current) => [
      ...current,
      {
        lineId: nextLineId.current++,
        product,
        unit,
        quantity: '1',
        unit_price: product.selling_price,
        discount_amount: '0.00',
        tax_amount: '0.00',
      },
    ])
  }

  function changeLineUnit(lineId, unitId) {
    setCart((current) =>
      current.map((line) => {
        if (line.lineId !== lineId) return line
        const unit = line.product.available_units?.find(
          (option) => String(option.id) === unitId,
        )
        if (!unit) return line
        const unitPrice = convertUnitPriceCents(
          line.product.selling_price,
          unit.base_multiplier,
        )
        return {
          ...line,
          unit,
          quantity: '1',
          unit_price: unitPrice ?? line.unit_price,
        }
      }),
    )
    setError('')
    setReceipt(null)
  }

  function updateLine(lineId, field, value) {
    setCart((current) =>
      current.map((line) =>
        line.lineId === lineId ? { ...line, [field]: value } : line,
      ),
    )
    setError('')
    setReceipt(null)
  }

  function removeLine(lineId) {
    setCart((current) => current.filter((line) => line.lineId !== lineId))
    setError('')
    setReceipt(null)
  }

  async function handleCheckout(event) {
    event.preventDefault()
    setError('')
    if (!branchId || !totals.valid || cart.length === 0) {
      setError('Add valid items to the cart before checkout.')
      return
    }
    if (paidCents === null || paidCents < 0n) {
      setError('Enter a valid payment amount with up to two decimal places.')
      return
    }
    if (isWalkInUnderpaid) {
      setError('A walk-in sale must be paid in full.')
      return
    }
    if (needsPaymentMethod) {
      setError('Choose the payment method for the amount received.')
      return
    }

    setBusy(true)
    let draftSaved = Boolean(draftId)
    try {
      const payload = draftPayload(customerId, cart)
      let saleId = draftId
      if (saleId) {
        await updateSaleDraft(branchId, saleId, payload)
      } else {
        const sale = await createSaleDraft(branchId, payload)
        saleId = sale.id
        draftSaved = true
        setDraftId(saleId)
      }

      const completed = await checkoutSale(branchId, saleId, {
        amount_paid: formatMoneyCents(paidCents),
        payment_method: paymentMethod.trim(),
      })
      setReceipt(completed)
      setCart([])
      setDraftId(null)
      setCustomerId('')
      setAmountPaid('')
      setPaymentMethod('')
      listBranchStock(branchId)
        .then((stock) => setProducts(stock.filter((product) => product.is_active)))
        .catch((refreshError) => {
          setError(`Sale completed, but stock could not be refreshed: ${refreshError.message}`)
        })
    } catch (requestError) {
      setError(
        draftSaved
          ? `Draft saved. Checkout did not complete: ${requestError.message}`
          : requestError.message,
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleSignOut() {
    setSignOutError('')
    try {
      await signOut()
    } catch (requestError) {
      setSignOutError(requestError.message)
    }
  }

  if (status === 'loading') {
    return <main className="pos-loading" role="status">Loading your branches…</main>
  }

  return (
    <main className="pos-shell">
      <WorkspaceHeader
        branchId={branchId}
        branches={branches}
        detail="Fast checkout and customer payments"
        eyebrow="Sales workspace"
        onSignOut={handleSignOut}
        title="Point of sale"
        user={user}
      />
      {signOutError && <p role="alert">{signOutError}</p>}

      {status === 'no-branches' && (
        <section className="pos-notice">
          <h2>No sales branch available</h2>
          <p>Ask an administrator to assign your account to an active branch with sales access.</p>
        </section>
      )}
      {branches.length > 1 && (
        <label className="branch-picker">
          Sales branch
          <select
            onChange={(event) => {
              setStatus('loading-branch')
              setBranchId(event.target.value)
            }}
            value={branchId}
          >
            <option value="">Choose a branch</option>
            {branches.map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.organization} — {branch.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {status === 'error' && <p className="pos-error" role="alert">{error}</p>}
      {status === 'loading-branch' && (
        <p className="pos-notice" role="status">Loading products and customers…</p>
      )}

      {status === 'ready' && branchId && (
        <>
          <div className="pos-layout">
            <section className="pos-panel product-panel" aria-labelledby="products-heading">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Catalog</p>
                  <h2 id="products-heading">Products</h2>
                </div>
                <span className="item-count">{filteredProducts.length} available</span>
              </div>
              <label className="search-field">
                Search products
                <input
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Name or SKU"
                  type="search"
                  value={search}
                />
              </label>
              <div className="product-list">
                {filteredProducts.map((product) => (
                  <article className="product-card" key={product.id}>
                    <div>
                      <h3>{product.name}</h3>
                      <p>{product.sku} · {product.selling_price} / {product.unit}</p>
                      <p className="stock-label">
                        In stock: {product.on_hand} {product.unit}
                      </p>
                    </div>
                    <button
                      disabled={busy || Number(product.on_hand) <= 0}
                      onClick={() => addProduct(product)}
                      type="button"
                    >
                      Add
                    </button>
                  </article>
                ))}
                {!filteredProducts.length && (
                  <p className="empty-state">No active products match this search.</p>
                )}
              </div>
            </section>

            <section className="pos-panel cart-panel" aria-labelledby="cart-heading">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Current transaction</p>
                  <h2 id="cart-heading">Cart</h2>
                </div>
                <span className="item-count">{cart.length} lines</span>
              </div>
              <label className="search-field">
                Customer
                <select
                  onChange={(event) => {
                    setCustomerId(event.target.value)
                    setAmountPaid('')
                  }}
                  value={customerId}
                >
                  <option value="">Walk-in customer</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}{customer.phone ? ` · ${customer.phone}` : ''}
                    </option>
                  ))}
                </select>
              </label>

              <div className="cart-lines">
                {cart.map((line) => {
                  const decimalPlaces = Number.isInteger(line.unit?.decimal_places)
                    ? line.unit.decimal_places
                    : Number.isInteger(line.product.quantity_decimal_places)
                      ? line.product.quantity_decimal_places
                      : 0
                  const subtotal = lineSubtotalCents(
                    line.quantity,
                    line.unit_price,
                    decimalPlaces,
                  )
                  return (
                    <article className="cart-line" key={line.lineId}>
                      <div className="cart-line-heading">
                        <div>
                          <h3>{line.product.name}</h3>
                          <p>{line.product.sku} · {line.unit?.symbol ?? line.product.unit}</p>
                        </div>
                        <button
                          aria-label={`Remove ${line.product.name}`}
                          className="remove-button"
                          onClick={() => removeLine(line.lineId)}
                          type="button"
                        >
                          Remove
                        </button>
                      </div>
                      <div className="line-fields">
                        <label>
                          Unit
                          <select
                            aria-label={`Unit for ${line.product.name}`}
                            onChange={(event) => changeLineUnit(line.lineId, event.target.value)}
                            value={line.unit?.id ?? line.product.base_unit ?? line.product.id}
                          >
                            {(line.product.available_units ?? [line.unit]).map((unit) => (
                              <option key={unit.id} value={unit.id}>
                                {unit.name} ({unit.symbol})
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Quantity
                          <input
                            aria-label={`Quantity for ${line.product.name}`}
                            inputMode="decimal"
                            min={line.product.fractional_quantity
                              ? quantityStep(decimalPlaces)
                              : '1'}
                            onChange={(event) => updateLine(line.lineId, 'quantity', event.target.value)}
                            step={line.product.fractional_quantity
                              ? quantityStep(decimalPlaces)
                              : '1'}
                            type="number"
                            value={line.quantity}
                          />
                        </label>
                        <label>
                          Unit price
                          <input
                            aria-label={`Unit price for ${line.product.name}`}
                            inputMode="decimal"
                            min="0"
                            onChange={(event) => updateLine(line.lineId, 'unit_price', event.target.value)}
                            step="0.01"
                            type="number"
                            value={line.unit_price}
                          />
                        </label>
                        <label>
                          Discount
                          <input
                            aria-label={`Discount for ${line.product.name}`}
                            inputMode="decimal"
                            min="0"
                            onChange={(event) => updateLine(line.lineId, 'discount_amount', event.target.value)}
                            step="0.01"
                            type="number"
                            value={line.discount_amount}
                          />
                        </label>
                        <label>
                          Tax
                          <input
                            aria-label={`Tax for ${line.product.name}`}
                            inputMode="decimal"
                            min="0"
                            onChange={(event) => updateLine(line.lineId, 'tax_amount', event.target.value)}
                            step="0.01"
                            type="number"
                            value={line.tax_amount}
                          />
                        </label>
                      </div>
                      <p className="line-total">
                        Line subtotal: {subtotal === null ? '—' : formatMoneyCents(subtotal)}
                      </p>
                    </article>
                  )
                })}
                {!cart.length && (
                  <p className="empty-state">Add a product to start a sale.</p>
                )}
              </div>

              <dl className="cart-totals">
                <div><dt>Subtotal</dt><dd>{formatMoneyCents(totals.subtotal)}</dd></div>
                <div><dt>Discount</dt><dd>−{formatMoneyCents(totals.discount)}</dd></div>
                <div><dt>Tax</dt><dd>{formatMoneyCents(totals.tax)}</dd></div>
                <div className="grand-total"><dt>Total</dt><dd>{formatMoneyCents(totals.total)}</dd></div>
              </dl>

              <form className="checkout-form" onSubmit={handleCheckout}>
                <label>
                  Amount received
                  <input
                    aria-label="Amount received"
                    inputMode="decimal"
                    min="0"
                    onChange={(event) => setAmountPaid(event.target.value)}
                    step="0.01"
                    type="number"
                    value={amountPaid || (currentCustomer ? '0.00' : formatMoneyCents(totals.total))}
                  />
                </label>
                <label>
                  Payment method
                  <input
                    onChange={(event) => setPaymentMethod(event.target.value)}
                    placeholder="Cash, card, mobile wallet…"
                    type="text"
                    value={paymentMethod}
                  />
                </label>
                {currentCustomer && (
                  <p className="checkout-hint">
                    Registered customers may pay later; an amount received of 0.00 records the sale as credit.
                  </p>
                )}
                {error && <p className="pos-error" role="alert">{error}</p>}
                <button
                  className="checkout-button"
                  disabled={busy || !totals.valid || !cart.length}
                  type="submit"
                >
                  {busy ? 'Completing sale…' : draftId ? 'Retry checkout' : 'Complete sale'}
                </button>
              </form>
            </section>
          </div>
          {receipt && (
            <section className="receipt-completion" aria-live="polite">
              <SaleReceipt sale={receipt} />
              <button
                className="button-secondary"
                onClick={() => setReceipt(null)}
                type="button"
              >
                New sale
              </button>
            </section>
          )}
        </>
      )}
    </main>
  )
}
