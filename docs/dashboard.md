# Branch operations dashboard

The authenticated React dashboard is available at `/dashboard`. It selects one
branch at a time and shows a practical operational snapshot based on the
current user's branch-role access:

- Admin, Manager, and Cashier: completed sales dated today and stock alerts.
- Admin, Manager, and Inventory/Store Staff: stock alerts, posted purchases
  dated today, and outstanding posted supplier invoice balances.
- Admin and Manager: both sets of figures.

“Today” uses the browser's local calendar date and the transaction's stored
sale/purchase date. Money is summed in integer cents. Low-stock items are
active branch products whose on-hand quantity is less than or equal to the
product threshold.

The dashboard uses existing branch-protected endpoints. It is an operational
overview, not a profit, cash reconciliation, or full accounting report. Sales
and purchase figures are gross transaction totals. The sales trend is
server-aggregated and net of posted sale returns; it is a separate measure
from the gross “Sales today” card. Purchase totals do not represent COGS or
margin.

The trend uses the branch-scoped reporting endpoint. Existing today's
sales/purchase cards still summarize returned matching lists in the browser.
Each card reports endpoint errors instead of silently treating unavailable
data as zero.

No business data is created or seeded by the dashboard.
