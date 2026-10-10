import { apiRequest } from './apiClient.js'

export function listProductBranches() {
  return apiRequest('/products/branches/')
}

export function getProductCatalogOptions(branchId) {
  return apiRequest(`/products/branches/${branchId}/options/`)
}

export function listProducts(branchId, search = '') {
  const query = search ? `?search=${encodeURIComponent(search)}` : ''
  return apiRequest(`/products/branches/${branchId}/${query}`)
}

export function createProduct(branchId, product) {
  return apiRequest(`/products/branches/${branchId}/`, {
    method: 'POST',
    body: product,
  })
}

export function updateProduct(branchId, productId, product) {
  return apiRequest(`/products/branches/${branchId}/${productId}/`, {
    method: 'PATCH',
    body: product,
  })
}
