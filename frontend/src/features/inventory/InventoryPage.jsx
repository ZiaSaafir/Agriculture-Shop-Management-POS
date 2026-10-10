import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import { listBranchStock } from '../../services/posApi.js'
import {
  listBranchMovements,
  recordInventoryMovement,
} from '../../services/inventoryApi.js'
import { listProductBranches } from '../../services/productApi.js'
import { quantityStep } from '../pos/money.js'

const INVENTORY_ROLES = ['Admin', 'Manager', 'Inventory/Store Staff']
const MANUAL_MOVEMENT_TYPES = [
  ['opening_stock', 'Opening stock'],
  ['damage', 'Damage'],
  ['loss', 'Loss'],
  ['adjustment_in', 'Adjustment in'],
  ['adjustment_out', 'Adjustment out'],
]

function quantityMicros(value) {
  const match = /^(\d+)(?:\.(\d*))?$/.exec(String(value))
  if (!match || (match[2]?.length ?? 0) > 6) return null
  return BigInt(match[1]) * 1_000_000n + BigInt((match[2] ?? '').padEnd(6, '0') || '0')
}

function isBelowThreshold(product) {
  const onHand = quantityMicros(product.on_hand)
  const threshold = quantityMicros(product.low_stock_threshold)
  return threshold !== null && threshold > 0n && onHand !== null && onHand <= threshold
}

function movementLabel(type) {
  return MANUAL_MOVEMENT_TYPES.find(([value]) => value === type)?.[1] ?? type
}

function localDate(value) {
  return new Date(value).toLocaleString()
}

export default function InventoryPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [stock, setStock] = useState([])
  const [movements, setMovements] = useState([])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loadingData, setLoadingData] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({
    product: '',
    movement_type: 'opening_stock',
    quantity: '',
    reason: '',
    reference: '',
  })

  const permitted = user?.roles.some((role) => INVENTORY_ROLES.includes(role)) ?? false

  useEffect(() => {
    if (authLoading || !user) return undefined
    if (!permitted) {
      setStatus('ready')
      return undefined
    }

    let active = true
    listProductBranches()
      .then((accessibleBranches) => {
        if (!active) return
        setBranches(accessibleBranches)
        setBranchId(
          accessibleBranches.length === 1
            ? String(accessibleBranches[0].id)
            : '',
        )
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
  }, [authLoading, permitted, user])

  useEffect(() => {
    if (!branchId || !permitted) {
      if (!branchId) {
        setStock([])
        setMovements([])
      }
      return undefined
    }

    let active = true
    setStatus('loading-branch')
    setError('')
    Promise.all([listBranchStock(branchId), listBranchMovements(branchId)])
      .then(([branchStock, branchMovements]) => {
        if (!active) return
        setStock(branchStock)
        setMovements(branchMovements)
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
  }, [branchId, permitted])

  const filteredStock = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return stock.filter(
      (product) =>
        !query ||
        product.name.toLocaleLowerCase().includes(query) ||
        product.sku.toLocaleLowerCase().includes(query),
    )
  }, [stock, search])
  const activeProducts = stock.filter((product) => product.is_active)
  const lowStockCount = stock.filter(isBelowThreshold).length
  const emptyStockCount = stock.filter(
    (product) => quantityMicros(product.on_hand) === 0n,
  ).length
  const selectedProduct = activeProducts.find(
    (product) => String(product.id) === form.product,
  )
  const quantityInputStep = selectedProduct
    ? quantityStep(selectedProduct.quantity_decimal_places)
    : '0.001'

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function refreshInventory() {
    setLoadingData(true)
    setError('')
    try {
      const [branchStock, branchMovements] = await Promise.all([
        listBranchStock(branchId),
        listBranchMovements(branchId),
      ])
      setStock(branchStock)
      setMovements(branchMovements)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoadingData(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    setSubmitting(true)
    try {
      await recordInventoryMovement(branchId, {
        product: Number(form.product),
        movement_type: form.movement_type,
        quantity: form.quantity,
        reason: form.reason.trim(),
        reference: form.reference.trim(),
      })
      setNotice('Stock movement recorded.')
      setForm((current) => ({
        ...current,
        quantity: '',
        reason: '',
        reference: '',
      }))
      await refreshInventory()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSignOut() {
    setError('')
    try {
      await signOut()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  if (authLoading || status === 'loading') {
    return <main className="pos-loading" role="status">Checking inventory access…</main>
  }

  if (!permitted) {
    return (
      <main className="pos-shell">
        <section className="pos-notice" role="alert">
          <h1>Inventory management is restricted</h1>
          <p>Your role can use POS stock lookup but cannot record stock movements.</p>
          <Link to="/">Return to point of sale</Link>
        </section>
      </main>
    )
  }

  return (
    <main className="pos-shell">
      <WorkspaceHeader
        branchId={branchId}
        branches={branches}
        detail="Branch-level stock and movement control"
        eyebrow="Stock management"
        onSignOut={handleSignOut}
        title="Inventory"
        user={user}
      />

      {branches.length > 1 && (
        <label className="branch-picker">
          Inventory branch
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
      {status === 'no-branches' && (
        <section className="pos-notice">
          <h2>No inventory branch available</h2>
          <p>Ask an administrator to assign your account to an active branch.</p>
        </section>
      )}
      {status === 'loading-branch' && (
        <p role="status">Loading stock balances and movement history…</p>
      )}
      {status === 'error' && <p className="pos-error" role="alert">{error}</p>}

      {status === 'ready' && branchId && (
        <>
          <section className="inventory-summary" aria-label="Stock summary">
            <article><span>Catalog products</span><strong>{stock.length}</strong></article>
            <article><span>Low stock</span><strong>{lowStockCount}</strong></article>
            <article><span>Out of stock</span><strong>{emptyStockCount}</strong></article>
          </section>

          <div className="inventory-layout">
            <section className="pos-panel" aria-labelledby="stock-heading">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Current balances</p>
                  <h2 id="stock-heading">Stock on hand</h2>
                </div>
                <button
                  className="button-secondary"
                  disabled={loadingData}
                  onClick={refreshInventory}
                  type="button"
                >
                  {loadingData ? 'Refreshing…' : 'Refresh'}
                </button>
              </div>
              <label className="search-field">
                Search stock
                <input
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Name or SKU"
                  type="search"
                  value={search}
                />
              </label>
              <div className="stock-list">
                {filteredStock.map((product) => (
                  <article className="stock-row" key={product.id}>
                    <div>
                      <h3>{product.name}</h3>
                      <p>{product.sku} · threshold {product.low_stock_threshold} {product.unit}</p>
                    </div>
                    <div className="stock-row-balance">
                      <strong>{product.on_hand} {product.unit}</strong>
                      {isBelowThreshold(product) && (
                        <span className="status-inactive">Low stock</span>
                      )}
                      {!product.is_active && <span className="item-count">Inactive</span>}
                    </div>
                  </article>
                ))}
                {!filteredStock.length && (
                  <p className="empty-state">
                    {search ? 'No stock items match your search.' : 'No catalog products are available.'}
                  </p>
                )}
              </div>
            </section>

            <section className="pos-panel" aria-labelledby="movement-heading">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Auditable inventory update</p>
                  <h2 id="movement-heading">Record movement</h2>
                </div>
              </div>
              <p className="checkout-hint">
                Every movement is immutable history. Use a clear reason; sales and purchases update stock through their own workflows.
              </p>
              {activeProducts.length ? (
                <form className="checkout-form inventory-form" onSubmit={handleSubmit}>
                  <label>
                    Product
                    <select
                      onChange={(event) => updateForm('product', event.target.value)}
                      required
                      value={form.product}
                    >
                      <option value="">Choose a product</option>
                      {activeProducts.map((product) => (
                        <option key={product.id} value={product.id}>
                          {product.name} · {product.sku}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Movement type
                    <select
                      onChange={(event) => updateForm('movement_type', event.target.value)}
                      value={form.movement_type}
                    >
                      {MANUAL_MOVEMENT_TYPES.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Quantity
                    <input
                      inputMode="decimal"
                      min={quantityInputStep}
                      onChange={(event) => updateForm('quantity', event.target.value)}
                      required
                      step={quantityInputStep}
                      type="number"
                      value={form.quantity}
                    />
                  </label>
                  <label>
                    Reason
                    <input
                      maxLength="500"
                      onChange={(event) => updateForm('reason', event.target.value)}
                      placeholder="Required audit explanation"
                      required
                      value={form.reason}
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
                  {error && <p className="pos-error" role="alert">{error}</p>}
                  {notice && <p className="success-message" role="status">{notice}</p>}
                  <button disabled={submitting} type="submit">
                    {submitting ? 'Recording…' : 'Record stock movement'}
                  </button>
                </form>
              ) : (
                <p className="empty-state">Add and activate a product before recording stock.</p>
              )}
            </section>
          </div>

          <section className="pos-panel movement-history" aria-labelledby="movement-history-heading">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Append-only ledger</p>
                <h2 id="movement-history-heading">Recent movements</h2>
              </div>
              <span className="item-count">{movements.length} records</span>
            </div>
            <div className="stock-list">
              {movements.slice(0, 50).map((movement) => (
                <article className="stock-row" key={movement.id}>
                  <div>
                    <h3>{movement.product_name_snapshot} · {movementLabel(movement.movement_type)}</h3>
                    <p>{movement.reason}{movement.reference ? ` · ${movement.reference}` : ''}</p>
                    <p>{localDate(movement.created_at)} · {movement.created_by}</p>
                  </div>
                  <strong>{movement.quantity} {movement.unit_symbol_snapshot}</strong>
                </article>
              ))}
              {!movements.length && (
                <p className="empty-state">No stock movements recorded for this branch yet.</p>
              )}
            </div>
          </section>
        </>
      )}
    </main>
  )
}
