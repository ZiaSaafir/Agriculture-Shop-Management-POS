const STORAGE_KEY = 'agriculture-pos.receipt-settings'

export const DEFAULT_RECEIPT_SETTINGS = Object.freeze({
  paperWidth: '80',
  footer: 'Thank you for your business.',
})

export function readReceiptSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return {
      paperWidth: saved.paperWidth === '58' ? '58' : '80',
      footer:
        typeof saved.footer === 'string'
          ? saved.footer.slice(0, 120)
          : DEFAULT_RECEIPT_SETTINGS.footer,
    }
  } catch {
    return DEFAULT_RECEIPT_SETTINGS
  }
}

export function saveReceiptSettings(settings) {
  const safeSettings = {
    paperWidth: settings.paperWidth === '58' ? '58' : '80',
    footer: String(settings.footer ?? '').slice(0, 120),
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(safeSettings))
  return safeSettings
}
