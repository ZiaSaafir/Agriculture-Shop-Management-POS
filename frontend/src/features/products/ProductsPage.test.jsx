import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthContext.jsx'
import ProductsPage from './ProductsPage.jsx'
import {
  createProduct,
  getProductCatalogOptions,
  listProductBranches,
  listProducts,
  updateProduct,
} from '../../services/productApi.js'

vi.mock('../../services/productApi.js', () => ({
  createProduct: vi.fn(),
  getProductCatalogOptions: vi.fn(),
  listProductBranches: vi.fn(),
  listProducts: vi.fn(),
  updateProduct: vi.fn(),
}))

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (data === null ? '' : JSON.stringify(data)),
  }
}

function renderCatalog(roles = ['Manager'], catalogProducts = []) {
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
  listProductBranches.mockResolvedValue([
    { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
  ])
  getProductCatalogOptions.mockResolvedValue({
    categories: [{ id: 2, name: 'Seeds' }],
    brands: [{ id: 3, name: 'Green Fields' }],
    varieties: [{ id: 4, name: 'Hybrid A', category_id: 2 }],
    units: [{ id: 6, name: 'Packet', symbol: 'pkt', decimal_places: 0 }],
  })
  listProducts.mockResolvedValue(catalogProducts)

  return render(
    <MemoryRouter>
      <AuthProvider>
        <ProductsPage />
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

describe('product catalog screen', () => {
  it('labels product pricing as PKR and warns that demo prices need local confirmation', async () => {
    renderCatalog(['Manager'], [
      {
        id: 11,
        category: 2,
        base_unit: 6,
        name: 'Sona Urea 46% N — 50 kg bag',
        sku: 'FERT-UREA-50',
        barcode: '',
        selling_price: '5200.00',
        is_active: true,
      },
    ])

    expect(
      await screen.findByText(
        (_, element) =>
          element.tagName === 'P' &&
          element.textContent.includes('PKR 5200.00 / pkt'),
      ),
    ).toBeInTheDocument()
    expect(screen.getByText(/Prices are displayed in PKR/)).toBeInTheDocument()
  })

  it('creates an organization product with decimal prices and configured unit', async () => {
    createProduct.mockResolvedValue({ id: 70 })
    renderCatalog()
    await screen.findByRole('heading', { name: 'Catalog items' })
    fireEvent.click(screen.getByRole('button', { name: 'Add product' }))

    fireEvent.change(screen.getByLabelText('Product name'), {
      target: { value: 'Hybrid Seed' },
    })
    fireEvent.change(screen.getByLabelText('SKU / internal code'), {
      target: { value: 'HYBRID-001' },
    })
    fireEvent.change(screen.getByLabelText('Category'), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByLabelText('Base unit'), {
      target: { value: '6' },
    })
    fireEvent.change(screen.getByLabelText('Company / brand'), {
      target: { value: '3' },
    })
    fireEvent.change(screen.getByLabelText('Variety / type'), {
      target: { value: '4' },
    })
    fireEvent.change(screen.getByLabelText('Purchase price (PKR)'), {
      target: { value: '11.25' },
    })
    fireEvent.change(screen.getByLabelText('Selling price (PKR)'), {
      target: { value: '15.50' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create product' }))

    expect(await screen.findByText('Product added to this organization catalog.')).toBeInTheDocument()
    expect(createProduct).toHaveBeenCalledWith('5', {
      category: 2,
      brand: 3,
      variety: 4,
      base_unit: 6,
      name: 'Hybrid Seed',
      sku: 'HYBRID-001',
      barcode: '',
      description: '',
      purchase_price: '11.25',
      selling_price: '15.50',
      low_stock_threshold: '0',
      allow_fractional_quantity: false,
      is_active: true,
    })
  })

  it('does not expose catalog management to cashiers', async () => {
    renderCatalog(['Cashier'])
    expect(await screen.findByRole('heading', { name: 'Catalog access is restricted' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return to point of sale' })).toBeInTheDocument()
    expect(getProductCatalogOptions).not.toHaveBeenCalled()
    expect(listProducts).not.toHaveBeenCalled()
    expect(updateProduct).not.toHaveBeenCalled()
  })
})
