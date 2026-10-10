from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Branch

from .models import Sale
from .permissions import CanManageBranchSales
from .serializers import (
    SaleCheckoutInputSerializer,
    SaleDraftInputSerializer,
    SaleDraftPatchInputSerializer,
    SaleSerializer,
    SalesReturnInputSerializer,
    SalesReturnSerializer,
)
from .services import (
    InsufficientStockError,
    complete_sale,
    create_draft_sale,
    update_draft_sale,
)
from .return_services import create_sales_return


class BranchSalesOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branches = Branch.objects.filter(
            is_active=True,
            organization__is_active=True,
        )
        if not request.user.is_superuser:
            branches = branches.filter(
                memberships__user=request.user,
                memberships__role__name__in=CanManageBranchSales.allowed_roles,
            )
        branches = branches.select_related("organization").distinct().order_by(
            "organization__name",
            "name",
            "pk",
        )
        return Response(
            [
                {
                    "id": branch.pk,
                    "name": branch.name,
                    "organization": branch.organization.name,
                }
                for branch in branches
            ]
        )


def _as_api_validation_error(error: DjangoValidationError) -> ValidationError:
    detail = error.message_dict if hasattr(error, "message_dict") else error.messages
    return ValidationError(detail)


class BranchSaleListView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSales]

    def get(self, request, branch_id):
        sales = (
            Sale.objects.filter(branch=self.sales_branch)
            .select_related(
                "customer",
                "created_by",
                "completed_by",
                "branch__organization",
            )
            .prefetch_related("items")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in Sale.Status.values:
                raise ValidationError({"status": "Select draft or completed."})
            sales = sales.filter(status=status_filter)
        search = request.query_params.get("search", "").strip()
        if search:
            sales = sales.filter(
                Q(customer_name_snapshot__icontains=search)
                | Q(items__product_name_snapshot__icontains=search)
                | Q(items__sku_snapshot__icontains=search)
            ).distinct()
        return Response(SaleSerializer(sales, many=True).data)

    def post(self, request, branch_id):
        serializer = SaleDraftInputSerializer(
            data=request.data,
            context={"branch": self.sales_branch},
        )
        serializer.is_valid(raise_exception=True)
        try:
            sale = create_draft_sale(
                branch=self.sales_branch,
                created_by=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class BranchSaleDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSales]

    def get_sale(self, sale_id):
        return get_object_or_404(
            Sale.objects.select_related(
                "customer",
                "created_by",
                "completed_by",
                "branch__organization",
            ).prefetch_related("items"),
            pk=sale_id,
            branch=self.sales_branch,
        )

    def get(self, request, branch_id, sale_id):
        return Response(SaleSerializer(self.get_sale(sale_id)).data)

    def patch(self, request, branch_id, sale_id):
        sale = self.get_sale(sale_id)
        serializer = SaleDraftPatchInputSerializer(
            data=request.data,
            context={"branch": self.sales_branch},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        update_customer = "customer" in data
        try:
            sale = update_draft_sale(
                sale=sale,
                customer=data.get("customer"),
                update_customer=update_customer,
                items=data.get("items"),
                sale_date=data.get("sale_date"),
                notes=data.get("notes"),
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        sale = self.get_sale(sale.pk)
        return Response(SaleSerializer(sale).data)


class BranchSaleCheckoutView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSales]

    def post(self, request, branch_id, sale_id):
        sale = get_object_or_404(
            Sale,
            pk=sale_id,
            branch=self.sales_branch,
        )
        serializer = SaleCheckoutInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sale = complete_sale(
                sale=sale,
                completed_by=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": "Insufficient stock to complete this sale.",
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_409_CONFLICT,
            )
        sale = (
            Sale.objects.select_related(
                "customer",
                "created_by",
                "completed_by",
                "branch__organization",
            )
            .prefetch_related("items")
            .get(pk=sale.pk)
        )
        return Response(SaleSerializer(sale).data)


class BranchSaleReturnsView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSales]

    def get_sale(self, sale_id):
        return get_object_or_404(
            Sale,
            pk=sale_id,
            branch=self.sales_branch,
            status=Sale.Status.COMPLETED,
        )

    def get(self, request, branch_id, sale_id):
        sale = self.get_sale(sale_id)
        returns = (
            sale.returns.select_related("sale", "created_by")
            .prefetch_related("items")
            .order_by("-return_date", "-pk")
        )
        return Response(SalesReturnSerializer(returns, many=True).data)

    def post(self, request, branch_id, sale_id):
        sale = self.get_sale(sale_id)
        serializer = SalesReturnInputSerializer(
            data=request.data,
            context={"branch": self.sales_branch, "sale_id": sale.pk},
        )
        serializer.is_valid(raise_exception=True)
        try:
            sales_return = create_sales_return(
                branch=self.sales_branch,
                sale=sale,
                created_by=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        sales_return = (
            type(sales_return).objects.select_related("sale", "created_by")
            .prefetch_related("items")
            .get(pk=sales_return.pk)
        )
        return Response(
            SalesReturnSerializer(sales_return).data,
            status=status.HTTP_201_CREATED,
        )
