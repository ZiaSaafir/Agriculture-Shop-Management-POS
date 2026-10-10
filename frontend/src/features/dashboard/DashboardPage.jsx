import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import {
  getBranchOperationalReport,
  listBranchSales,
  listSalesBranches,
  listBranchStock,
} from '../../services/posApi.js'
import { listProductBranches } from '../../services/productApi.js'
import { listPurchases, listSupplierInvoiceBalances } from '../../services/procurementApi.js'
import { formatMoneyCents, parseMoneyCents, parseQuantityMicros } from '../pos/money.js'

const SALES_ROLES = ['Admin', 'Manager', 'Cashier']
const PROCUREMENT_ROLES = ['Admin', 'Manager', 'Inventory/Store Staff']

function localDate() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function localDateOffset(offsetDays) {
  const date = new Date()
  date.setDate(date.getDate() + offsetDays)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function emptyMetrics() {
  return {
    stock: null,
    sales: null,
    purchases: null,
    invoices: null,
    report: null,
  }
}

function sumMoney(records, field) {
  return records.reduce((total, record) => {
    const amount = parseMoneyCents(record[field])
    return total + (amount ?? 0n)
  }, 0n)
}

function MetricCard({ label, value, detail, to }) {
  const content = (
    <>
      <span>{label}</span>
      <strong>{value}</strong>
      <span className="dashboard-metric-detail">{detail}</span>
    </>
  )

  return to ? (
    <Link className="dashboard-metric" to={to}>{content}</Link>
  ) : (
    <article className="dashboard-metric">{content}</article>
  )
}

export default function DashboardPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const roles = user?.roles ?? []
  const canSeeSales = roles.some((role) => SALES_ROLES.includes(role))
  const canSeeProcurement = roles.some((role) => PROCUREMENT_ROLES.includes(role))
  const canSeeStock = roles.some((role) =>
    ['Admin', 'Manager', 'Cashier', 'Inventory/Store Staff'].includes(role),
  )
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [metrics, setMetrics] = useState(emptyMetrics)
  const [metricErrors, setMetricErrors] = useState({})
  const [status, setStatus] = useState('loading')
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [signOutError, setSignOutError] = useState('')
  const today = localDate()

  useEffect(() => {
    if (authLoading || !user || (!canSeeSales && !canSeeProcurement)) return undefined
    let active = true
    const requestBranches = canSeeSales ? listSalesBranches : listProductBranches
    requestBranches()
      .then((result) => {
        if (!active) return
        setBranches(result)
        setBranchId(result.length === 1 ? String(result[0].id) : '')
        setStatus(
          result.length === 0
            ? 'no-branches'
            : result.length === 1
              ? 'loading-metrics'
              : 'ready',
        )
      })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [authLoading, canSeeProcurement, canSeeSales, user])

  const loadMetrics = useCallback(async (selectedBranchId) => {
    if (!selectedBranchId) {
      setMetrics(emptyMetrics())
      setMetricErrors({})
      return
    }

    setRefreshing(true)
    setMetricErrors({})
    const requests = []
    if (canSeeStock) {
      requests.push(['stock', listBranchStock(selectedBranchId)])
    }
    if (canSeeSales) {
      requests.push([
        'sales',
        listBranchSales(selectedBranchId, { status: 'completed' }),
      ])
      requests.push([
        'report',
        getBranchOperationalReport(
          selectedBranchId,
          localDateOffset(-13),
          localDate(),
        ),
      ])
    }
    if (canSeeProcurement) {
      requests.push([
        'purchases',
        listPurchases(selectedBranchId, 'posted'),
      ])
      requests.push([
        'invoices',
        listSupplierInvoiceBalances(selectedBranchId),
      ])
    }

    const results = await Promise.allSettled(requests.map(([, request]) => request))
    const nextMetrics = emptyMetrics()
    const nextErrors = {}
    results.forEach((result, index) => {
      const key = requests[index][0]
      if (result.status === 'fulfilled') {
        nextMetrics[key] = result.value
      } else {
        nextErrors[key] = result.reason?.message ?? 'This section could not be loaded.'
      }
    })
    setMetrics(nextMetrics)
    setMetricErrors(nextErrors)
    setRefreshing(false)
  }, [canSeeProcurement, canSeeSales, canSeeStock])

  useEffect(() => {
    if (!branchId || authLoading || (!canSeeSales && !canSeeProcurement)) return undefined
    let active = true
    setStatus('loading-metrics')
    loadMetrics(branchId)
      .then(() => {
        if (active) setStatus('ready')
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
  }, [authLoading, branchId, canSeeProcurement, canSeeSales, loadMetrics])

  const stockSummary = useMemo(() => {
    if (!metrics.stock) return null
    const active = metrics.stock.filter((item) => item.is_active)
    const lowStock = active.filter((item) => {
      const onHand = parseQuantityMicros(item.on_hand, 6)
      const threshold = parseQuantityMicros(item.low_stock_threshold, 6)
      return onHand !== null && threshold !== null && onHand <= threshold
    })
    return { activeCount: active.length, lowStock }
  }, [metrics.stock])

  const salesToday = useMemo(
    () => metrics.sales?.filter((sale) => sale.sale_date === today) ?? null,
    [metrics.sales, today],
  )
  const purchasesToday = useMemo(
    () => metrics.purchases?.filter((purchase) => purchase.purchase_date === today) ?? null,
    [metrics.purchases, today],
  )
  const outstandingTotal = useMemo(
    () =>
      metrics.invoices
        ? sumMoney(metrics.invoices, 'outstanding_amount')
        : null,
    [metrics.invoices],
  )

  async function handleRefresh() {
    setError('')
    try {
      await loadMetrics(branchId)
    } catch (requestError) {
      setError(requestError.message)
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

  if (authLoading) {
    return <main className="pos-loading" role="status">Loading your dashboard…</main>
  }

  if (!canSeeSales && !canSeeProcurement) {
    return (
      <main className="pos-shell">
        <section className="pos-notice">
          <h1>Dashboard access is not configured</h1>
          <p>
            Ask an administrator for a branch role with sales or inventory access.
            The current dashboard does not expose financial figures to this role.
          </p>
          <Link to="/">Continue to the point of sale</Link>
        </section>
      </main>
    )
  }

  return (
    <main className="pos-shell">
      <WorkspaceHeader
        branchId={branchId}
        branches={branches}
        detail={`Today, ${today}`}
        eyebrow="Branch operations"
        onSignOut={handleSignOut}
        title="Dashboard"
        user={user}
      />
      {signOutError && <p className="pos-error" role="alert">{signOutError}</p>}

      {branches.length > 1 && (
        <label className="branch-picker">
          Dashboard branch
          <select
            onChange={(event) => {
              setStatus(event.target.value ? 'loading-metrics' : 'ready')
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
      {error && <p className="pos-error" role="alert">{error}</p>}
      {status === 'no-branches' && (
        <section className="pos-notice">
          <h2>No accessible branch</h2>
          <p>Ask an administrator to assign your account to an active branch.</p>
        </section>
      )}
      {branchId && status === 'loading-metrics' && (
        <p role="status">Refreshing branch figures…</p>
      )}
      {branchId && status === 'ready' && (
        <>
          <section aria-label="Quick actions" className="quick-links">
            <h2>Quick actions</h2>
            <div className="quick-links-grid">
              {canSeeSales && (
                <Link className="quick-action" to="/">
                  <span>Sales workspace</span>
                  <strong>Start a sale</strong>
                </Link>
              )}
              {canSeeStock && (
                <Link className="quick-action" to="/inventory">
                  <span>Stock operations</span>
                  <strong>Review inventory</strong>
                </Link>
              )}
              {canSeeProcurement && (
                <Link className="quick-action" to="/procurement">
                  <span>Supplier operations</span>
                  <strong>Record a purchase</strong>
                </Link>
              )}
              {canSeeSales && (
                <Link className="quick-action" to="/contacts/customers">
                  <span>Customer accounts</span>
                  <strong>View customer balances</strong>
                </Link>
              )}
            </div>
          </section>
          <div className="dashboard-heading">
            <div>
              <h2>Today at a glance</h2>
              <p>Figures are branch-specific and based on the records available to your role.</p>
            </div>
            <button
              className="button-secondary"
              disabled={refreshing}
              onClick={handleRefresh}
              type="button"
            >
              {refreshing ? 'Refreshing…' : 'Refresh figures'}
            </button>
          </div>

          <section aria-label="Branch summary figures" className="dashboard-grid">
            {canSeeSales && (
              <MetricCard
                detail={metricErrors.sales
                  ? `Unavailable: ${metricErrors.sales}`
                  : `${salesToday?.length ?? '—'} completed transaction(s) dated ${today}`}
                label="Sales today"
                to="/sales"
                value={salesToday
                  ? formatMoneyCents(sumMoney(salesToday, 'total'))
                  : metricErrors.sales ? 'Unavailable' : '—'}
              />
            )}
            {canSeeStock && (
              <MetricCard
                detail={metricErrors.stock
                  ? `Unavailable: ${metricErrors.stock}`
                  : `${stockSummary?.lowStock.length ?? '—'} active product(s) at or below their low-stock threshold`}
                label="Low-stock products"
                to="/inventory"
                value={stockSummary
                  ? String(stockSummary.lowStock.length)
                  : metricErrors.stock ? 'Unavailable' : '—'}
              />
            )}
            {canSeeStock && (
              <MetricCard
                detail={metricErrors.stock
                  ? `Unavailable: ${metricErrors.stock}`
                  : 'Active products in this branch stock view'}
                label="Active stock items"
                to="/inventory"
                value={stockSummary
                  ? String(stockSummary.activeCount)
                  : metricErrors.stock ? 'Unavailable' : '—'}
              />
            )}
            {canSeeProcurement && (
              <MetricCard
                detail={metricErrors.invoices
                  ? `Unavailable: ${metricErrors.invoices}`
                  : `${metrics.invoices?.length ?? '—'} posted invoice(s) with outstanding balances`}
                label="Supplier invoices outstanding"
                to="/procurement"
                value={outstandingTotal === null
                  ? metricErrors.invoices ? 'Unavailable' : '—'
                  : formatMoneyCents(outstandingTotal)}
              />
            )}
            {canSeeProcurement && (
              <MetricCard
                detail={metricErrors.purchases
                  ? `Unavailable: ${metricErrors.purchases}`
                  : `${purchasesToday?.length ?? '—'} posted invoice(s) dated ${today}`}
                label="Purchases received today"
                to="/procurement"
                value={purchasesToday
                  ? formatMoneyCents(sumMoney(purchasesToday, 'total'))
                  : metricErrors.purchases ? 'Unavailable' : '—'}
              />
            )}
          </section>

          {canSeeSales && metrics.report && (
            <section className="pos-panel dashboard-sales-chart">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Last 14 days · net of posted returns</p>
                  <h2>Sales trend</h2>
                </div>
                <Link className="button-secondary nav-link" to="/reports">
                  View reports
                </Link>
              </div>
              <div className="dashboard-chart" role="img" aria-label="Net sales by day">
                {metrics.report.daily_sales.map((row) => (
                  <div className="dashboard-chart-column" key={row.date}>
                    <span className="dashboard-chart-value">
                      {Number(row.net_sales).toLocaleString('en-PK')}
                    </span>
                    <div className="dashboard-chart-plot">
                    <span
                      className={`dashboard-chart-bar${Number(row.net_sales) < 0 ? ' is-negative' : ''}`}
                      style={{
                        height: `${Math.max(
                          2,
                          Math.abs(Number(row.net_sales)) /
                            Math.max(
                              1,
                              ...metrics.report.daily_sales.map(
                                (item) => Math.abs(Number(item.net_sales)),
                              ),
                            ) *
                            46,
                        )}%`,
                        top: Number(row.net_sales) < 0 ? '50%' : undefined,
                        bottom: Number(row.net_sales) < 0 ? undefined : '50%',
                      }}
                      title={`Net sales PKR ${row.net_sales}`}
                    />
                    </div>
                    <small>{row.date.slice(5)}</small>
                  </div>
                ))}
                {!metrics.report.daily_sales.length && (
                  <p className="empty-state">No sales or returns in this period.</p>
                )}
              </div>
            </section>
          )}
          {metricErrors.report && (
            <p className="pos-error" role="alert">
              The sales trend could not be loaded: {metricErrors.report}
            </p>
          )}

          {metricErrors.stock && (
            <p className="pos-error" role="alert">
              Stock figures could not be loaded: {metricErrors.stock}
            </p>
          )}
          {!metricErrors.stock && stockSummary?.lowStock.length > 0 && (
            <section className="pos-panel dashboard-attention">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Replenishment attention</p>
                  <h2>Products at or below low-stock threshold</h2>
                </div>
                <Link className="button-secondary nav-link" to="/inventory">
                  Review inventory
                </Link>
              </div>
              <div className="sales-list">
                {stockSummary.lowStock.slice(0, 8).map((item) => (
                  <article className="sales-list-item" key={item.id}>
                    <div>
                      <strong>{item.name}</strong>
                      <p>SKU {item.sku} · {item.unit}</p>
                    </div>
                    <div className="sales-list-actions">
                      <span>On hand {item.on_hand} {item.unit}</span>
                      <span>Threshold {item.low_stock_threshold} {item.unit}</span>
                    </div>
                  </article>
                ))}
              </div>
              {stockSummary.lowStock.length > 8 && (
                <p className="checkout-hint">
                  Showing 8 of {stockSummary.lowStock.length} items; open Inventory to see all.
                </p>
              )}
            </section>
          )}
          {!metricErrors.sales && canSeeSales && salesToday?.length === 0 && (
            <p className="empty-state">No completed sales are recorded for this branch today.</p>
          )}
          {!metricErrors.purchases && canSeeProcurement && purchasesToday?.length === 0 && (
            <p className="empty-state">No purchases were received for this branch today.</p>
          )}
          <p className="dashboard-disclaimer">
            Operational overview only — not an accounting report. Sales and purchase figures are
            gross transaction totals, not profit or cash reconciliation. “Today” uses this
            browser’s local date. The trend chart is net of posted customer returns; post-sale
            customer payments are not represented.
          </p>
        </>
      )}
    </main>
  )
}
