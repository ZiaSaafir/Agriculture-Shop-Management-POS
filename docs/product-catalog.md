# Product catalog and units

## Organization and branch relationship

Categories, brands, varieties, units, and products belong to an organization,
not to a branch. This gives all branches in one organization the same product
definitions and avoids copying a product catalog per shop. Branch-specific
stock is recorded as inventory rows that reference both a branch and a
product.

Organization ownership is also a future tenant boundary: catalog data for one
organization should not be exposed to another organization's users.

## Models

- `ProductCategory`: organization-owned category name and optional description.
- `Brand`: organization-owned company/brand reference.
- `ProductVariety`: organization-owned variety/type, optionally scoped to a
  product category.
- `Unit`: organization-owned unit name, symbol, dimensional group, and display
  precision, plus an optional verified factor to the canonical unit for that
  dimension.
- `Product`: organization-owned SKU, optional barcode, descriptive fields,
  category, optional brand/variety, required base unit, prices, stock threshold,
  and active state.

Product SKUs are unique inside an organization. A non-empty barcode is also
unique inside that organization. Empty barcodes may repeat. Related category,
brand, variety, and unit records must belong to the product's organization.
Referenced catalog records use protected deletion; deactivate them instead of
removing definitions that may later be part of transaction history.

Prices use `DecimalField` with two decimal places and nonnegative database
constraints. The low-stock threshold uses decimal quantity precision. Posted
sales and purchases snapshot product/unit/price/line details; current catalog
edits do not rewrite those snapshots.

## Units and conversion boundary

Each organization defines its reusable units in admin; there is no hard-coded
list of sale units. A factor is configured on a unit in Django admin and is
relative to a stable canonical unit for its dimension: grams for mass,
millilitres for volume, and one piece for count. The factor must be positive.
Verified standard names/symbols are initialized by migration (for example,
`each`, `kg`, `g`, `litre`, `ml`, and `dozen`); other units remain unavailable
for conversion until an administrator enters a confirmed factor.

Conversions are offered only between units in the same dimension that both
have verified factors. There is no assumed relationship for packaging units:
a bag, bottle, box, or packet does not automatically convert to a weight or
count. Ambiguous local measures such as maund must remain unconfigured until
the shop confirms its intended standard. Configure factors before using the
unit and do not change factors after transaction use.

The product base unit is the immutable unit used by stock movements. At POS,
the cashier can choose any verified compatible organization unit; the sale
records the entered quantity, unit, and conversion factor, while inventory
decrements the exact base-unit quantity. A product has a separate
`allow_fractional_quantity` switch (off by default); its selected unit's
precision still applies. The base unit cannot be changed after product
creation because that would reinterpret existing stock.

## Creating catalog entries

The management API and React catalog page are available to Admin, Manager, and
Inventory/Store Staff members of the selected active branch. The selected
branch is only an authorization and organization-selection context: products
remain organization-owned and shared by that organization's branches.

- `GET /api/products/branches/` lists branches where the user can manage the
  catalog.
- `GET /api/products/branches/{branch_id}/options/` returns active categories,
  brands, varieties, and units for that organization's forms.
- `GET /api/products/branches/{branch_id}/?search=...` lists catalog products.
- `POST /api/products/branches/{branch_id}/` creates a product in that
  organization.
- `GET` and `PATCH /api/products/branches/{branch_id}/{product_id}/` read or
  update a product within that organization.

Before using the catalog screen, an administrator must create the organization,
branch, membership, and initial category and units through Django admin:

1. Add product categories, units, and (as needed) brands and varieties.
2. Add products using records from the same organization.
3. Avoid deleting referenced records; deactivate them instead.

No organization, branch, unit, category, brand, variety, or product rows are
seeded by migrations. Migrations only attach factors to existing unit records
whose standard factor is verified by their exact name/symbol; they never add
catalog or business transactions.
