from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.suppliers.models import Supplier
from apps.suppliers.services import supplier_branch_balance

from .models import Purchase, PurchaseReturn, SupplierPayment
from .payment_services import (
    branch_supplier_invoice_balances,
    record_supplier_payment,
)
from .permissions import CanManageBranchPurchases
from .serializers import (
    PurchaseDraftInputSerializer,
    PurchaseDraftPatchInputSerializer,
    PurchaseReturnInputSerializer,
    PurchaseReturnPatchInputSerializer,
    PurchaseReturnSerializer,
    PurchaseSerializer,
    SupplierInvoiceBalanceSerializer,
    SupplierPaymentInputSerializer,
    SupplierPaymentSerializer,
)
from .services import create_draft_purchase, post_purchase, update_draft_purchase
from .return_services import (
    InsufficientStockError,
    create_draft_purchase_return,
    post_purchase_return,
    update_draft_purchase_return,
)


def _as_api_validation_error(error: DjangoValidationError) -> ValidationError:
    detail = error.message_dict if hasattr(error, "message_dict") else error.messages
    return ValidationError(detail)


class BranchPurchaseListView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get(self, request, branch_id):
        purchases = (
            Purchase.objects.filter(branch=self.purchase_branch)
            .select_related("supplier", "created_by", "posted_by")
            .prefetch_related("items")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in Purchase.Status.values:
                raise ValidationError({"status": "Select draft or posted."})
            purchases = purchases.filter(status=status_filter)
        supplier_id = request.query_params.get("supplier")
        if supplier_id:
            supplier_id = serializers.IntegerField(min_value=1).run_validation(
                supplier_id
            )
            purchases = purchases.filter(supplier_id=supplier_id)
        search = request.query_params.get("search", "").strip()
        if search:
            purchases = purchases.filter(
                Q(supplier_invoice_number__icontains=search)
                | Q(supplier_name_snapshot__icontains=search)
            )
        return Response(PurchaseSerializer(purchases, many=True).data)

    def post(self, request, branch_id):
        serializer = PurchaseDraftInputSerializer(
            data=request.data,
            context={"branch": self.purchase_branch},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            purchase = create_draft_purchase(
                branch=self.purchase_branch,
                created_by=request.user,
                **data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        return Response(
            PurchaseSerializer(purchase).data,
            status=status.HTTP_201_CREATED,
        )


class BranchPurchaseDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get_purchase(self, purchase_id):
        return get_object_or_404(
            Purchase.objects.select_related(
                "supplier",
                "created_by",
                "posted_by",
            ).prefetch_related("items"),
            pk=purchase_id,
            branch=self.purchase_branch,
        )

    def get(self, request, branch_id, purchase_id):
        return Response(PurchaseSerializer(self.get_purchase(purchase_id)).data)

    def patch(self, request, branch_id, purchase_id):
        purchase = self.get_purchase(purchase_id)
        serializer = PurchaseDraftPatchInputSerializer(
            data=request.data,
            context={"branch": self.purchase_branch},
        )
        serializer.is_valid(raise_exception=True)
        try:
            purchase = update_draft_purchase(
                purchase=purchase,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        purchase = self.get_purchase(purchase.pk)
        return Response(PurchaseSerializer(purchase).data)


class BranchPurchaseReceiveView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def post(self, request, branch_id, purchase_id):
        purchase = get_object_or_404(
            Purchase,
            pk=purchase_id,
            branch=self.purchase_branch,
        )
        try:
            purchase = post_purchase(purchase=purchase, posted_by=request.user)
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        purchase = (
            Purchase.objects.select_related("supplier", "created_by", "posted_by")
            .prefetch_related("items")
            .get(pk=purchase.pk)
        )
        return Response(PurchaseSerializer(purchase).data)


class BranchSupplierInvoiceBalancesView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get(self, request, branch_id):
        supplier = None
        supplier_id = request.query_params.get("supplier")
        if supplier_id:
            supplier_id = serializers.IntegerField(min_value=1).run_validation(
                supplier_id
            )
            supplier = get_object_or_404(
                Supplier,
                pk=supplier_id,
                organization_id=self.purchase_branch.organization_id,
            )
        balances = branch_supplier_invoice_balances(
            branch=self.purchase_branch,
            supplier=supplier,
        )
        return Response(SupplierInvoiceBalanceSerializer(balances, many=True).data)


class BranchSupplierPaymentListView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get(self, request, branch_id):
        payments = (
            SupplierPayment.objects.filter(branch=self.purchase_branch)
            .select_related("supplier", "created_by")
            .prefetch_related("allocations")
        )
        supplier_id = request.query_params.get("supplier")
        if supplier_id:
            supplier_id = serializers.IntegerField(min_value=1).run_validation(
                supplier_id
            )
            payments = payments.filter(supplier_id=supplier_id)
        return Response(SupplierPaymentSerializer(payments, many=True).data)

    def post(self, request, branch_id):
        serializer = SupplierPaymentInputSerializer(
            data=request.data,
            context={"branch": self.purchase_branch},
        )
        serializer.is_valid(raise_exception=True)
        try:
            payment = record_supplier_payment(
                branch=self.purchase_branch,
                created_by=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        payment = (
            SupplierPayment.objects.select_related("supplier", "created_by")
            .prefetch_related("allocations")
            .get(pk=payment.pk)
        )
        return Response(
            {
                "payment": SupplierPaymentSerializer(payment).data,
                "supplier_payable_balance": str(
                    supplier_branch_balance(
                        supplier=payment.supplier,
                        branch=self.purchase_branch,
                    )
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class BranchSupplierPaymentDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get(self, request, branch_id, payment_id):
        payment = get_object_or_404(
            SupplierPayment.objects.select_related("supplier", "created_by")
            .prefetch_related("allocations"),
            pk=payment_id,
            branch=self.purchase_branch,
        )
        return Response(SupplierPaymentSerializer(payment).data)


class BranchPurchaseReturnListView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get(self, request, branch_id):
        returns = (
            PurchaseReturn.objects.filter(branch=self.purchase_branch)
            .select_related("purchase", "supplier", "created_by", "posted_by")
            .prefetch_related("items")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in PurchaseReturn.Status.values:
                raise ValidationError({"status": "Select draft or posted."})
            returns = returns.filter(status=status_filter)
        purchase_id = request.query_params.get("purchase")
        if purchase_id:
            purchase_id = serializers.IntegerField(min_value=1).run_validation(
                purchase_id
            )
            returns = returns.filter(purchase_id=purchase_id)
        supplier_id = request.query_params.get("supplier")
        if supplier_id:
            supplier_id = serializers.IntegerField(min_value=1).run_validation(
                supplier_id
            )
            returns = returns.filter(supplier_id=supplier_id)
        return Response(PurchaseReturnSerializer(returns, many=True).data)

    def post(self, request, branch_id):
        serializer = PurchaseReturnInputSerializer(
            data=request.data,
            context={"branch": self.purchase_branch},
        )
        serializer.is_valid(raise_exception=True)
        try:
            purchase_return = create_draft_purchase_return(
                branch=self.purchase_branch,
                created_by=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        return Response(
            PurchaseReturnSerializer(purchase_return).data,
            status=status.HTTP_201_CREATED,
        )


class BranchPurchaseReturnDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def get_purchase_return(self, return_id):
        return get_object_or_404(
            PurchaseReturn.objects.select_related(
                "purchase",
                "supplier",
                "created_by",
                "posted_by",
            ).prefetch_related("items"),
            pk=return_id,
            branch=self.purchase_branch,
        )

    def get(self, request, branch_id, return_id):
        return Response(
            PurchaseReturnSerializer(
                self.get_purchase_return(return_id)
            ).data
        )

    def patch(self, request, branch_id, return_id):
        purchase_return = self.get_purchase_return(return_id)
        serializer = PurchaseReturnPatchInputSerializer(
            data=request.data,
            context={
                "branch": self.purchase_branch,
                "purchase": purchase_return.purchase,
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            purchase_return = update_draft_purchase_return(
                purchase_return=purchase_return,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        purchase_return = self.get_purchase_return(purchase_return.pk)
        return Response(PurchaseReturnSerializer(purchase_return).data)


class BranchPurchaseReturnPostView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchPurchases]

    def post(self, request, branch_id, return_id):
        purchase_return = get_object_or_404(
            PurchaseReturn.objects.select_related("purchase"),
            pk=return_id,
            branch=self.purchase_branch,
        )
        try:
            purchase_return = post_purchase_return(
                purchase_return=purchase_return,
                posted_by=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_api_validation_error(exc) from exc
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": "Insufficient stock to complete this return.",
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_409_CONFLICT,
            )
        purchase_return = (
            PurchaseReturn.objects.select_related(
                "purchase",
                "supplier",
                "created_by",
                "posted_by",
            )
            .prefetch_related("items")
            .get(pk=purchase_return.pk)
        )
        return Response(PurchaseReturnSerializer(purchase_return).data)
