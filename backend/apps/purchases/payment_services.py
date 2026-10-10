from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.organizations.models import Branch
from apps.suppliers.models import Supplier, SupplierLedgerEntry
from apps.suppliers.services import post_supplier_ledger_entry

from .models import (
    Purchase,
    PurchaseReturnLine,
    SupplierPayment,
    SupplierPaymentAllocation,
)


@transaction.atomic
def record_supplier_payment(
    *,
    branch: Branch,
    supplier: Supplier,
    amount: Decimal,
    created_by,
    allocations: list[dict] | None = None,
    payment_date=None,
    payment_method: str = "",
    reference: str = "",
    notes: str = "",
) -> SupplierPayment:
    if not branch.is_active or not branch.organization.is_active:
        raise ValidationError({"branch": "Payments require an active branch."})
    if not supplier.is_active or not supplier.organization.is_active:
        raise ValidationError({"supplier": "Choose an active supplier."})
    if branch.organization_id != supplier.organization_id:
        raise ValidationError(
            {"supplier": "Supplier must belong to this branch's organization."}
        )

    amount = SupplierPayment._meta.get_field("amount").clean(amount, None)
    allocations = allocations or []
    invoice_ids = [allocation["purchase"].pk for allocation in allocations]
    if len(invoice_ids) != len(set(invoice_ids)):
        raise ValidationError(
            {"allocations": "Each purchase invoice may be allocated only once."}
        )

    locked_purchases = list(
        Purchase.objects.select_for_update()
        .filter(
            pk__in=invoice_ids,
            organization_id=supplier.organization_id,
            branch=branch,
            supplier=supplier,
            status=Purchase.Status.POSTED,
        )
        .order_by("pk")
    )
    if set(invoice_ids) != {purchase.pk for purchase in locked_purchases}:
        raise ValidationError(
            {
                "allocations": (
                    "Allocations must reference posted invoices for this supplier "
                    "and branch."
                )
            }
        )

    supplier = Supplier.objects.select_for_update().select_related(
        "organization"
    ).get(pk=supplier.pk)
    if not supplier.is_active or not supplier.organization.is_active:
        raise ValidationError({"supplier": "Choose an active supplier."})

    already_paid = {
        row["purchase_id"]: row["allocated"]
        for row in SupplierPaymentAllocation.objects.filter(
            purchase_id__in=invoice_ids
        )
        .values("purchase_id")
        .annotate(allocated=Sum("amount"))
    }
    returned_credits = {
        row["purchase_line__purchase_id"]: row["credited"]
        for row in PurchaseReturnLine.objects.filter(
            purchase_line__purchase_id__in=invoice_ids,
            purchase_return__status="posted",
        )
        .values("purchase_line__purchase_id")
        .annotate(credited=Sum("credit_amount"))
    }
    allocations_by_id = {purchase.pk: purchase for purchase in locked_purchases}
    allocated_total = Decimal("0.00")
    for allocation in allocations:
        purchase = allocations_by_id[allocation["purchase"].pk]
        allocation_amount = SupplierPaymentAllocation._meta.get_field(
            "amount"
        ).clean(allocation["amount"], None)
        paid = already_paid.get(purchase.pk, Decimal("0.00"))
        net_invoice_total = max(
            Decimal("0.00"),
            purchase.total - returned_credits.get(purchase.pk, Decimal("0.00")),
        )
        outstanding = max(Decimal("0.00"), net_invoice_total - paid)
        if allocation_amount > outstanding:
            raise ValidationError(
                {
                    "allocations": (
                        f"Allocation exceeds the outstanding balance of "
                        f"{purchase.purchase_number} ({outstanding})."
                    )
                }
            )
        allocated_total += allocation_amount

    if allocated_total > amount:
        raise ValidationError(
            {"allocations": "Allocated amounts cannot exceed the payment amount."}
        )

    payment = SupplierPayment(
        organization=branch.organization,
        branch=branch,
        supplier=supplier,
        supplier_name_snapshot=supplier.name,
        amount=amount,
        payment_date=payment_date or timezone.localdate(),
        payment_method=payment_method.strip(),
        reference=reference.strip(),
        notes=notes.strip(),
        created_by=created_by,
    )
    payment.full_clean()
    payment._creating_supplier_payment = True
    payment.save(force_insert=True)

    for allocation in allocations:
        purchase = allocations_by_id[allocation["purchase"].pk]
        payment_allocation = SupplierPaymentAllocation(
            payment=payment,
            purchase=purchase,
            purchase_number_snapshot=purchase.purchase_number,
            amount=allocation["amount"],
        )
        payment_allocation.full_clean()
        payment_allocation._creating_payment_allocation = True
        payment_allocation.save(force_insert=True)

    post_supplier_ledger_entry(
        supplier=supplier,
        branch=branch,
        entry_type=SupplierLedgerEntry.EntryType.PAYMENT,
        amount=amount,
        reason=f"Supplier payment {payment.payment_number}",
        reference=reference.strip() or payment.payment_number,
        created_by=created_by,
    )
    return payment


def branch_supplier_invoice_balances(
    *, branch: Branch, supplier: Supplier | None = None
) -> list[dict]:
    purchases = Purchase.objects.filter(
        branch=branch,
        status=Purchase.Status.POSTED,
    ).select_related("supplier")
    if supplier is not None:
        purchases = purchases.filter(supplier=supplier)
    allocated_totals: dict[int, Decimal] = {}
    for row in (
        SupplierPaymentAllocation.objects.filter(purchase__in=purchases)
        .values("purchase_id")
        .annotate(total=Sum("amount"))
    ):
        allocated_totals[row["purchase_id"]] = row["total"]
    returned_totals: dict[int, Decimal] = {}
    for row in (
        PurchaseReturnLine.objects.filter(
            purchase_line__purchase__in=purchases,
            purchase_return__status="posted",
        )
        .values("purchase_line__purchase_id")
        .annotate(total=Sum("credit_amount"))
    ):
        returned_totals[row["purchase_line__purchase_id"]] = row["total"]

    return [
        {
            "purchase": purchase,
            "paid_amount": allocated_totals.get(purchase.pk, Decimal("0.00")),
            "returned_amount": returned_totals.get(
                purchase.pk,
                Decimal("0.00"),
            ),
            "net_total": max(
                Decimal("0.00"),
                purchase.total
                - returned_totals.get(purchase.pk, Decimal("0.00")),
            ),
            "outstanding_amount": max(
                Decimal("0.00"),
                purchase.total
                - returned_totals.get(purchase.pk, Decimal("0.00"))
                - allocated_totals.get(purchase.pk, Decimal("0.00")),
            ),
        }
        for purchase in purchases.order_by("purchase_date", "pk")
    ]
