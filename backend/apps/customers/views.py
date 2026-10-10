from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer, CustomerLedgerEntry
from .permissions import CanManageBranchCustomers
from .serializers import CustomerLedgerEntrySerializer, CustomerSerializer
from .services import customer_branch_balance


class BranchCustomerListView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchCustomers]

    def get(self, request, branch_id):
        customers = Customer.objects.filter(
            organization=self.customer_branch.organization,
        )
        if request.query_params.get("include_inactive") != "true":
            customers = customers.filter(is_active=True)
        search = request.query_params.get("search", "").strip()
        if search:
            customers = customers.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
            )
        customers = customers.order_by("name", "id")
        return Response(CustomerSerializer(customers, many=True).data)

    def post(self, request, branch_id):
        serializer = CustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save(
            organization=self.customer_branch.organization,
        )
        return Response(
            CustomerSerializer(customer).data,
            status=status.HTTP_201_CREATED,
        )


class BranchCustomerDetailView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchCustomers]

    def get_customer(self, customer_id):
        return get_object_or_404(
            Customer,
            pk=customer_id,
            organization=self.customer_branch.organization,
        )

    def get(self, request, branch_id, customer_id):
        customer = self.get_customer(customer_id)
        return Response(CustomerSerializer(customer).data)

    def patch(self, request, branch_id, customer_id):
        customer = self.get_customer(customer_id)
        serializer = CustomerSerializer(
            customer,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(CustomerSerializer(customer).data)


class BranchCustomerLedgerView(APIView):
    permission_classes = [IsAuthenticated, CanManageBranchCustomers]

    def get(self, request, branch_id, customer_id):
        customer = get_object_or_404(
            Customer,
            pk=customer_id,
            organization=self.customer_branch.organization,
        )
        entries = CustomerLedgerEntry.objects.filter(
            organization=self.customer_branch.organization,
            branch=self.customer_branch,
            customer=customer,
        ).select_related("created_by")
        return Response(
            {
                "customer": CustomerSerializer(customer).data,
                "branch_id": self.customer_branch.pk,
                "balance": str(
                    customer_branch_balance(
                        customer=customer,
                        branch=self.customer_branch,
                    )
                ),
                "entries": CustomerLedgerEntrySerializer(entries, many=True).data,
            }
        )
