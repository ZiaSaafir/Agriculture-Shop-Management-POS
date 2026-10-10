export const ROLE_ACCESS = Object.freeze({
  dashboard: ['Admin', 'Manager', 'Cashier', 'Inventory/Store Staff'],
  reports: ['Admin', 'Manager', 'Cashier', 'Inventory/Store Staff'],
  sales: ['Admin', 'Manager', 'Cashier'],
  inventory: ['Admin', 'Manager', 'Inventory/Store Staff'],
  products: ['Admin', 'Manager', 'Inventory/Store Staff'],
  procurement: ['Admin', 'Manager', 'Inventory/Store Staff'],
  customers: ['Admin', 'Manager', 'Cashier'],
  suppliers: ['Admin', 'Manager', 'Inventory/Store Staff'],
  settings: ['Admin'],
})

export function hasAccess(roles, capability) {
  const allowedRoles = ROLE_ACCESS[capability]
  return Boolean(
    allowedRoles &&
      roles?.some((role) => allowedRoles.includes(role)),
  )
}

export function capabilityForPath(pathname) {
  if (pathname === '/' || pathname === '/sales' || pathname.startsWith('/sales/')) {
    return 'sales'
  }
  if (pathname === '/dashboard' || pathname.startsWith('/dashboard/')) {
    return 'dashboard'
  }
  if (pathname === '/reports' || pathname.startsWith('/reports/')) {
    return 'reports'
  }
  if (pathname === '/settings' || pathname.startsWith('/settings/')) {
    return 'settings'
  }
  if (pathname === '/inventory' || pathname.startsWith('/inventory/')) {
    return 'inventory'
  }
  if (pathname === '/products' || pathname.startsWith('/products/')) {
    return 'products'
  }
  if (pathname === '/procurement' || pathname.startsWith('/procurement/')) {
    return 'procurement'
  }
  if (pathname === '/contacts/customers') return 'customers'
  if (pathname === '/contacts/suppliers') return 'suppliers'
  if (pathname.startsWith('/contacts/')) return 'unrecognized'
  return null
}

export function homeForRoles(roles) {
  if (hasAccess(roles, 'sales')) return '/'
  if (hasAccess(roles, 'dashboard')) return '/dashboard'
  if (hasAccess(roles, 'inventory')) return '/inventory'
  return null
}
