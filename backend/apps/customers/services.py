from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, When

from apps.organizations.models import Branch

from .models import Customer, CustomerLedgerEntry


@transaction.atomic
def post_customer_ledger_entry(
    *,
    customer: Customer,
    branch: Branch,
    entry_type: str,
    amount: Decimal,
    reason: str,
    created_by,
    reference: str = "",
) -> CustomerLedgerEntry:
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if not customer.is_active:
        raise ValidationError({"customer": "Cannot post to an inactive customer."})
    if not customer.organization.is_active:
        raise ValidationError(
            {"customer": "Cannot post to an inactive organization."}
        )
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Cannot post to an inactive branch."})
    if branch.organization_id != customer.organization_id:
        raise ValidationError(
            {"branch": "Customer and branch must belong to the same organization."}
        )
    if entry_type not in CustomerLedgerEntry.EntryType.values:
        raise ValidationError({"entry_type": "Select a valid ledger entry type."})
    amount = CustomerLedgerEntry._meta.get_field("amount").clean(amount, None)
    if not reason or not reason.strip():
        raise ValidationError({"reason": "A reason is required."})

    entry = CustomerLedgerEntry(
        organization=customer.organization,
        customer=customer,
        branch=branch,
        entry_type=entry_type,
        amount=amount,
        reason=reason.strip(),
        reference=reference.strip(),
        customer_name_snapshot=customer.name,
        created_by=created_by,
    )
    entry.full_clean()
    entry._posting_customer_ledger = True
    entry.save(force_insert=True)
    return entry


def customer_branch_balance(*, customer: Customer, branch: Branch) -> Decimal:
    signed_amount = Case(
        When(
            entry_type__in=CustomerLedgerEntry.DEBIT_TYPES,
            then=F("amount"),
        ),
        default=-F("amount"),
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )
    return (
        CustomerLedgerEntry.objects.filter(
            organization_id=customer.organization_id,
            customer=customer,
            branch=branch,
        ).aggregate(total=Sum(signed_amount))["total"]
        or Decimal("0.00")
    )
