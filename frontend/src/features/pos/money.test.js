import { describe, expect, it } from 'vitest'
import {
  calculateCart,
  convertUnitPriceCents,
  formatMoneyCents,
  lineSubtotalCents,
  parseMoneyCents,
} from './money.js'

describe('POS money calculations', () => {
  it('converts base-unit prices to a selected unit using exact cents', () => {
    expect(convertUnitPriceCents('1250.00', '0.001')).toBe('1.25')
    expect(convertUnitPriceCents('12.50', '12')).toBe('150.00')
  })

  it('uses integer cents and rounds half up for fractional quantities', () => {
    expect(lineSubtotalCents('0.5', '1.01', 1)).toBe(51n)
    expect(formatMoneyCents(51n)).toBe('0.51')
  })

  it('calculates sale totals without binary floating-point arithmetic', () => {
    const totals = calculateCart([
      {
        quantity: '3',
        unit_price: '12.00',
        discount_amount: '2.00',
        tax_amount: '1.00',
        product: { quantity_decimal_places: 0 },
      },
    ])

    expect(totals).toEqual({
      subtotal: 3600n,
      discount: 200n,
      tax: 100n,
      total: 3500n,
      valid: true,
    })
  })

  it('rejects invalid decimals and a discount greater than its line subtotal', () => {
    expect(parseMoneyCents('1.001')).toBeNull()
    const totals = calculateCart([
      {
        quantity: '1',
        unit_price: '2.00',
        discount_amount: '2.01',
        tax_amount: '0.00',
        product: { quantity_decimal_places: 0 },
      },
    ])
    expect(totals.valid).toBe(false)
  })
})
