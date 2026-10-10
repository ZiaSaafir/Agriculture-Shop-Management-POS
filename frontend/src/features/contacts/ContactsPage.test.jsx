import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthContext.jsx'
import ContactsPage from './ContactsPage.jsx'
import {
  createContact,
  getContactLedger,
  listContacts,
  updateContact,
} from '../../services/contactApi.js'
import { listSalesBranches } from '../../services/posApi.js'
import { listProductBranches } from '../../services/productApi.js'

vi.mock('../../services/contactApi.js', () => ({
  createContact: vi.fn(),
  getContactLedger: vi.fn(),
  listContacts: vi.fn(),
  updateContact: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  listSalesBranches: vi.fn(),
}))

vi.mock('../../services/productApi.js', () => ({
  listProductBranches: vi.fn(),
}))

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (data === null ? '' : JSON.stringify(data)),
  }
}

function renderContacts(type, roles) {
  document.cookie = 'csrftoken=test-token; path=/'
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
      .mockResolvedValueOnce(
        response(200, {
          id: 1,
          username: 'shop-manager',
          first_name: 'Shop',
          roles,
        }),
      ),
  )
  listSalesBranches.mockResolvedValue([
    { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
  ])
  listProductBranches.mockResolvedValue([
    { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
  ])
  listContacts.mockResolvedValue([
    {
      id: 9,
      name: type === 'customers' ? 'Local Farmer' : 'Seed Company',
      phone: '555-0100',
      address: '',
      account_reference: type === 'suppliers' ? 'ACCT-1' : undefined,
      notes: '',
      is_active: true,
    },
  ])

  return render(
    <MemoryRouter initialEntries={[`/contacts/${type}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/contacts/:type" element={<ContactsPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
})

describe('customer and supplier workspaces', () => {
  it('creates a customer and presents its branch ledger as read-only', async () => {
    createContact.mockResolvedValue({ id: 10 })
    getContactLedger.mockResolvedValue({
      customer: { id: 9, name: 'Local Farmer' },
      branch_id: 5,
      balance: '7017.00',
      entries: [
        {
          id: 1,
          entry_type: 'sale',
          signed_amount: '17.00',
          reason: 'Sale SALE-000001',
          reference: 'SALE-000001',
          created_at: '2026-10-08T12:00:00Z',
          created_by: 'cashier',
        },
        {
          id: 2,
          entry_type: 'opening_debit',
          signed_amount: '8500.00',
          reason: 'DEMO ONLY - assumed opening amount due.',
          reference: 'DEMO-CUST-EXAMPLE',
          created_at: '2026-10-08T11:00:00Z',
          created_by: 'admin',
        },
        {
          id: 3,
          entry_type: 'opening_credit',
          signed_amount: '-1500.00',
          reason: 'DEMO ONLY - assumed customer credit.',
          reference: 'DEMO-CUST-CREDIT',
          created_at: '2026-10-08T10:00:00Z',
          created_by: 'admin',
        },
      ],
    })
    renderContacts('customers', ['Manager'])
    await screen.findByRole('button', { name: 'View ledger' })

    fireEvent.click(screen.getByRole('button', { name: 'View ledger' }))
    expect(await screen.findByText('Customer owes: 7017.00')).toBeInTheDocument()
    expect(screen.getByText('Sale SALE-000001 · SALE-000001')).toBeInTheDocument()
    expect(screen.getAllByText('Demo entry')).toHaveLength(2)
    expect(screen.getByText('PKR 8,500.00')).toBeInTheDocument()
    expect(screen.getAllByText('Debit')).toHaveLength(2)
    expect(screen.getByText('PKR 1,500.00')).toBeInTheDocument()
    expect(screen.getByText('Credit')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add customer' }))
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Another Farmer' },
    })
    fireEvent.change(screen.getByLabelText('Phone'), {
      target: { value: '555-0101' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create customer' }))

    expect(await screen.findByText('Customer added.')).toBeInTheDocument()
    expect(createContact).toHaveBeenCalledWith('customer', '5', {
      name: 'Another Farmer',
      phone: '555-0101',
      address: '',
      notes: '',
      is_active: true,
    })
    expect(updateContact).not.toHaveBeenCalled()
  })

  it('uses supplier-scoped branches and keeps supplier payable ledger read-only', async () => {
    getContactLedger.mockResolvedValue({
      supplier: { id: 9, name: 'Seed Company' },
      branch_id: 5,
      payable_balance: '32500.00',
      entries: [
        {
          id: 1,
          entry_type: 'opening_payable',
          signed_amount: '37500.00',
          reason: 'DEMO ONLY - assumed supplier payable.',
          reference: 'DEMO-SUP-PAYABLE',
          created_at: '2026-10-08T12:00:00Z',
          created_by: 'admin',
        },
        {
          id: 2,
          entry_type: 'opening_advance',
          signed_amount: '-5000.00',
          reason: 'DEMO ONLY - assumed advance.',
          reference: 'DEMO-SUP-ADVANCE',
          created_at: '2026-10-08T11:00:00Z',
          created_by: 'admin',
        },
      ],
    })
    renderContacts('suppliers', ['Inventory/Store Staff'])
    await screen.findByRole('button', { name: 'View ledger' })

    fireEvent.click(screen.getByRole('button', { name: 'View ledger' }))
    expect(await screen.findByText('Payable to supplier: 32500.00')).toBeInTheDocument()
    expect(screen.getByText('PKR 37,500.00')).toBeInTheDocument()
    expect(screen.getByText('PKR 5,000.00')).toBeInTheDocument()
    expect(screen.getByText('Debit')).toBeInTheDocument()
    expect(screen.getByText('Credit')).toBeInTheDocument()
    expect(listProductBranches).toHaveBeenCalled()
    expect(listSalesBranches).not.toHaveBeenCalled()
  })

  it('does not expose suppliers to cashiers', async () => {
    renderContacts('suppliers', ['Cashier'])
    expect(await screen.findByRole('heading', { name: 'Suppliers access is restricted' })).toBeInTheDocument()
    expect(listProductBranches).not.toHaveBeenCalled()
    expect(listContacts).not.toHaveBeenCalled()
  })
})
