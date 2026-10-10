from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.organizations.models import Branch, BranchMembership, Organization
from apps.products.models import Product, ProductCategory, Unit

from .models import StockBalance, StockMovement
from .services import (
    InsufficientStockError,
    ledger_quantity,
    record_stock_movement,
)


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Inventory Test Shop",
            slug="inventory-test-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
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
        self.product = Product.objects.create(
            organization=self.organization,
            category=self.category,
            base_unit=self.unit,
            name="Urea",
            sku="UREA-001",
            purchase_price=Decimal("4000.00"),
            selling_price=Decimal("4500.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="inventory-staff",
            password="a-strong-test-password",
        )

    def record(self, movement_type, quantity, reason="Test movement"):
        return record_stock_movement(
            branch=self.branch,
            product=self.product,
            movement_type=movement_type,
            quantity=Decimal(quantity),
            reason=reason,
            created_by=self.user,
        )

    def test_ledger_changes_balance_and_is_reconciled(self):
        opening = self.record("opening_stock", "100.000")
        purchase = self.record("purchase", "25.500")
        sale = self.record("sale", "10.250")
        damage = self.record("damage", "1.000")

        balance = StockBalance.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(balance.on_hand, Decimal("114.250000"))
        self.assertEqual(ledger_quantity(branch=self.branch, product=self.product), balance.on_hand)
        self.assertEqual(opening.signed_quantity, Decimal("100.000"))
        self.assertEqual(sale.signed_quantity, Decimal("-10.250"))
        self.assertEqual(StockMovement.objects.count(), 4)

    def test_negative_stock_is_rejected_without_recording_a_movement(self):
        self.record("opening_stock", "3.000")

        with self.assertRaises(InsufficientStockError):
            self.record("sale", "3.001")

        balance = StockBalance.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(balance.on_hand, Decimal("3.000000"))
        self.assertEqual(ledger_quantity(branch=self.branch, product=self.product), balance.on_hand)

    def test_movements_are_immutable(self):
        movement = self.record("opening_stock", "5.000")
        self.product.name = "Updated Urea Name"
        self.product.save(update_fields=("name",))

        movement.refresh_from_db()
        self.assertEqual(movement.product_name_snapshot, "Urea")
        self.assertEqual(movement.unit_symbol_snapshot, "kg")

        movement.reason = "Changed after the fact"
        with self.assertRaises(ValueError):
            movement.save()
        with self.assertRaises(ValueError):
            movement.delete()
        with self.assertRaises(ValueError):
            StockMovement.objects.filter(pk=movement.pk).update(reason="Bulk edit")
        with self.assertRaises(ValueError):
            StockMovement.objects.filter(pk=movement.pk).delete()

    def test_movements_must_be_created_through_the_service(self):
        with self.assertRaises(ValueError):
            StockMovement.objects.create(
                branch=self.branch,
                product=self.product,
                movement_type="opening_stock",
                quantity=Decimal("1.000"),
                reason="Bypass service",
                created_by=self.user,
            )

    def test_product_and_branch_must_belong_to_the_same_organization(self):
        other_organization = Organization.objects.create(
            name="Other Inventory Shop",
            slug="other-inventory-shop",
        )
        other_branch = Branch.objects.create(
            organization=other_organization,
            name="Other Shop",
            code="OTHER",
        )

        with self.assertRaises(ValidationError):
            record_stock_movement(
                branch=other_branch,
                product=self.product,
                movement_type="opening_stock",
                quantity=Decimal("1.000"),
                reason="Invalid cross-organization stock",
                created_by=self.user,
            )

    def test_reason_is_required(self):
        with self.assertRaises(ValidationError):
            self.record("opening_stock", "1.000", reason="   ")

    def test_quantity_respects_unit_precision(self):
        self.unit.decimal_places = 2
        self.unit.save(update_fields=("decimal_places",))

        with self.assertRaises(ValidationError):
            self.record("opening_stock", "1.001")


class BranchInventoryApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="API Inventory Shop",
            slug="api-inventory-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.other_branch = Branch.objects.create(
            organization=self.organization,
            name="Second Shop",
            code="SECOND",
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Seeds",
        )
        unit = Unit.objects.create(
            organization=self.organization,
            name="Packet",
            symbol="pkt",
            dimension=Unit.Dimension.PACKAGING,
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="Wheat Seed",
            sku="WHEAT-001",
            purchase_price=Decimal("100.00"),
            selling_price=Decimal("125.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="branch-inventory-staff",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.INVENTORY_STAFF),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_manual_movement_is_branch_scoped_and_updates_stock(self):
        zero_stock = self.client.get(
            f"/api/inventory/branches/{self.branch.pk}/stock/"
        )
        self.assertEqual(zero_stock.status_code, 200)
        self.assertEqual(zero_stock.data[0]["on_hand"], "0.000000")

        response = self.client.post(
            f"/api/inventory/branches/{self.branch.pk}/movements/",
            {
                "product": self.product.pk,
                "movement_type": "opening_stock",
                "quantity": "10.000000",
                "reason": "Initial count",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.user.username)
        self.assertEqual(
            self.client.get(f"/api/inventory/branches/{self.branch.pk}/stock/").data[
                0
            ]["on_hand"],
            "10.000000",
        )
        self.assertEqual(
            self.client.get(
                f"/api/inventory/branches/{self.branch.pk}/movements/"
            ).status_code,
            200,
        )

    def test_membership_does_not_grant_access_to_another_branch(self):
        response = self.client.get(
            f"/api/inventory/branches/{self.other_branch.pk}/stock/"
        )

        self.assertEqual(response.status_code, 403)

    def test_inventory_endpoint_rejects_sales_movement_creation(self):
        response = self.client.post(
            f"/api/inventory/branches/{self.branch.pk}/movements/",
            {
                "product": self.product.pk,
                "movement_type": "sale",
                "quantity": "1.000000",
                "reason": "Sales workflow is not implemented yet",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_cashier_can_view_stock_but_cannot_record_manual_movements(self):
        cashier = get_user_model().objects.create_user(username="pos-cashier")
        BranchMembership.objects.create(
            user=cashier,
            branch=self.branch,
            role=Group.objects.get(name=Role.CASHIER),
        )
        self.client.force_authenticate(cashier)

        stock = self.client.get(
            f"/api/inventory/branches/{self.branch.pk}/stock/"
        )
        self.assertEqual(stock.status_code, 200)
        self.assertEqual(stock.data[0]["selling_price"], "125.00")
        self.assertEqual(stock.data[0]["quantity_decimal_places"], 3)

        movement = self.client.post(
            f"/api/inventory/branches/{self.branch.pk}/movements/",
            {
                "product": self.product.pk,
                "movement_type": "opening_stock",
                "quantity": "1",
                "reason": "Cashier must not adjust stock",
            },
            format="json",
        )
        self.assertEqual(movement.status_code, 403)
