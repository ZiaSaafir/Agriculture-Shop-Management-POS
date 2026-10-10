from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When

from apps.organizations.models import Branch
from apps.products.models import Product

from .models import StockBalance, StockMovement


class InsufficientStockError(Exception):
    def __init__(self, available, requested):
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient stock: {available} available, {requested} requested."
        )


@transaction.atomic
def record_stock_movement(
    *,
    branch: Branch,
    product: Product,
    movement_type: str,
    quantity: Decimal,
    reason: str,
    created_by,
    reference: str = "",
) -> StockMovement:
    if movement_type not in StockMovement.MovementType.values:
        raise ValidationError({"movement_type": "Select a valid stock movement type."})
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if not reason or not reason.strip():
        raise ValidationError({"reason": "A reason is required."})
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Stock can only change in an active branch."})
    if branch.organization_id != product.organization_id:
        raise ValidationError(
            {"product": "Product and branch must belong to the same organization."}
        )
    quantity = StockMovement._meta.get_field("quantity").clean(quantity, None)
    quantity_at_unit_precision = quantity.quantize(
        Decimal(1).scaleb(-product.base_unit.decimal_places)
    )
    if quantity != quantity_at_unit_precision:
        raise ValidationError(
            {
                "quantity": (
                    f"Quantity supports at most "
                    f"{product.base_unit.decimal_places} decimal places for "
                    f"{product.base_unit.symbol}."
                )
            }
        )

    balance, _ = StockBalance.objects.get_or_create(
        branch=branch,
        product=product,
        defaults={"on_hand": Decimal("0")},
    )

    balance = StockBalance.objects.select_for_update().get(pk=balance.pk)
    movement = StockMovement(
        branch=branch,
        product=product,
        movement_type=movement_type,
        product_name_snapshot=product.name,
        unit_symbol_snapshot=product.base_unit.symbol,
        quantity=quantity,
        reason=reason.strip(),
        reference=reference.strip(),
        created_by=created_by,
    )
    movement.full_clean()

    next_quantity = balance.on_hand + movement.signed_quantity
    if next_quantity < 0:
        raise InsufficientStockError(balance.on_hand, quantity)

    movement._recording_stock_change = True
    movement.save(force_insert=True)
    balance.on_hand = next_quantity
    balance.save(update_fields=("on_hand", "updated_at"))
    return movement


def ledger_quantity(*, branch: Branch, product: Product) -> Decimal:
    signed_quantity = Case(
        When(
            movement_type__in=StockMovement.INCREASING_TYPES,
            then=F("quantity"),
        ),
        default=-F("quantity"),
        output_field=DecimalField(max_digits=19, decimal_places=6),
    )
    return (
        StockMovement.objects.filter(branch=branch, product=product).aggregate(
            total=Sum(signed_quantity)
        )["total"]
        or Decimal("0")
    )
