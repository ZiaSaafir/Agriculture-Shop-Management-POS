import { Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import LoginPage from './features/auth/LoginPage.jsx'
import ContactsPage from './features/contacts/ContactsPage.jsx'
import DashboardPage from './features/dashboard/DashboardPage.jsx'
import InventoryPage from './features/inventory/InventoryPage.jsx'
import PosPage from './features/pos/PosPage.jsx'
import ProcurementPage from './features/procurement/ProcurementPage.jsx'
import ProductsPage from './features/products/ProductsPage.jsx'
import ReportsPage from './features/reports/ReportsPage.jsx'
import SalesHistoryPage from './features/sales/SalesHistoryPage.jsx'
import SettingsPage from './features/settings/SettingsPage.jsx'
import './styles.css'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/" element={<PosPage />} />
        <Route path="/contacts/:type" element={<ContactsPage />} />
        <Route path="/inventory" element={<InventoryPage />} />
        <Route path="/procurement" element={<ProcurementPage />} />
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/sales" element={<SalesHistoryPage />} />
        <Route path="/sales/:saleId" element={<SalesHistoryPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
