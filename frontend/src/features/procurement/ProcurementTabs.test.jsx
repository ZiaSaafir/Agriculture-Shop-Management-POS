import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ProcurementPage from './ProcurementPage.jsx'
import PurchasesTab from './PurchasesTab.jsx'
import SupplierPaymentsTab from './SupplierPaymentsTab.jsx'
import PurchaseReturnsTab from './PurchaseReturnsTab.jsx'
import { useAuth } from '../auth/AuthContext.jsx'
import { listContacts } from '../../services/contactApi.js'
import { listBranchStock } from '../../services/posApi.js'
import { listProductBranches, listProducts } from '../../services/productApi.js'
import {
  createPurchaseDraft,
  createPurchaseReturnDraft,
  createSupplierPayment,
  getPurchase,
  listPurchaseReturns,
  listPurchases,
  listSupplierInvoiceBalances,
  listSupplierPayments,
  postPurchaseReturn,
  receivePurchase,
} from '../../services/procurementApi.js'

vi.mock('../../services/procurementApi.js', () => ({
  createPurchaseDraft: vi.fn(),
  createPurchaseReturnDraft: vi.fn(),
  createSupplierPayment: vi.fn(),
  getPurchase: vi.fn(),
  listPurchaseReturns: vi.fn(),
  listPurchases: vi.fn(),
  listSupplierInvoiceBalances: vi.fn(),
  listSupplierPayments: vi.fn(),
  postPurchaseReturn: vi.fn(),
  receivePurchase: vi.fn(),
}))

vi.mock('../auth/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../services/contactApi.js', () => ({
  listContacts: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  listBranchStock: vi.fn(),
}))

vi.mock('../../services/productApi.js', () => ({
  listProductBranches: vi.fn(),
  listProducts: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const supplier = { id: 3, name: 'Green Fields Supply' }
const product = {
  id: 7,
  name: 'Garden Seed',
  sku: 'SEED-01',
  unit: 'packet',
  quantity_decimal_places: 0,
  purchase_price: '2.25',
  is_active: true,
}

const draftPurchase = {
  id: 41,
  purchase_number: 'PUR-000041',
  supplier: supplier.id,
  supplier_name_snapshot: supplier.name,
  supplier_invoice_number: 'GF-882',
  purchase_date: '2026-06-04',
  notes: '',
  status: 'draft',
  subtotal: '4.50',
  discount_total: '0.00',
  tax_total: '0.00',
  total: '4.50',
  items: [{
    id: 55,
    product: product.id,
    product_name_snapshot: product.name,
    sku_snapshot: product.sku,
    unit_symbol_snapshot: product.unit,
    quantity: '2.000000',
    unit_cost: '2.25',
    subtotal: '4.50',
    discount_amount: '0.00',
    tax_amount: '0.00',
    total: '4.50',
  }],
}

describe('procurement workflows', () => {
  it('keeps draft form state while switching workflows and restricts cashier accounts', async () => {
    useAuth.mockReturnValue({
      user: {
        id: 1,
        username: 'store-staff',
        first_name: 'Store',
        roles: ['Inventory/Store Staff'],
      },
      loading: false,
      signOut: vi.fn(),
    })
    listProductBranches.mockResolvedValue([
      { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
    ])
    listContacts.mockResolvedValue([supplier])
    listProducts.mockResolvedValue([product])
    listBranchStock.mockResolvedValue([
      {
        product: product.id,
        unit: product.unit,
        quantity_decimal_places: 0,
        on_hand: '12.000000',
      },
    ])
    listPurchases.mockResolvedValue([])
    listPurchaseReturns.mockResolvedValue([])
    listSupplierInvoiceBalances.mockResolvedValue([])
    listSupplierPayments.mockResolvedValue([])

    const { unmount } = render(
      <MemoryRouter>
        <ProcurementPage />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'New purchase draft' })
    fireEvent.change(screen.getAllByLabelText('Supplier')[0], {
      target: { value: String(supplier.id) },
    })
    expect(screen.getAllByLabelText('Supplier')[0]).toHaveValue(String(supplier.id))
    fireEvent.click(screen.getByRole('button', { name: 'Supplier payments' }))
    await screen.findByRole('heading', { name: 'Record a supplier payment' })
    fireEvent.click(screen.getByRole('button', { name: 'Purchases' }))
    expect(screen.getAllByLabelText('Supplier')[0]).toHaveValue(String(supplier.id))

    unmount()
    vi.clearAllMocks()
    useAuth.mockReturnValue({
      user: {
        id: 2,
        username: 'cashier',
        roles: ['Cashier'],
      },
      loading: false,
      signOut: vi.fn(),
    })
    render(
      <MemoryRouter>
        <ProcurementPage />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('heading', { name: 'Procurement access is restricted' }))
      .toBeInTheDocument()
    expect(listProductBranches).not.toHaveBeenCalled()
  })

  it('saves a purchase draft and requires explicit confirmation to receive it', async () => {
    listPurchases.mockResolvedValue([])
    createPurchaseDraft.mockResolvedValue(draftPurchase)
    receivePurchase.mockResolvedValue({ ...draftPurchase, status: 'posted' })

    render(<PurchasesTab branchId="5" products={[product]} suppliers={[supplier]} />)
    await screen.findByRole('heading', { name: 'New purchase draft' })

    fireEvent.change(screen.getByLabelText('Supplier'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add product' }))
    fireEvent.change(screen.getByLabelText('Quantity (packet)'), {
      target: { value: '2' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save purchase draft' }))

    expect(await screen.findByText(/saved as a draft/)).toBeInTheDocument()
    expect(createPurchaseDraft).toHaveBeenCalledWith('5', expect.objectContaining({
      supplier: 3,
      items: [expect.objectContaining({ product: 7, quantity: '2' })],
    }))
    expect(receivePurchase).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Review and receive purchase' }))
    const confirmation = screen.getByRole('alertdialog')
    expect(confirmation).toHaveTextContent('cannot be edited after posting')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and post purchase' }))

    await waitFor(() => expect(receivePurchase).toHaveBeenCalledWith('5', 41))
    expect(await screen.findByText('Purchase received. Stock and supplier payable were updated.'))
      .toBeInTheDocument()
  })

  it('shows invoice allocation and the advance before recording a supplier payment', async () => {
    listSupplierInvoiceBalances.mockResolvedValue([
      {
        purchase_id: 41,
        purchase_number: 'PUR-000041',
        supplier_invoice_number: 'GF-882',
        supplier_name: supplier.name,
        purchase_date: '2026-06-04',
        total: '100.00',
        returned_amount: '0.00',
        net_total: '100.00',
        paid_amount: '20.00',
        outstanding_amount: '80.00',
      },
    ])
    listSupplierPayments.mockResolvedValue([])
    createSupplierPayment.mockResolvedValue({
      payment: {
        payment_number: 'SPAY-000008',
        amount: '50.00',
        allocated_amount: '30.00',
        unallocated_amount: '20.00',
      },
      supplier_payable_balance: '50.00',
    })

    render(<SupplierPaymentsTab branchId="5" suppliers={[supplier]} />)
    fireEvent.change(await screen.findByLabelText('Supplier'), {
      target: { value: '3' },
    })
    await screen.findByText(/Outstanding 80.00/)
    fireEvent.change(screen.getByLabelText('Amount paid'), {
      target: { value: '50.00' },
    })
    fireEvent.change(screen.getByLabelText('Allocate to invoice PUR-000041'), {
      target: { value: '30.00' },
    })
    expect(screen.getByText('20.00')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review payment' }))
    const paymentReview = screen.getByRole('alertdialog')
    expect(paymentReview).toHaveTextContent('Allocated to invoices: 30.00')
    expect(paymentReview).toHaveTextContent('Supplier advance: 20.00')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and record payment' }))

    await waitFor(() =>
      expect(createSupplierPayment).toHaveBeenCalledWith('5', expect.objectContaining({
        supplier: 3,
        amount: '50.00',
        allocations: [{ purchase: 41, amount: '30.00' }],
      })),
    )
    expect(await screen.findByText(/20.00 remains as supplier advance/)).toBeInTheDocument()
  })

  it('keeps a supplier return as a draft until the separate posting confirmation', async () => {
    listPurchases.mockResolvedValue([{
      id: 41,
      purchase_number: 'PUR-000041',
      supplier_name_snapshot: supplier.name,
      purchase_date: '2026-06-04',
      total: '4.50',
      status: 'posted',
      items: draftPurchase.items,
    }])
    getPurchase.mockResolvedValue({ ...draftPurchase, status: 'posted' })
    listPurchaseReturns.mockResolvedValue([])
    const returnDraft = {
      id: 91,
      return_number: 'PRET-000091',
      supplier_credit_note_reference: 'CN-22',
      return_date: '2026-06-05',
      notes: '',
      status: 'draft',
      credit_total: '2.25',
      items: [{
        purchase_line: 55,
        product_name_snapshot: product.name,
        sku_snapshot: product.sku,
        unit_symbol_snapshot: product.unit,
        quantity: '1.000000',
        credit_amount: '2.25',
      }],
    }
    createPurchaseReturnDraft.mockResolvedValue(returnDraft)
    postPurchaseReturn.mockResolvedValue({ ...returnDraft, status: 'posted' })

    render(<PurchaseReturnsTab branchId="5" products={[product]} />)
    fireEvent.change(await screen.findByLabelText('Original posted purchase'), {
      target: { value: '41' },
    })
    fireEvent.change(await screen.findByLabelText('Quantity returned (packet)'), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText('Supplier-confirmed credit'), {
      target: { value: '2.25' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save return draft' }))

    expect(await screen.findByText(/saved as a draft/)).toBeInTheDocument()
    expect(postPurchaseReturn).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Review and post supplier return' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('reduce this branch’s stock')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and post return' }))

    await waitFor(() => expect(postPurchaseReturn).toHaveBeenCalledWith('5', 91))
    expect(await screen.findByText(
      'Supplier return posted. Branch stock and supplier account were updated.',
    )).toBeInTheDocument()
  })
})
