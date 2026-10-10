const QUANTITY_SCALE = 1_000_000n

function parseScaled(value, decimalPlaces) {
  const text = String(value).trim()
  const match = /^(\d+)(?:\.(\d*))?$/.exec(text)
  if (!match || (match[2]?.length ?? 0) > decimalPlaces) {
    return null
  }

  const fraction = (match[2] ?? '').padEnd(decimalPlaces, '0')
  return BigInt(match[1]) * 10n ** BigInt(decimalPlaces) + BigInt(fraction || '0')
}

export function parseMoneyCents(value) {
  return parseScaled(value, 2)
}

export function formatMoneyCents(cents) {
  const negative = cents < 0n
  const absolute = negative ? -cents : cents
  const major = absolute / 100n
  const minor = String(absolute % 100n).padStart(2, '0')
  return `${negative ? '-' : ''}${major}.${minor}`
}

export function convertUnitPriceCents(basePrice, multiplier) {
  const baseCents = parseMoneyCents(basePrice)
  const [whole, fraction = ''] = String(multiplier).split('.')
  if (!baseCents || !/^\d+$/.test(whole) || !/^\d*$/.test(fraction)) return null
  const scale = 10n ** BigInt(fraction.length)
  const factor = BigInt(whole) * scale + BigInt(fraction || '0')
  const converted = (baseCents * factor + scale / 2n) / scale
  return formatMoneyCents(converted)
}

export function parseQuantityMicros(value, decimalPlaces) {
  const amount = parseScaled(value, decimalPlaces)
  if (amount === null) {
    return null
  }

  return amount * 10n ** BigInt(6 - decimalPlaces)
}

export function formatQuantityMicros(quantityMicros, decimalPlaces) {
  const scale = 10n ** BigInt(6 - decimalPlaces)
  const quantity = quantityMicros / scale
  const precisionScale = 10n ** BigInt(decimalPlaces)
  const whole = quantity / precisionScale
  const fraction = quantity % precisionScale

  if (decimalPlaces === 0) {
    return String(whole)
  }
  return `${whole}.${String(fraction).padStart(decimalPlaces, '0')}`
}

export function lineSubtotalCents(quantity, unitPrice, quantityDecimalPlaces) {
  const quantityMicros = parseQuantityMicros(quantity, quantityDecimalPlaces)
  const unitPriceCents = parseMoneyCents(unitPrice)
  if (quantityMicros === null || unitPriceCents === null) {
    return null
  }

  const numerator = quantityMicros * unitPriceCents
  return (numerator + QUANTITY_SCALE / 2n) / QUANTITY_SCALE
}

export function calculateCart(lines) {
  let subtotal = 0n
  let discount = 0n
  let tax = 0n
  let total = 0n
  let valid = lines.length > 0

  for (const line of lines) {
    const decimalPlaces =
      line.unit?.decimal_places ?? line.product.quantity_decimal_places
    const quantity = parseQuantityMicros(
      line.quantity,
      decimalPlaces,
    )
    const lineSubtotal = lineSubtotalCents(
      line.quantity,
      line.unit_price,
      decimalPlaces,
    )
    const lineDiscount = parseMoneyCents(line.discount_amount)
    const lineTax = parseMoneyCents(line.tax_amount)
    if (
      quantity === null ||
      quantity <= 0n ||
      lineSubtotal === null ||
      lineDiscount === null ||
      lineTax === null ||
      lineDiscount > lineSubtotal
    ) {
      valid = false
      continue
    }

    subtotal += lineSubtotal
    discount += lineDiscount
    tax += lineTax
    total += lineSubtotal - lineDiscount + lineTax
  }

  return { subtotal, discount, tax, total, valid }
}

export function quantityStep(decimalPlaces) {
  return decimalPlaces === 0 ? '1' : `0.${'0'.repeat(decimalPlaces - 1)}1`
}
