from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Branch

from .models import Brand, Product, ProductCategory, ProductVariety, Unit
from .permissions import ProductCatalogBranchPermission
from .serializers import ProductApiSerializer


class ProductBranchOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        branches = Branch.objects.filter(
            is_active=True,
            organization__is_active=True,
        )
        if not request.user.is_superuser:
            branches = branches.filter(
                memberships__user=request.user,
                memberships__role__name__in=ProductCatalogBranchPermission.allowed_roles,
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


class ProductCatalogOptionsView(APIView):
    permission_classes = [IsAuthenticated, ProductCatalogBranchPermission]

    def get(self, request, branch_id):
        organization = self.product_branch.organization
        return Response(
            {
                "categories": list(
                    ProductCategory.objects.filter(
                        organization=organization,
                        is_active=True,
                    ).values("id", "name")
                ),
                "brands": list(
                    Brand.objects.filter(
                        organization=organization,
                        is_active=True,
                    ).values("id", "name")
                ),
                "varieties": list(
                    ProductVariety.objects.filter(
                        organization=organization,
                        is_active=True,
                    ).values("id", "name", "category_id")
                ),
                "units": list(
                    Unit.objects.filter(
                        organization=organization,
                        is_active=True,
                    ).values(
                        "id",
                        "name",
                        "symbol",
                        "dimension",
                        "decimal_places",
                        "canonical_factor",
                    )
                ),
            }
        )


class BranchProductListView(APIView):
    permission_classes = [IsAuthenticated, ProductCatalogBranchPermission]

    def get_queryset(self):
        products = Product.objects.filter(
            organization=self.product_branch.organization,
        ).select_related("category", "brand", "variety", "base_unit")
        active_filter = self.request.query_params.get("active")
        if active_filter == "true":
            products = products.filter(is_active=True)
        elif active_filter == "false":
            products = products.filter(is_active=False)
        search = self.request.query_params.get("search", "").strip()
        if search:
            products = products.filter(
                Q(name__icontains=search)
                | Q(sku__icontains=search)
                | Q(barcode__icontains=search)
                | Q(brand__name__icontains=search)
            )
        return products

    def get(self, request, branch_id):
        return Response(
            ProductApiSerializer(
                self.get_queryset(),
                many=True,
                context={"organization": self.product_branch.organization},
            ).data
        )

    def post(self, request, branch_id):
        serializer = ProductApiSerializer(
            data=request.data,
            context={"organization": self.product_branch.organization},
        )
        serializer.is_valid(raise_exception=True)
        try:
            product = serializer.save(organization=self.product_branch.organization)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            raise ValidationError(detail) from exc
        return Response(
            ProductApiSerializer(
                product,
                context={"organization": self.product_branch.organization},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class BranchProductDetailView(APIView):
    permission_classes = [IsAuthenticated, ProductCatalogBranchPermission]

    def get_product(self, product_id):
        return get_object_or_404(
            Product.objects.select_related("category", "brand", "variety", "base_unit"),
            pk=product_id,
            organization=self.product_branch.organization,
        )

    def get(self, request, branch_id, product_id):
        return Response(
            ProductApiSerializer(
                self.get_product(product_id),
                context={"organization": self.product_branch.organization},
            ).data
        )

    def patch(self, request, branch_id, product_id):
        product = self.get_product(product_id)
        serializer = ProductApiSerializer(
            product,
            data=request.data,
            partial=True,
            context={"organization": self.product_branch.organization},
        )
        serializer.is_valid(raise_exception=True)
        try:
            product = serializer.save()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            raise ValidationError(detail) from exc
        return Response(
            ProductApiSerializer(
                product,
                context={"organization": self.product_branch.organization},
            ).data
        )
