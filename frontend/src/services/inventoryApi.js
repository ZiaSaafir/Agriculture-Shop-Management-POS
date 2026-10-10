import { apiRequest } from './apiClient.js'

export function listBranchMovements(branchId) {
  return apiRequest(`/inventory/branches/${branchId}/movements/`)
}

export function recordInventoryMovement(branchId, movement) {
  return apiRequest(`/inventory/branches/${branchId}/movements/`, {
    method: 'POST',
    body: movement,
  })
}
