import { describe, expect, it } from 'vitest'
import {
  capabilityForPath,
  hasAccess,
  homeForRoles,
} from './roleAccess.js'

describe('role access policy', () => {
  it('grants each role only its intended workspace capabilities', () => {
    expect(hasAccess(['Cashier'], 'sales')).toBe(true)
    expect(hasAccess(['Cashier'], 'customers')).toBe(true)
    expect(hasAccess(['Cashier'], 'procurement')).toBe(false)
    expect(hasAccess(['Inventory/Store Staff'], 'inventory')).toBe(true)
    expect(hasAccess(['Inventory/Store Staff'], 'sales')).toBe(false)
    expect(hasAccess(['Admin'], 'settings')).toBe(true)
    expect(hasAccess(['Manager'], 'settings')).toBe(false)
    expect(hasAccess(['Unrecognized role'], 'dashboard')).toBe(false)
  })

  it('maps routed feature paths and leaves unrelated paths unclassified', () => {
    expect(capabilityForPath('/sales/42')).toBe('sales')
    expect(capabilityForPath('/sales-report')).toBe(null)
    expect(capabilityForPath('/contacts/customers')).toBe('customers')
    expect(capabilityForPath('/contacts/unrecognized')).toBe('unrecognized')
    expect(capabilityForPath('/settings')).toBe('settings')
  })

  it('chooses a usable workspace for recognized roles', () => {
    expect(homeForRoles(['Cashier'])).toBe('/')
    expect(homeForRoles(['Inventory/Store Staff'])).toBe('/dashboard')
    expect(homeForRoles(['Unrecognized role'])).toBe(null)
  })
})
