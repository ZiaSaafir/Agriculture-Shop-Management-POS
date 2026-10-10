from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.organizations.models import Branch
from apps.products.models import Product


class ImmutableStockMovementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Stock movements are immutable; record a reversal.")

    def delete(self):
        raise ValueError("Stock movements are immutable; record a reversal.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Record stock movements through the inventory service.")


class StockBalance(models.Model):
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_balances",
    )
    on_hand = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0"),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("product__name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("branch", "product"),
                name="unique_stock_balance_per_branch_product",
            ),
            models.CheckConstraint(
                condition=Q(on_hand__gte=0),
                name="stock_balance_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "on_hand"),
                name="stock_branch_on_hand_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.branch_id and self.product_id:
            branch_organization_id = (
                Branch.objects.filter(pk=self.branch_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            product_organization_id = (
                Product.objects.filter(pk=self.product_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if (
                branch_organization_id is not None
                and product_organization_id is not None
                and branch_organization_id != product_organization_id
            ):
                raise ValidationError(
                    {"product": "Product and branch must belong to the same organization."}
                )

    def __str__(self):
        return f"{self.branch}: {self.product} = {self.on_hand}"


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        OPENING_STOCK = "opening_stock", "Opening stock"
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        CUSTOMER_RETURN = "customer_return", "Customer return"
        SUPPLIER_RETURN = "supplier_return", "Supplier return"
        DAMAGE = "damage", "Damage"
        LOSS = "loss", "Loss"
        ADJUSTMENT_IN = "adjustment_in", "Adjustment in"
        ADJUSTMENT_OUT = "adjustment_out", "Adjustment out"
        TRANSFER_IN = "transfer_in", "Transfer in"
        TRANSFER_OUT = "transfer_out", "Transfer out"

    INCREASING_TYPES = (
        MovementType.OPENING_STOCK,
        MovementType.PURCHASE,
        MovementType.CUSTOMER_RETURN,
        MovementType.ADJUSTMENT_IN,
        MovementType.TRANSFER_IN,
    )
    DECREASING_TYPES = (
        MovementType.SALE,
        MovementType.SUPPLIER_RETURN,
        MovementType.DAMAGE,
        MovementType.LOSS,
        MovementType.ADJUSTMENT_OUT,
        MovementType.TRANSFER_OUT,
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_type = models.CharField(
        max_length=24,
        choices=MovementType.choices,
    )
    product_name_snapshot = models.CharField(max_length=200)
    unit_symbol_snapshot = models.CharField(max_length=24)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableStockMovementQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="stock_movement_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    movement_type__in=(
                        "opening_stock",
                        "purchase",
                        "sale",
                        "customer_return",
                        "supplier_return",
                        "damage",
                        "loss",
                        "adjustment_in",
                        "adjustment_out",
                        "transfer_in",
                        "transfer_out",
                    )
                ),
                name="stock_movement_type_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "product", "created_at"),
                name="mov_br_prod_time_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.branch_id and self.product_id:
            branch_organization_id = (
                Branch.objects.filter(pk=self.branch_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            product_organization_id = (
                Product.objects.filter(pk=self.product_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if (
                branch_organization_id is not None
                and product_organization_id is not None
                and branch_organization_id != product_organization_id
            ):
                errors["product"] = (
                    "Product and branch must belong to the same organization."
                )
        if self.movement_type not in self.MovementType.values:
            errors["movement_type"] = "Select a valid stock movement type."
        if not self.reason or not self.reason.strip():
            errors["reason"] = "A reason is required for every stock movement."
        if errors:
            raise ValidationError(errors)

    @property
    def signed_quantity(self):
        if self.movement_type in self.INCREASING_TYPES:
            return self.quantity
        return -self.quantity

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("Stock movements are immutable; record a reversal.")
        if not getattr(self, "_recording_stock_change", False):
            raise ValueError("Record stock movements through the inventory service.")
        if not self.pk:
            self.product_name_snapshot = self.product.name
            self.unit_symbol_snapshot = self.product.base_unit.symbol
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Stock movements are immutable; record a reversal.")

    def __str__(self):
        return f"{self.get_movement_type_display()}: {self.quantity} {self.product}"
