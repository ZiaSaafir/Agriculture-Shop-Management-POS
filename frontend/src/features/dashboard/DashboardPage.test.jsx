import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import DashboardPage from './DashboardPage.jsx'
import {
  getBranchOperationalReport,
  listBranchSales,
  listBranchStock,
  listSalesBranches,
} from '../../services/posApi.js'
import { listProductBranches } from '../../services/productApi.js'
import {
  listPurchases,
  listSupplierInvoiceBalances,
} from '../../services/procurementApi.js'

vi.mock('../auth/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  getBranchOperationalReport: vi.fn(),
  listBranchSales: vi.fn(),
  listBranchStock: vi.fn(),
  listSalesBranches: vi.fn(),
}))

vi.mock('../../services/productApi.js', () => ({
  listProductBranches: vi.fn(),
}))

vi.mock('../../services/procurementApi.js', () => ({
  listPurchases: vi.fn(),
  listSupplierInvoiceBalances: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderDashboard(roles) {
  useAuth.mockReturnValue({
    user: { id: 1, username: 'shop-user', first_name: 'Shop', roles },
    loading: false,
    signOut: vi.fn(),
  })
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

describe('branch operations dashboard', () => {
  it('summarizes current-day sales, stock alerts, receiving, and invoice balances', async () => {
    const today = new Date()
    const localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60_000)
      .toISOString()
      .slice(0, 10)
    const yesterday = new Date(today.getTime() - 86_400_000)
    const localYesterday = new Date(
      yesterday.getTime() - yesterday.getTimezoneOffset() * 60_000,
    ).toISOString().slice(0, 10)
    listSalesBranches.mockResolvedValue([
      { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
    ])
    listBranchStock.mockResolvedValue([
      {
        id: 7,
        name: 'Maize Seed',
        sku: 'MAIZE-01',
        unit: 'packet',
        quantity_decimal_places: 0,
        low_stock_threshold: '5.000',
        on_hand: '4.000000',
        is_active: true,
      },
      {
        id: 8,
        name: 'Fertilizer',
        sku: 'FERT-01',
        unit: 'kg',
        quantity_decimal_places: 3,
        low_stock_threshold: '1.000',
        on_hand: '9.000000',
        is_active: true,
      },
    ])
    listBranchSales.mockResolvedValue([
      { id: 1, status: 'completed', sale_date: localToday, total: '12.50' },
      { id: 2, status: 'completed', sale_date: localToday, total: '7.25' },
      { id: 3, status: 'completed', sale_date: localYesterday, total: '99.00' },
    ])
    getBranchOperationalReport.mockResolvedValue({
      daily_sales: [{ date: localToday, sales: '19.75', returns: '0.00', net_sales: '19.75' }],
    })
    listPurchases.mockResolvedValue([
      { id: 4, status: 'posted', purchase_date: localToday, total: '40.00' },
      { id: 5, status: 'posted', purchase_date: localYesterday, total: '90.00' },
    ])
    listSupplierInvoiceBalances.mockResolvedValue([
      { purchase_id: 6, outstanding_amount: '16.40' },
      { purchase_id: 7, outstanding_amount: '3.60' },
    ])

    renderDashboard(['Admin'])
    expect(await screen.findByRole('heading', { name: 'Today at a glance' }))
      .toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Sales today/ })).toHaveTextContent('19.75')
    expect(screen.getByRole('link', { name: /Low-stock products/ })).toHaveTextContent('1')
    expect(screen.getByRole('link', { name: /Supplier invoices outstanding/ }))
      .toHaveTextContent('20.00')
    expect(screen.getByRole('link', { name: /Purchases received today/ }))
      .toHaveTextContent('40.00')
    expect(screen.getByText('Maize Seed')).toBeInTheDocument()
    expect(screen.queryByText('Fertilizer')).not.toBeInTheDocument()
    expect(screen.getByText(/not an accounting report/i)).toBeInTheDocument()
  })

  it('shows only cashier-authorized sales and stock figures', async () => {
    listSalesBranches.mockResolvedValue([
      { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
    ])
    listBranchStock.mockResolvedValue([])
    listBranchSales.mockResolvedValue([])
    getBranchOperationalReport.mockResolvedValue({ daily_sales: [] })

    renderDashboard(['Cashier'])
    expect(await screen.findByRole('heading', { name: 'Today at a glance' }))
      .toBeInTheDocument()
    expect(screen.getByText('Sales today')).toBeInTheDocument()
    expect(screen.getByText('Active stock items')).toBeInTheDocument()
    expect(screen.queryByText('Supplier invoices outstanding')).not.toBeInTheDocument()
    expect(listPurchases).not.toHaveBeenCalled()
    expect(listSupplierInvoiceBalances).not.toHaveBeenCalled()
    expect(listProductBranches).not.toHaveBeenCalled()
  })

  it('uses inventory-accessible branches for inventory-only roles', async () => {
    listProductBranches.mockResolvedValue([
      { id: 12, name: 'Store', organization: 'Farm Supply' },
    ])
    listBranchStock.mockResolvedValue([])
    listPurchases.mockResolvedValue([])
    listSupplierInvoiceBalances.mockResolvedValue([])

    renderDashboard(['Inventory/Store Staff'])
    await screen.findByRole('heading', { name: 'Today at a glance' })
    await waitFor(() => expect(listBranchStock).toHaveBeenCalledWith('12'))
    expect(listSalesBranches).not.toHaveBeenCalled()
    expect(listBranchSales).not.toHaveBeenCalled()
    expect(screen.queryByText('Sales today')).not.toBeInTheDocument()
    expect(screen.getByText('Purchases received today')).toBeInTheDocument()
  })

  it('does not grant dashboard access to roles without relevant branch permissions', async () => {
    renderDashboard(['No role'])
    expect(await screen.findByRole('heading', { name: 'Dashboard access is not configured' }))
      .toBeInTheDocument()
    expect(listSalesBranches).not.toHaveBeenCalled()
    expect(listProductBranches).not.toHaveBeenCalled()
  })
})
