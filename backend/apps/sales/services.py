from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.customers.models import Customer, CustomerLedgerEntry
from apps.customers.services import post_customer_ledger_entry
from apps.inventory.models import StockMovement
from apps.inventory.services import InsufficientStockError, record_stock_movement
from apps.organizations.models import Branch
from apps.products.models import Product

from .models import Sale, SaleLine

MONEY_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _save_sale(sale: Sale, **kwargs) -> None:
    sale._sales_service_write = True
    try:
        sale.save(**kwargs)
    finally:
        del sale._sales_service_write


def _validate_branch_customer(
    *,
    branch: Branch,
    customer: Customer | None,
) -> None:
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Sales require an active branch."})
    if customer is not None:
        if not customer.is_active or not customer.organization.is_active:
            raise ValidationError({"customer": "Choose an active customer."})
        if customer.organization_id != branch.organization_id:
            raise ValidationError(
                {"customer": "Customer must belong to this branch's organization."}
            )


def _replace_sale_items(sale: Sale, items: list[dict]) -> None:
    if not items:
        raise ValidationError({"items": "A sale must contain at least one item."})

    product_ids = {item["product"].pk for item in items}
    products = {
        product.pk: product
        for product in Product.objects.select_related("base_unit").filter(
            pk__in=product_ids,
            organization_id=sale.organization_id,
            is_active=True,
            base_unit__is_active=True,
        )
    }
    if product_ids != set(products):
        raise ValidationError(
            {"items": "Every product must be active and belong to this organization."}
        )

    sale.items.all().delete_for_sales_service()
    subtotal_total = Decimal("0.00")
    discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")

    for item in items:
        product = products[item["product"].pk]
        quantity = item["quantity"]
        transaction_unit = item.get("transaction_unit", product.base_unit)
        if (
            transaction_unit.organization_id != sale.organization_id
            or not transaction_unit.is_active
        ):
            raise ValidationError(
                {"items": f"Choose an active unit for {product.name}."}
            )
        if transaction_unit.pk == product.base_unit_id:
            factor = Decimal("1")
        elif (
            transaction_unit.dimension != product.base_unit.dimension
            or transaction_unit.canonical_factor is None
            or product.base_unit.canonical_factor is None
        ):
            raise ValidationError(
                {
                    "items": (
                        f"No verified conversion exists from "
                        f"{transaction_unit.symbol} to {product.base_unit.symbol}."
                    )
                }
            )
        else:
            factor = (
                transaction_unit.canonical_factor
                / product.base_unit.canonical_factor
            ).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)

        if not product.allow_fractional_quantity and quantity != quantity.to_integral_value():
            raise ValidationError(
                {
                    "items": (
                        f"{product.name} does not allow fractional quantities. "
                        "Enable fractional quantities in product settings if needed."
                    )
                }
            )
        precision = Decimal(1).scaleb(-transaction_unit.decimal_places)
        if quantity.quantize(precision) != quantity:
            raise ValidationError(
                {
                    "items": (
                        f"{product.name} quantity supports at most "
                        f"{transaction_unit.decimal_places} decimal places "
                        f"({transaction_unit.symbol})."
                    )
                }
            )
        base_quantity = quantity * factor
        base_quantity = base_quantity.quantize(Decimal("0.000001"))
        base_precision = Decimal(1).scaleb(-product.base_unit.decimal_places)
        if base_quantity.quantize(base_precision) != base_quantity:
            raise ValidationError(
                {
                    "items": (
                        f"{quantity} {transaction_unit.symbol} cannot be represented "
                        f"at the precision supported by {product.base_unit.symbol}."
                    )
                }
            )
        unit_price = item.get("unit_price")
        if unit_price is None:
            unit_price = _money(product.selling_price * factor)
        line_subtotal = _money(quantity * unit_price)
        discount = item.get("discount_amount", Decimal("0.00"))
        tax = item.get("tax_amount", Decimal("0.00"))
        if discount > line_subtotal:
            raise ValidationError(
                {"items": f"Discount cannot exceed the subtotal for {product.name}."}
            )
        line = SaleLine(
            sale=sale,
            product=product,
            product_name_snapshot=product.name,
            sku_snapshot=product.sku,
            unit_symbol_snapshot=transaction_unit.symbol,
            quantity=quantity,
            base_quantity=base_quantity,
            transaction_unit=transaction_unit,
            unit_to_base_factor=factor,
            unit_price=unit_price,
            subtotal=line_subtotal,
            discount_amount=discount,
            tax_amount=tax,
            total=line_subtotal - discount + tax,
        )
        line.full_clean()
        line._sales_service_write = True
        line.save(force_insert=True)
        del line._sales_service_write
        subtotal_total += line_subtotal
        discount_total += discount
        tax_total += tax

    sale.subtotal = subtotal_total
    sale.discount_total = discount_total
    sale.tax_total = tax_total
    sale.total = subtotal_total - discount_total + tax_total
    for field_name in ("subtotal", "discount_total", "tax_total", "total"):
        try:
            setattr(
                sale,
                field_name,
                Sale._meta.get_field(field_name).clean(
                    getattr(sale, field_name),
                    sale,
                ),
            )
        except ValidationError as exc:
            raise ValidationError(
                {"items": "Sale totals exceed the supported amount."}
            ) from exc
    _save_sale(
        sale,
        update_fields=(
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "updated_at",
        ),
    )


@transaction.atomic
def create_draft_sale(
    *,
    branch: Branch,
    items: list[dict],
    created_by,
    customer: Customer | None = None,
    sale_date=None,
    notes: str = "",
) -> Sale:
    _validate_branch_customer(branch=branch, customer=customer)
    sale = Sale(
        organization=branch.organization,
        branch=branch,
        customer=customer,
        customer_name_snapshot=customer.name if customer else "Walk-in",
        sale_date=sale_date or timezone.localdate(),
        notes=notes.strip(),
        created_by=created_by,
    )
    _save_sale(sale, force_insert=True)
    _replace_sale_items(sale, items)
    return sale


@transaction.atomic
def update_draft_sale(
    *,
    sale: Sale,
    customer: Customer | None = None,
    update_customer: bool = False,
    items: list[dict] | None = None,
    sale_date=None,
    notes: str | None = None,
) -> Sale:
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.DRAFT:
        raise ValidationError({"status": "Only draft sales can be edited."})
    selected_customer = customer if update_customer else sale.customer
    _validate_branch_customer(branch=sale.branch, customer=selected_customer)

    if update_customer:
        sale.customer = selected_customer
        sale.customer_name_snapshot = (
            selected_customer.name if selected_customer else "Walk-in"
        )
    if sale_date is not None:
        sale.sale_date = sale_date
    if notes is not None:
        sale.notes = notes.strip()
    _save_sale(
        sale,
        update_fields=(
            "customer",
            "customer_name_snapshot",
            "sale_date",
            "notes",
            "updated_at",
        ),
    )
    if items is not None:
        _replace_sale_items(sale, items)
    return sale


@transaction.atomic
def complete_sale(
    *,
    sale: Sale,
    completed_by,
    amount_paid: Decimal,
    payment_method: str = "",
    payment_reference: str = "",
) -> Sale:
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.DRAFT:
        raise ValidationError({"status": "Only draft sales can be completed."})
    _validate_branch_customer(branch=sale.branch, customer=sale.customer)
    if sale.total <= 0:
        raise ValidationError({"total": "A sale total must be greater than zero."})
    amount_paid = Sale._meta.get_field("amount_paid").clean(amount_paid, sale)
    if sale.customer is None and amount_paid < sale.total:
        raise ValidationError(
            {"amount_paid": "Walk-in sales must be paid in full at checkout."}
        )
    if amount_paid > 0 and not payment_method.strip():
        raise ValidationError(
            {"payment_method": "Choose the payment method used at checkout."}
        )

    lines = list(
        sale.items.select_related("product", "product__base_unit")
        .order_by("product_id", "pk")
    )
    if not lines:
        raise ValidationError({"items": "A sale must contain at least one item."})
    for line in lines:
        product = line.product
        if not product.is_active or not product.base_unit.is_active:
            raise ValidationError(
                {"items": f"{product.name} is no longer active for sale."}
            )
        line._sales_service_write = True
        line.save(
            update_fields=(
                "product_name_snapshot",
                "sku_snapshot",
                "unit_symbol_snapshot",
            )
        )
        del line._sales_service_write
        record_stock_movement(
            branch=sale.branch,
            product=product,
            movement_type=StockMovement.MovementType.SALE,
            quantity=line.base_quantity,
            reason=f"Point-of-sale transaction {sale.sale_number}",
            reference=sale.sale_number,
            created_by=completed_by,
        )

    if sale.customer is not None:
        sale.customer = Customer.objects.select_for_update().get(
            pk=sale.customer_id
        )
        if not sale.customer.is_active or not sale.customer.organization.is_active:
            raise ValidationError({"customer": "Choose an active customer."})

    if sale.customer is not None:
        post_customer_ledger_entry(
            customer=sale.customer,
            branch=sale.branch,
            entry_type=CustomerLedgerEntry.EntryType.SALE,
            amount=sale.total,
            reason=f"Sale {sale.sale_number}",
            reference=sale.sale_number,
            created_by=completed_by,
        )
        if amount_paid > 0:
            post_customer_ledger_entry(
                customer=sale.customer,
                branch=sale.branch,
                entry_type=CustomerLedgerEntry.EntryType.PAYMENT,
                amount=amount_paid,
                reason=f"Payment at sale {sale.sale_number}",
                reference=payment_reference.strip() or sale.sale_number,
                created_by=completed_by,
            )

    sale.amount_paid = amount_paid
    sale.payment_method = payment_method.strip()
    sale.payment_reference = payment_reference.strip()
    sale.status = Sale.Status.COMPLETED
    sale.customer_name_snapshot = (
        sale.customer.name if sale.customer else "Walk-in"
    )
    sale.completed_by = completed_by
    sale.completed_at = timezone.now()
    _save_sale(
        sale,
        update_fields=(
            "amount_paid",
            "payment_method",
            "payment_reference",
            "status",
            "customer_name_snapshot",
            "completed_by",
            "completed_at",
            "updated_at",
        ),
    )
    return sale


__all__ = (
    "InsufficientStockError",
    "complete_sale",
    "create_draft_sale",
    "update_draft_sale",
)
