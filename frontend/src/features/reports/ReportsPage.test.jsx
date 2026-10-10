import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import ReportsPage from './ReportsPage.jsx'
import {
  getBranchOperationalReport,
  listSalesBranches,
} from '../../services/posApi.js'

vi.mock('../auth/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  getBranchOperationalReport: vi.fn(),
  listSalesBranches: vi.fn(),
}))

vi.mock('../../services/productApi.js', () => ({
  listProductBranches: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const report = {
  branch: { id: 5, name: 'Main Shop' },
  range: { start_date: '2026-10-01', end_date: '2026-10-08' },
  sales: {
    count: 1,
    gross: '100.00',
    returns: '25.00',
    net: '75.00',
    discounts: '5.00',
    amount_received: '75.00',
    returns_by_disposition: [
      { disposition: 'store_credit', count: 1, total: '25.00' },
    ],
    by_payment_method: [
      { payment_method: 'Cash', count: 1, gross: '100.00', received: '75.00' },
    ],
  },
  purchases: {
    count: 1,
    gross: '40.00',
    returns: '0.00',
    net: '40.00',
    by_supplier: [{ supplier_name_snapshot: 'Seed Co', count: 1, gross: '40.00' }],
  },
  receivables: '10.00',
  supplier_payables: '20.00',
  inventory: {
    low_stock_count: 2,
    movement_counts: [{ movement_type: 'sale', count: 1 }],
  },
  daily_sales: [
    {
      date: '2026-10-08',
      sales: '100.00',
      returns: '25.00',
      net_sales: '75.00',
    },
  ],
  top_products: [],
}

describe('branch operational reports', () => {
  it('loads branch aggregates, return breakdown, and server-side date filters', async () => {
    useAuth.mockReturnValue({
      user: {
        id: 1,
        username: 'manager',
        first_name: 'Shop',
        roles: ['Manager'],
      },
      loading: false,
      signOut: vi.fn(),
    })
    listSalesBranches.mockResolvedValue([
      { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
    ])
    getBranchOperationalReport.mockResolvedValue(report)

    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Business reports' }))
      .toBeInTheDocument()
    expect((await screen.findAllByText('PKR 75.00')).length).toBeGreaterThan(0)
    expect(screen.getByText('PKR 20.00')).toBeInTheDocument()
    expect(screen.getByText('Store credit')).toBeInTheDocument()
    expect(screen.getByText(/Profit, cost of goods sold/)).toBeInTheDocument()
    await waitFor(() =>
      expect(getBranchOperationalReport).toHaveBeenCalledWith(
        '5',
        expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      ),
    )

    fireEvent.change(screen.getByLabelText('From'), {
      target: { value: '2026-10-02' },
    })
    await waitFor(() =>
      expect(getBranchOperationalReport).toHaveBeenLastCalledWith(
        '5',
        '2026-10-02',
        expect.any(String),
      ),
    )
  })

  it('filters visible report sections without changing the selected date range', async () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'manager', roles: ['Manager'] },
      loading: false,
      signOut: vi.fn(),
    })
    listSalesBranches.mockResolvedValue([
      { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
    ])
    getBranchOperationalReport.mockResolvedValue(report)

    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>,
    )

    await screen.findByRole('heading', { name: 'Daily sales trend' })
    fireEvent.click(screen.getByRole('tab', { name: 'Purchases' }))
    expect(screen.getByRole('heading', { name: 'Purchases by supplier' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Daily sales trend' }))
      .not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Purchases' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })
})
