# Branch operational reports

The authenticated `/reports` workspace provides date-filtered, branch-scoped
operational summaries for Admin, Manager, Cashier, and Inventory/Store Staff.
The backend validates an inclusive date range of at most 366 calendar days and
performs aggregation against existing PostgreSQL records.

Use the Today, This week, This month, Last 7 days, and Last month presets, or
enter a custom date range. Branch selection and date filters apply to the
server-side report. Section tabs narrow the on-screen and printed view to Sales,
Purchases, Inventory, Accounts, or all sections. CSV export includes the
selected branch/date range, every summary and detail table, daily totals, and
inventory movement counts.

Available measures include completed sales, tender received and sales grouped
by payment method, posted sale returns by disposition, net sales after returns,
discounts, posted purchases and purchase returns grouped by supplier, current
customer receivables and supplier payables, current low-stock count, daily
sales/return totals, top-selling products, and inventory movement counts. The
report can also be printed or saved as PDF through the browser; the printout
contains the selected branch, date range, current section filter, summaries,
and details.

Date-filtered measures use each sale, purchase, or return's recorded date.
Customer receivables and low-stock count are current values, not historical
snapshots as of the report end date. Top products show gross sold quantities
and line totals, not net-of-return quantities.

Profit, COGS, stock valuation, till cash balances, split tenders, expenses,
supplier balances as-of-date, and cash-flow reconciliation are not reported.
The application does not yet store the complete accounting/costing data needed
to calculate those values. Reports must not be treated as a statutory ledger
or tax filing.

Endpoint:

- `GET /api/reports/branches/{branch_id}/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

Access is limited to active branches where the user has a supported membership
role; superusers may access all active branches.
