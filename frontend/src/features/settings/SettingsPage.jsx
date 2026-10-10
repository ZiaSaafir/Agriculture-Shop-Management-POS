import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import WorkspaceHeader from '../../components/WorkspaceHeader.jsx'
import { hasAccess } from '../../auth/roleAccess.js'
import {
  disconnectGoogleDrive,
  listBackupSettings,
  startGoogleDriveConnection,
  updateBackupSettings,
} from '../../services/posApi.js'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  DEFAULT_RECEIPT_SETTINGS,
  readReceiptSettings,
  saveReceiptSettings,
} from './receiptSettings.js'

function displayDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function displaySize(value) {
  if (value === null || value === undefined) return '—'
  const megabytes = Number(value) / (1024 * 1024)
  return megabytes < 1
    ? `${Math.max(1, Math.round(Number(value) / 1024))} KB`
    : `${megabytes.toFixed(1)} MB`
}

export default function SettingsPage() {
  const { user, loading: authLoading, signOut } = useAuth()
  const location = useLocation()
  const canManage = hasAccess(user?.roles, 'settings')
  const [organizations, setOrganizations] = useState([])
  const [organizationId, setOrganizationId] = useState('')
  const [driveFolderId, setDriveFolderId] = useState('')
  const [dailyEnabled, setDailyEnabled] = useState(false)
  const [receiptSettings, setReceiptSettings] = useState(() => readReceiptSettings())
  const [status, setStatus] = useState('loading')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const selectedOrganization = useMemo(
    () => organizations.find((item) => String(item.organization_id) === organizationId),
    [organizationId, organizations],
  )

  useEffect(() => {
    if (authLoading || !user || !canManage) return undefined
    let active = true
    listBackupSettings()
      .then((rows) => {
        if (!active) return
        setOrganizations(rows)
        setOrganizationId(rows.length ? String(rows[0].organization_id) : '')
        setStatus('ready')
      })
      .catch((requestError) => {
        if (!active) return
        setError(requestError.message)
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [authLoading, canManage, user])

  useEffect(() => {
    if (!selectedOrganization) return
    setDriveFolderId(selectedOrganization.drive_folder_id)
    setDailyEnabled(selectedOrganization.daily_enabled)
  }, [selectedOrganization])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const result = params.get('google_drive')
    if (!result) return
    if (result === 'connected') {
      setNotice(params.get('message') || 'Google Drive is connected.')
      listBackupSettings()
        .then(setOrganizations)
        .catch((requestError) => setError(requestError.message))
    } else {
      setError(params.get('message') || 'Google Drive could not be connected.')
    }
  }, [location.search])

  async function handleSignOut() {
    setError('')
    try {
      await signOut()
    } catch (signOutError) {
      setError(signOutError.message)
    }
  }

  async function handleSaveBackupSettings(event) {
    event.preventDefault()
    if (!selectedOrganization) return
    setError('')
    setNotice('')
    setBusy(true)
    try {
      const updated = await updateBackupSettings(organizationId, {
        drive_folder_id: driveFolderId,
        daily_enabled: dailyEnabled,
      })
      setOrganizations((current) =>
        current.map((item) =>
          item.organization_id === updated.organization_id ? updated : item,
        ),
      )
      setNotice('Backup settings saved.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleConnectDrive() {
    if (!selectedOrganization) return
    setError('')
    setBusy(true)
    try {
      const result = await startGoogleDriveConnection(organizationId)
      window.location.assign(result.authorization_url)
    } catch (requestError) {
      setError(requestError.message)
      setBusy(false)
    }
  }

  async function handleDisconnectDrive() {
    if (!selectedOrganization) return
    setError('')
    setNotice('')
    setBusy(true)
    try {
      const updated = await disconnectGoogleDrive(organizationId)
      setOrganizations((current) =>
        current.map((item) =>
          item.organization_id === updated.organization_id ? updated : item,
        ),
      )
      setDailyEnabled(false)
      setNotice('Google Drive was disconnected; automatic uploads are off.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  function handleSaveReceiptSettings(event) {
    event.preventDefault()
    setError('')
    try {
      setReceiptSettings(saveReceiptSettings(receiptSettings))
      setNotice('Receipt printing settings saved in this browser.')
    } catch {
      setError('Receipt settings could not be saved in this browser.')
    }
  }

  if (authLoading || status === 'loading') {
    return <main className="pos-loading" role="status">Loading shop settings…</main>
  }

  if (!canManage) {
    return (
      <main className="pos-shell">
        <section className="pos-notice" role="alert">
          <h1>Settings access is restricted</h1>
          <p>Only shop administrators can change settings and backup connections.</p>
          <Link to="/">Return to point of sale</Link>
        </section>
      </main>
    )
  }

  return (
    <main className="pos-shell settings-page">
      <WorkspaceHeader
        detail="Receipt printing, cloud backup, and shop data protection"
        eyebrow="Administration"
        onSignOut={handleSignOut}
        title="Settings"
        user={user}
      />

      {error && <p className="pos-error" role="alert">{error}</p>}
      {notice && <p className="pos-notice settings-notice" role="status">{notice}</p>}

      {organizations.length > 1 && (
        <label className="branch-picker">
          Organization
          <select
            onChange={(event) => setOrganizationId(event.target.value)}
            value={organizationId}
          >
            {organizations.map((item) => (
              <option key={item.organization_id} value={item.organization_id}>
                {item.organization_name}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="settings-grid">
        <section className="pos-panel settings-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Thermal printer</p>
              <h2>Receipt layout</h2>
            </div>
          </div>
          <p className="settings-description">
            Choose the roll width used by the print layout. In the browser print
            dialog, select the matching thermal printer and paper size.
          </p>
          <form className="settings-form" onSubmit={handleSaveReceiptSettings}>
            <label>
              Receipt paper width
              <select
                onChange={(event) =>
                  setReceiptSettings((current) => ({
                    ...current,
                    paperWidth: event.target.value,
                  }))
                }
                value={receiptSettings.paperWidth}
              >
                <option value="58">58 mm compact thermal roll</option>
                <option value="80">80 mm standard thermal roll</option>
              </select>
            </label>
            <label>
              Receipt footer
              <input
                maxLength="120"
                onChange={(event) =>
                  setReceiptSettings((current) => ({
                    ...current,
                    footer: event.target.value,
                  }))
                }
                value={receiptSettings.footer}
              />
            </label>
            <div className="settings-form-actions">
              <button className="button-primary" type="submit">Save receipt settings</button>
              <button
                className="button-secondary"
                onClick={() => setReceiptSettings(DEFAULT_RECEIPT_SETTINGS)}
                type="button"
              >
                Use defaults
              </button>
            </div>
          </form>
          <p className="checkout-hint">
            Settings are saved in this browser. The thermal printer must be
            installed in Windows; the app sends the receipt through the browser
            print dialog.
          </p>
        </section>

        <section className="pos-panel settings-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">PostgreSQL backup</p>
              <h2>Daily Google Drive backup</h2>
            </div>
            {selectedOrganization?.daily_enabled && (
              <span className="status-active">Daily backup enabled</span>
            )}
          </div>
          {!selectedOrganization && status === 'ready' && (
            <p className="empty-state">No organization is available to configure.</p>
          )}
          {selectedOrganization && (
            <>
              <p className="settings-description">
                Connect one Google account. The shop server uploads an encrypted,
                compressed PostgreSQL backup to that account when the daily
                scheduled task runs.
              </p>
              {!selectedOrganization.google_drive_configured && (
                <div className="pos-notice settings-setup-note">
                  <strong>Google OAuth is not configured on this server.</strong>
                  <p>
                    Add the Google OAuth client ID and secret to the private
                    project <code>.env</code> file, add the callback URL shown
                    below as an authorized redirect URI in Google Cloud, then
                    restart Django.
                  </p>
                  <code>http://127.0.0.1:8000/api/backups/google/callback/</code>
                </div>
              )}
              {!selectedOrganization.daily_backup_supported && (
                <div className="pos-notice settings-setup-note">
                  Automatic whole-database uploads are supported only while this
                  installation contains one organization. This prevents one
                  shop&apos;s Google Drive from receiving another shop&apos;s data.
                </div>
              )}
              <div className="settings-connection">
                <span>Connected Google account</span>
                <strong>
                  {selectedOrganization.google_email || 'No account connected'}
                </strong>
              </div>
              <div className="settings-form-actions">
                <button
                  className="button-secondary"
                  disabled={busy || !selectedOrganization.google_drive_configured}
                  onClick={handleConnectDrive}
                  type="button"
                >
                  {selectedOrganization.google_email ? 'Reconnect Google Drive' : 'Connect Google Drive'}
                </button>
                {selectedOrganization.drive_connected && (
                  <button
                    className="button-secondary"
                    disabled={busy}
                    onClick={handleDisconnectDrive}
                    type="button"
                  >
                    Disconnect
                  </button>
                )}
              </div>
              <form className="settings-form" onSubmit={handleSaveBackupSettings}>
                <label>
                  Google Drive folder ID <span className="optional-label">Optional</span>
                  <input
                    autoComplete="off"
                    maxLength="200"
                    onChange={(event) => setDriveFolderId(event.target.value)}
                    placeholder="Leave blank to use My Drive"
                    value={driveFolderId}
                  />
                </label>
                <label className="settings-checkbox">
                  <input
                    checked={dailyEnabled}
                    disabled={
                      !selectedOrganization.drive_connected
                      || (!selectedOrganization.daily_backup_supported && !dailyEnabled)
                    }
                    onChange={(event) => setDailyEnabled(event.target.checked)}
                    type="checkbox"
                  />
                  <span>Upload a PostgreSQL backup every day</span>
                </label>
                <button className="button-primary" disabled={busy} type="submit">
                  {busy ? 'Saving…' : 'Save backup settings'}
                </button>
              </form>
              <div className="settings-download">
                <div>
                  <strong>Manual backup to USB or another location</strong>
                  <p>
                    Download the PostgreSQL custom-format file, then choose the
                    USB drive in your browser&apos;s save dialog.
                  </p>
                </div>
                {selectedOrganization.manual_backup_allowed ? (
                  <a
                    className="button-secondary nav-link"
                    href={`/api/backups/organizations/${selectedOrganization.organization_id}/download/`}
                  >
                    Download .dump backup
                  </a>
                ) : (
                  <span className="checkout-hint">
                    Only the system administrator can download a whole-database
                    backup when more than one organization exists.
                  </span>
                )}
              </div>
            </>
          )}
        </section>

        {selectedOrganization && (
          <section className="pos-panel settings-panel settings-history">
            <div className="panel-heading">
              <div><p className="eyebrow">Recent activity</p><h2>Backup history</h2></div>
            </div>
            {!selectedOrganization.recent_backups.length ? (
              <p className="empty-state">No backups have been created yet.</p>
            ) : (
              <div className="settings-history-list">
                {selectedOrganization.recent_backups.map((run) => (
                  <article className="settings-history-row" key={run.id}>
                    <div>
                      <strong>{run.file_name || run.destination}</strong>
                      <span>{displayDate(run.started_at)}</span>
                    </div>
                    <span className={`backup-status backup-status-${run.status}`}>
                      {run.status}
                    </span>
                    <span>{displaySize(run.file_size)}</span>
                    {run.error_message && <p role="alert">{run.error_message}</p>}
                  </article>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  )
}
