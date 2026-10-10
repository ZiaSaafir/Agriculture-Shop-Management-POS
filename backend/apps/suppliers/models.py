from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.organizations.models import Branch, Organization


class Supplier(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="suppliers",
    )
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=500, blank=True)
    account_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        indexes = [
            models.Index(
                fields=("organization", "is_active", "name"),
                name="supplier_org_active_name_idx",
            ),
        ]

    def __str__(self):
        return self.name


class ImmutableSupplierLedgerQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Supplier ledger entries are immutable.")

    def delete(self):
        raise ValueError("Supplier ledger entries are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Post supplier ledger entries through the ledger service.")


class SupplierLedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        PAYMENT = "payment", "Payment"
        RETURN = "return", "Supplier return"
        OPENING_PAYABLE = "opening_payable", "Opening payable"
        OPENING_ADVANCE = "opening_advance", "Opening advance"
        ADJUSTMENT_PAYABLE = "adjustment_payable", "Payable adjustment"
        ADJUSTMENT_ADVANCE = "adjustment_advance", "Advance adjustment"

    INCREASES_PAYABLE_TYPES = (
        EntryType.PURCHASE,
        EntryType.OPENING_PAYABLE,
        EntryType.ADJUSTMENT_PAYABLE,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="supplier_ledger_entries",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="supplier_ledger_entries",
    )
    entry_type = models.CharField(max_length=24, choices=EntryType.choices)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)
    supplier_name_snapshot = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supplier_ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableSupplierLedgerQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="supplier_ledger_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    entry_type__in=(
                        "purchase",
                        "payment",
                        "return",
                        "opening_payable",
                        "opening_advance",
                        "adjustment_payable",
                        "adjustment_advance",
                    )
                ),
                name="supplier_ledger_entry_type_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "supplier", "created_at"),
                name="sup_ledger_branch_time_idx",
            ),
            models.Index(
                fields=("organization", "supplier", "created_at"),
                name="sup_ledger_org_time_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.supplier_id and self.organization_id:
            supplier_organization_id = (
                Supplier.objects.filter(pk=self.supplier_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if supplier_organization_id != self.organization_id:
                errors["supplier"] = "Supplier must belong to this organization."
        if self.branch_id and self.organization_id:
            branch_organization_id = (
                Branch.objects.filter(pk=self.branch_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if branch_organization_id != self.organization_id:
                errors["branch"] = "Branch must belong to this organization."
        if self.entry_type not in self.EntryType.values:
            errors["entry_type"] = "Select a valid supplier ledger entry type."
        if not self.reason or not self.reason.strip():
            errors["reason"] = "A reason is required for every ledger entry."
        if errors:
            raise ValidationError(errors)

    @property
    def signed_amount(self):
        if self.entry_type in self.INCREASES_PAYABLE_TYPES:
            return self.amount
        return -self.amount

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("Supplier ledger entries are immutable.")
        if not getattr(self, "_posting_supplier_ledger", False):
            raise ValueError("Post entries through the supplier ledger service.")
        if not self.pk:
            self.supplier_name_snapshot = self.supplier.name
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Supplier ledger entries are immutable.")

    def __str__(self):
        return f"{self.get_entry_type_display()}: {self.amount} ({self.supplier})"
