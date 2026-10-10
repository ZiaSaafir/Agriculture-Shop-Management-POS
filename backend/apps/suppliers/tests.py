from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.organizations.models import Branch, BranchMembership, Organization

from .models import Supplier, SupplierLedgerEntry
from .services import post_supplier_ledger_entry, supplier_branch_balance


class SupplierLedgerServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Supplier Test Shop",
            slug="supplier-test-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Farm Inputs Ltd",
            phone="03001234567",
            account_reference="SUP-001",
        )
        self.user = get_user_model().objects.create_user(
            username="supplier-ledger-staff",
            password="a-strong-test-password",
        )

    def post(self, entry_type, amount, reason="Test ledger entry"):
        return post_supplier_ledger_entry(
            supplier=self.supplier,
            branch=self.branch,
            entry_type=entry_type,
            amount=Decimal(amount),
            reason=reason,
            created_by=self.user,
        )

    def test_purchases_payments_and_returns_calculate_payable_and_advance(self):
        purchase = self.post("purchase", "10000.00", "Supplier invoice")
        payment = self.post("payment", "12000.00", "Payment and advance")
        returned = self.post("return", "500.00", "Returned damaged goods")

        self.assertEqual(purchase.signed_amount, Decimal("10000.00"))
        self.assertEqual(payment.signed_amount, Decimal("-12000.00"))
        self.assertEqual(
            supplier_branch_balance(supplier=self.supplier, branch=self.branch),
            Decimal("-2500.00"),
        )
        self.assertEqual(
            SupplierLedgerEntry.objects.filter(supplier=self.supplier).count(),
            3,
        )
        self.assertEqual(returned.supplier_name_snapshot, self.supplier.name)

    def test_entries_are_immutable_and_created_only_by_service(self):
        entry = self.post(
            "opening_payable",
            "500.00",
            "Imported opening payable",
        )
        self.supplier.name = "Updated Supplier Name"
        self.supplier.save(update_fields=("name",))
        entry.refresh_from_db()
        self.assertEqual(entry.supplier_name_snapshot, "Farm Inputs Ltd")

        entry.reason = "Changed"
        with self.assertRaises(ValueError):
            entry.save()
        with self.assertRaises(ValueError):
            entry.delete()
        with self.assertRaises(ValueError):
            SupplierLedgerEntry.objects.filter(pk=entry.pk).update(amount="1.00")
        with self.assertRaises(ValueError):
            post_supplier_ledger_entry(
                supplier=self.supplier,
                branch=self.branch,
                entry_type="purchase",
                amount=Decimal("0"),
                reason="Invalid amount",
                created_by=self.user,
            )

    def test_ledger_rejects_cross_organization_branch(self):
        other_organization = Organization.objects.create(
            name="Other Supplier Shop",
            slug="other-supplier-shop",
        )
        other_branch = Branch.objects.create(
            organization=other_organization,
            name="Other Branch",
            code="OTHER",
        )

        with self.assertRaises(ValidationError):
            post_supplier_ledger_entry(
                supplier=self.supplier,
                branch=other_branch,
                entry_type="purchase",
                amount=Decimal("100.00"),
                reason="Invalid cross-organization entry",
                created_by=self.user,
            )


class BranchSupplierApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Supplier API Shop",
            slug="supplier-api-shop",
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
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Supplier One",
            phone="03000000000",
        )
        self.user = get_user_model().objects.create_user(
            username="supplier-store-staff",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.INVENTORY_STAFF),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_store_staff_can_search_create_update_and_view_ledger(self):
        root = f"/api/suppliers/branches/{self.branch.pk}/"
        listing = self.client.get(root, {"search": "Supplier"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 1)

        created = self.client.post(
            root,
            {
                "name": "  New Supplier  ",
                "phone": "03001112222",
                "account_reference": "NEW-01",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["name"], "New Supplier")

        updated = self.client.patch(
            f"{root}{created.data['id']}/",
            {"notes": "Seed supplier"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["notes"], "Seed supplier")

        ledger = self.client.get(f"{root}{self.supplier.pk}/ledger/")
        self.assertEqual(ledger.status_code, 200)
        self.assertEqual(ledger.data["payable_balance"], "0.00")
        self.assertEqual(ledger.data["entries"], [])

    def test_membership_is_required_for_the_exact_branch(self):
        response = self.client.get(
            f"/api/suppliers/branches/{self.other_branch.pk}/"
        )
        self.assertEqual(response.status_code, 403)

    def test_supplier_from_another_organization_is_hidden(self):
        other_organization = Organization.objects.create(
            name="Private Supplier Shop",
            slug="private-supplier-shop",
        )
        private_supplier = Supplier.objects.create(
            organization=other_organization,
            name="Private Supplier",
        )

        response = self.client.get(
            f"/api/suppliers/branches/{self.branch.pk}/{private_supplier.pk}/"
        )
        self.assertEqual(response.status_code, 404)
