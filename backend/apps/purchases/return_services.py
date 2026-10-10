from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import StockMovement
from apps.inventory.services import InsufficientStockError, record_stock_movement
from apps.organizations.models import Branch
from apps.suppliers.models import SupplierLedgerEntry
from apps.suppliers.services import post_supplier_ledger_entry

from .models import (
    Purchase,
    PurchaseLine,
    PurchaseReturn,
    PurchaseReturnLine,
)


def _save_return(purchase_return: PurchaseReturn, **kwargs) -> None:
    purchase_return._purchase_return_service_write = True
    try:
        purchase_return.save(**kwargs)
    finally:
        del purchase_return._purchase_return_service_write


def _validate_purchase(*, branch: Branch, purchase: Purchase) -> None:
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Returns require an active branch."})
    if purchase.branch_id != branch.pk:
        raise ValidationError({"purchase": "Purchase must belong to this branch."})
    if purchase.status != Purchase.Status.POSTED:
        raise ValidationError({"purchase": "Only posted purchases can be returned."})
    if not purchase.supplier.is_active or not purchase.organization.is_active:
        raise ValidationError({"purchase": "The supplier or organization is inactive."})


def _write_return_items(
    purchase_return: PurchaseReturn,
    items: list[dict],
) -> None:
    if not items:
        raise ValidationError({"items": "A return must contain at least one item."})

    line_ids = [item["purchase_line"].pk for item in items]
    if len(line_ids) != len(set(line_ids)):
        raise ValidationError(
            {"items": "Each original purchase line may appear only once per return."}
        )

    source_lines = {
        line.pk: line
        for line in PurchaseLine.objects.select_related(
            "product",
            "product__base_unit",
        ).filter(
            pk__in=line_ids,
            purchase_id=purchase_return.purchase_id,
        )
    }
    if set(line_ids) != set(source_lines):
        raise ValidationError(
            {"items": "Every return line must belong to the original purchase."}
        )

    already_returned = {
        row["purchase_line_id"]: row["returned"]
        for row in PurchaseReturnLine.objects.filter(
            purchase_line_id__in=line_ids,
            purchase_return__status=PurchaseReturn.Status.POSTED,
        )
        .values("purchase_line_id")
        .annotate(returned=Sum("quantity"))
    }
    purchase_return.items.all().delete_for_return_service()
    credit_total = Decimal("0.00")
    for item in items:
        purchase_line = source_lines[item["purchase_line"].pk]
        quantity = item["quantity"]
        precision = Decimal(1).scaleb(
            -purchase_line.product.base_unit.decimal_places
        )
        if quantity.quantize(precision) != quantity:
            raise ValidationError(
                {
                    "items": (
                        f"{purchase_line.product_name_snapshot} supports at most "
                        f"{purchase_line.product.base_unit.decimal_places} decimal "
                        f"places ({purchase_line.unit_symbol_snapshot})."
                    )
                }
            )
        remaining = purchase_line.quantity - already_returned.get(
            purchase_line.pk,
            Decimal("0"),
        )
        if quantity > remaining:
            raise ValidationError(
                {
                    "items": (
                        f"Return quantity for {purchase_line.product_name_snapshot} "
                        f"exceeds the remaining returnable quantity ({remaining})."
                    )
                }
            )
        line = PurchaseReturnLine(
            purchase_return=purchase_return,
            purchase_line=purchase_line,
            product=purchase_line.product,
            product_name_snapshot=purchase_line.product_name_snapshot,
            sku_snapshot=purchase_line.sku_snapshot,
            unit_symbol_snapshot=purchase_line.unit_symbol_snapshot,
            quantity=quantity,
            credit_amount=item["credit_amount"],
        )
        line.full_clean()
        line._purchase_return_service_write = True
        line.save(force_insert=True)
        del line._purchase_return_service_write
        credit_total += line.credit_amount

    try:
        purchase_return.credit_total = PurchaseReturn._meta.get_field(
            "credit_total"
        ).clean(credit_total, purchase_return)
    except ValidationError as exc:
        raise ValidationError(
            {"items": "Return credit exceeds the supported amount."}
        ) from exc
    _save_return(
        purchase_return,
        update_fields=("credit_total", "updated_at"),
    )


@transaction.atomic
def create_draft_purchase_return(
    *,
    branch: Branch,
    purchase: Purchase,
    items: list[dict],
    created_by,
    supplier_credit_note_reference: str = "",
    return_date=None,
    notes: str = "",
) -> PurchaseReturn:
    purchase = Purchase.objects.select_for_update().select_related(
        "organization",
        "branch",
        "supplier",
    ).get(pk=purchase.pk)
    _validate_purchase(branch=branch, purchase=purchase)
    purchase_return = PurchaseReturn(
        organization=purchase.organization,
        branch=branch,
        purchase=purchase,
        supplier=purchase.supplier,
        supplier_name_snapshot=purchase.supplier_name_snapshot,
        supplier_credit_note_reference=supplier_credit_note_reference.strip(),
        return_date=return_date or timezone.localdate(),
        notes=notes.strip(),
        created_by=created_by,
    )
    purchase_return.full_clean()
    _save_return(purchase_return, force_insert=True)
    _write_return_items(purchase_return, items)
    return purchase_return


@transaction.atomic
def update_draft_purchase_return(
    *,
    purchase_return: PurchaseReturn,
    supplier_credit_note_reference: str | None = None,
    return_date=None,
    notes: str | None = None,
    items: list[dict] | None = None,
) -> PurchaseReturn:
    purchase_id = PurchaseReturn.objects.values_list(
        "purchase_id",
        flat=True,
    ).get(pk=purchase_return.pk)
    purchase = Purchase.objects.select_for_update().select_related(
        "organization",
        "branch",
        "supplier",
    ).get(pk=purchase_id)
    purchase_return = PurchaseReturn.objects.select_for_update().get(
        pk=purchase_return.pk
    )
    if purchase_return.status != PurchaseReturn.Status.DRAFT:
        raise ValidationError({"status": "Only draft returns can be edited."})
    _validate_purchase(branch=purchase.branch, purchase=purchase)

    if supplier_credit_note_reference is not None:
        purchase_return.supplier_credit_note_reference = (
            supplier_credit_note_reference.strip()
        )
    if return_date is not None:
        purchase_return.return_date = return_date
    if notes is not None:
        purchase_return.notes = notes.strip()
    _save_return(
        purchase_return,
        update_fields=(
            "supplier_credit_note_reference",
            "return_date",
            "notes",
            "updated_at",
        ),
    )
    if items is not None:
        _write_return_items(purchase_return, items)
    return purchase_return


@transaction.atomic
def post_purchase_return(
    *,
    purchase_return: PurchaseReturn,
    posted_by,
) -> PurchaseReturn:
    purchase_id = PurchaseReturn.objects.values_list(
        "purchase_id",
        flat=True,
    ).get(pk=purchase_return.pk)
    purchase = Purchase.objects.select_for_update().select_related(
        "organization",
        "branch",
        "supplier",
    ).get(pk=purchase_id)
    purchase_return = PurchaseReturn.objects.select_for_update().get(
        pk=purchase_return.pk
    )
    if purchase_return.status != PurchaseReturn.Status.DRAFT:
        raise ValidationError({"status": "Only draft returns can be posted."})
    _validate_purchase(branch=purchase.branch, purchase=purchase)
    lines = list(
        purchase_return.items.select_related(
            "purchase_line",
            "product",
            "product__base_unit",
        ).order_by("product_id", "pk")
    )
    if not lines:
        raise ValidationError({"items": "A return must contain at least one item."})
    if purchase_return.credit_total <= 0:
        raise ValidationError({"credit_total": "Return credit must be greater than zero."})

    reference = purchase_return.return_number
    reason = f"Supplier return: {reference}"
    for line in lines:
        already_returned = (
            PurchaseReturnLine.objects.filter(
                purchase_line=line.purchase_line,
                purchase_return__status=PurchaseReturn.Status.POSTED,
            ).aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )
        remaining = line.purchase_line.quantity - already_returned
        if line.quantity > remaining:
            raise ValidationError(
                {
                    "items": (
                        f"Return quantity for {line.product_name_snapshot} now "
                        f"exceeds the remaining quantity ({remaining})."
                    )
                }
            )
        record_stock_movement(
            branch=purchase.branch,
            product=line.product,
            movement_type=StockMovement.MovementType.SUPPLIER_RETURN,
            quantity=line.quantity,
            reason=reason,
            reference=reference,
            created_by=posted_by,
        )

    post_supplier_ledger_entry(
        supplier=purchase.supplier,
        branch=purchase.branch,
        entry_type=SupplierLedgerEntry.EntryType.RETURN,
        amount=purchase_return.credit_total,
        reason=reason,
        reference=purchase_return.supplier_credit_note_reference.strip()
        or reference,
        created_by=posted_by,
    )
    purchase_return.status = PurchaseReturn.Status.POSTED
    purchase_return.supplier_name_snapshot = purchase.supplier.name
    purchase_return.posted_by = posted_by
    purchase_return.posted_at = timezone.now()
    _save_return(
        purchase_return,
        update_fields=(
            "status",
            "supplier_name_snapshot",
            "posted_by",
            "posted_at",
            "updated_at",
        ),
    )
    return purchase_return


__all__ = (
    "InsufficientStockError",
    "create_draft_purchase_return",
    "post_purchase_return",
    "update_draft_purchase_return",
)
