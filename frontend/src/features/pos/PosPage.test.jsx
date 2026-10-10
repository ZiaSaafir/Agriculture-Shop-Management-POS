import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthContext.jsx'
import PosPage from './PosPage.jsx'
import {
  checkoutSale,
  createSaleDraft,
  listBranchCustomers,
  listBranchStock,
  listSalesBranches,
  updateSaleDraft,
} from '../../services/posApi.js'

vi.mock('../../services/posApi.js', () => ({
  checkoutSale: vi.fn(),
  createSaleDraft: vi.fn(),
  listBranchCustomers: vi.fn(),
  listBranchStock: vi.fn(),
  listSalesBranches: vi.fn(),
  updateSaleDraft: vi.fn(),
}))

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (data === null ? '' : JSON.stringify(data)),
  }
}

function renderPos(stock = [
  {
    id: 7,
    name: 'Garden Seed',
    sku: 'SEED-01',
    unit: 'packet',
    base_unit: 11,
    quantity_decimal_places: 0,
    fractional_quantity: false,
    available_units: [
      {
        id: 11,
        name: 'Packet',
        symbol: 'packet',
        decimal_places: 0,
        base_multiplier: '1',
      },
    ],
    selling_price: '4.25',
    on_hand: '6.000000',
    is_active: true,
  },
]) {
  document.cookie = 'csrftoken=test-token; path=/'
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
      .mockResolvedValueOnce(
        response(200, {
          id: 1,
          username: 'shop-cashier',
          first_name: 'Shop',
          roles: ['Cashier'],
        }),
      ),
  )
  listSalesBranches.mockResolvedValue([
    { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
  ])
  listBranchStock.mockResolvedValue(stock)
  listBranchCustomers.mockResolvedValue([
    { id: 9, name: 'Local Farmer', phone: '555-0100' },
  ])

  return render(
    <MemoryRouter>
      <AuthProvider>
        <PosPage />
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

describe('POS checkout screen', () => {
  it('creates and checks out a walk-in sale from the branch catalog', async () => {
    createSaleDraft.mockResolvedValue({ id: 41 })
    checkoutSale.mockResolvedValue({
      id: 41,
      sale_number: 'SALE-000041',
      sale_date: '2026-10-08',
      organization_name: 'Farm Supply',
      branch_name: 'Main Shop',
      customer_name_snapshot: 'Walk-in',
      items: [],
      subtotal: '8.50',
      discount_total: '0.00',
      tax_total: '0.00',
      status: 'completed',
      total: '8.50',
      amount_paid: '8.50',
      balance_due: '0.00',
      change_due: '0.00',
      customer_advance_amount: '0.00',
    })

    renderPos()
    await screen.findByRole('heading', { name: 'Products' })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Quantity for Garden Seed' }), {
      target: { value: '2' },
    })
    expect(screen.getAllByText('8.50').length).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText('Payment method'), {
      target: { value: 'Cash' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Complete sale' }))

    expect(await screen.findByRole('heading', { name: 'SALE-000041' })).toBeInTheDocument()
    expect(createSaleDraft).toHaveBeenCalledWith('5', {
      customer: null,
      items: [
        {
          product: 7,
          quantity: '2',
          transaction_unit: 11,
          unit_price: '4.25',
          discount_amount: '0.00',
          tax_amount: '0.00',
        },
      ],
    })
    expect(checkoutSale).toHaveBeenCalledWith('5', 41, {
      amount_paid: '8.50',
      payment_method: 'Cash',
    })
  })

  it('keeps a saved draft and retries checkout after a server rejection', async () => {
    createSaleDraft.mockResolvedValue({ id: 52 })
    checkoutSale
      .mockRejectedValueOnce(new Error('Insufficient stock.'))
      .mockResolvedValueOnce({
        id: 52,
        sale_number: 'SALE-000052',
        sale_date: '2026-10-08',
        organization_name: 'Farm Supply',
        branch_name: 'Main Shop',
        customer_name_snapshot: 'Walk-in',
        items: [],
        subtotal: '4.25',
        discount_total: '0.00',
        tax_total: '0.00',
        status: 'completed',
        total: '4.25',
        amount_paid: '4.25',
        balance_due: '0.00',
        change_due: '0.00',
        customer_advance_amount: '0.00',
      })

    renderPos()
    await screen.findByRole('heading', { name: 'Products' })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.change(screen.getByLabelText('Payment method'), {
      target: { value: 'Cash' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Complete sale' }))
    expect(await screen.findByText(/Draft saved\. Checkout did not complete/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry checkout' }))
    expect(await screen.findByRole('heading', { name: 'SALE-000052' })).toBeInTheDocument()
    expect(updateSaleDraft).toHaveBeenCalledWith('5', 52, {
      customer: null,
      items: [
        {
          product: 7,
          quantity: '1',
          transaction_unit: 11,
          unit_price: '4.25',
          discount_amount: '0.00',
          tax_amount: '0.00',
        },
      ],
    })
  })

  it('allows a registered customer to complete a zero-tender credit sale', async () => {
    createSaleDraft.mockResolvedValue({ id: 61 })
    checkoutSale.mockResolvedValue({
      id: 61,
      sale_number: 'SALE-000061',
      sale_date: '2026-10-08',
      organization_name: 'Farm Supply',
      branch_name: 'Main Shop',
      customer_name_snapshot: 'Local Farmer',
      items: [],
      subtotal: '4.25',
      discount_total: '0.00',
      tax_total: '0.00',
      status: 'completed',
      total: '4.25',
      amount_paid: '0.00',
      balance_due: '4.25',
      change_due: '0.00',
      customer_advance_amount: '0.00',
    })
    renderPos()
    await screen.findByRole('heading', { name: 'Products' })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.change(screen.getByLabelText('Customer'), {
      target: { value: '9' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Complete sale' }))

    await waitFor(() =>
      expect(checkoutSale).toHaveBeenCalledWith('5', 61, {
        amount_paid: '0.00',
        payment_method: '',
      }),
    )
  })

  it('uses configured unit factors and the selected unit for checkout', async () => {
    const stock = [
      {
        id: 8,
        name: 'Crop Nutrient',
        sku: 'NUTRIENT-01',
        unit: 'kg',
        base_unit: 21,
        quantity_decimal_places: 3,
        fractional_quantity: true,
        available_units: [
          {
            id: 21,
            name: 'Kilogram',
            symbol: 'kg',
            decimal_places: 3,
            base_multiplier: '1',
          },
          {
            id: 22,
            name: 'Gram',
            symbol: 'g',
            decimal_places: 0,
            base_multiplier: '0.001',
          },
        ],
        selling_price: '1000.00',
        on_hand: '5.000000',
        is_active: true,
      },
    ]
    createSaleDraft.mockResolvedValue({ id: 71 })
    checkoutSale.mockResolvedValue({
      id: 71,
      sale_number: 'SALE-000071',
      sale_date: '2026-10-08',
      organization_name: 'Farm Supply',
      branch_name: 'Main Shop',
      customer_name_snapshot: 'Walk-in',
      items: [],
      subtotal: '1000.00',
      discount_total: '0.00',
      tax_total: '0.00',
      status: 'completed',
      total: '1000.00',
      amount_paid: '1000.00',
      balance_due: '0.00',
      change_due: '0.00',
      customer_advance_amount: '0.00',
    })

    renderPos(stock)
    await screen.findByRole('heading', { name: 'Products' })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    fireEvent.change(screen.getByLabelText('Unit for Crop Nutrient'), {
      target: { value: '22' },
    })
    fireEvent.change(screen.getByLabelText('Quantity for Crop Nutrient'), {
      target: { value: '1000' },
    })
    expect(screen.getAllByText('1000.00').length).toBeGreaterThan(0)
    fireEvent.change(screen.getByLabelText('Payment method'), {
      target: { value: 'Cash' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Complete sale' }))

    await waitFor(() =>
      expect(createSaleDraft).toHaveBeenCalledWith('5', {
        customer: null,
        items: [
          {
            product: 8,
            quantity: '1000',
            transaction_unit: 22,
            unit_price: '1.00',
            discount_amount: '0.00',
            tax_amount: '0.00',
          },
        ],
      }),
    )
  })
})
