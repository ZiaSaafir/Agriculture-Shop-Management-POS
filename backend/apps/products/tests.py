from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.organizations.models import Branch, BranchMembership, Organization

from .models import Brand, Product, ProductCategory, ProductVariety, Unit
from .serializers import ProductSerializer


class ProductCatalogModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Catalog Test Shop",
            slug="catalog-test-shop",
        )
        self.category = ProductCategory.objects.create(
            organization=self.organization,
            name="Fertilizer",
        )
        self.unit = Unit.objects.create(
            organization=self.organization,
            name="Kilogram",
            symbol="kg",
            dimension=Unit.Dimension.MASS,
        )

    def make_product(self, **overrides):
        values = {
            "organization": self.organization,
            "category": self.category,
            "base_unit": self.unit,
            "name": "Urea",
            "sku": "UREA-001",
            "purchase_price": Decimal("4000.00"),
            "selling_price": Decimal("4500.00"),
        }
        values.update(overrides)
        return Product.objects.create(**values)

    def test_products_support_decimal_prices_optional_barcode_and_variety(self):
        brand = Brand.objects.create(
            organization=self.organization,
            name="Example Fertilizer Company",
        )
        variety = ProductVariety.objects.create(
            organization=self.organization,
            name="Urea 46%",
            category=self.category,
        )

        product = self.make_product(brand=brand, variety=variety)

        self.assertEqual(product.purchase_price, Decimal("4000.00"))
        self.assertEqual(product.selling_price, Decimal("4500.00"))
        self.assertEqual(product.barcode, "")
        self.assertEqual(product.base_unit, self.unit)

    def test_product_related_records_must_belong_to_the_same_organization(self):
        another_organization = Organization.objects.create(
            name="Another Catalog",
            slug="another-catalog",
        )
        other_category = ProductCategory.objects.create(
            organization=another_organization,
            name="Fertilizer",
        )
        product = Product(
            organization=self.organization,
            category=other_category,
            base_unit=self.unit,
            name="Invalid Urea",
            sku="INVALID-UREA",
            purchase_price=Decimal("1.00"),
            selling_price=Decimal("2.00"),
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_sku_and_nonempty_barcode_are_unique_per_organization(self):
        self.make_product(barcode="123456")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(name="Duplicate SKU", barcode="654321")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_product(
                name="Duplicate Barcode",
                sku="UREA-002",
                barcode="123456",
            )

        another_organization = Organization.objects.create(
            name="Another Catalog",
            slug="another-catalog",
        )
        other_category = ProductCategory.objects.create(
            organization=another_organization,
            name="Fertilizer",
        )
        other_unit = Unit.objects.create(
            organization=another_organization,
            name="Kilogram",
            symbol="kg",
            dimension=Unit.Dimension.MASS,
        )
        self.make_product(
            organization=another_organization,
            category=other_category,
            base_unit=other_unit,
            name="Other Urea",
            barcode="123456",
        )

    def test_serializer_rejects_category_from_another_organization(self):
        another_organization = Organization.objects.create(
            name="Another Catalog",
            slug="another-catalog",
        )
        other_category = ProductCategory.objects.create(
            organization=another_organization,
            name="Seed",
        )
        serializer = ProductSerializer(
            data={
                "organization": self.organization.pk,
                "category": other_category.pk,
                "base_unit": self.unit.pk,
                "name": "Invalid product",
                "sku": "INVALID-001",
                "barcode": "",
                "description": "",
                "purchase_price": "1.00",
                "selling_price": "2.00",
                "low_stock_threshold": "0.000",
                "is_active": True,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("category", serializer.errors)


class ProductCatalogApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Product API Shop",
            slug="product-api-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main",
            code="MAIN",
        )
        self.other_branch = Branch.objects.create(
            organization=self.organization,
            name="Other",
            code="OTHER",
        )
        self.category = ProductCategory.objects.create(
            organization=self.organization,
            name="Seed",
        )
        self.unit = Unit.objects.create(
            organization=self.organization,
            name="Packet",
            symbol="pkt",
            dimension=Unit.Dimension.PACKAGING,
            decimal_places=0,
        )
        self.user = get_user_model().objects.create_user(
            username="product-manager",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.MANAGER),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_catalog_options_and_product_create_are_organization_scoped(self):
        options = self.client.get(
            f"/api/products/branches/{self.branch.pk}/options/"
        )
        self.assertEqual(options.status_code, 200)
        self.assertEqual(
            options.data["categories"],
            [{"id": self.category.pk, "name": "Seed"}],
        )
        self.assertEqual(
            options.data["units"],
            [
                {
                    "id": self.unit.pk,
                    "name": "Packet",
                    "symbol": "pkt",
                    "decimal_places": 0,
                }
            ],
        )

        response = self.client.post(
            f"/api/products/branches/{self.branch.pk}/",
            {
                "category": self.category.pk,
                "base_unit": self.unit.pk,
                "name": "Garden Seed",
                "sku": "SEED-100",
                "barcode": "",
                "description": "",
                "purchase_price": "4.00",
                "selling_price": "6.50",
                "low_stock_threshold": "5.000",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["organization"], self.organization.pk)
        self.assertEqual(response.data["purchase_price"], "4.00")
        self.assertEqual(
            Product.objects.get(pk=response.data["id"]).organization,
            self.organization,
        )

    def test_catalog_rejects_cross_organization_relations_and_other_branch_access(self):
        other_organization = Organization.objects.create(
            name="Other Product Shop",
            slug="other-product-shop",
        )
        foreign_category = ProductCategory.objects.create(
            organization=other_organization,
            name="Foreign category",
        )
        invalid_product = self.client.post(
            f"/api/products/branches/{self.branch.pk}/",
            {
                "category": foreign_category.pk,
                "base_unit": self.unit.pk,
                "name": "Invalid Product",
                "sku": "INVALID-100",
                "purchase_price": "1.00",
                "selling_price": "2.00",
                "low_stock_threshold": "0.000",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(invalid_product.status_code, 400)
        self.assertIn("category", invalid_product.data)

        forbidden = self.client.get(
            f"/api/products/branches/{self.other_branch.pk}/"
        )
        self.assertEqual(forbidden.status_code, 403)
