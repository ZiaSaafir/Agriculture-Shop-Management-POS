import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { hasAccess } from '../../auth/roleAccess.js'
import { getBranchOperationalReport, listSalesBranches } from '../../services/posApi.js'
import { listProductBranches } from '../../services/productApi.js'

function localDate(date = new Date()) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function monthStart() {
  const now = new Date()
  return localDate(new Date(now.getFullYear(), now.getMonth(), 1))
}

function getPresetRange(preset) {
  const today = new Date()
  const end = localDate(today)
  if (preset === 'today') return [end, end]
  if (preset === 'last7') {
    const start = new Date(today)
    start.setDate(start.getDate() - 6)
    return [localDate(start), end]
  }
  if (preset === 'week') {
    const start = new Date(today)
    const daysSinceMonday = (start.getDay() + 6) % 7
    start.setDate(start.getDate() - daysSinceMonday)
    return [localDate(start), end]
  }
  if (preset === 'lastMonth') {
    const start = new Date(today.getFullYear(), today.getMonth() - 1, 1)
    const monthEnd = new Date(today.getFullYear(), today.getMonth(), 0)
    return [localDate(start), localDate(monthEnd)]
  }
  return [monthStart(), end]
}

function csvCell(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

function downloadCsv(report, selectedSection) {
  const rows = [
    ['Section', 'Metric', 'Value'],
    ['Report', 'Branch', report.branch.name],
    ['Report', 'Date range', `${report.range.start_date} to ${report.range.end_date}`],
    ['Sales', 'Transactions', report.sales.count],
    ['Sales', 'Gross sales (PKR)', report.sales.gross],
    ['Sales', 'Returns (PKR)', report.sales.returns],
    ['Sales', 'Net sales after returns (PKR)', report.sales.net],
    ['Sales', 'Discounts (PKR)', report.sales.discounts],
    ['Sales', 'Amount received (PKR)', report.sales.amount_received],
    ...report.sales.returns_by_disposition.map((row) => [
      'Sales returns',
      `${row.disposition} count`,
      row.count,
    ]),
    [],
    ['Sales by payment method', 'Method', 'Transactions', 'Gross (PKR)', 'Received (PKR)'],
    ...report.sales.by_payment_method.map((row) => [
      'Sales by payment method',
      row.payment_method || 'Not specified',
      row.count,
      row.gross,
      row.received,
    ]),
    ['Purchases', 'Transactions', report.purchases.count],
    ...report.sales.returns_by_disposition.map((row) => [
      'Sales returns',
      `${row.disposition} total (PKR)`,
      row.total,
    ]),
    ['Purchases', 'Posted purchases (PKR)', report.purchases.gross],
    ['Purchases', 'Purchase returns (PKR)', report.purchases.returns],
    ['Purchases', 'Net purchases (PKR)', report.purchases.net],
    [],
    ['Purchases by supplier', 'Supplier', 'Purchases', 'Gross (PKR)'],
    ...report.purchases.by_supplier.map((row) => [
      'Purchases by supplier',
      row.supplier_name_snapshot,
      row.count,
      row.gross,
    ]),
    ['Accounts', 'Customer receivables (PKR, current)', report.receivables],
    ['Accounts', 'Supplier payables (PKR, current)', report.supplier_payables],
    ['Inventory', 'Low-stock products', report.inventory.low_stock_count],
    ...report.inventory.movement_counts.map((row) => [
      'Inventory',
      `${row.movement_type} movements`,
      row.count,
    ]),
    [],
    ['Daily trend', 'Date', 'Sales (PKR)', 'Returns (PKR)', 'Net sales (PKR)'],
    ...report.daily_sales.map((row) => [
      'Daily trend',
      row.date,
      row.sales,
      row.returns,
      row.net_sales,
    ]),
    [],
    ['Top products', 'Product', 'Unit', 'Base quantity sold', 'Sales (PKR)'],
    ...report.top_products.map((row) => [
      'Top products',
      row.product_name_snapshot,
      row.unit_symbol_snapshot,
      row.sold_quantity,
      row.sales_total,
    ]),
  ]
  const sections = {
    sales: new Set([
      'Report',
      'Sales',
      'Sales returns',
      'Sales by payment method',
      'Daily trend',
      'Top products',
    ]),
    purchases: new Set(['Report', 'Purchases', 'Purchases by supplier']),
    inventory: new Set(['Report', 'Inventory']),
    accounts: new Set(['Report', 'Accounts']),
  }
  const visibleRows =
    selectedSection === 'all'
      ? rows
      : rows.filter((row) => sections[selectedSection]?.has(row[0]))
  const content = visibleRows.map((row) => row.map(csvCell).join(',')).join('\r\n')
  const objectUrl = URL.createObjectURL(
    new Blob([content], { type: 'text/csv;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `branch-report-${report.branch.name.replaceAll(/[^a-z0-9-]+/gi, '-')}-${report.range.start_date}-${report.range.end_date}.csv`
  link.click()
  URL.revokeObjectURL(objectUrl)
}

function Metric({ label, value, detail }) {
  return (
    <article className="dashboard-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <span className="dashboard-metric-detail">{detail}</span>}
    </article>
  )
}

export default function ReportsPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const canView = hasAccess(user?.roles, 'reports')
  const salesBranches = hasAccess(user?.roles, 'sales')
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [startDate, setStartDate] = useState(monthStart)
  const [endDate, setEndDate] = useState(localDate)
  const [rangePreset, setRangePreset] = useState('month')
  const [reportSection, setReportSection] = useState('all')
  const [report, setReport] = useState(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    if (authLoading || !user || !canView) return undefined
    let active = true
    const loadBranches = salesBranches ? listSalesBranches : listProductBranches
    loadBranches()
      .then((rows) => {
        if (!active) return
        setBranches(rows)
        setBranchId(rows.length === 1 ? String(rows[0].id) : '')
        setStatus(rows.length ? 'ready' : 'no-branches')
      })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [authLoading, canView, salesBranches, user])

  useEffect(() => {
    if (!branchId || !canView) return undefined
    if (!startDate || !endDate) return undefined
    if (startDate > endDate) {
      setReport(null)
      setError('The start date must be on or before the end date.')
      setStatus('error')
      return undefined
    }
    let active = true
    setStatus('loading-report')
    setError('')
    setReport(null)
    getBranchOperationalReport(branchId, startDate, endDate)
      .then((data) => {
        if (!active) return
        setReport(data)
        setStatus('ready')
      })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        setReport(null)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [branchId, canView, endDate, startDate])

  const maxDailySales = useMemo(
    () =>
      Math.max(
        1,
        ...(report?.daily_sales ?? []).flatMap((row) => [
          Number(row.sales),
          Number(row.returns),
        ]),
      ),
    [report],
  )

  async function handleSignOut() {
    try {
      await signOut()
    } catch (signOutError) {
      setError(signOutError.message)
    }
  }

  function selectDatePreset(preset) {
    const [start, end] = getPresetRange(preset)
    setRangePreset(preset)
    setStartDate(start)
    setEndDate(end)
  }

  if (authLoading || status === 'loading') {
    return <main className="pos-loading" role="status">Loading reporting access…</main>
  }

  if (!canView) {
    return (
      <main className="pos-shell reports-page">
        <section className="pos-notice" role="alert">
          <h1>Report access is restricted</h1>
          <p>Your role cannot view branch operational reports.</p>
          <Link to="/">Return to point of sale</Link>
        </section>
      </main>
    )
  }

  return (
    <main className="pos-shell reports-page">
      <WorkspaceHeader
        branchId={branchId}
        branches={branches}
        detail="Branch-scoped operational performance"
        eyebrow="Reports"
        onSignOut={handleSignOut}
        title="Business reports"
        user={user}
      />
      {branches.length > 1 && (
        <label className="branch-picker">
          Report branch
          <select onChange={(event) => setBranchId(event.target.value)} value={branchId}>
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
          <h2>No accessible branch</h2>
          <p>Ask an administrator to assign your account to an active branch.</p>
        </section>
      )}
      {error && <p className="pos-error" role="alert">{error}</p>}
      <section className="report-filter-panel no-print" aria-label="Report filters">
        <div className="report-filter-presets" role="group" aria-label="Date range presets">
          {[
            ['today', 'Today'],
            ['week', 'This week'],
            ['month', 'This month'],
            ['last7', 'Last 7 days'],
            ['lastMonth', 'Last month'],
          ].map(([value, label]) => (
            <button
              aria-pressed={rangePreset === value}
              className={rangePreset === value ? 'report-preset is-selected' : 'report-preset'}
              key={value}
              onClick={() => selectDatePreset(value)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
        <div className="report-filter-controls">
          <label>
            From
            <input
              onChange={(event) => {
                setRangePreset('custom')
                setStartDate(event.target.value)
              }}
              type="date"
              value={startDate}
            />
          </label>
          <label>
            To
            <input
              onChange={(event) => {
                setRangePreset('custom')
                setEndDate(event.target.value)
              }}
              type="date"
              value={endDate}
            />
          </label>
          <button
            className="button-secondary"
            disabled={!report || status !== 'ready'}
            onClick={() => downloadCsv(report, reportSection)}
            type="button"
          >
            Export filtered CSV
          </button>
          <button
            className="button-primary"
            disabled={!report || status !== 'ready'}
            onClick={() => window.print()}
            type="button"
          >
            Print / Save PDF
          </button>
        </div>
        <div className="report-section-filter" role="tablist" aria-label="Report sections">
          {[
            ['all', 'All sections'],
            ['sales', 'Sales'],
            ['purchases', 'Purchases'],
            ['inventory', 'Inventory'],
            ['accounts', 'Accounts'],
          ].map(([value, label]) => (
            <button
              aria-selected={reportSection === value}
              className={reportSection === value ? 'report-section-tab is-selected' : 'report-section-tab'}
              key={value}
              onClick={() => setReportSection(value)}
              role="tab"
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </section>
      {status === 'loading-report' && <p role="status">Calculating branch report…</p>}
      {report && status === 'ready' && (
        <>
          <header className="report-print-heading">
            <p className="eyebrow">Agriculture POS · operational report</p>
            <h1>{report.branch.name}</h1>
            <p>{report.range.start_date} to {report.range.end_date}</p>
          </header>
          <section aria-label="Report summary" className="dashboard-grid">
            {(reportSection === 'all' || reportSection === 'sales') && (
              <>
                <Metric detail={`${report.sales.count} completed transactions`} label="Gross sales" value={`PKR ${report.sales.gross}`} />
                <Metric detail={`Returns: PKR ${report.sales.returns}`} label="Net sales after returns" value={`PKR ${report.sales.net}`} />
              </>
            )}
            {(reportSection === 'all' || reportSection === 'purchases') && (
              <Metric detail={`${report.purchases.count} posted purchases · returns PKR ${report.purchases.returns}`} label="Net purchases" value={`PKR ${report.purchases.net}`} />
            )}
            {(reportSection === 'all' || reportSection === 'accounts') && (
              <>
                <Metric label="Customer receivables (current)" value={`PKR ${report.receivables}`} />
                <Metric label="Supplier payables (current)" value={`PKR ${report.supplier_payables}`} />
              </>
            )}
            {(reportSection === 'all' || reportSection === 'inventory') && (
              <Metric label="Products at/below low-stock threshold" value={report.inventory.low_stock_count} />
            )}
          </section>
          {(reportSection === 'all' || reportSection === 'sales') && (
          <section className="pos-panel report-panel report-daily-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{report.range.start_date} to {report.range.end_date}</p>
                <h2>Daily sales trend</h2>
              </div>
            </div>
            {!report.daily_sales.length && <p className="empty-state">No sales or returns in this date range.</p>}
            <div
              className={`report-chart${report.daily_sales.length > 31 ? ' report-chart-print-long' : ''}`}
              role="img"
              aria-label="Daily gross sales and return totals"
            >
              {report.daily_sales.map((row) => (
                <div className="report-chart-column" key={row.date}>
                  <div className="report-chart-bars">
                    <span
                      className="report-chart-sales"
                      style={{ height: `${Math.max(2, Number(row.sales) / maxDailySales * 100)}%` }}
                      title={`Sales PKR ${row.sales}`}
                    />
                    <span
                      className="report-chart-returns"
                      style={{ height: `${Math.max(2, Number(row.returns) / maxDailySales * 100)}%` }}
                      title={`Returns PKR ${row.returns}`}
                    />
                  </div>
                  <small>{row.date.slice(5)}</small>
                  <span>PKR {row.net_sales}</span>
                </div>
              ))}
            </div>
            <p className="checkout-hint report-chart-legend">
              <span><i className="report-legend-sales" /> Sales</span>
              <span><i className="report-legend-returns" /> Returns</span>
              <span>Net figures are printed in the daily detail table.</span>
            </p>
            <div className="report-table-wrapper">
              <table className="report-data-table">
                <thead>
                  <tr><th>Date</th><th>Gross sales</th><th>Returns</th><th>Net sales</th></tr>
                </thead>
                <tbody>
                  {report.daily_sales.map((row) => (
                    <tr key={row.date}>
                      <th scope="row">{row.date}</th>
                      <td>PKR {row.sales}</td>
                      <td>PKR {row.returns}</td>
                      <td>PKR {row.net_sales}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          )}
          {(reportSection === 'all' || reportSection === 'sales') && (
          <section className="pos-panel report-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Sales and collections</p><h2>Payment methods</h2></div>
            </div>
            {!report.sales.by_payment_method.length && (
              <p className="empty-state">No completed sales in this date range.</p>
            )}
            <div className="sales-list">
              {report.sales.by_payment_method.map((row) => (
                <article className="sales-list-item" key={row.payment_method || 'unspecified'}>
                  <div>
                    <strong>{row.payment_method || 'Not specified'}</strong>
                    <p>{row.count} transaction(s)</p>
                  </div>
                  <span>Received PKR {row.received}</span>
                  <strong>PKR {row.gross}</strong>
                </article>
              ))}
            </div>
          </section>
          )}
          {(reportSection === 'all' || reportSection === 'sales') && (
          <section className="pos-panel report-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Recorded handling choice</p><h2>Returns by disposition</h2></div>
            </div>
            {!report.sales.returns_by_disposition.length && (
              <p className="empty-state">No sales returns in this date range.</p>
            )}
            <div className="sales-list">
              {report.sales.returns_by_disposition.map((row) => (
                <article className="sales-list-item" key={row.disposition}>
                  <strong>
                    {row.disposition === 'debt_reduction'
                      ? 'Debt reduction'
                      : row.disposition === 'store_credit'
                        ? 'Store credit'
                        : 'Cash refund'}
                  </strong>
                  <span>{row.count} return(s)</span>
                  <strong>PKR {row.total}</strong>
                </article>
              ))}
            </div>
          </section>
          )}
          {(reportSection === 'all' || reportSection === 'purchases') && (
          <section className="pos-panel report-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Posted purchases in selected dates</p><h2>Purchases by supplier</h2></div>
            </div>
            {!report.purchases.by_supplier.length && (
              <p className="empty-state">No posted purchases in this date range.</p>
            )}
            <div className="sales-list">
              {report.purchases.by_supplier.map((row) => (
                <article className="sales-list-item" key={row.supplier_name_snapshot}>
                  <strong>{row.supplier_name_snapshot}</strong>
                  <span>{row.count} purchase(s)</span>
                  <strong>PKR {row.gross}</strong>
                </article>
              ))}
            </div>
          </section>
          )}
          {(reportSection === 'all' || reportSection === 'sales') && (
          <section className="pos-panel report-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Completed sales in selected dates</p><h2>Top products</h2></div>
            </div>
            {!report.top_products.length && <p className="empty-state">No sold products in this date range.</p>}
            <div className="sales-list">
              {report.top_products.map((product) => (
                <article className="sales-list-item" key={`${product.product_name_snapshot}-${product.unit_symbol_snapshot}`}>
                  <div>
                    <strong>{product.product_name_snapshot}</strong>
                    <p>{product.sold_quantity} {product.unit_symbol_snapshot} sold</p>
                  </div>
                  <strong>PKR {product.sales_total}</strong>
                </article>
              ))}
            </div>
          </section>
          )}
          {(reportSection === 'all' || reportSection === 'inventory') && (
          <section className="pos-panel report-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Inventory activity</p><h2>Stock movements</h2></div>
            </div>
            {!report.inventory.movement_counts.length ? (
              <p className="empty-state">No stock movements in this date range.</p>
            ) : (
              <div className="sales-list">
                {report.inventory.movement_counts.map((row) => (
                  <article className="sales-list-item" key={row.movement_type}>
                    <strong>{row.movement_type.replaceAll('_', ' ')}</strong>
                    <span>{row.count} movement(s)</span>
                  </article>
                ))}
              </div>
            )}
          </section>
          )}
          <p className="checkout-hint report-limit-note">
            Profit, cost of goods sold, stock valuation, and till cash movements are not reported:
            the current system does not yet retain the accounting data needed to calculate them reliably.
            Customer receivables and supplier payables are current branch balances, not balances as of the selected end date.
          </p>
        </>
      )}
    </main>
  )
}
