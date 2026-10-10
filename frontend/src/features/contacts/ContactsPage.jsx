import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import {
  createContact,
  getContactLedger,
  listContacts,
  updateContact,
} from '../../services/contactApi.js'
import { listSalesBranches } from '../../services/posApi.js'
import { listProductBranches } from '../../services/productApi.js'
import { formatMoneyCents, parseMoneyCents } from '../pos/money.js'

const EMPTY_FORM = {
  name: '',
  phone: '',
  address: '',
  account_reference: '',
  notes: '',
  is_active: true,
}

const CUSTOMER_ROLES = ['Admin', 'Manager', 'Cashier']
const SUPPLIER_ROLES = ['Admin', 'Manager', 'Inventory/Store Staff']

function entryTypeLabel(type) {
  return type.replaceAll('_', ' ')
}

function signedAmountCents(amount) {
  const isNegative = amount.startsWith('-')
  const absoluteAmount = parseMoneyCents(isNegative ? amount.slice(1) : amount)
  if (absoluteAmount === null) return null
  return isNegative ? -absoluteAmount : absoluteAmount
}

function formatPkrAmount(cents) {
  const formatted = formatMoneyCents(cents < 0n ? -cents : cents)
  const [whole, fraction] = formatted.split('.')
  return `PKR ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`
}

export default function ContactsPage() {
  const { type = 'customer' } = useParams()
  const isSupplier = type === 'suppliers'
  const contactType = isSupplier ? 'supplier' : 'customer'
  const singular = isSupplier ? 'Supplier' : 'Customer'
  const plural = isSupplier ? 'Suppliers' : 'Customers'
  const { user, loading: authLoading, signOut } = useAuth()
  const [branches, setBranches] = useState([])
  const [branchId, setBranchId] = useState('')
  const [contacts, setContacts] = useState([])
  const [search, setSearch] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [ledger, setLedger] = useState(null)
  const [ledgerError, setLedgerError] = useState('')
  const formRef = useRef(null)
  const nameInputRef = useRef(null)
  const allowedRoles = isSupplier ? SUPPLIER_ROLES : CUSTOMER_ROLES
  const permitted =
    user?.roles.some((role) => allowedRoles.includes(role)) ?? false

  useEffect(() => {
    if (authLoading || !user) return undefined
    if (!permitted) {
      setStatus('ready')
      return undefined
    }

    let active = true
    const branchRequest = isSupplier ? listProductBranches : listSalesBranches
    branchRequest()
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
  }, [authLoading, isSupplier, permitted, user])

  useEffect(() => {
    if (!branchId || !permitted) {
      if (!branchId) setContacts([])
      return undefined
    }

    let active = true
    setStatus('loading-branch')
    setError('')
    setLedger(null)
    listContacts(contactType, branchId, '', includeInactive)
      .then((branchContacts) => {
        if (!active) return
        setContacts(branchContacts)
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
  }, [branchId, contactType, includeInactive, permitted])

  const visibleContacts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return contacts.filter(
      (contact) =>
        !query ||
        contact.name.toLocaleLowerCase().includes(query) ||
        contact.phone.toLocaleLowerCase().includes(query),
    )
  }, [contacts, search])
  const selectedContact = contacts.find(
    (contact) => contact.id === ledger?.contact_id,
  )

  useEffect(() => {
    if (!showForm) return
    const focusForm = () => {
      formRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
      nameInputRef.current?.focus?.({ preventScroll: true })
    }
    if (window.requestAnimationFrame) window.requestAnimationFrame(focusForm)
    else focusForm()
  }, [showForm])

  function startCreate() {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
    setError('')
    setNotice('')
  }

  function startEdit(contact) {
    setEditingId(contact.id)
    setForm({
      name: contact.name,
      phone: contact.phone,
      address: contact.address,
      account_reference: contact.account_reference ?? '',
      notes: contact.notes,
      is_active: contact.is_active,
    })
    setShowForm(true)
    setError('')
    setNotice('')
  }

  async function reloadContacts() {
    setContacts(
      await listContacts(contactType, branchId, '', includeInactive),
    )
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setNotice('')
    setSaving(true)
    try {
      const payload = isSupplier
        ? form
        : {
            name: form.name,
            phone: form.phone,
            address: form.address,
            notes: form.notes,
            is_active: form.is_active,
          }
      if (editingId) {
        await updateContact(contactType, branchId, editingId, payload)
        setNotice(`${singular} details saved.`)
      } else {
        await createContact(contactType, branchId, payload)
        setNotice(`${singular} added.`)
      }
      await reloadContacts()
      setShowForm(false)
      setEditingId(null)
      setForm(EMPTY_FORM)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleLedger(contact) {
    setLedger(null)
    setLedgerError('')
    try {
      const details = await getContactLedger(contactType, branchId, contact.id)
      setLedger({ ...details, contact_id: contact.id })
    } catch (requestError) {
      setLedgerError(requestError.message)
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
    return <main className="pos-loading" role="status">Checking {plural.toLowerCase()} access…</main>
  }

  if (!permitted) {
    return (
      <main className="pos-shell">
        <section className="pos-notice" role="alert">
          <h1>{plural} access is restricted</h1>
          <p>Your current role cannot manage this contact list.</p>
          <Link to="/">Return to point of sale</Link>
        </section>
      </main>
    )
  }

  const balance = isSupplier
    ? ledger?.payable_balance
    : ledger?.balance
  const balanceAmount = balance?.startsWith('-') ? balance.slice(1) : balance
  const balanceLabel =
    balance === '0.00' || balance === '-0.00'
      ? `No outstanding balance: ${balanceAmount}`
      : isSupplier
        ? balance?.startsWith('-')
          ? `Supplier advance: ${balanceAmount}`
          : `Payable to supplier: ${balanceAmount}`
        : balance?.startsWith('-')
          ? `Customer advance: ${balanceAmount}`
          : `Customer owes: ${balanceAmount}`

  return (
    <main className="pos-shell">
      <WorkspaceHeader
        branchId={branchId}
        branches={branches}
        detail={`${singular} directory and branch ledger`}
        eyebrow="Organization contacts"
        onSignOut={handleSignOut}
        title={plural}
        user={user}
      />

      {branches.length > 1 && (
        <label className="branch-picker">
          {singular} branch
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
          <h2>No {singular.toLowerCase()} branch available</h2>
          <p>Ask an administrator to assign your account to an active branch.</p>
        </section>
      )}
      {status === 'loading-branch' && (
        <p role="status">Loading organization {plural.toLowerCase()}…</p>
      )}
      {status === 'error' && <p className="pos-error" role="alert">{error}</p>}

      {status === 'ready' && branchId && (
        <>
          <section className="catalog-toolbar" aria-label={`${plural} actions`}>
            <label className="search-field">
              Search {plural.toLowerCase()}
              <input
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name or phone"
                type="search"
                value={search}
              />
            </label>
            <label className="inactive-toggle">
              <input
                checked={includeInactive}
                onChange={(event) => setIncludeInactive(event.target.checked)}
                type="checkbox"
              />
              Include inactive
            </label>
            <button onClick={startCreate} type="button">Add {singular.toLowerCase()}</button>
          </section>
          {notice && <p className="success-message" role="status">{notice}</p>}
          {error && <p className="pos-error" role="alert">{error}</p>}

          <section aria-label={`${plural} summary`} className="contact-summary">
            <article className="contact-summary-card">
              <span>Directory records</span>
              <strong>{contacts.length}</strong>
            </article>
            <article className="contact-summary-card">
              <span>Active</span>
              <strong>{contacts.filter((contact) => contact.is_active).length}</strong>
            </article>
            <article className="contact-summary-card">
              <span>Inactive</span>
              <strong>{contacts.filter((contact) => !contact.is_active).length}</strong>
            </article>
          </section>

          <section className="pos-panel catalog-panel" aria-labelledby="contacts-heading">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Profiles are shared within the organization</p>
                <h2 id="contacts-heading">{plural}</h2>
              </div>
              <span className="item-count">{visibleContacts.length} records</span>
            </div>
            <div className="catalog-list">
              {visibleContacts.map((contact) => (
                <article className="catalog-product" key={contact.id}>
                  <div className="contact-identity">
                    <span aria-hidden="true" className="contact-initial">
                      {contact.name.trim().charAt(0).toLocaleUpperCase()}
                    </span>
                    <div className="catalog-product-main">
                      <h3>{contact.name}</h3>
                      {contact.name.startsWith('DEMO -') && (
                        <span className="ledger-demo-badge">Demo profile</span>
                      )}
                      <p>{contact.phone || 'No phone recorded'}</p>
                      {isSupplier && contact.account_reference && (
                        <p>Account: {contact.account_reference}</p>
                      )}
                      <span className={contact.is_active ? 'status-active' : 'status-inactive'}>
                        {contact.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </div>
                  <div className="catalog-product-meta">
                    <button
                      className="button-secondary"
                      onClick={() => handleLedger(contact)}
                      type="button"
                    >
                      View ledger
                    </button>
                    <button
                      className="button-secondary"
                      onClick={() => startEdit(contact)}
                      type="button"
                    >
                      Edit
                    </button>
                  </div>
                </article>
              ))}
              {!visibleContacts.length && (
                <p className="empty-state">
                  {search ? `No ${plural.toLowerCase()} match your search.` : `No ${plural.toLowerCase()} have been added yet.`}
                </p>
              )}
            </div>
          </section>

          {ledgerError && <p className="pos-error" role="alert">{ledgerError}</p>}
          {ledger && (
            <section className="pos-panel ledger-panel" aria-labelledby="ledger-heading">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Immutable branch ledger</p>
                  <h2 id="ledger-heading">{selectedContact?.name} balance</h2>
                </div>
                <button
                  className="button-secondary"
                  onClick={() => setLedger(null)}
                  type="button"
                >
                  Close ledger
                </button>
              </div>
              <p className="ledger-balance">{balanceLabel}</p>
              <div className="stock-list">
                {ledger.entries.map((entry) => {
                  const amountCents = signedAmountCents(entry.signed_amount)
                  const isDebit = amountCents === null
                    ? !entry.signed_amount.startsWith('-')
                    : isSupplier
                      ? amountCents < 0n
                      : amountCents >= 0n
                  return (
                    <article className="stock-row" key={entry.id}>
                      <div>
                        <div className="ledger-entry-meta">
                          <h3>{entryTypeLabel(entry.entry_type)}</h3>
                          <span className="ledger-type-badge">
                            {isDebit ? 'Debit' : 'Credit'}
                          </span>
                          {entry.reference?.startsWith('DEMO-') && (
                            <span className="ledger-demo-badge">Demo entry</span>
                          )}
                        </div>
                        <p>
                          {entry.reason}
                          {entry.reference ? ` · ${entry.reference}` : ''}
                        </p>
                        <p>
                          {new Date(entry.created_at).toLocaleString()}
                          {' · '}
                          {entry.created_by}
                        </p>
                      </div>
                      <strong
                        className={`ledger-entry-amount ${
                          isDebit ? 'is-debit' : 'is-credit'
                        }`}
                      >
                        {amountCents === null
                          ? 'Invalid amount'
                          : formatPkrAmount(amountCents)}
                    </strong>
                  </article>
                )
              })}
                {!ledger.entries.length && (
                  <p className="empty-state">No ledger entries for this branch.</p>
                )}
              </div>
            </section>
          )}

          {showForm && (
            <section
              className="pos-panel catalog-form-panel"
              aria-labelledby="contact-form-heading"
              ref={formRef}
            >
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{editingId ? 'Update contact details' : `New ${singular.toLowerCase()}`}</p>
                  <h2 id="contact-form-heading">
                    {editingId ? `Edit ${singular.toLowerCase()}` : `Add ${singular.toLowerCase()}`}
                  </h2>
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
                  Name
                  <input
                    maxLength="200"
                    onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                    ref={nameInputRef}
                    required
                    value={form.name}
                  />
                </label>
                <label>
                  Phone
                  <input
                    maxLength="32"
                    onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))}
                    value={form.phone}
                  />
                </label>
                {isSupplier && (
                  <label>
                    Supplier account reference
                    <input
                      maxLength="100"
                      onChange={(event) => setForm((current) => ({ ...current, account_reference: event.target.value }))}
                      value={form.account_reference}
                    />
                  </label>
                )}
                <label>
                  Address
                  <input
                    maxLength="500"
                    onChange={(event) => setForm((current) => ({ ...current, address: event.target.value }))}
                    value={form.address}
                  />
                </label>
                <label className="product-description">
                  Notes
                  <textarea
                    onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                    rows="3"
                    value={form.notes}
                  />
                </label>
                {editingId && (
                  <label className="inactive-toggle">
                    <input
                      checked={form.is_active}
                      onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))}
                      type="checkbox"
                    />
                    Contact is active
                  </label>
                )}
                <div className="product-form-actions">
                  <button disabled={saving} type="submit">
                    {saving ? 'Saving…' : editingId ? 'Save changes' : `Create ${singular.toLowerCase()}`}
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
