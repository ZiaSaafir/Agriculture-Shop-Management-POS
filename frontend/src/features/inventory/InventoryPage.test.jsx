import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthContext.jsx'
import InventoryPage from './InventoryPage.jsx'
import {
  listBranchMovements,
  recordInventoryMovement,
} from '../../services/inventoryApi.js'
import { listBranchStock } from '../../services/posApi.js'
import { listProductBranches } from '../../services/productApi.js'

vi.mock('../../services/inventoryApi.js', () => ({
  listBranchMovements: vi.fn(),
  recordInventoryMovement: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  listBranchStock: vi.fn(),
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

function renderInventory(roles = ['Inventory/Store Staff']) {
  document.cookie = 'csrftoken=test-token; path=/'
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
      .mockResolvedValueOnce(
        response(200, {
          id: 1,
          username: 'store-staff',
          first_name: 'Store',
          roles,
        }),
      ),
  )
  listProductBranches.mockResolvedValue([
    { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
  ])
  listBranchStock.mockResolvedValue([
    {
      id: 7,
      name: 'Garden Seed',
      sku: 'SEED-01',
      unit: 'packet',
      quantity_decimal_places: 0,
      selling_price: '4.25',
      low_stock_threshold: '5.000',
      on_hand: '4.000000',
      is_active: true,
    },
  ])
  listBranchMovements.mockResolvedValue([])

  return render(
    <MemoryRouter>
      <AuthProvider>
        <InventoryPage />
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

describe('inventory screen', () => {
  it('shows low stock and records an attributed manual movement', async () => {
    recordInventoryMovement.mockResolvedValue({ id: 99 })
    renderInventory()
    await screen.findByRole('heading', { name: 'Stock on hand' })

    expect(screen.getAllByText('Low stock').length).toBeGreaterThan(0)
    fireEvent.change(screen.getByLabelText('Product'), {
      target: { value: '7' },
    })
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Physical count correction' },
    })
    fireEvent.change(screen.getByLabelText('Movement type'), {
      target: { value: 'adjustment_in' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Record stock movement' }))

    expect(await screen.findByText('Stock movement recorded.')).toBeInTheDocument()
    expect(recordInventoryMovement).toHaveBeenCalledWith('5', {
      product: 7,
      movement_type: 'adjustment_in',
      quantity: '2',
      reason: 'Physical count correction',
      reference: '',
    })
  })

  it('does not request management data for a cashier role', async () => {
    renderInventory(['Cashier'])
    expect(await screen.findByRole('heading', { name: 'Inventory management is restricted' })).toBeInTheDocument()
    expect(listProductBranches).not.toHaveBeenCalled()
    expect(listBranchStock).not.toHaveBeenCalled()
    expect(recordInventoryMovement).not.toHaveBeenCalled()
  })
})
