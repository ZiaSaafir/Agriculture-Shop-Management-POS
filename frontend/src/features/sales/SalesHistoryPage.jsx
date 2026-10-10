import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import SaleReceipt from '../../components/SaleReceipt.jsx'
import { formatMoneyCents, parseMoneyCents } from '../pos/money.js'
import {
  createSalesReturn,
  getBranchSale,
  listBranchSales,
  listSalesReturns,
  listSalesBranches,
} from '../../services/posApi.js'

const SALES_ROLES = ['Admin', 'Manager', 'Cashier']

function formatCurrency(value) {
  const cents = parseMoneyCents(value)
  return cents === null ? value : formatMoneyCents(cents)
}

function formatTimestamp(value) {
  if (!value) return 'Not completed'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function SaleStatus({ status }) {
  return (
    <span className={status === 'completed' ? 'status-active' : 'status-inactive'}>
      {status === 'completed' ? 'Completed' : 'Draft'}
    </span>
  )
}

export default function SalesHistoryPage() {
  const { saleId } = useParams()
  const { user, loading: authLoading, signOut } = useAuth()
  const permitted = user?.roles.some((role) => SALES_ROLES.includes(role)) ?? false
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [sales, setSales] = useState([])
  const [sale, setSale] = useState(null)
  const [returns, setReturns] = useState([])
  const [showReturnForm, setShowReturnForm] = useState(false)
  const [returnDisposition, setReturnDisposition] = useState('store_credit')
  const [returnQuantities, setReturnQuantities] = useState({})
  const [returnNotes, setReturnNotes] = useState('')
  const [returnBusy, setReturnBusy] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('completed')
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [signOutError, setSignOutError] = useState('')

  useEffect(() => {
    if (authLoading || !user || !permitted) return undefined
    let active = true
    listSalesBranches()
      .then((result) => {
        if (!active) return
        setBranches(result)
        setBranchId(result.length === 1 ? String(result[0].id) : '')
        setStatus(result.length ? 'ready' : 'no-branches')
      })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [authLoading, permitted, user])

  useEffect(() => {
    if (!branchId || !permitted) {
      setSales([])
      setSale(null)
      return undefined
    }
    let active = true
    setStatus('loading-sales')
    setError('')
    setSale(null)
    const request = saleId
      ? getBranchSale(branchId, saleId).then((detail) => {
          if (active) {
            setSale(detail)
            return listSalesReturns(branchId, saleId).then((returnRows) => {
              if (active) setReturns(returnRows)
            })
          }
        })
      : listBranchSales(branchId, { status: statusFilter, search }).then((result) => {
          if (active) setSales(result)
        })
    request
      .then(() => {
        if (active) setStatus('ready')
      })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [branchId, permitted, saleId, search, statusFilter])

  const completedTotals = useMemo(
    () => {
      const completed = sales.filter((item) => item.status === 'completed')
      return {
        count: completed.length,
        total: completed.reduce(
          (sum, item) => sum + (parseMoneyCents(item.total) ?? 0n),
          0n,
        ),
        due: completed.reduce(
          (sum, item) => sum + (parseMoneyCents(item.balance_due) ?? 0n),
          0n,
        ),
      }
    },
    [sales],
  )

  async function handleSignOut() {
    setSignOutError('')
    try {
      await signOut()
    } catch (requestError) {
      setSignOutError(requestError.message)
    }
  }

  async function handleReturnSubmit(event) {
    event.preventDefault()
    setError('')
    const items = (sale?.items ?? [])
      .filter((item) => Number(returnQuantities[item.id] || 0) > 0)
      .map((item) => ({
        sale_line: item.id,
        quantity: returnQuantities[item.id],
      }))
    if (!items.length) {
      setError('Enter a return quantity for at least one sale line.')
      return
    }
    setReturnBusy(true)
    try {
      await createSalesReturn(branchId, saleId, {
        disposition: returnDisposition,
        notes: returnNotes,
        items,
      })
      setReturns(await listSalesReturns(branchId, saleId))
      setReturnQuantities({})
      setReturnNotes('')
      setShowReturnForm(false)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setReturnBusy(false)
    }
  }

  if (authLoading) {
    return <main className="pos-loading" role="status">Checking sales access…</main>
  }

  if (!permitted) {
    return (
      <main className="pos-shell">
        <section className="pos-notice" role="alert">
          <h1>Sales history access is restricted</h1>
          <p>Your role does not have access to branch sales.</p>
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
        detail="Completed transactions and saved invoice details"
        eyebrow="Branch transactions"
        onSignOut={handleSignOut}
        title={saleId ? 'Sale details' : 'Sales history'}
        user={user}
      />
      {signOutError && <p className="pos-error" role="alert">{signOutError}</p>}

      {branches.length > 1 && (
        <label className="branch-picker">
          Sales branch
          <select
            onChange={(event) => setBranchId(event.target.value)}
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

      {error && <p className="pos-error" role="alert">{error}</p>}
      {status === 'no-branches' && (
        <section className="pos-notice">
          <h2>No sales branch available</h2>
          <p>Ask an administrator to assign your account to an active branch with sales access.</p>
        </section>
      )}
      {branchId && status === 'loading-sales' && (
        <p role="status">{saleId ? 'Loading sale details…' : 'Loading sales…'}</p>
      )}

      {branchId && !saleId && (
        <>
          {status === 'ready' && (
            <section aria-label="Sales summary" className="inventory-summary">
              <article>
                <span>Completed sales in this result</span>
                <strong>{completedTotals.count}</strong>
              </article>
              <article>
                <span>Completed sale total</span>
                <strong>{formatMoneyCents(completedTotals.total)}</strong>
              </article>
              <article>
                <span>Outstanding customer balances</span>
                <strong>{formatMoneyCents(completedTotals.due)}</strong>
              </article>
            </section>
          )}
          <section className="pos-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Searchable branch records</p>
                <h2>Transactions</h2>
              </div>
              <button
                className="button-secondary"
                onClick={() => {
                  setSearchInput('')
                  setSearch('')
                }}
                type="button"
              >
                Clear search
              </button>
            </div>
            <div className="catalog-toolbar">
              <label className="search-field">
                Search customer, product, or SKU
                <input
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Enter a name or product code"
                  type="search"
                  value={searchInput}
                />
              </label>
              <label className="search-field">
                Status
                <select
                  onChange={(event) => setStatusFilter(event.target.value)}
                  value={statusFilter}
                >
                  <option value="completed">Completed</option>
                  <option value="draft">Drafts</option>
                  <option value="">All statuses</option>
                </select>
              </label>
              <button
                onClick={() => setSearch(searchInput.trim())}
                type="button"
              >
                Search
              </button>
            </div>
            {status === 'ready' && !sales.length && (
              <p className="empty-state">
                No transactions match these filters. Try a different search or status.
              </p>
            )}
            {status === 'ready' && sales.length > 0 && (
              <div className="sales-list" aria-label="Sales transactions">
                {sales.map((item) => (
                  <article className="sales-list-item" key={item.id}>
                    <div className="sales-list-main">
                      <div className="sales-list-heading">
                        <h3>{item.sale_number}</h3>
                        <SaleStatus status={item.status} />
                      </div>
                      <p>
                        {item.customer_name_snapshot || 'Walk-in customer'}
                        {' · '}{item.sale_date}
                        {item.completed_at ? ` · ${formatTimestamp(item.completed_at)}` : ''}
                      </p>
                      <p>
                        {item.items.length} item(s)
                        {item.completed_by ? ` · Completed by ${item.completed_by}` : ''}
                      </p>
                    </div>
                    <div className="sales-list-actions">
                      <strong>{formatCurrency(item.total)}</strong>
                      {item.status === 'completed' && (parseMoneyCents(item.balance_due) ?? 0n) > 0n && (
                        <span className="status-inactive">
                          Due {formatCurrency(item.balance_due)}
                        </span>
                      )}
                      {item.status === 'completed' && (parseMoneyCents(item.customer_advance_amount) ?? 0n) > 0n && (
                        <span className="status-active">
                          Customer advance {formatCurrency(item.customer_advance_amount)}
                        </span>
                      )}
                      <Link className="button-secondary nav-link" to={`/sales/${item.id}`}>
                        View receipt
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}
            <p className="checkout-hint">
              Totals summarize the displayed results only. Drafts are not included in completed
              sales totals. Refunds, returns, voids, and receipt printing are not available yet.
            </p>
          </section>
        </>
      )}

      {branchId && saleId && status === 'ready' && sale && (
        <section className="pos-panel sale-detail">
          {sale.status === 'completed' && <SaleReceipt sale={sale} />}
          <div className="panel-heading">
            <div>
              <p className="eyebrow">{sale.sale_number}</p>
              <h2>{sale.customer_name_snapshot || 'Walk-in customer'}</h2>
            </div>
            <SaleStatus status={sale.status} />
          </div>
          <dl className="sale-detail-meta">
            <div><dt>Sale date</dt><dd>{sale.sale_date}</dd></div>
            <div><dt>Completed</dt><dd>{formatTimestamp(sale.completed_at)}</dd></div>
            <div><dt>Created by</dt><dd>{sale.created_by}</dd></div>
            <div><dt>Completed by</dt><dd>{sale.completed_by || 'Not completed'}</dd></div>
            <div><dt>Payment method</dt><dd>{sale.payment_method || 'Not recorded'}</dd></div>
            {sale.payment_reference && (
              <div><dt>Payment reference</dt><dd>{sale.payment_reference}</dd></div>
            )}
          </dl>
          <div className="sales-list">
            {sale.items.map((item) => (
              <article className="sales-list-item" key={item.id}>
                <div>
                  <strong>{item.product_name_snapshot}</strong>
                  <p>
                    SKU {item.sku_snapshot || '—'} · {item.quantity} {item.unit_symbol_snapshot}
                    {' · '}Unit price {formatCurrency(item.unit_price)}
                  </p>
                </div>
                <div className="sales-list-actions">
                  <span>Discount {formatCurrency(item.discount_amount)}</span>
                  <span>Tax {formatCurrency(item.tax_amount)}</span>
                  <strong>{formatCurrency(item.total)}</strong>
                </div>
              </article>
            ))}
          </div>
          <dl className="sale-total-list">
            <div><dt>Subtotal</dt><dd>{formatCurrency(sale.subtotal)}</dd></div>
            <div><dt>Discount</dt><dd>{formatCurrency(sale.discount_total)}</dd></div>
            <div><dt>Tax</dt><dd>{formatCurrency(sale.tax_total)}</dd></div>
            <div><dt>Total</dt><dd>{formatCurrency(sale.total)}</dd></div>
            <div><dt>Amount received</dt><dd>{formatCurrency(sale.amount_paid)}</dd></div>
            {sale.customer ? (
              <>
                <div><dt>Balance due</dt><dd>{formatCurrency(sale.balance_due)}</dd></div>
                <div><dt>Customer advance</dt><dd>{formatCurrency(sale.customer_advance_amount)}</dd></div>
              </>
            ) : (
              <div><dt>Change due</dt><dd>{formatCurrency(sale.change_due)}</dd></div>
            )}
          </dl>
          {sale.notes && <p className="checkout-hint">Notes: {sale.notes}</p>}
          <p className="checkout-hint">
            This is a read-only record. Historical product names and prices are from the completed sale.
          </p>
          {sale.status === 'completed' && (
            <section className="sales-return-panel" aria-label="Sales returns">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Auditable inventory and account adjustment</p>
                  <h3>Returns</h3>
                </div>
                <button
                  className="button-secondary no-print"
                  onClick={() => {
                    setReturnDisposition(sale.customer ? 'store_credit' : 'cash_refund')
                    setShowReturnForm((visible) => !visible)
                  }}
                  type="button"
                >
                  {showReturnForm ? 'Cancel return' : 'Record return'}
                </button>
              </div>
              {returns.map((salesReturn) => (
                <article className="sales-list-item" key={salesReturn.id}>
                  <div>
                    <strong>{salesReturn.return_number} · {salesReturn.disposition_label}</strong>
                    <p>{salesReturn.return_date} · {salesReturn.created_by}</p>
                    {salesReturn.items.map((item) => (
                      <p key={item.id}>
                        {item.quantity} {item.unit_symbol_snapshot} {item.product_name_snapshot}
                      </p>
                    ))}
                  </div>
                  <strong>{formatCurrency(salesReturn.total)}</strong>
                </article>
              ))}
              {!returns.length && <p className="empty-state">No returns recorded.</p>}
              {showReturnForm && (
                <form className="product-form no-print" onSubmit={handleReturnSubmit}>
                  <label>
                    Refund disposition
                    <select
                      onChange={(event) => setReturnDisposition(event.target.value)}
                      value={returnDisposition}
                    >
                      {sale.customer && (
                        <>
                          <option value="debt_reduction">Reduce outstanding debt</option>
                          <option value="store_credit">Issue store credit</option>
                        </>
                      )}
                      <option value="cash_refund">Refund cash</option>
                    </select>
                  </label>
                  {sale.items.map((item) => {
                    const returned = returns
                      .flatMap((salesReturn) => salesReturn.items)
                      .filter((returnItem) => returnItem.sale_line === item.id)
                      .reduce((sum, returnItem) => sum + Number(returnItem.quantity), 0)
                    const remaining = Math.max(0, Number(item.quantity) - returned)
                    if (remaining <= 0) return null
                    return (
                      <label key={item.id}>
                        Return quantity · {item.product_name_snapshot}
                        <input
                          aria-label={`Return quantity for ${item.product_name_snapshot}`}
                          max={remaining}
                          min="0"
                          onChange={(event) =>
                            setReturnQuantities((current) => ({
                              ...current,
                              [item.id]: event.target.value,
                            }))
                          }
                          step="any"
                          type="number"
                          value={returnQuantities[item.id] ?? ''}
                        />
                        <small>
                          Remaining: {remaining} {item.unit_symbol_snapshot}
                        </small>
                      </label>
                    )
                  })}
                  <label className="product-description">
                    Return note
                    <textarea
                      onChange={(event) => setReturnNotes(event.target.value)}
                      rows="2"
                      value={returnNotes}
                    />
                  </label>
                  <button disabled={returnBusy} type="submit">
                    {returnBusy ? 'Posting return…' : 'Post return'}
                  </button>
                </form>
              )}
            </section>
          )}
          <Link className="button-secondary nav-link" to="/sales">Back to sales history</Link>
        </section>
      )}
    </main>
  )
}
