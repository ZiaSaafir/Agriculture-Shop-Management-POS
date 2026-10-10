import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import { listContacts } from '../../services/contactApi.js'
import { listBranchStock } from '../../services/posApi.js'
import { listProductBranches, listProducts } from '../../services/productApi.js'
import PurchasesTab from './PurchasesTab.jsx'
import SupplierPaymentsTab from './SupplierPaymentsTab.jsx'
import PurchaseReturnsTab from './PurchaseReturnsTab.jsx'

const PROCUREMENT_ROLES = ['Admin', 'Manager', 'Inventory/Store Staff']

export default function ProcurementPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const permitted = user?.roles.some((role) => PROCUREMENT_ROLES.includes(role)) ?? false
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [suppliers, setSuppliers] = useState([])
  const [products, setProducts] = useState([])
  const [tab, setTab] = useState('purchases')
  const [pendingBranchId, setPendingBranchId] = useState(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const branchConfirmationRef = useRef(null)

  useEffect(() => {
    if (pendingBranchId !== null) branchConfirmationRef.current?.focus()
  }, [pendingBranchId])

  useEffect(() => {
    if (authLoading || !user || !permitted) return undefined
    let active = true
    listProductBranches()
      .then((result) => {
        if (!active) return
        setBranches(result)
        setBranchId(result.length === 1 ? String(result[0].id) : '')
        setStatus(
          result.length === 0
            ? 'no-branches'
            : result.length === 1
              ? 'loading-branch'
              : 'ready',
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
      setSuppliers([])
      setProducts([])
      return undefined
    }
    let active = true
    setStatus('loading-branch')
    setError('')
    Promise.all([
      listContacts('supplier', branchId),
      listProducts(branchId),
      listBranchStock(branchId),
    ])
      .then(([supplierResults, productResults, stockResults]) => {
        if (!active) return
        const stockByProduct = new Map(
          stockResults.map((stock) => [String(stock.product), stock]),
        )
        setSuppliers(supplierResults)
        setProducts(
          productResults.map((product) => ({
            ...product,
            ...(stockByProduct.get(String(product.id)) ?? {}),
            id: product.id,
            quantity_decimal_places:
              stockByProduct.get(String(product.id))?.quantity_decimal_places ?? 6,
          })),
        )
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

  async function handleSignOut() {
    setError('')
    try {
      await signOut()
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  function requestBranchChange(nextBranchId) {
    if (nextBranchId === branchId) return
    if (!branchId) {
      setStatus(nextBranchId ? 'loading-branch' : 'ready')
      setBranchId(nextBranchId)
      return
    }
    setPendingBranchId(nextBranchId)
  }

  function confirmBranchChange() {
    if (pendingBranchId === null) return
    setError('')
    setStatus(pendingBranchId ? 'loading-branch' : 'ready')
    setBranchId(pendingBranchId)
    setPendingBranchId(null)
  }

  if (authLoading) {
    return <main className="pos-loading" role="status">Checking procurement access…</main>
  }

  if (!permitted) {
    return (
      <main className="pos-shell">
        <section className="pos-notice" role="alert">
          <h1>Procurement access is restricted</h1>
          <p>Your role cannot create or post purchases, payments, or supplier returns.</p>
          <Link to="/">Return to point of sale</Link>
        </section>
      </main>
    )
  }

  if (status === 'loading') {
    return <main className="pos-loading" role="status">Checking procurement access…</main>
  }

  return (
    <main className="pos-shell">
      <WorkspaceHeader
        branchId={branchId}
        branches={branches}
        detail="Purchasing, supplier payments, and returns"
        eyebrow="Branch operations"
        onSignOut={handleSignOut}
        title="Procurement"
        user={user}
      />

      {branches.length > 1 && (
        <label className="branch-picker">
          Branch for purchase and supplier accounts
          <select
            onChange={(event) => requestBranchChange(event.target.value)}
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

      {pendingBranchId !== null && (
        <section
          aria-labelledby="branch-switch-title"
          aria-modal="false"
          className="pos-notice branch-switch-confirmation"
          role="alertdialog"
        >
          <h2 id="branch-switch-title">Switch procurement branch?</h2>
          <p>
            Unsaved changes on this page will be discarded. Saved drafts stay with
            their original branch. Continue only if that is what you intend.
          </p>
          <div className="product-form-actions">
            <button
              className="button-secondary"
              onClick={() => setPendingBranchId(null)}
              type="button"
            >
              Stay on this branch
            </button>
            <button
              onClick={confirmBranchChange}
              ref={branchConfirmationRef}
              type="button"
            >
              Switch branch
            </button>
          </div>
        </section>
      )}

      {error && <p className="pos-error" role="alert">{error}</p>}
      {status === 'no-branches' && (
        <section className="pos-notice">
          <h2>No branch available</h2>
          <p>Ask an administrator to assign your account to an active branch.</p>
        </section>
      )}
      {branchId && status === 'loading-branch' && (
        <p role="status">Loading branch suppliers and products…</p>
      )}
      {branchId && status === 'ready' && (
        <>
          {!suppliers.length && (
            <p className="pos-notice" role="status">
              Add an active supplier and products before entering a purchase.
            </p>
          )}
          <div className="workspace-tabs" role="group" aria-label="Procurement workflows">
            {[
              ['purchases', 'Purchases'],
              ['payments', 'Supplier payments'],
              ['returns', 'Purchase returns'],
            ].map(([key, label]) => (
              <button
                aria-pressed={tab === key}
                className={tab === key ? 'workspace-tab is-selected' : 'workspace-tab'}
                id={`procurement-tab-${key}`}
                key={key}
                onClick={() => setTab(key)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <section className="procurement-workspace">
            <div hidden={tab !== 'purchases'}>
              <PurchasesTab
                branchId={branchId}
                key={branchId}
                products={products}
                suppliers={suppliers}
              />
            </div>
            <div hidden={tab !== 'payments'}>
              <SupplierPaymentsTab
                branchId={branchId}
                key={branchId}
                suppliers={suppliers}
              />
            </div>
            <div hidden={tab !== 'returns'}>
              <PurchaseReturnsTab
                branchId={branchId}
                key={branchId}
                products={products}
              />
            </div>
          </section>
        </>
      )}
    </main>
  )
}
