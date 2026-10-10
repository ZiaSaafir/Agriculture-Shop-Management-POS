export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function readCsrfCookie() {
  const cookie = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith('csrftoken='))

  return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : null
}

function responseError(data) {
  if (typeof data?.detail === 'string') {
    const stockDetails =
      data.available !== undefined && data.requested !== undefined
        ? ` Available: ${data.available}; requested: ${data.requested}.`
        : ''
    return `${data.detail}${stockDetails}`
  }

  if (data && typeof data === 'object') {
    return Object.entries(data)
      .map(([field, messages]) => {
        const text = Array.isArray(messages) ? messages.join(' ') : String(messages)
        return field === 'non_field_errors' ? text : `${field}: ${text}`
      })
      .join(' ')
  }

  return 'The request could not be completed.'
}

export async function apiRequest(path, { method = 'GET', body } = {}) {
  const upperMethod = method.toUpperCase()
  const headers = { Accept: 'application/json' }

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(upperMethod)) {
    const csrfToken = readCsrfCookie()
    if (!csrfToken) {
      throw new Error('CSRF token is unavailable. Reload the page and try again.')
    }
    headers['X-CSRFToken'] = csrfToken
  }

  const response = await fetch(`/api${path}`, {
    method: upperMethod,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  let data = null
  if (response.status !== 204) {
    const responseBody = await response.text()
    if (responseBody) {
      try {
        data = JSON.parse(responseBody)
      } catch {
        throw new Error('The server returned an invalid response.')
      }
    }
  }

  if (!response.ok) {
    throw new ApiError(responseError(data), response.status)
  }

  return data
}
