from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import StockMovement
from apps.inventory.services import record_stock_movement
from apps.organizations.models import Branch
from apps.products.models import Product
from apps.suppliers.models import Supplier, SupplierLedgerEntry
from apps.suppliers.services import post_supplier_ledger_entry

from .models import Purchase, PurchaseLine

MONEY_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _save_purchase(purchase: Purchase, **kwargs) -> None:
    purchase._purchase_service_write = True
    try:
        purchase.save(**kwargs)
    finally:
        del purchase._purchase_service_write


def _validate_purchase_context(*, branch: Branch, supplier: Supplier) -> None:
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Purchases require an active branch."})
    if not supplier.is_active or not supplier.organization.is_active:
        raise ValidationError({"supplier": "Choose an active supplier."})
    if branch.organization_id != supplier.organization_id:
        raise ValidationError(
            {"supplier": "Supplier must belong to this branch's organization."}
        )


def _write_items(purchase: Purchase, items: list[dict]) -> None:
    if not items:
        raise ValidationError({"items": "A purchase must contain at least one item."})

    product_ids = {item["product"].pk for item in items}
    products = {
        product.pk: product
        for product in Product.objects.select_related("base_unit").filter(
            pk__in=product_ids,
            organization_id=purchase.organization_id,
            is_active=True,
            base_unit__is_active=True,
        )
    }
    if product_ids != set(products):
        raise ValidationError(
            {"items": "Every product must be active and belong to this organization."}
        )

    purchase.items.all().delete_for_purchase_service()
    subtotal_total = Decimal("0.00")
    discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")

    for item in items:
        product = products[item["product"].pk]
        quantity = item["quantity"]
        precision = Decimal(1).scaleb(-product.base_unit.decimal_places)
        if quantity.quantize(precision) != quantity:
            raise ValidationError(
                {
                    "items": (
                        f"{product.name} quantity supports at most "
                        f"{product.base_unit.decimal_places} decimal places "
                        f"({product.base_unit.symbol})."
                    )
                }
            )

        line_subtotal = _money(quantity * item["unit_cost"])
        discount = item.get("discount_amount", Decimal("0.00"))
        tax = item.get("tax_amount", Decimal("0.00"))
        if discount > line_subtotal:
            raise ValidationError(
                {"items": f"Discount cannot exceed the subtotal for {product.name}."}
            )
        line_total = line_subtotal - discount + tax
        line = PurchaseLine(
            purchase=purchase,
            product=product,
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
            unit_symbol_snapshot=product.base_unit.symbol,
            quantity=quantity,
            unit_cost=item["unit_cost"],
            subtotal=line_subtotal,
            discount_amount=discount,
            tax_amount=tax,
            total=line_total,
        )
        line.full_clean()
        line._purchase_service_write = True
        line.save(force_insert=True)
        del line._purchase_service_write
        subtotal_total += line_subtotal
        discount_total += discount
        tax_total += tax

    purchase.subtotal = subtotal_total
    purchase.discount_total = discount_total
    purchase.tax_total = tax_total
    purchase.total = subtotal_total - discount_total + tax_total
    for field_name in ("subtotal", "discount_total", "tax_total", "total"):
        try:
            setattr(
                purchase,
                field_name,
                Purchase._meta.get_field(field_name).clean(
                    getattr(purchase, field_name),
                    purchase,
                ),
            )
        except ValidationError as exc:
            raise ValidationError(
                {"items": "Purchase totals exceed the supported amount."}
            ) from exc
    _save_purchase(
        purchase,
        update_fields=(
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "updated_at",
        )
    )


@transaction.atomic
def create_draft_purchase(
    *,
    branch: Branch,
    supplier: Supplier,
    items: list[dict],
    created_by,
    supplier_invoice_number: str = "",
    purchase_date=None,
    notes: str = "",
) -> Purchase:
    _validate_purchase_context(branch=branch, supplier=supplier)
    purchase = Purchase(
        organization=branch.organization,
        branch=branch,
        supplier=supplier,
        supplier_name_snapshot=supplier.name,
        supplier_invoice_number=supplier_invoice_number.strip(),
        purchase_date=purchase_date or timezone.localdate(),
        notes=notes.strip(),
        created_by=created_by,
    )
    _save_purchase(purchase, force_insert=True)
    _write_items(purchase, items)
    return purchase


@transaction.atomic
def update_draft_purchase(
    *,
    purchase: Purchase,
    supplier: Supplier | None = None,
    items: list[dict] | None = None,
    supplier_invoice_number: str | None = None,
    purchase_date=None,
    notes: str | None = None,
) -> Purchase:
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status != Purchase.Status.DRAFT:
        raise ValidationError({"status": "Only draft purchases can be edited."})

    selected_supplier = supplier or purchase.supplier
    _validate_purchase_context(branch=purchase.branch, supplier=selected_supplier)
    if supplier is not None:
        purchase.supplier = supplier
        purchase.supplier_name_snapshot = supplier.name
    if supplier_invoice_number is not None:
        purchase.supplier_invoice_number = supplier_invoice_number.strip()
    if purchase_date is not None:
        purchase.purchase_date = purchase_date
    if notes is not None:
        purchase.notes = notes.strip()
    _save_purchase(
        purchase,
        update_fields=(
            "supplier",
            "supplier_name_snapshot",
            "supplier_invoice_number",
            "purchase_date",
            "notes",
            "updated_at",
        )
    )
    if items is not None:
        _write_items(purchase, items)
    return purchase


@transaction.atomic
def post_purchase(*, purchase: Purchase, posted_by) -> Purchase:
    purchase = (
        Purchase.objects.select_for_update()
        .select_related("organization", "branch", "supplier")
        .get(pk=purchase.pk)
    )
    if purchase.status != Purchase.Status.DRAFT:
        raise ValidationError({"status": "Only draft purchases can be received."})
    _validate_purchase_context(branch=purchase.branch, supplier=purchase.supplier)
    if purchase.total <= 0:
        raise ValidationError({"total": "A purchase total must be greater than zero."})

    lines = list(
        purchase.items.select_related("product", "product__base_unit")
        .order_by("product_id", "pk")
    )
    if not lines:
        raise ValidationError({"items": "A purchase must contain at least one item."})

    reference = purchase.purchase_number
    reason = f"Purchase received: {reference}"
    for line in lines:
        product = line.product
        if not product.is_active or not product.base_unit.is_active:
            raise ValidationError(
                {"items": f"{product.name} is no longer active for purchasing."}
            )
        line.product_name_snapshot = product.name
        line.sku_snapshot = product.sku
        line.unit_symbol_snapshot = product.base_unit.symbol
        line._purchase_service_write = True
        line.save(
            update_fields=(
                "product_name_snapshot",
                "sku_snapshot",
                "unit_symbol_snapshot",
            )
        )
        del line._purchase_service_write
        record_stock_movement(
            branch=purchase.branch,
            product=product,
            movement_type=StockMovement.MovementType.PURCHASE,
            quantity=line.quantity,
            reason=reason,
            reference=reference,
            created_by=posted_by,
        )

    post_supplier_ledger_entry(
        supplier=purchase.supplier,
        branch=purchase.branch,
        entry_type=SupplierLedgerEntry.EntryType.PURCHASE,
        amount=purchase.total,
        reason=reason,
        reference=reference,
        created_by=posted_by,
    )
    purchase.status = Purchase.Status.POSTED
    purchase.supplier_name_snapshot = purchase.supplier.name
    purchase.posted_by = posted_by
    purchase.posted_at = timezone.now()
    _save_purchase(
        purchase,
        update_fields=(
            "status",
            "supplier_name_snapshot",
            "posted_by",
            "posted_at",
            "updated_at",
        )
    )
    return purchase
