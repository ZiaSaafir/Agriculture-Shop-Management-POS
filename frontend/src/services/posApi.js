import { apiRequest } from './apiClient.js'

export function listSalesBranches() {
  return apiRequest('/sales/branches/')
}

export function listBranchStock(branchId) {
  return apiRequest(`/inventory/branches/${branchId}/stock/`)
}

export function listBranchCustomers(branchId, search = '') {
  const query = search ? `?search=${encodeURIComponent(search)}` : ''
  return apiRequest(`/customers/branches/${branchId}/${query}`)
}

export function createSaleDraft(branchId, draft) {
  return apiRequest(`/sales/branches/${branchId}/`, {
    method: 'POST',
    body: draft,
  })
}

export function updateSaleDraft(branchId, saleId, draft) {
  return apiRequest(`/sales/branches/${branchId}/${saleId}/`, {
    method: 'PATCH',
    body: draft,
  })
}

export function checkoutSale(branchId, saleId, payment) {
  return apiRequest(`/sales/branches/${branchId}/${saleId}/checkout/`, {
    method: 'POST',
    body: payment,
  })
}

export function listBranchSales(branchId, { status = '', search = '' } = {}) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (search.trim()) params.set('search', search.trim())
  const query = params.size ? `?${params}` : ''
  return apiRequest(`/sales/branches/${branchId}/${query}`)
}

export function getBranchSale(branchId, saleId) {
  return apiRequest(`/sales/branches/${branchId}/${saleId}/`)
}

export function listSalesReturns(branchId, saleId) {
  return apiRequest(`/sales/branches/${branchId}/${saleId}/returns/`)
}

export function createSalesReturn(branchId, saleId, payload) {
  return apiRequest(`/sales/branches/${branchId}/${saleId}/returns/`, {
    method: 'POST',
    body: payload,
  })
}

export function getBranchOperationalReport(branchId, startDate, endDate) {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  })
  return apiRequest(`/reports/branches/${branchId}/?${params}`)
}

export function listBackupSettings() {
  return apiRequest('/backups/organizations/')
}

export function updateBackupSettings(organizationId, payload) {
  return apiRequest(`/backups/organizations/${organizationId}/`, {
    method: 'PATCH',
    body: payload,
  })
}

export function startGoogleDriveConnection(organizationId) {
  return apiRequest('/backups/google/start/', {
    method: 'POST',
    body: { organization_id: organizationId },
  })
}

export function disconnectGoogleDrive(organizationId) {
  return apiRequest(`/backups/organizations/${organizationId}/google/disconnect/`, {
    method: 'POST',
    body: {},
  })
}
