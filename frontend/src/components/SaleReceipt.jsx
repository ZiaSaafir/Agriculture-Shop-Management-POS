import { useState } from 'react'
import { readReceiptSettings } from '../features/settings/receiptSettings.js'

function receiptMessage(sale) {
  const lines = [
    sale.organization_name,
    sale.branch_name,
    `Receipt ${sale.sale_number}`,
    `Customer: ${sale.customer_name_snapshot || 'Walk-in customer'}`,
    ...sale.items.map(
      (item) =>
        `${item.quantity} ${item.unit_symbol_snapshot} ${item.product_name_snapshot}: PKR ${item.total}`,
    ),
    `Total: PKR ${sale.total}`,
    `Received: PKR ${sale.amount_paid}`,
    sale.balance_due !== '0.00' ? `Due: PKR ${sale.balance_due}` : '',
  ].filter(Boolean)
  return lines.join('\n')
}

export default function SaleReceipt({ sale }) {
  const [receiptSettings] = useState(readReceiptSettings)
  const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(receiptMessage(sale))}`

  return (
    <section
      aria-label="Sale receipt"
      className={`receipt-print receipt-width-${receiptSettings.paperWidth}`}
      style={{ '--receipt-width': `${receiptSettings.paperWidth}mm` }}
    >
      <div className="receipt-actions no-print">
        <button className="button-secondary" onClick={() => window.print()} type="button">
          Print / Save PDF
        </button>
        <a
          className="button-secondary nav-link"
          href={whatsappUrl}
          rel="noreferrer"
          target="_blank"
        >
          Share on WhatsApp
        </a>
      </div>
      <header className="receipt-heading">
        <p className="eyebrow">{sale.organization_name || 'Shop receipt'}</p>
        <h2>{sale.sale_number}</h2>
        <p>{sale.branch_name} · {sale.sale_date}</p>
        <p>{sale.customer_name_snapshot || 'Walk-in customer'}</p>
        {sale.customer_phone && <p>{sale.customer_phone}</p>}
      </header>
      <div className="receipt-lines">
        {sale.items.map((item) => (
          <div className="receipt-line" key={item.id}>
            <span>
              {item.product_name_snapshot}
              <small>{item.quantity} {item.unit_symbol_snapshot} × PKR {item.unit_price}</small>
            </span>
            <strong>PKR {item.total}</strong>
          </div>
        ))}
      </div>
      <dl className="receipt-totals">
        <div><dt>Subtotal</dt><dd>PKR {sale.subtotal}</dd></div>
        <div><dt>Discount</dt><dd>PKR {sale.discount_total}</dd></div>
        <div><dt>Tax</dt><dd>PKR {sale.tax_total}</dd></div>
        <div><dt>Total</dt><dd>PKR {sale.total}</dd></div>
        <div><dt>Received</dt><dd>PKR {sale.amount_paid}</dd></div>
        {sale.balance_due !== '0.00' && (
          <div><dt>Balance due</dt><dd>PKR {sale.balance_due}</dd></div>
        )}
        {sale.change_due !== '0.00' && (
          <div><dt>Change</dt><dd>PKR {sale.change_due}</dd></div>
        )}
      </dl>
      <p className="receipt-footer">{receiptSettings.footer}</p>
    </section>
  )
}
