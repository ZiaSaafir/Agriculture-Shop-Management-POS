from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.organizations.models import Branch, Organization
from apps.products.models import Product
from apps.suppliers.models import Supplier


class PurchaseQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Edit purchases through the purchase service.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create purchases through the purchase service.")

    def delete(self):
        if self.filter(status=Purchase.Status.POSTED).exists():
            raise ValueError("Posted purchases cannot be deleted.")
        return super().delete()


class Purchase(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted / received"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    supplier_name_snapshot = models.CharField(max_length=200)
    supplier_invoice_number = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(default=timezone.localdate)
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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_purchases",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="posted_purchases",
        null=True,
        blank=True,
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = PurchaseQuerySet.as_manager()

    class Meta:
        ordering = ("-purchase_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=("draft", "posted")),
                name="purchase_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(tax_total__gte=0)
                & Q(total__gte=0),
                name="purchase_totals_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("discount_total") + F("tax_total")),
                name="purchase_total_matches_components",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "status", "purchase_date"),
                name="purch_branch_status_date_idx",
            ),
            models.Index(
                fields=("supplier", "purchase_date"),
                name="purchase_supplier_date_idx",
            ),
        ]

    @property
    def purchase_number(self):
        return f"PUR-{self.pk:06d}" if self.pk else None

    def clean(self):
        super().clean()
        errors = {}
        if self.branch_id and self.organization_id:
            branch_org_id = Branch.objects.filter(pk=self.branch_id).values_list(
                "organization_id", flat=True
            ).first()
            if branch_org_id != self.organization_id:
                errors["branch"] = "Branch must belong to this organization."
        if self.supplier_id and self.organization_id:
            supplier_org_id = Supplier.objects.filter(pk=self.supplier_id).values_list(
                "organization_id", flat=True
            ).first()
            if supplier_org_id != self.organization_id:
                errors["supplier"] = "Supplier must belong to this organization."
        if self.status == self.Status.POSTED and (
            self.posted_by_id is None or self.posted_at is None
        ):
            errors["status"] = "Posted purchases require a posting user and time."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not getattr(self, "_purchase_service_write", False):
            raise ValueError("Write purchases through the purchase service.")
        if self.pk:
            existing_status = (
                type(self).objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if existing_status == self.Status.POSTED:
                raise ValueError("Posted purchases are immutable.")
        elif self.status != self.Status.DRAFT:
            raise ValueError("Create purchases as drafts.")
        if not self.pk:
            self.supplier_name_snapshot = self.supplier.name
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.POSTED:
            raise ValueError("Posted purchases cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.purchase_number or "New purchase"


class PurchaseLineQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Edit purchase lines through the purchase service.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create purchase lines through the purchase service.")

    def delete(self):
        raise ValueError("Remove purchase lines through the purchase service.")

    def delete_for_purchase_service(self):
        if self.filter(purchase__status=Purchase.Status.POSTED).exists():
            raise ValueError("Lines on posted purchases are immutable.")
        return super().delete()


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="purchase_lines",
    )
    product_name_snapshot = models.CharField(max_length=200)
    sku_snapshot = models.CharField(max_length=64)
    unit_symbol_snapshot = models.CharField(max_length=24)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    unit_cost = models.DecimalField(
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
    objects = PurchaseLineQuerySet.as_manager()

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="purchase_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0)
                & Q(subtotal__gte=0)
                & Q(discount_amount__gte=0)
                & Q(tax_amount__gte=0)
                & Q(total__gte=0),
                name="purchase_line_amounts_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(discount_amount__lte=F("subtotal")),
                name="purchase_line_discount_within_subtotal",
            ),
            models.CheckConstraint(
                condition=Q(
                    total=F("subtotal") - F("discount_amount") + F("tax_amount")
                ),
                name="purchase_line_total_matches_components",
            ),
        ]
        indexes = [
            models.Index(
                fields=("purchase", "product"),
                name="purch_line_purch_prod_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.purchase_id and self.product_id:
            purchase_org_id = Purchase.objects.filter(
                pk=self.purchase_id
            ).values_list("organization_id", flat=True).first()
            if (
                purchase_org_id is not None
                and purchase_org_id != self.product.organization_id
            ):
                raise ValidationError(
                    {"product": "Product must belong to the purchase organization."}
                )

    def save(self, *args, **kwargs):
        if not getattr(self, "_purchase_service_write", False):
            raise ValueError("Write purchase lines through the purchase service.")
        if self.pk and Purchase.objects.filter(
            pk=self.purchase_id,
            status=Purchase.Status.POSTED,
        ).exists():
            raise ValueError("Lines on posted purchases are immutable.")
        if not self.pk:
            self.product_name_snapshot = self.product.name
            self.sku_snapshot = self.product.sku
            self.unit_symbol_snapshot = self.product.base_unit.symbol
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Remove purchase lines through the purchase service.")

    def __str__(self):
        return f"{self.quantity} {self.unit_symbol_snapshot} {self.product_name_snapshot}"


class PurchaseReturnQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Edit purchase returns through the return service.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create purchase returns through the return service.")

    def delete(self):
        if self.filter(status=PurchaseReturn.Status.POSTED).exists():
            raise ValueError("Posted purchase returns cannot be deleted.")
        return super().delete()


class PurchaseReturn(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted / returned"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="purchase_returns",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="purchase_returns",
    )
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.PROTECT,
        related_name="returns",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_returns",
    )
    supplier_name_snapshot = models.CharField(max_length=200)
    supplier_credit_note_reference = models.CharField(max_length=100, blank=True)
    return_date = models.DateField(default=timezone.localdate)
    notes = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    credit_total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_purchase_returns",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="posted_purchase_returns",
        null=True,
        blank=True,
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = PurchaseReturnQuerySet.as_manager()

    class Meta:
        ordering = ("-return_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=("draft", "posted")),
                name="purchase_return_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(credit_total__gte=0),
                name="purchase_return_credit_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "status", "return_date"),
                name="purch_return_branch_date_idx",
            ),
            models.Index(
                fields=("purchase", "return_date"),
                name="purch_return_purchase_date_idx",
            ),
        ]

    @property
    def return_number(self):
        return f"PRET-{self.pk:06d}" if self.pk else None

    def clean(self):
        super().clean()
        errors = {}
        if self.purchase_id:
            purchase = Purchase.objects.filter(pk=self.purchase_id).values(
                "organization_id",
                "branch_id",
                "supplier_id",
                "status",
            ).first()
            if purchase:
                for field, purchase_field in (
                    ("organization", "organization_id"),
                    ("branch", "branch_id"),
                    ("supplier", "supplier_id"),
                ):
                    if getattr(self, f"{field}_id") != purchase[purchase_field]:
                        errors[field] = (
                            "Return must match the original purchase's "
                            "organization, branch, and supplier."
                        )
                if purchase["status"] != Purchase.Status.POSTED:
                    errors["purchase"] = "Only posted purchases can be returned."
        if self.status == self.Status.POSTED and (
            self.posted_by_id is None or self.posted_at is None
        ):
            errors["status"] = "Posted returns require a posting user and time."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not getattr(self, "_purchase_return_service_write", False):
            raise ValueError("Write purchase returns through the return service.")
        if self.pk:
            existing_status = type(self).objects.filter(pk=self.pk).values_list(
                "status", flat=True
            ).first()
            if existing_status == self.Status.POSTED:
                raise ValueError("Posted purchase returns are immutable.")
        elif self.status != self.Status.DRAFT:
            raise ValueError("Create purchase returns as drafts.")
        if not self.pk:
            self.supplier_name_snapshot = self.supplier.name
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == self.Status.POSTED:
            raise ValueError("Posted purchase returns cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.return_number or "New purchase return"


class PurchaseReturnLineQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Edit return lines through the return service.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create return lines through the return service.")

    def delete(self):
        raise ValueError("Remove return lines through the return service.")

    def delete_for_return_service(self):
        if self.filter(purchase_return__status=PurchaseReturn.Status.POSTED).exists():
            raise ValueError("Lines on posted returns are immutable.")
        return super().delete()


class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(
        PurchaseReturn,
        on_delete=models.CASCADE,
        related_name="items",
    )
    purchase_line = models.ForeignKey(
        PurchaseLine,
        on_delete=models.PROTECT,
        related_name="return_lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="purchase_return_lines",
    )
    product_name_snapshot = models.CharField(max_length=200)
    sku_snapshot = models.CharField(max_length=64)
    unit_symbol_snapshot = models.CharField(max_length=24)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    credit_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = PurchaseReturnLineQuerySet.as_manager()

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_return", "purchase_line"),
                name="unique_purchase_line_per_return",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0) & Q(credit_amount__gt=0),
                name="purchase_return_line_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("purchase_line", "created_at"),
                name="purch_return_line_source_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.purchase_return_id and self.purchase_line_id:
            return_purchase_id = PurchaseReturn.objects.filter(
                pk=self.purchase_return_id
            ).values_list("purchase_id", flat=True).first()
            source_purchase_id = PurchaseLine.objects.filter(
                pk=self.purchase_line_id
            ).values_list("purchase_id", flat=True).first()
            if (
                return_purchase_id is not None
                and source_purchase_id is not None
                and return_purchase_id != source_purchase_id
            ):
                raise ValidationError(
                    {"purchase_line": "Choose a line from the original purchase."}
                )

    def save(self, *args, **kwargs):
        if not getattr(self, "_purchase_return_service_write", False):
            raise ValueError("Write return lines through the return service.")
        if self.pk and PurchaseReturn.objects.filter(
            pk=self.purchase_return_id,
            status=PurchaseReturn.Status.POSTED,
        ).exists():
            raise ValueError("Lines on posted returns are immutable.")
        if not self.pk:
            self.product = self.purchase_line.product
            self.product_name_snapshot = self.purchase_line.product_name_snapshot
            self.sku_snapshot = self.purchase_line.sku_snapshot
            self.unit_symbol_snapshot = self.purchase_line.unit_symbol_snapshot
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Remove return lines through the return service.")


class SupplierPaymentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Supplier payments are immutable.")

    def delete(self):
        raise ValueError("Supplier payments are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create supplier payments through the payment service.")


class SupplierPayment(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="supplier_payments",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="supplier_payments",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    supplier_name_snapshot = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=40, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supplier_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SupplierPaymentQuerySet.as_manager()

    class Meta:
        ordering = ("-payment_date", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="supplier_payment_amount_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "supplier", "payment_date"),
                name="sup_payment_branch_date_idx",
            ),
        ]

    @property
    def payment_number(self):
        return f"SPAY-{self.pk:06d}" if self.pk else None

    @property
    def allocated_amount(self):
        return sum(
            (allocation.amount for allocation in self.allocations.all()),
            Decimal("0.00"),
        )

    @property
    def unallocated_amount(self):
        return self.amount - self.allocated_amount

    def clean(self):
        super().clean()
        errors = {}
        if self.branch_id and self.organization_id:
            branch_organization_id = Branch.objects.filter(pk=self.branch_id).values_list(
                "organization_id", flat=True
            ).first()
            if branch_organization_id != self.organization_id:
                errors["branch"] = "Branch must belong to this organization."
        if self.supplier_id and self.organization_id:
            supplier_organization_id = Supplier.objects.filter(
                pk=self.supplier_id
            ).values_list("organization_id", flat=True).first()
            if supplier_organization_id != self.organization_id:
                errors["supplier"] = "Supplier must belong to this organization."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not getattr(self, "_creating_supplier_payment", False):
            raise ValueError("Create supplier payments through the payment service.")
        if self.pk:
            raise ValueError("Supplier payments are immutable.")
        if not self.pk:
            self.supplier_name_snapshot = self.supplier.name
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Supplier payments are immutable.")

    def __str__(self):
        return self.payment_number or "New supplier payment"


class SupplierPaymentAllocationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Supplier payment allocations are immutable.")

    def delete(self):
        raise ValueError("Supplier payment allocations are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Create payment allocations through the payment service.")


class SupplierPaymentAllocation(models.Model):
    payment = models.ForeignKey(
        SupplierPayment,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )
    purchase_number_snapshot = models.CharField(max_length=32)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SupplierPaymentAllocationQuerySet.as_manager()

    class Meta:
        ordering = ("purchase_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("payment", "purchase"),
                name="unique_purchase_per_supplier_payment",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="supplier_payment_allocation_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=("purchase", "created_at"),
                name="sup_pay_alloc_purch_date_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not getattr(self, "_creating_payment_allocation", False):
            raise ValueError("Create payment allocations through the payment service.")
        if self.pk:
            raise ValueError("Supplier payment allocations are immutable.")
        self.purchase_number_snapshot = self.purchase.purchase_number
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        errors = {}
        if self.payment_id and self.purchase_id:
            payment = SupplierPayment.objects.filter(pk=self.payment_id).values(
                "organization_id",
                "branch_id",
                "supplier_id",
            ).first()
            purchase = Purchase.objects.filter(pk=self.purchase_id).values(
                "organization_id",
                "branch_id",
                "supplier_id",
                "status",
            ).first()
            if payment and purchase:
                for field in ("organization_id", "branch_id", "supplier_id"):
                    if payment[field] != purchase[field]:
                        errors["purchase"] = (
                            "Purchase and payment must have the same organization, "
                            "branch, and supplier."
                        )
                        break
                if purchase["status"] != Purchase.Status.POSTED:
                    errors["purchase"] = "Payments can only be allocated to posted purchases."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        raise ValueError("Supplier payment allocations are immutable.")

    def __str__(self):
        return f"{self.purchase_number_snapshot}: {self.amount}"
