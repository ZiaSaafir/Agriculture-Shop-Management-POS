import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './features/auth/AuthContext.jsx'

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (data === null ? '' : JSON.stringify(data)),
  }
}

function renderApp(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; Max-Age=0; path=/'
})

describe('authentication flow', () => {
  it('redirects anonymous visitors to the login form', async () => {
    document.cookie = 'csrftoken=test-token; path=/'
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
        .mockResolvedValueOnce(
          response(401, { detail: 'Authentication required.' }),
        ),
    )

    renderApp('/')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('protects the sales-history route from anonymous visitors', async () => {
    document.cookie = 'csrftoken=test-token; path=/'
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
        .mockResolvedValueOnce(
          response(401, { detail: 'Authentication required.' }),
        ),
    )

    renderApp('/sales')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('protects the dashboard route from anonymous visitors', async () => {
    document.cookie = 'csrftoken=test-token; path=/'
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
        .mockResolvedValueOnce(
          response(401, { detail: 'Authentication required.' }),
        ),
    )

    renderApp('/dashboard')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('logs in, displays the authenticated user, and logs out', async () => {
    const user = {
      id: 1,
      username: 'shop-cashier',
      first_name: 'Shop',
      last_name: 'Cashier',
      roles: ['Cashier'],
    }
    document.cookie = 'csrftoken=test-token; path=/'
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
      .mockResolvedValueOnce(response(401, { detail: 'Authentication required.' }))
      .mockResolvedValueOnce(response(200, { detail: 'CSRF cookie set.' }))
      .mockResolvedValueOnce(response(200, user))
      .mockResolvedValueOnce(
        response(200, [
          { id: 5, name: 'Main Shop', organization: 'Farm Supply' },
        ]),
      )
      .mockResolvedValueOnce(response(200, []))
      .mockResolvedValueOnce(response(200, []))
      .mockResolvedValueOnce(response(204, null))
    vi.stubGlobal('fetch', fetchMock)

    renderApp('/login')
    fireEvent.change(await screen.findByLabelText('Username'), {
      target: { value: 'shop-cashier' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'correct-password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Shop')).toBeInTheDocument()
    expect(screen.getByText('Role: Cashier')).toBeInTheDocument()
    expect(screen.getByText('Farm Supply')).toBeInTheDocument()
    expect(screen.getByText('Main Shop')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sales history' })).toHaveAttribute(
      'href',
      '/sales',
    )
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute(
      'href',
      '/dashboard',
    )
    expect(screen.getByRole('link', { name: 'Customers' })).toHaveAttribute(
      'href',
      '/contacts/customers',
    )
    expect(screen.queryByRole('link', { name: 'Procurement' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Products' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Inventory' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls[3][1].headers['X-CSRFToken']).toBe('test-token')

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})
