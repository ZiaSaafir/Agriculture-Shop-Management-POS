from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import DecimalField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import Product

from .models import StockBalance, StockMovement
from .permissions import CanAccessBranchInventory, CanViewBranchInventory
from .serializers import (
    ManualStockMovementInputSerializer,
    ProductStockSerializer,
    StockMovementSerializer,
)
from .services import InsufficientStockError, record_stock_movement


class BranchInventoryView(APIView):
    permission_classes = [IsAuthenticated, CanViewBranchInventory]

    def get(self, request, branch_id):
        balance = StockBalance.objects.filter(
            branch=self.inventory_branch,
            product=OuterRef("pk"),
        ).values("on_hand")[:1]
        quantity_field = DecimalField(max_digits=18, decimal_places=6)
        products = (
            Product.objects.filter(
                organization_id=self.inventory_branch.organization_id,
            )
            .select_related("base_unit")
            .prefetch_related("organization__units")
            .annotate(
                on_hand=Coalesce(
                    Subquery(balance, output_field=quantity_field),
                    Value(Decimal("0"), output_field=quantity_field),
                    output_field=quantity_field,
                )
            )
            .order_by("name", "pk")
        )
        return Response(ProductStockSerializer(products, many=True).data)


class BranchStockMovementsView(APIView):
    permission_classes = [IsAuthenticated, CanAccessBranchInventory]

    def get(self, request, branch_id):
        movements = (
            StockMovement.objects.filter(branch=self.inventory_branch)
            .select_related("product", "product__base_unit", "created_by")
        )
        return Response(StockMovementSerializer(movements, many=True).data)

    def post(self, request, branch_id):
        serializer = ManualStockMovementInputSerializer(
            data=request.data,
            context={"branch": self.inventory_branch},
        )
        serializer.is_valid(raise_exception=True)
        try:
            movement = record_stock_movement(
                branch=self.inventory_branch,
                created_by=request.user,
                **serializer.validated_data,
            )
        except InsufficientStockError as exc:
            return Response(
                {
                    "detail": "Insufficient stock for this movement.",
                    "available": str(exc.available),
                    "requested": str(exc.requested),
                },
                status=status.HTTP_409_CONFLICT,
            )
        except DjangoValidationError as exc:
            detail = (
                exc.message_dict
                if hasattr(exc, "message_dict")
                else exc.messages
            )
            raise ValidationError(detail) from exc

        movement = (
            StockMovement.objects.select_related(
                "product",
                "product__base_unit",
                "created_by",
            )
            .get(pk=movement.pk)
        )
        return Response(
            StockMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )
