import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import {
  createProduct,
  getProductCatalogOptions,
  listProductBranches,
  listProducts,
  updateProduct,
} from '../../services/productApi.js'

const EMPTY_FORM = {
  category: '',
  brand: '',
  variety: '',
  base_unit: '',
  name: '',
  sku: '',
  barcode: '',
  description: '',
  purchase_price: '',
  selling_price: '',
  low_stock_threshold: '0',
  allow_fractional_quantity: false,
  is_active: true,
}

const CATALOG_ROLES = ['Admin', 'Manager', 'Inventory/Store Staff']

function formFromProduct(product) {
  return {
    category: String(product.category),
    brand: product.brand ? String(product.brand) : '',
    variety: product.variety ? String(product.variety) : '',
    base_unit: String(product.base_unit),
    name: product.name,
    sku: product.sku,
    barcode: product.barcode,
    description: product.description,
    purchase_price: product.purchase_price,
    selling_price: product.selling_price,
    low_stock_threshold: product.low_stock_threshold,
    allow_fractional_quantity: product.allow_fractional_quantity,
    is_active: product.is_active,
  }
}

function productPayload(form) {
  return {
    ...form,
    category: Number(form.category),
    brand: form.brand ? Number(form.brand) : null,
    variety: form.variety ? Number(form.variety) : null,
    base_unit: Number(form.base_unit),
  }
}

export default function ProductsPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [options, setOptions] = useState(null)
  const [products, setProducts] = useState([])
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showInactive, setShowInactive] = useState(false)
  const formRef = useRef(null)
  const nameInputRef = useRef(null)
  const permitted =
    user?.roles.some((role) => CATALOG_ROLES.includes(role)) ?? false

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
        setOptions(null)
        setProducts([])
      }
      return undefined
    }

    let active = true
    setStatus('loading-branch')
    setError('')
    setNotice('')
    Promise.all([
      getProductCatalogOptions(branchId),
      listProducts(branchId),
    ])
      .then(([catalogOptions, catalogProducts]) => {
        if (!active) return
        setOptions(catalogOptions)
        setProducts(catalogProducts)
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

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return products.filter((product) => {
      if (!showInactive && !product.is_active) return false
      return (
        !query ||
        product.name.toLocaleLowerCase().includes(query) ||
        product.sku.toLocaleLowerCase().includes(query) ||
        product.barcode.toLocaleLowerCase().includes(query)
      )
    })
  }, [products, search, showInactive])

  const availableVarieties = options?.varieties.filter(
    (variety) =>
      !variety.category_id || String(variety.category_id) === form.category,
  ) ?? []
  const hasFormOptions =
    Boolean(options?.categories.length) && Boolean(options?.units.length)

  useEffect(() => {
    if (!showForm) return
    const focusForm = () => {
      formRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      nameInputRef.current?.focus?.({ preventScroll: true })
    }
    if (window.requestAnimationFrame) window.requestAnimationFrame(focusForm)
    else focusForm()
  }, [showForm])

  function beginCreate() {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
    setError('')
    setNotice('')
  }

  function beginEdit(product) {
    setEditingId(product.id)
    setForm(formFromProduct(product))
    setShowForm(true)
    setError('')
    setNotice('')
  }

  function updateForm(field, value) {
    setForm((current) => ({
      ...current,
      [field]: value,
      ...(field === 'category' ? { variety: '' } : {}),
    }))
  }

  async function refreshProducts() {
    const catalogProducts = await listProducts(branchId)
    setProducts(catalogProducts)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    setSaving(true)
    try {
      if (editingId) {
        await updateProduct(branchId, editingId, productPayload(form))
        setNotice('Product changes saved.')
      } else {
        await createProduct(branchId, productPayload(form))
        setNotice('Product added to this organization catalog.')
      }
      await refreshProducts()
      setShowForm(false)
      setEditingId(null)
      setForm(EMPTY_FORM)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
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
    return <main className="pos-loading" role="status">Loading product access…</main>
  }

  if (!permitted) {
    return (
      <main className="pos-shell">
        <section className="pos-notice" role="alert">
          <h1>Catalog access is restricted</h1>
          <p>Your role can use sales but cannot manage the product catalog.</p>
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
        detail="Shared organization catalog"
        eyebrow="Product management"
        onSignOut={handleSignOut}
        title="Products"
        user={user}
      />

      {branches.length > 1 && (
        <label className="branch-picker">
          Select a branch to manage its organization catalog
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
          <h2>No catalog branch available</h2>
          <p>Ask an administrator to assign your account to an active branch.</p>
        </section>
      )}
      {status === 'loading-branch' && (
        <p role="status">Loading the organization catalog…</p>
      )}
      {status === 'error' && <p className="pos-error" role="alert">{error}</p>}

      {status === 'ready' && branchId && options && (
        <>
          <section className="catalog-toolbar" aria-label="Product catalog actions">
            <label className="search-field">
              Search products
              <input
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name, SKU, or barcode"
                type="search"
                value={search}
              />
            </label>
            <label className="inactive-toggle">
              <input
                checked={showInactive}
                onChange={(event) => setShowInactive(event.target.checked)}
                type="checkbox"
              />
              Show inactive
            </label>
            <button disabled={!hasFormOptions} onClick={beginCreate} type="button">
              Add product
            </button>
          </section>

          {notice && <p className="success-message" role="status">{notice}</p>}
          {error && <p className="pos-error" role="alert">{error}</p>}
          {!hasFormOptions && (
            <p className="pos-notice" role="status">
              Set up at least one active category and unit in Django admin before adding products.
            </p>
          )}

          <section className="pos-panel catalog-panel" aria-labelledby="catalog-heading">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">One catalog per organization</p>
                <h2 id="catalog-heading">Catalog items</h2>
              </div>
              <span className="item-count">{filteredProducts.length} products</span>
            </div>
            <p className="checkout-hint catalog-price-note">
              Prices are displayed in PKR. Demo estimates are not supplier quotes;
              confirm current cost and selling price before live transactions.
            </p>
            <div className="catalog-list">
              {filteredProducts.map((product) => {
                const category = options.categories.find(
                  (option) => option.id === product.category,
                )
                const unit = options.units.find(
                  (option) => option.id === product.base_unit,
                )
                return (
                  <article className="catalog-product" key={product.id}>
                    <div className="catalog-product-main">
                      <h3>{product.name}</h3>
                      {product.sku.endsWith('-DEMO') && (
                        <span className="demo-product-badge">Demo product</span>
                      )}
                      <p>{product.sku}{product.barcode ? ` · ${product.barcode}` : ''}</p>
                      <p>
                        {category?.name ?? 'Category unavailable'} ·
                        {' '}PKR {product.selling_price} / {unit?.symbol ?? 'unit'}
                      </p>
                    </div>
                    <div className="catalog-product-meta">
                      <span className={product.is_active ? 'status-active' : 'status-inactive'}>
                        {product.is_active ? 'Active' : 'Inactive'}
                      </span>
                      <button
                        className="button-secondary"
                        onClick={() => beginEdit(product)}
                        type="button"
                      >
                        Edit
                      </button>
                    </div>
                  </article>
                )
              })}
              {!filteredProducts.length && (
                <p className="empty-state">
                  {search ? 'No products match your search.' : 'No products in this catalog yet.'}
                </p>
              )}
            </div>
          </section>

          {showForm && (
            <section
              className="pos-panel catalog-form-panel"
              aria-labelledby="product-form-heading"
              ref={formRef}
            >
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{editingId ? 'Update catalog details' : 'New catalog item'}</p>
                  <h2 id="product-form-heading">{editingId ? 'Edit product' : 'Add product'}</h2>
                </div>
                <button
                  className="button-secondary"
                  onClick={() => setShowForm(false)}
                  type="button"
                >
                  Cancel
                </button>
              </div>
              <form className="product-form" onSubmit={handleSubmit}>
                <label>
                  Product name
                  <input
                    maxLength="200"
                    onChange={(event) => updateForm('name', event.target.value)}
                    ref={nameInputRef}
                    required
                    value={form.name}
                  />
                </label>
                <label>
                  SKU / internal code
                  <input
                    maxLength="64"
                    onChange={(event) => updateForm('sku', event.target.value)}
                    required
                    value={form.sku}
                  />
                </label>
                <label>
                  Category
                  <select
                    onChange={(event) => updateForm('category', event.target.value)}
                    required
                    value={form.category}
                  >
                    <option value="">Choose a category</option>
                    {options.categories.map((category) => (
                      <option key={category.id} value={category.id}>{category.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Base unit
                  <select
                    disabled={Boolean(editingId)}
                    onChange={(event) => updateForm('base_unit', event.target.value)}
                    required
                    value={form.base_unit}
                  >
                    <option value="">Choose a unit</option>
                    {options.units.map((unit) => (
                      <option key={unit.id} value={unit.id}>
                        {unit.name} ({unit.symbol})
                      </option>
                    ))}
                  </select>
                  {editingId && (
                    <small>
                      The base unit is fixed after creation so existing stock keeps its meaning.
                    </small>
                  )}
                </label>
                <label>
                  Company / brand
                  <select
                    onChange={(event) => updateForm('brand', event.target.value)}
                    value={form.brand}
                  >
                    <option value="">No brand</option>
                    {options.brands.map((brand) => (
                      <option key={brand.id} value={brand.id}>{brand.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Variety / type
                  <select
                    onChange={(event) => updateForm('variety', event.target.value)}
                    value={form.variety}
                  >
                    <option value="">No variety</option>
                    {availableVarieties.map((variety) => (
                      <option key={variety.id} value={variety.id}>{variety.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Purchase price (PKR)
                  <input
                    inputMode="decimal"
                    min="0"
                    onChange={(event) => updateForm('purchase_price', event.target.value)}
                    required
                    step="0.01"
                    type="number"
                    value={form.purchase_price}
                  />
                </label>
                <label>
                  Selling price (PKR)
                  <input
                    inputMode="decimal"
                    min="0"
                    onChange={(event) => updateForm('selling_price', event.target.value)}
                    required
                    step="0.01"
                    type="number"
                    value={form.selling_price}
                  />
                </label>
                <label>
                  Low-stock threshold
                  <input
                    inputMode="decimal"
                    min="0"
                    onChange={(event) => updateForm('low_stock_threshold', event.target.value)}
                    required
                    step="0.001"
                    type="number"
                    value={form.low_stock_threshold}
                  />
                </label>
                <label className="inactive-toggle">
                  <input
                    checked={form.allow_fractional_quantity}
                    onChange={(event) =>
                      updateForm('allow_fractional_quantity', event.target.checked)
                    }
                    type="checkbox"
                  />
                  Allow fractional quantities
                </label>
                <label>
                  Barcode (optional)
                  <input
                    maxLength="64"
                    onChange={(event) => updateForm('barcode', event.target.value)}
                    value={form.barcode}
                  />
                </label>
                <label className="product-description">
                  Description
                  <textarea
                    onChange={(event) => updateForm('description', event.target.value)}
                    rows="3"
                    value={form.description}
                  />
                </label>
                {editingId && (
                  <label className="inactive-toggle">
                    <input
                      checked={form.is_active}
                      onChange={(event) => updateForm('is_active', event.target.checked)}
                      type="checkbox"
                    />
                    Product is active
                  </label>
                )}
                <div className="product-form-actions">
                  <button disabled={saving} type="submit">
                    {saving ? 'Saving…' : editingId ? 'Save changes' : 'Create product'}
                  </button>
                  <button
                    className="button-secondary"
                    disabled={saving}
                    onClick={() => setShowForm(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </section>
          )}
        </>
      )}
    </main>
  )
}
