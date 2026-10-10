from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.organizations.models import Branch, Organization


class Customer(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="customers",
    )
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        indexes = [
            models.Index(
                fields=("organization", "is_active", "name"),
                name="customer_org_active_name_idx",
            ),
        ]

    def __str__(self):
        return self.name


class ImmutableCustomerLedgerQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Customer ledger entries are immutable.")

    def delete(self):
        raise ValueError("Customer ledger entries are immutable.")

    def bulk_create(self, *args, **kwargs):
        raise ValueError("Post customer ledger entries through the ledger service.")


class CustomerLedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        SALE = "sale", "Sale"
        PAYMENT = "payment", "Payment"
        RETURN = "return", "Customer return"
        OPENING_DEBIT = "opening_debit", "Opening balance debit"
        OPENING_CREDIT = "opening_credit", "Opening balance credit"
        ADJUSTMENT_DEBIT = "adjustment_debit", "Debit adjustment"
        ADJUSTMENT_CREDIT = "adjustment_credit", "Credit adjustment"

    DEBIT_TYPES = (
        EntryType.SALE,
        EntryType.OPENING_DEBIT,
        EntryType.ADJUSTMENT_DEBIT,
    )
    CREDIT_TYPES = (
        EntryType.PAYMENT,
        EntryType.RETURN,
        EntryType.OPENING_CREDIT,
        EntryType.ADJUSTMENT_CREDIT,
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="customer_ledger_entries",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="customer_ledger_entries",
    )
    entry_type = models.CharField(max_length=24, choices=EntryType.choices)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)
    customer_name_snapshot = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_ledger_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableCustomerLedgerQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="customer_ledger_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    entry_type__in=(
                        "sale",
                        "payment",
                        "return",
                        "opening_debit",
                        "opening_credit",
                        "adjustment_debit",
                        "adjustment_credit",
                    )
                ),
                name="customer_ledger_entry_type_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("branch", "customer", "created_at"),
                name="cust_ledger_branch_time_idx",
            ),
            models.Index(
                fields=("organization", "customer", "created_at"),
                name="cust_ledger_org_time_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.customer_id and self.organization_id:
            customer_organization_id = (
                Customer.objects.filter(pk=self.customer_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if customer_organization_id != self.organization_id:
                errors["customer"] = "Customer must belong to this organization."
        if self.branch_id and self.organization_id:
            branch_organization_id = (
                Branch.objects.filter(pk=self.branch_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if branch_organization_id != self.organization_id:
                errors["branch"] = "Branch must belong to this organization."
        if self.entry_type not in self.EntryType.values:
            errors["entry_type"] = "Select a valid ledger entry type."
        if not self.reason or not self.reason.strip():
            errors["reason"] = "A reason is required for every ledger entry."
        if errors:
            raise ValidationError(errors)

    @property
    def signed_amount(self):
        if self.entry_type in self.DEBIT_TYPES:
            return self.amount
        return -self.amount

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValueError("Customer ledger entries are immutable.")
        if not getattr(self, "_posting_customer_ledger", False):
            raise ValueError("Post entries through the customer ledger service.")
        if not self.pk:
            self.customer_name_snapshot = self.customer.name
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Customer ledger entries are immutable.")

    def __str__(self):
        return f"{self.get_entry_type_display()}: {self.amount} ({self.customer})"
