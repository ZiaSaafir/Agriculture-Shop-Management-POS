import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthContext.jsx'
import {
  listBackupSettings,
  updateBackupSettings,
} from '../../services/posApi.js'
import SettingsPage from './SettingsPage.jsx'

vi.mock('../auth/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../services/posApi.js', () => ({
  disconnectGoogleDrive: vi.fn(),
  listBackupSettings: vi.fn(),
  startGoogleDriveConnection: vi.fn(),
  updateBackupSettings: vi.fn(),
}))

const backupSettings = {
  organization_id: 5,
  organization_name: 'Farm Supply',
  google_drive_configured: true,
  google_email: 'backup@example.com',
  drive_connected: true,
  drive_folder_id: 'folder123',
  daily_enabled: false,
  daily_backup_supported: true,
  manual_backup_allowed: true,
  latest_backup: null,
  recent_backups: [
    {
      id: 9,
      status: 'succeeded',
      destination: 'download',
      file_name: 'agriculture-pos-2026-10-08.dump',
      file_size: 2048,
      error_message: '',
      started_at: '2026-10-08T10:00:00Z',
      completed_at: '2026-10-08T10:00:03Z',
    },
  ],
}

describe('administrator settings', () => {
  it('saves thermal paper preferences and daily backup settings', async () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'admin', roles: ['Admin'] },
      loading: false,
      signOut: vi.fn(),
    })
    listBackupSettings.mockResolvedValue([backupSettings])
    updateBackupSettings.mockResolvedValue({
      ...backupSettings,
      drive_folder_id: 'newFolder',
      daily_enabled: true,
    })

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Settings' }))
      .toBeInTheDocument()
    expect(screen.getByText('backup@example.com')).toBeInTheDocument()
    expect(screen.getByText('agriculture-pos-2026-10-08.dump')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Receipt paper width'), {
      target: { value: '58' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save receipt settings' }))
    expect(JSON.parse(localStorage.getItem('agriculture-pos.receipt-settings')))
      .toEqual({ paperWidth: '58', footer: 'Thank you for your business.' })

    fireEvent.change(screen.getByLabelText('Google Drive folder ID Optional'), {
      target: { value: 'newFolder' },
    })
    fireEvent.click(screen.getByLabelText('Upload a PostgreSQL backup every day'))
    fireEvent.click(screen.getByRole('button', { name: 'Save backup settings' }))
    await waitFor(() =>
      expect(updateBackupSettings).toHaveBeenCalledWith('5', {
        drive_folder_id: 'newFolder',
        daily_enabled: true,
      }),
    )
    expect(screen.getByRole('link', { name: 'Download .dump backup' }))
      .toHaveAttribute('href', '/api/backups/organizations/5/download/')
  })
})
