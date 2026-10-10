from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When

from apps.organizations.models import Branch

from .models import Supplier, SupplierLedgerEntry


@transaction.atomic
def post_supplier_ledger_entry(
    *,
    supplier: Supplier,
    branch: Branch,
    entry_type: str,
    amount: Decimal,
    reason: str,
    created_by,
    reference: str = "",
) -> SupplierLedgerEntry:
    supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
    if not supplier.is_active:
        raise ValidationError({"supplier": "Cannot post to an inactive supplier."})
    if not supplier.organization.is_active:
        raise ValidationError(
            {"supplier": "Cannot post to an inactive organization."}
        )
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Cannot post to an inactive branch."})
    if branch.organization_id != supplier.organization_id:
        raise ValidationError(
            {"branch": "Supplier and branch must belong to the same organization."}
        )
    if entry_type not in SupplierLedgerEntry.EntryType.values:
        raise ValidationError({"entry_type": "Select a valid ledger entry type."})
    amount = SupplierLedgerEntry._meta.get_field("amount").clean(amount, None)
    if not reason or not reason.strip():
        raise ValidationError({"reason": "A reason is required."})

    entry = SupplierLedgerEntry(
        organization=supplier.organization,
        supplier=supplier,
        branch=branch,
        entry_type=entry_type,
        amount=amount,
        reason=reason.strip(),
        reference=reference.strip(),
        supplier_name_snapshot=supplier.name,
        created_by=created_by,
    )
    entry.full_clean()
    entry._posting_supplier_ledger = True
    entry.save(force_insert=True)
    return entry


def supplier_branch_balance(*, supplier: Supplier, branch: Branch) -> Decimal:
    signed_amount = Case(
        When(
            entry_type__in=SupplierLedgerEntry.INCREASES_PAYABLE_TYPES,
            then=F("amount"),
        ),
        default=-F("amount"),
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )
    return (
        SupplierLedgerEntry.objects.filter(
            organization_id=supplier.organization_id,
            supplier=supplier,
            branch=branch,
        ).aggregate(total=Sum(signed_amount))["total"]
        or Decimal("0.00")
    )
