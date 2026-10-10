import { apiRequest } from './apiClient.js'

function branchPath(branchId) {
  return `/purchases/branches/${branchId}`
}

export function listPurchases(branchId, status = '') {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiRequest(`${branchPath(branchId)}/${query}`)
}

export function createPurchaseDraft(branchId, purchase) {
  return apiRequest(`${branchPath(branchId)}/`, {
    method: 'POST',
    body: purchase,
  })
}

export function updatePurchaseDraft(branchId, purchaseId, purchase) {
  return apiRequest(`${branchPath(branchId)}/${purchaseId}/`, {
    method: 'PATCH',
    body: purchase,
  })
}

export function receivePurchase(branchId, purchaseId) {
  return apiRequest(`${branchPath(branchId)}/${purchaseId}/receive/`, {
    method: 'POST',
    body: {},
  })
}

export function listSupplierInvoiceBalances(branchId, supplierId = '') {
  const query = supplierId ? `?supplier=${encodeURIComponent(supplierId)}` : ''
  return apiRequest(`${branchPath(branchId)}/outstanding/${query}`)
}

export function listSupplierPayments(branchId, supplierId = '') {
  const query = supplierId ? `?supplier=${encodeURIComponent(supplierId)}` : ''
  return apiRequest(`${branchPath(branchId)}/payments/${query}`)
}

export function createSupplierPayment(branchId, payment) {
  return apiRequest(`${branchPath(branchId)}/payments/`, {
    method: 'POST',
    body: payment,
  })
}

export function listPurchaseReturns(branchId, filters = {}) {
  const params = new URLSearchParams()
  if (filters.purchase) params.set('purchase', filters.purchase)
  if (filters.status) params.set('status', filters.status)
  const query = params.size ? `?${params}` : ''
  return apiRequest(`${branchPath(branchId)}/returns/${query}`)
}

export function getPurchase(branchId, purchaseId) {
  return apiRequest(`${branchPath(branchId)}/${purchaseId}/`)
}

export function createPurchaseReturnDraft(branchId, purchaseReturn) {
  return apiRequest(`${branchPath(branchId)}/returns/`, {
    method: 'POST',
    body: purchaseReturn,
  })
}

export function updatePurchaseReturnDraft(branchId, returnId, purchaseReturn) {
  return apiRequest(`${branchPath(branchId)}/returns/${returnId}/`, {
    method: 'PATCH',
    body: purchaseReturn,
  })
}

export function postPurchaseReturn(branchId, returnId) {
  return apiRequest(`${branchPath(branchId)}/returns/${returnId}/post/`, {
    method: 'POST',
    body: {},
  })
}
