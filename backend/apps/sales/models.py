from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.customers.models import Customer
from apps.organizations.models import Branch, Organization
from apps.products.models import Product, Unit


class SaleQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Edit sales through the checkout service.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create sales through the checkout service.")

    def delete(self):
        if self.filter(status=Sale.Status.COMPLETED).exists():
            raise ValueError("Completed sales cannot be deleted.")
        return super().delete()


class Sale(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COMPLETED = "completed", "Completed"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )
    customer_name_snapshot = models.CharField(max_length=200, blank=True)
    sale_date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    subtotal = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount_paid = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    payment_method = models.CharField(max_length=40, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_sales",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_sales",
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = SaleQuerySet.as_manager()

    class Meta:
        ordering = ("-sale_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=("draft", "completed")),
                name="sale_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(tax_total__gte=0)
                & Q(total__gte=0)
                & Q(amount_paid__gte=0),
                name="sale_amounts_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("discount_total") + F("tax_total")),
                name="sale_total_matches_components",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "status", "sale_date"),
                name="sale_branch_status_date_idx",
            ),
            models.Index(
                fields=("customer", "sale_date"),
                name="sale_customer_date_idx",
            ),
        ]

    @property
    def sale_number(self):
        return f"SALE-{self.pk:06d}" if self.pk else None

    @property
    def balance_due(self):
        return max(Decimal("0.00"), self.total - self.amount_paid)

    @property
    def change_due(self):
        if self.customer_id:
            return Decimal("0.00")
        return max(Decimal("0.00"), self.amount_paid - self.total)

    @property
    def customer_advance_amount(self):
        if self.customer_id:
            return max(Decimal("0.00"), self.amount_paid - self.total)
        return Decimal("0.00")

    def clean(self):
        super().clean()
        errors = {}
        if self.branch_id and self.organization_id:
            branch_org_id = Branch.objects.filter(pk=self.branch_id).values_list(
                "organization_id", flat=True
            ).first()
            if branch_org_id != self.organization_id:
                errors["branch"] = "Branch must belong to this organization."
        if self.customer_id and self.organization_id:
            customer_org_id = Customer.objects.filter(pk=self.customer_id).values_list(
                "organization_id", flat=True
            ).first()
            if customer_org_id != self.organization_id:
                errors["customer"] = "Customer must belong to this organization."
        if self.status == self.Status.COMPLETED and (
            self.completed_by_id is None or self.completed_at is None
        ):
            errors["status"] = "Completed sales require a user and completion time."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not getattr(self, "_sales_service_write", False):
            raise ValueError("Write sales through the checkout service.")
        if self.pk:
            existing_status = type(self).objects.filter(pk=self.pk).values_list(
                "status", flat=True
            ).first()
            if existing_status == self.Status.COMPLETED:
                raise ValueError("Completed sales are immutable.")
        elif self.status != self.Status.DRAFT:
            raise ValueError("Create sales as drafts.")
        if self.customer_id:
            self.customer_name_snapshot = self.customer.name
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.COMPLETED:
            raise ValueError("Completed sales cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.sale_number or "New sale"


class SaleLineQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Edit sale lines through the checkout service.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create sale lines through the checkout service.")

    def delete(self):
        raise ValueError("Remove sale lines through the checkout service.")

    def delete_for_sales_service(self):
        if self.filter(sale__status=Sale.Status.COMPLETED).exists():
            raise ValueError("Lines on completed sales are immutable.")
        return super().delete()


class SaleLine(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sale_lines",
    )
    product_name_snapshot = models.CharField(max_length=200)
    sku_snapshot = models.CharField(max_length=64)
    unit_symbol_snapshot = models.CharField(max_length=24)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    base_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    transaction_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="sale_lines",
    )
    unit_to_base_factor = models.DecimalField(
        max_digits=24,
        decimal_places=12,
        default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.000000000001"))],
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    subtotal = models.DecimalField(max_digits=16, decimal_places=2)
    discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    total = models.DecimalField(max_digits=16, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SaleLineQuerySet.as_manager()

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="sale_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(base_quantity__gt=0)
                & Q(unit_to_base_factor__gt=0),
                name="sale_line_base_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0)
                & Q(subtotal__gte=0)
                & Q(discount_amount__gte=0)
                & Q(tax_amount__gte=0)
                & Q(total__gte=0),
                name="sale_line_amounts_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(discount_amount__lte=F("subtotal")),
                name="sale_line_discount_within_subtotal",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("discount_amount") + F("tax_amount")),
                name="sale_line_total_matches_components",
            ),
        ]
        indexes = [
            models.Index(fields=("sale", "product"), name="sale_line_sale_prod_idx"),
        ]

    def clean(self):
        super().clean()
        if self.sale_id and self.product_id:
            sale_org_id = Sale.objects.filter(pk=self.sale_id).values_list(
                "organization_id", flat=True
            ).first()
            if sale_org_id is not None and sale_org_id != self.product.organization_id:
                raise ValidationError(
                    {"product": "Product must belong to the sale organization."}
                )

    def save(self, *args, **kwargs):
        if not getattr(self, "_sales_service_write", False):
            raise ValueError("Write sale lines through the checkout service.")
        if self.pk and Sale.objects.filter(
            pk=self.sale_id,
            status=Sale.Status.COMPLETED,
        ).exists():
            raise ValueError("Lines on completed sales are immutable.")
        if not self.pk:
            self.product_name_snapshot = self.product.name
            self.sku_snapshot = self.product.sku
            if not self.transaction_unit_id:
                self.transaction_unit = self.product.base_unit
            self.unit_symbol_snapshot = self.transaction_unit.symbol
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Remove sale lines through the checkout service.")

    def __str__(self):
        return f"{self.quantity} {self.unit_symbol_snapshot} {self.product_name_snapshot}"


class SalesReturnQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Posted customer returns are immutable.")

    def delete(self):
        raise ValueError("Posted customer returns are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create returns through the return service.")


class SalesReturn(models.Model):
    class Disposition(models.TextChoices):
        DEBT_REDUCTION = "debt_reduction", "Reduce customer debt"
        STORE_CREDIT = "store_credit", "Issue store credit"
        CASH_REFUND = "cash_refund", "Refund cash"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="sales_returns",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="sales_returns",
    )
    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="returns",
    )
    disposition = models.CharField(max_length=24, choices=Disposition.choices)
    return_date = models.DateField(default=timezone.localdate)
    total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_returns_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SalesReturnQuerySet.as_manager()

    class Meta:
        ordering = ("-return_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(disposition__in=(
                    "debt_reduction",
                    "store_credit",
                    "cash_refund",
                )),
                name="sales_return_disposition_valid",
            ),
            models.CheckConstraint(
                condition=Q(total__gte=0),
                name="sales_return_total_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "return_date"),
                name="sales_return_branch_date_idx",
            ),
        ]

    @property
    def return_number(self):
        return f"RET-{self.pk:06d}" if self.pk else None

    def save(self, *args, **kwargs):
        if not getattr(self, "_sales_return_service_write", False):
            raise ValueError("Create customer returns through the return service.")
        if self.pk:
            raise ValueError("Posted customer returns are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Posted customer returns are immutable.")


class SalesReturnLineQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Customer return lines are immutable.")

    def delete(self):
        raise ValueError("Customer return lines are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create return lines through the return service.")


class SalesReturnLine(models.Model):
    sales_return = models.ForeignKey(
        SalesReturn,
        on_delete=models.PROTECT,
        related_name="items",
    )
    sale_line = models.ForeignKey(
        SaleLine,
        on_delete=models.PROTECT,
        related_name="return_lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sales_return_lines",
    )
    product_name_snapshot = models.CharField(max_length=200)
    sku_snapshot = models.CharField(max_length=64)
    unit_symbol_snapshot = models.CharField(max_length=24)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    base_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    credit_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0) & Q(base_quantity__gt=0),
                name="sales_return_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(credit_amount__gte=0),
                name="sales_return_line_credit_nonnegative",
            ),
            models.UniqueConstraint(
                fields=("sales_return", "sale_line"),
                name="unique_sale_line_per_return",
            ),
        ]
    objects = SalesReturnLineQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not getattr(self, "_sales_return_service_write", False):
            raise ValueError("Create return lines through the return service.")
        if self.pk:
            raise ValueError("Posted return lines are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Posted return lines are immutable.")
