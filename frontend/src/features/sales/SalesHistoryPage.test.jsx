import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import SalesHistoryPage from './SalesHistoryPage.jsx'
import {
  getBranchSale,
  listBranchSales,
  listSalesBranches,
  listSalesReturns,
} from '../../services/posApi.js'

vi.mock('../auth/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  getBranchSale: vi.fn(),
  listBranchSales: vi.fn(),
  listSalesBranches: vi.fn(),
  listSalesReturns: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const user = {
  id: 1,
  username: 'shop-cashier',
  first_name: 'Shop',
  roles: ['Cashier'],
}

const sale = {
  id: 41,
  sale_number: 'SALE-000041',
  branch: 5,
  branch_name: 'Main Shop',
  organization_name: 'Farm Supply',
  customer: 9,
  customer_phone: '555-0100',
  customer_name_snapshot: 'Local Farmer',
  sale_date: '2026-10-08',
  notes: '',
  status: 'completed',
  subtotal: '40.00',
  discount_total: '2.00',
  tax_total: '0.50',
  total: '38.50',
  amount_paid: '20.00',
  balance_due: '18.50',
  change_due: '0.00',
  customer_advance_amount: '0.00',
  payment_method: 'Cash',
  payment_reference: 'TILL-4',
  completed_by: 'shop-cashier',
  created_by: 'shop-cashier',
  completed_at: '2026-10-08T01:45:00Z',
  items: [{
    id: 88,
    product: 12,
    product_name_snapshot: 'Maize Seed',
    sku_snapshot: 'MAIZE-01',
    unit_symbol_snapshot: 'packet',
    quantity: '2.000000',
    unit_price: '20.00',
    subtotal: '40.00',
    discount_amount: '2.00',
    tax_amount: '0.50',
    total: '38.50',
  }],
}

function renderHistory(path = '/sales') {
  useAuth.mockReturnValue({ user, loading: false, signOut: vi.fn() })
  listSalesBranches.mockResolvedValue([
    { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
  ])
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/sales" element={<SalesHistoryPage />} />
        <Route path="/sales/:saleId" element={<SalesHistoryPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('sales history workspace', () => {
  it('loads completed sales and applies branch-scoped search and status filters', async () => {
    listBranchSales.mockResolvedValue([sale])
    renderHistory()

    expect(await screen.findByRole('heading', { name: 'Sales history' })).toBeInTheDocument()
    expect(await screen.findByText('SALE-000041')).toBeInTheDocument()
    expect(screen.getAllByText('38.50').length).toBeGreaterThan(0)
    expect(listBranchSales).toHaveBeenCalledWith('5', {
      status: 'completed',
      search: '',
    })

    fireEvent.change(screen.getByLabelText('Search customer, product, or SKU'), {
      target: { value: 'MAIZE-01' },
    })
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() =>
      expect(listBranchSales).toHaveBeenLastCalledWith('5', {
        status: '',
        search: 'MAIZE-01',
      }),
    )
  })

  it('shows read-only receipt details and customer debt using historical snapshots', async () => {
    getBranchSale.mockResolvedValue(sale)
    listSalesReturns.mockResolvedValue([])
    renderHistory('/sales/41')

    expect(await screen.findByRole('heading', { name: 'Sale details' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Local Farmer' })).toBeInTheDocument()
    expect(screen.getAllByText('Maize Seed').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('SKU MAIZE-01 · 2.000000 packet · Unit price 20.00'))
      .toBeInTheDocument()
    expect(screen.getByText('18.50')).toBeInTheDocument()
    expect(screen.getByText(/Historical product names and prices/)).toBeInTheDocument()
    expect(getBranchSale).toHaveBeenCalledWith('5', '41')
  })

  it('blocks roles without branch sales permission', async () => {
    useAuth.mockReturnValue({
      user: { ...user, roles: ['Inventory/Store Staff'] },
      loading: false,
      signOut: vi.fn(),
    })
    render(
      <MemoryRouter>
        <SalesHistoryPage />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Sales history access is restricted' }))
      .toBeInTheDocument()
    expect(listSalesBranches).not.toHaveBeenCalled()
  })
})
