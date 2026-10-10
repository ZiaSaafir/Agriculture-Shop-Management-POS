import { apiRequest } from './apiClient.js'

function rootFor(type) {
  return type === 'supplier' ? '/suppliers' : '/customers'
}

export function listContacts(type, branchId, search = '', includeInactive = false) {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  if (includeInactive) params.set('include_inactive', 'true')
  const query = params.size ? `?${params}` : ''
  return apiRequest(`${rootFor(type)}/branches/${branchId}/${query}`)
}

export function createContact(type, branchId, contact) {
  return apiRequest(`${rootFor(type)}/branches/${branchId}/`, {
    method: 'POST',
    body: contact,
  })
}

export function updateContact(type, branchId, contactId, contact) {
  return apiRequest(`${rootFor(type)}/branches/${branchId}/${contactId}/`, {
    method: 'PATCH',
    body: contact,
  })
}

export function getContactLedger(type, branchId, contactId) {
  return apiRequest(`${rootFor(type)}/branches/${branchId}/${contactId}/ledger/`)
}
