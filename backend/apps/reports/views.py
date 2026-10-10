from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Role
from apps.customers.models import CustomerLedgerEntry
from apps.inventory.models import StockBalance, StockMovement
from apps.organizations.models import Branch
from apps.products.models import Product
from apps.purchases.models import Purchase, PurchaseReturn
from apps.sales.models import Sale, SaleLine, SalesReturn
from apps.suppliers.models import SupplierLedgerEntry

REPORT_ROLES = (Role.ADMIN, Role.MANAGER, Role.CASHIER, Role.INVENTORY_STAFF)
MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)
QUANTITY_FIELD = DecimalField(max_digits=18, decimal_places=6)


class CanViewBranchReports(BasePermission):
    message = "You do not have reporting access to this branch."

    def has_permission(self, request, view):
        from django.shortcuts import get_object_or_404

        branch = get_object_or_404(
            Branch.objects.select_related("organization"),
            pk=view.kwargs["branch_id"],
            is_active=True,
            organization__is_active=True,
        )
        view.report_branch = branch
        return request.user.is_superuser or request.user.branch_memberships.filter(
            branch=branch,
            role__name__in=REPORT_ROLES,
        ).exists()


class BranchOperationalReportView(APIView):
    permission_classes = [IsAuthenticated, CanViewBranchReports]

    def get(self, request, branch_id):
        start_date = self._date_param(request, "start_date")
        end_date = self._date_param(request, "end_date")
        if start_date > end_date:
            raise ValidationError({"date_range": "Start date must not follow end date."})
        if end_date - start_date > timedelta(days=365):
            raise ValidationError({"date_range": "Choose a range of at most 366 days."})

        branch = self.report_branch
        completed_sales = Sale.objects.filter(
            branch=branch,
            status=Sale.Status.COMPLETED,
            sale_date__range=(start_date, end_date),
        )
        sales_returns = SalesReturn.objects.filter(
            branch=branch,
            return_date__range=(start_date, end_date),
        )
        posted_purchases = Purchase.objects.filter(
            branch=branch,
            status=Purchase.Status.POSTED,
            purchase_date__range=(start_date, end_date),
        )
        purchase_returns = PurchaseReturn.objects.filter(
            branch=branch,
            status=PurchaseReturn.Status.POSTED,
            return_date__range=(start_date, end_date),
        )

        sales = completed_sales.aggregate(
            count=Count("id"),
            gross=Coalesce(Sum("total"), Decimal("0.00"), output_field=MONEY_FIELD),
            amount_received=Coalesce(
                Sum("amount_paid"),
                Decimal("0.00"),
                output_field=MONEY_FIELD,
            ),
            discounts=Coalesce(
                Sum("discount_total"),
                Decimal("0.00"),
                output_field=MONEY_FIELD,
            ),
        )
        sales_by_payment_method = list(
            completed_sales.values("payment_method")
            .annotate(
                count=Count("id"),
                gross=Sum("total"),
                received=Sum("amount_paid"),
            )
            .order_by("payment_method")
        )
        returned_total = sales_returns.aggregate(
            total=Coalesce(Sum("total"), Decimal("0.00"), output_field=MONEY_FIELD)
        )["total"]
        returns_by_disposition = list(
            sales_returns.values("disposition")
            .annotate(
                count=Count("id"),
                total=Sum("total"),
            )
            .order_by("disposition")
        )
        purchases = posted_purchases.aggregate(
            count=Count("id"),
            gross=Coalesce(Sum("total"), Decimal("0.00"), output_field=MONEY_FIELD),
        )
        purchases_by_supplier = list(
            posted_purchases.values("supplier_name_snapshot")
            .annotate(
                count=Count("id"),
                gross=Sum("total"),
            )
            .order_by("-gross", "supplier_name_snapshot")
        )
        purchase_return_total = purchase_returns.aggregate(
            total=Coalesce(Sum("credit_total"), Decimal("0.00"), output_field=MONEY_FIELD)
        )["total"]

        daily = {}
        sale_days = (
            completed_sales.values("sale_date")
            .annotate(total=Sum("total"))
            .order_by("sale_date")
        )
        return_days = (
            sales_returns.values("return_date")
            .annotate(total=Sum("total"))
            .order_by("return_date")
        )
        for row in sale_days:
            daily[row["sale_date"]] = {
                "date": row["sale_date"],
                "sales": row["total"],
                "returns": Decimal("0.00"),
            }
        for row in return_days:
            day = row["return_date"]
            daily.setdefault(
                day,
                {"date": day, "sales": Decimal("0.00"), "returns": Decimal("0.00")},
            )["returns"] = row["total"]
        daily_rows = []
        for day_offset in range((end_date - start_date).days + 1):
            day = start_date + timedelta(days=day_offset)
            row = daily.get(
                day,
                {
                    "date": day,
                    "sales": Decimal("0.00"),
                    "returns": Decimal("0.00"),
                },
            )
            daily_rows.append({**row, "net_sales": row["sales"] - row["returns"]})
        sold_products = list(
            SaleLine.objects.filter(
                sale__branch=branch,
                sale__status=Sale.Status.COMPLETED,
                sale__sale_date__range=(start_date, end_date),
            )
            .values("product_name_snapshot", "unit_symbol_snapshot")
            .annotate(
                sold_quantity=Sum("quantity"),
                sales_total=Sum("total"),
            )
            .order_by("-sales_total", "product_name_snapshot")[:10]
        )

        balance = StockBalance.objects.filter(
            branch=branch,
            product=OuterRef("pk"),
        ).values("on_hand")[:1]
        stock_products = Product.objects.filter(
            organization_id=branch.organization_id,
            is_active=True,
        ).annotate(
            on_hand=Coalesce(
                Subquery(balance, output_field=QUANTITY_FIELD),
                Value(Decimal("0"), output_field=QUANTITY_FIELD),
                output_field=QUANTITY_FIELD,
            )
        )
        low_stock_count = stock_products.filter(
            on_hand__lte=F("low_stock_threshold")
        ).count()
        movement_counts = list(
            StockMovement.objects.filter(
                branch=branch,
                created_at__date__range=(start_date, end_date),
            )
            .values("movement_type")
            .annotate(count=Count("id"))
            .order_by("movement_type")
        )
        receivable_signed = Case(
            When(
                entry_type__in=CustomerLedgerEntry.DEBIT_TYPES,
                then=F("amount"),
            ),
            default=-F("amount"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        customer_balances = (
            CustomerLedgerEntry.objects.filter(branch=branch)
            .values("customer_id")
            .annotate(balance=Sum(receivable_signed))
        )
        receivables = sum(
            (balance["balance"] or Decimal("0.00"))
            for balance in customer_balances
            if (balance["balance"] or Decimal("0.00")) > 0
        )
        payable_signed = Case(
            When(
                entry_type__in=SupplierLedgerEntry.INCREASES_PAYABLE_TYPES,
                then=F("amount"),
            ),
            default=-F("amount"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        supplier_balances = (
            SupplierLedgerEntry.objects.filter(branch=branch)
            .values("supplier_id")
            .annotate(balance=Sum(payable_signed))
        )
        supplier_payables = sum(
            (balance["balance"] or Decimal("0.00"))
            for balance in supplier_balances
            if (balance["balance"] or Decimal("0.00")) > 0
        )

        return Response(
            {
                "branch": {"id": branch.pk, "name": branch.name},
                "range": {"start_date": start_date, "end_date": end_date},
                "sales": {
                    "count": sales["count"],
                    "gross": sales["gross"],
                    "amount_received": sales["amount_received"],
                    "returns": returned_total,
                    "net": sales["gross"] - returned_total,
                    "discounts": sales["discounts"],
                    "returns_by_disposition": returns_by_disposition,
                    "by_payment_method": sales_by_payment_method,
                },
                "purchases": {
                    "count": purchases["count"],
                    "gross": purchases["gross"],
                    "returns": purchase_return_total,
                    "net": purchases["gross"] - purchase_return_total,
                    "by_supplier": purchases_by_supplier,
                },
                "receivables": receivables,
                "supplier_payables": supplier_payables,
                "inventory": {
                    "low_stock_count": low_stock_count,
                    "movement_counts": movement_counts,
                },
                "daily_sales": daily_rows,
                "top_products": sold_products,
            }
        )

    @staticmethod
    def _date_param(request, name):
        raw = request.query_params.get(name)
        if raw is None:
            raise ValidationError({name: "Provide a date in YYYY-MM-DD format."})
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(
                {name: "Provide a valid date in YYYY-MM-DD format."}
            ) from exc
