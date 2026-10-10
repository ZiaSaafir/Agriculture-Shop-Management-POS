import { NavLink } from 'react-router-dom'
import { hasAccess } from '../auth/roleAccess.js'

const NAV_ITEMS = [
  { label: 'Overview', to: '/dashboard', capability: 'dashboard' },
  { label: 'Reports', to: '/reports', capability: 'reports' },
  { label: 'Point of sale', to: '/', capability: 'sales', end: true },
  { label: 'Sales history', to: '/sales', capability: 'sales' },
  { label: 'Products', to: '/products', capability: 'products' },
  { label: 'Inventory', to: '/inventory', capability: 'inventory' },
  { label: 'Procurement', to: '/procurement', capability: 'procurement' },
  { label: 'Customers', to: '/contacts/customers', capability: 'customers' },
  { label: 'Suppliers', to: '/contacts/suppliers', capability: 'suppliers' },
  { label: 'Settings', to: '/settings', capability: 'settings' },
]

export default function RoleNavigation({ user }) {
  return (
    <div className="workspace-navigation">
      <nav aria-label="Main navigation" className="page-actions">
        {NAV_ITEMS.filter(({ capability }) =>
          hasAccess(user?.roles, capability),
        ).map(({ label, to, end }) => (
          <NavLink
            className={({ isActive }) =>
              isActive ? 'nav-link is-active' : 'nav-link'
            }
            end={end}
            key={to}
            to={to}
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
