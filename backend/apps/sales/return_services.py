from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.customers.models import Customer, CustomerLedgerEntry
from apps.customers.services import customer_branch_balance, post_customer_ledger_entry
from apps.inventory.models import StockMovement
from apps.inventory.services import record_stock_movement

from .models import Sale, SaleLine, SalesReturn, SalesReturnLine

MONEY_QUANTUM = Decimal("0.01")


def _money(value):
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@transaction.atomic
def create_sales_return(
    *,
    branch,
    sale: Sale,
    items: list[dict],
    disposition: str,
    created_by,
    notes: str = "",
    return_date=None,
) -> SalesReturn:
    sale = (
        Sale.objects.select_for_update()
        .select_related("organization", "branch", "customer")
        .get(pk=sale.pk)
    )
    if sale.branch_id != branch.pk or sale.status != Sale.Status.COMPLETED:
        raise ValidationError(
            {"sale": "Returns require a completed sale from this branch."}
        )
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Returns require an active branch."})
    if disposition not in SalesReturn.Disposition.values:
        raise ValidationError({"disposition": "Select a valid return disposition."})
    if not items:
        raise ValidationError({"items": "A return must contain at least one item."})
    if disposition != SalesReturn.Disposition.CASH_REFUND and sale.customer_id is None:
        raise ValidationError(
            {"disposition": "Walk-in sales can only receive a cash refund."}
        )
    if sale.customer_id:
        sale.customer = Customer.objects.select_for_update().select_related(
            "organization"
        ).get(pk=sale.customer_id)
        if not sale.customer.is_active or not sale.customer.organization.is_active:
            raise ValidationError(
                {"customer": "Returns require an active customer and organization."}
            )

    line_ids = [item["sale_line"].pk for item in items]
    if len(line_ids) != len(set(line_ids)):
        raise ValidationError(
            {"items": "Each original sale line may appear only once per return."}
        )
    source_lines = {
        line.pk: line
        for line in SaleLine.objects.select_for_update()
        .select_related("product", "product__base_unit", "transaction_unit")
        .filter(pk__in=line_ids, sale=sale)
    }
    if set(line_ids) != set(source_lines):
        raise ValidationError(
            {"items": "Every return line must belong to the original sale."}
        )

    already_returned = {
        row["sale_line_id"]: row
        for row in SalesReturnLine.objects.filter(
            sale_line_id__in=line_ids,
        )
        .values("sale_line_id")
        .annotate(
            returned_quantity=Sum("base_quantity"),
            credit_total=Sum("credit_amount"),
        )
    }
    calculated_items = []
    return_total = Decimal("0.00")
    for item in items:
        sale_line = source_lines[item["sale_line"].pk]
        quantity = item["quantity"]
        precision = Decimal(1).scaleb(-sale_line.transaction_unit.decimal_places)
        if quantity.quantize(precision) != quantity:
            raise ValidationError(
                {
                    "items": (
                        f"{sale_line.product_name_snapshot} supports at most "
                        f"{sale_line.transaction_unit.decimal_places} decimal places "
                        f"({sale_line.unit_symbol_snapshot})."
                    )
                }
            )
        if (
            not sale_line.product.allow_fractional_quantity
            and quantity != quantity.to_integral_value()
        ):
            raise ValidationError(
                {
                    "items": (
                        f"{sale_line.product_name_snapshot} does not allow "
                        "fractional quantities."
                    )
                }
            )
        base_quantity = (quantity * sale_line.unit_to_base_factor).quantize(
            Decimal("0.000001")
        )
        prior = already_returned.get(sale_line.pk, {})
        already_returned_base = prior.get("returned_quantity") or Decimal("0")
        remaining_base = sale_line.base_quantity - already_returned_base
        if base_quantity <= 0 or base_quantity > remaining_base:
            remaining_transaction_quantity = (
                remaining_base / sale_line.unit_to_base_factor
            )
            raise ValidationError(
                {
                    "items": (
                        f"Return quantity for {sale_line.product_name_snapshot} "
                        f"exceeds the remaining quantity "
                        f"({remaining_transaction_quantity} "
                        f"{sale_line.unit_symbol_snapshot})."
                    )
                }
            )
        remaining_credit = sale_line.total - (prior.get("credit_total") or Decimal("0"))
        if base_quantity == remaining_base:
            credit_amount = remaining_credit
        else:
            credit_amount = _money(
                sale_line.total * base_quantity / sale_line.base_quantity
            )
            credit_amount = min(credit_amount, remaining_credit)
        calculated_items.append(
            {
                "sale_line": sale_line,
                "quantity": quantity,
                "base_quantity": base_quantity,
                "credit_amount": credit_amount,
            }
        )
        return_total += credit_amount

    return_total = _money(return_total)
    if disposition == SalesReturn.Disposition.DEBT_REDUCTION:
        if sale.customer_id is None:
            raise ValidationError(
                {"disposition": "Debt reduction requires a registered customer."}
            )
        balance = customer_branch_balance(customer=sale.customer, branch=branch)
        if balance <= 0 or return_total > balance:
            raise ValidationError(
                {
                    "disposition": (
                        "Return value exceeds the customer's outstanding debt. "
                        "Choose store credit or a cash refund instead."
                    )
                }
            )

    sales_return = SalesReturn(
        organization=sale.organization,
        branch=branch,
        sale=sale,
        disposition=disposition,
        return_date=return_date or timezone.localdate(),
        total=return_total,
        notes=notes.strip(),
        created_by=created_by,
    )
    sales_return.full_clean()
    sales_return._sales_return_service_write = True
    sales_return.save(force_insert=True)
    del sales_return._sales_return_service_write

    for item in calculated_items:
        sale_line = item["sale_line"]
        return_line = SalesReturnLine(
            sales_return=sales_return,
            sale_line=sale_line,
            product=sale_line.product,
            product_name_snapshot=sale_line.product_name_snapshot,
            sku_snapshot=sale_line.sku_snapshot,
            unit_symbol_snapshot=sale_line.unit_symbol_snapshot,
            quantity=item["quantity"],
            base_quantity=item["base_quantity"],
            credit_amount=item["credit_amount"],
        )
        return_line.full_clean()
        return_line._sales_return_service_write = True
        return_line.save(force_insert=True)
        del return_line._sales_return_service_write
        record_stock_movement(
            branch=branch,
            product=sale_line.product,
            movement_type=StockMovement.MovementType.CUSTOMER_RETURN,
            quantity=item["base_quantity"],
            reason=f"Customer return {sales_return.return_number}",
            reference=sales_return.return_number,
            created_by=created_by,
        )

    if sale.customer_id and return_total > 0:
        post_customer_ledger_entry(
            customer=sale.customer,
            branch=branch,
            entry_type=CustomerLedgerEntry.EntryType.RETURN,
            amount=return_total,
            reason=f"Customer return {sales_return.return_number}",
            reference=sales_return.return_number,
            created_by=created_by,
        )
        if disposition == SalesReturn.Disposition.CASH_REFUND:
            post_customer_ledger_entry(
                customer=sale.customer,
                branch=branch,
                entry_type=CustomerLedgerEntry.EntryType.ADJUSTMENT_DEBIT,
                amount=return_total,
                reason=f"Cash refund for {sales_return.return_number}",
                reference=sales_return.return_number,
                created_by=created_by,
            )
    return sales_return
