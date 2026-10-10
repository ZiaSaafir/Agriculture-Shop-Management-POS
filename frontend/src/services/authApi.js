import { apiRequest } from './apiClient.js'
export { ApiError } from './apiClient.js'

export async function initializeSession() {
  await apiRequest('/auth/csrf/')
  return apiRequest('/auth/me/')
}

export async function login(credentials) {
  await apiRequest('/auth/csrf/')
  return apiRequest('/auth/login/', { method: 'POST', body: credentials })
}

export function logout() {
  return apiRequest('/auth/logout/', { method: 'POST', body: {} })
}
