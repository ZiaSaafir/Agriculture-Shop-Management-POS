from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Supplier, SupplierLedgerEntry
from .permissions import CanManageBranchSuppliers
from .serializers import SupplierLedgerEntrySerializer, SupplierSerializer
from .services import supplier_branch_balance


class BranchSupplierListView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSuppliers]

    def get(self, request, branch_id):
        suppliers = Supplier.objects.filter(
            organization=self.supplier_branch.organization,
        )
        if request.query_params.get("include_inactive") != "true":
            suppliers = suppliers.filter(is_active=True)
        search = request.query_params.get("search", "").strip()
        if search:
            suppliers = suppliers.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
            )
        suppliers = suppliers.order_by("name", "id")
        return Response(SupplierSerializer(suppliers, many=True).data)

    def post(self, request, branch_id):
        serializer = SupplierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplier = serializer.save(
            organization=self.supplier_branch.organization,
        )
        return Response(
            SupplierSerializer(supplier).data,
            status=status.HTTP_201_CREATED,
        )


class BranchSupplierDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSuppliers]

    def get_supplier(self, supplier_id):
        return get_object_or_404(
            Supplier,
            pk=supplier_id,
            organization=self.supplier_branch.organization,
        )

    def get(self, request, branch_id, supplier_id):
        supplier = self.get_supplier(supplier_id)
        return Response(SupplierSerializer(supplier).data)

    def patch(self, request, branch_id, supplier_id):
        supplier = self.get_supplier(supplier_id)
        serializer = SupplierSerializer(
            supplier,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        supplier = serializer.save()
        return Response(SupplierSerializer(supplier).data)


class BranchSupplierLedgerView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchSuppliers]

    def get(self, request, branch_id, supplier_id):
        supplier = get_object_or_404(
            Supplier,
            pk=supplier_id,
            organization=self.supplier_branch.organization,
        )
        entries = SupplierLedgerEntry.objects.filter(
            organization=self.supplier_branch.organization,
            branch=self.supplier_branch,
            supplier=supplier,
        ).select_related("created_by")
        return Response(
            {
                "supplier": SupplierSerializer(supplier).data,
                "branch_id": self.supplier_branch.pk,
                "payable_balance": str(
                    supplier_branch_balance(
                        supplier=supplier,
                        branch=self.supplier_branch,
                    )
                ),
                "entries": SupplierLedgerEntrySerializer(entries, many=True).data,
            }
        )
