from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.organizations.models import Branch, BranchMembership, Organization

from .models import Customer, CustomerLedgerEntry
from .services import customer_branch_balance, post_customer_ledger_entry


class CustomerLedgerServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Customer Test Shop",
            slug="customer-test-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Amina Khan",
            phone="03001234567",
        )
        self.user = get_user_model().objects.create_user(
            username="customer-ledger-staff",
            password="a-strong-test-password",
        )

    def post(self, entry_type, amount, reason="Test ledger entry"):
        return post_customer_ledger_entry(
            customer=self.customer,
            branch=self.branch,
            entry_type=entry_type,
            amount=Decimal(amount),
            reason=reason,
            created_by=self.user,
        )

    def test_debits_credits_and_advances_are_derived_from_ledger(self):
        sale = self.post("sale", "10000.00", "Invoice")
        payment = self.post("payment", "12000.00", "Payment with advance")
        returned = self.post("return", "500.00", "Customer return")

        self.assertEqual(sale.signed_amount, Decimal("10000.00"))
        self.assertEqual(payment.signed_amount, Decimal("-12000.00"))
        self.assertEqual(
            customer_branch_balance(customer=self.customer, branch=self.branch),
            Decimal("-2500.00"),
        )
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(customer=self.customer).count(),
            3,
        )
        self.assertEqual(returned.customer_name_snapshot, self.customer.name)

    def test_entry_is_immutable_and_cannot_be_created_outside_service(self):
        entry = self.post("opening_debit", "500.00", "Imported opening balance")
        self.customer.name = "Updated Customer Name"
        self.customer.save(update_fields=("name",))

        entry.refresh_from_db()
        self.assertEqual(entry.customer_name_snapshot, "Amina Khan")
        entry.reason = "Changed"
        with self.assertRaises(ValueError):
            entry.save()
        with self.assertRaises(ValueError):
            entry.delete()
        with self.assertRaises(ValueError):
            CustomerLedgerEntry.objects.filter(pk=entry.pk).update(amount="1.00")
        with self.assertRaises(ValueError):
            post_customer_ledger_entry(
                customer=self.customer,
                branch=self.branch,
                entry_type="sale",
                amount=Decimal("0"),
                reason="Invalid",
                created_by=self.user,
            )

    def test_ledger_entry_rejects_cross_organization_branch(self):
        other_organization = Organization.objects.create(
            name="Other Customer Shop",
            slug="other-customer-shop",
        )
        other_branch = Branch.objects.create(
            organization=other_organization,
            name="Other Branch",
            code="OTHER",
        )

        with self.assertRaises(ValidationError):
            post_customer_ledger_entry(
                customer=self.customer,
                branch=other_branch,
                entry_type="sale",
                amount=Decimal("100.00"),
                reason="Invalid cross-organization entry",
                created_by=self.user,
            )


class BranchCustomerApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Customer API Shop",
            slug="customer-api-shop",
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
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Customer One",
            phone="03000000000",
        )
        self.user = get_user_model().objects.create_user(
            username="customer-cashier",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.CASHIER),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_cashier_can_list_create_update_and_read_branch_ledger(self):
        list_url = f"/api/customers/branches/{self.branch.pk}/"
        response = self.client.get(list_url, {"search": "Customer"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

        created = self.client.post(
            list_url,
            {"name": "  New Customer  ", "phone": "03001112222"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["name"], "New Customer")

        updated = self.client.patch(
            f"{list_url}{created.data['id']}/",
            {"notes": "Seed customer"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["notes"], "Seed customer")

        ledger = self.client.get(
            f"{list_url}{self.customer.pk}/ledger/",
        )
        self.assertEqual(ledger.status_code, 200)
        self.assertEqual(ledger.data["balance"], "0.00")
        self.assertEqual(ledger.data["entries"], [])

    def test_access_is_limited_to_the_users_branch(self):
        response = self.client.get(
            f"/api/customers/branches/{self.other_branch.pk}/"
        )
        self.assertEqual(response.status_code, 403)

    def test_other_organization_customer_is_not_found(self):
        other_organization = Organization.objects.create(
            name="Other API Shop",
            slug="other-api-shop",
        )
        other_customer = Customer.objects.create(
            organization=other_organization,
            name="Private Customer",
        )

        response = self.client.get(
            f"/api/customers/branches/{self.branch.pk}/{other_customer.pk}/"
        )
        self.assertEqual(response.status_code, 404)
