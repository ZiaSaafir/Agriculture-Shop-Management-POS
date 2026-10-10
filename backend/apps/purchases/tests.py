from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import record_stock_movement
from apps.organizations.models import Branch, BranchMembership, Organization
from apps.products.models import Product, ProductCategory, Unit
from apps.suppliers.models import Supplier, SupplierLedgerEntry
from apps.suppliers.services import supplier_branch_balance

from .models import Purchase, PurchaseLine
from .models import (
    PurchaseReturn,
    PurchaseReturnLine,
    SupplierPayment,
    SupplierPaymentAllocation,
)
from .payment_services import (
    branch_supplier_invoice_balances,
    record_supplier_payment,
)
from .return_services import (
    InsufficientStockError,
    create_draft_purchase_return,
    post_purchase_return,
    update_draft_purchase_return,
)
from .services import create_draft_purchase, post_purchase, update_draft_purchase


class PurchasePostingTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Purchase Test Shop",
            slug="purchase-test-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Farm Supplies",
        )
        self.unit = Unit.objects.create(
            organization=self.organization,
            name="Kilogram",
            symbol="kg",
            dimension=Unit.Dimension.MASS,
            decimal_places=3,
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Fertilizer",
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=self.unit,
            name="Test Fertilizer",
            sku="FERT-001",
            purchase_price=Decimal("9.00"),
            selling_price=Decimal("12.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="purchase-store-staff",
            password="a-strong-test-password",
        )
        self.items = [
            {
                "product": self.product,
                "quantity": Decimal("3.000"),
                "unit_cost": Decimal("10.00"),
                "discount_amount": Decimal("5.00"),
                "tax_amount": Decimal("2.00"),
            }
        ]

    def create_draft(self, **kwargs):
        return create_draft_purchase(
            branch=self.branch,
            supplier=self.supplier,
            items=kwargs.pop("items", self.items),
            created_by=self.user,
            **kwargs,
        )

    def test_draft_has_no_stock_or_payable_effect_until_received(self):
        purchase = self.create_draft(supplier_invoice_number="INV-100")
        self.assertEqual(purchase.status, Purchase.Status.DRAFT)
        self.assertEqual(purchase.subtotal, Decimal("30.00"))
        self.assertEqual(purchase.discount_total, Decimal("5.00"))
        self.assertEqual(purchase.tax_total, Decimal("2.00"))
        self.assertEqual(purchase.total, Decimal("27.00"))
        self.assertFalse(
            StockMovement.objects.filter(branch=self.branch).exists()
        )
        self.assertFalse(
            SupplierLedgerEntry.objects.filter(supplier=self.supplier).exists()
        )

        purchase = post_purchase(purchase=purchase, posted_by=self.user)
        balance = StockBalance.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(purchase.status, Purchase.Status.POSTED)
        self.assertEqual(purchase.total, Decimal("27.00"))
        self.assertEqual(balance.on_hand, Decimal("3.000000"))
        self.assertEqual(
            supplier_branch_balance(supplier=self.supplier, branch=self.branch),
            Decimal("27.00"),
        )
        movement = StockMovement.objects.get(branch=self.branch)
        ledger_entry = SupplierLedgerEntry.objects.get(supplier=self.supplier)
        self.assertEqual(movement.movement_type, StockMovement.MovementType.PURCHASE)
        self.assertEqual(movement.quantity, Decimal("3.000000"))
        self.assertEqual(ledger_entry.entry_type, SupplierLedgerEntry.EntryType.PURCHASE)
        self.assertEqual(ledger_entry.amount, purchase.total)
        self.assertEqual(movement.reference, purchase.purchase_number)
        self.assertEqual(ledger_entry.reference, purchase.purchase_number)

    def test_purchase_must_contain_positive_value_and_cannot_post_twice(self):
        zero_cost_items = [
            {
                **self.items[0],
                "unit_cost": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "tax_amount": Decimal("0.00"),
            }
        ]
        free_purchase = self.create_draft(items=zero_cost_items)
        with self.assertRaises(ValidationError):
            post_purchase(purchase=free_purchase, posted_by=self.user)
        free_purchase.refresh_from_db()
        self.assertEqual(free_purchase.status, Purchase.Status.DRAFT)
        self.assertFalse(StockMovement.objects.filter(branch=self.branch).exists())

        purchase = self.create_draft()
        post_purchase(purchase=purchase, posted_by=self.user)
        with self.assertRaises(ValidationError):
            post_purchase(purchase=purchase, posted_by=self.user)
        self.assertEqual(StockMovement.objects.filter(branch=self.branch).count(), 1)
        self.assertEqual(
            SupplierLedgerEntry.objects.filter(supplier=self.supplier).count(),
            1,
        )

    def test_posted_purchase_and_lines_are_immutable(self):
        purchase = self.create_draft()
        post_purchase(purchase=purchase, posted_by=self.user)
        purchase.refresh_from_db()
        with self.assertRaises(ValueError):
            purchase.notes = "Edited after posting"
            purchase.save()
        line = PurchaseLine.objects.get(purchase=purchase)
        with self.assertRaises(ValueError):
            line.delete()
        with self.assertRaises(ValueError):
            PurchaseLine.objects.filter(pk=line.pk).update(quantity=Decimal("9"))
        with self.assertRaises(ValidationError):
            update_draft_purchase(purchase=purchase, notes="No longer editable")

    def test_draft_replacement_updates_totals_without_effects(self):
        purchase = self.create_draft()
        updated_items = [
            {
                "product": self.product,
                "quantity": Decimal("4.000"),
                "unit_cost": Decimal("10.00"),
                "discount_amount": Decimal("0.00"),
                "tax_amount": Decimal("0.00"),
            }
        ]
        purchase = update_draft_purchase(
            purchase=purchase,
            items=updated_items,
            notes="Corrected supplier draft",
        )
        self.assertEqual(purchase.total, Decimal("40.00"))
        self.assertEqual(purchase.items.count(), 1)
        self.assertFalse(StockMovement.objects.filter(branch=self.branch).exists())


class BranchPurchaseApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Purchase API Shop",
            slug="purchase-api-shop",
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
            name="API Supplier",
        )
        unit = Unit.objects.create(
            organization=self.organization,
            name="Piece",
            symbol="pc",
            dimension=Unit.Dimension.COUNT,
            decimal_places=0,
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Tools",
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="Hoe",
            sku="HOE-001",
            purchase_price=Decimal("500.00"),
            selling_price=Decimal("700.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="purchase-api-staff",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.INVENTORY_STAFF),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_store_staff_can_create_edit_and_receive_a_purchase(self):
        root = f"/api/purchases/branches/{self.branch.pk}/"
        payload = {
            "supplier": self.supplier.pk,
            "supplier_invoice_number": "SUP-INV-42",
            "items": [
                {
                    "product": self.product.pk,
                    "quantity": "2",
                    "unit_cost": "125.00",
                    "discount_amount": "5.00",
                    "tax_amount": "10.00",
                }
            ],
        }
        created = self.client.post(root, payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], Purchase.Status.DRAFT)
        self.assertEqual(created.data["total"], "255.00")

        purchase_id = created.data["id"]
        patched = self.client.patch(
            f"{root}{purchase_id}/",
            {"notes": "Received from regular supplier"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data["notes"], "Received from regular supplier")

        received = self.client.post(f"{root}{purchase_id}/receive/", {}, format="json")
        self.assertEqual(received.status_code, 200, received.data)
        self.assertEqual(received.data["status"], Purchase.Status.POSTED)
        self.assertEqual(received.data["purchase_number"], f"PUR-{purchase_id:06d}")
        self.assertEqual(
            StockBalance.objects.get(
                branch=self.branch,
                product=self.product,
            ).on_hand,
            Decimal("2"),
        )

        listing = self.client.get(root, {"status": "posted"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 1)

    def test_purchase_api_requires_membership_in_requested_branch(self):
        response = self.client.get(
            f"/api/purchases/branches/{self.other_branch.pk}/"
        )
        self.assertEqual(response.status_code, 403)


class SupplierPaymentSettlementTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Settlement Shop",
            slug="settlement-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Settlement Supplier",
        )
        self.unit = Unit.objects.create(
            organization=self.organization,
            name="Piece",
            symbol="pc",
            dimension=Unit.Dimension.COUNT,
            decimal_places=0,
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Settlement Tools",
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=self.unit,
            name="Spade",
            sku="SPADE-01",
            purchase_price=Decimal("10.00"),
            selling_price=Decimal("15.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="settlement-staff",
            password="a-strong-test-password",
        )
        self.first_purchase = self.make_posted_purchase("20.00", "SUP-INV-1")
        self.second_purchase = self.make_posted_purchase("30.00", "SUP-INV-2")

    def make_posted_purchase(self, unit_cost, invoice_number):
        purchase = create_draft_purchase(
            branch=self.branch,
            supplier=self.supplier,
            created_by=self.user,
            supplier_invoice_number=invoice_number,
            items=[
                {
                    "product": self.product,
                    "quantity": Decimal("1"),
                    "unit_cost": Decimal(unit_cost),
                }
            ],
        )
        return post_purchase(purchase=purchase, posted_by=self.user)

    def test_payment_can_settle_multiple_invoices_and_leave_advance(self):
        payment = record_supplier_payment(
            branch=self.branch,
            supplier=self.supplier,
            amount=Decimal("35.00"),
            created_by=self.user,
            reference="BANK-REF-77",
            payment_method="Bank transfer",
            allocations=[
                {"purchase": self.first_purchase, "amount": Decimal("20.00")},
                {"purchase": self.second_purchase, "amount": Decimal("10.00")},
            ],
        )

        payment.refresh_from_db()
        balances = {
            row["purchase"].pk: row
            for row in branch_supplier_invoice_balances(
                branch=self.branch,
                supplier=self.supplier,
            )
        }
        self.assertEqual(payment.amount, Decimal("35.00"))
        self.assertEqual(payment.allocations.count(), 2)
        self.assertEqual(
            balances[self.first_purchase.pk]["outstanding_amount"],
            Decimal("0.00"),
        )
        self.assertEqual(
            balances[self.second_purchase.pk]["outstanding_amount"],
            Decimal("20.00"),
        )
        self.assertEqual(
            SupplierPaymentAllocation.objects.filter(payment=payment).aggregate(
                total=Sum("amount")
            )["total"],
            Decimal("30.00"),
        )
        self.assertEqual(
            supplier_branch_balance(supplier=self.supplier, branch=self.branch),
            Decimal("15.00"),
        )
        entry = SupplierLedgerEntry.objects.get(
            supplier=self.supplier,
            entry_type=SupplierLedgerEntry.EntryType.PAYMENT,
        )
        self.assertEqual(entry.amount, Decimal("35.00"))
        self.assertEqual(entry.reference, "BANK-REF-77")

    def test_payment_cannot_overallocate_invoice_or_exceed_tender(self):
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                branch=self.branch,
                supplier=self.supplier,
                amount=Decimal("40.00"),
                created_by=self.user,
                allocations=[
                    {
                        "purchase": self.first_purchase,
                        "amount": Decimal("21.00"),
                    }
                ],
            )
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                branch=self.branch,
                supplier=self.supplier,
                amount=Decimal("10.00"),
                created_by=self.user,
                allocations=[
                    {
                        "purchase": self.first_purchase,
                        "amount": Decimal("11.00"),
                    }
                ],
            )
        self.assertEqual(SupplierPayment.objects.count(), 0)
        self.assertEqual(
            SupplierLedgerEntry.objects.filter(
                entry_type=SupplierLedgerEntry.EntryType.PAYMENT
            ).count(),
            0,
        )

    def test_remaining_amount_is_supplier_advance(self):
        payment = record_supplier_payment(
            branch=self.branch,
            supplier=self.supplier,
            amount=Decimal("60.00"),
            created_by=self.user,
            allocations=[
                {"purchase": self.first_purchase, "amount": Decimal("20.00")},
                {"purchase": self.second_purchase, "amount": Decimal("30.00")},
            ],
        )
        self.assertEqual(
            payment.amount
            - sum(
                (item.amount for item in payment.allocations.all()),
                Decimal("0.00"),
            ),
            Decimal("10.00"),
        )
        self.assertEqual(
            supplier_branch_balance(supplier=self.supplier, branch=self.branch),
            Decimal("-10.00"),
        )
        self.assertEqual(
            branch_supplier_invoice_balances(
                branch=self.branch,
                supplier=self.supplier,
            ),
            [
                {
                    "purchase": self.first_purchase,
                    "paid_amount": Decimal("20.00"),
                    "returned_amount": Decimal("0.00"),
                    "net_total": Decimal("20.00"),
                    "outstanding_amount": Decimal("0.00"),
                },
                {
                    "purchase": self.second_purchase,
                    "paid_amount": Decimal("30.00"),
                    "returned_amount": Decimal("0.00"),
                    "net_total": Decimal("30.00"),
                    "outstanding_amount": Decimal("0.00"),
                },
            ],
        )


class BranchSupplierPaymentApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Settlement API Shop",
            slug="settlement-api-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.other_branch = Branch.objects.create(
            organization=self.organization,
            name="Other Shop",
            code="OTHER",
        )
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="API Settlement Supplier",
        )
        unit = Unit.objects.create(
            organization=self.organization,
            name="Piece",
            symbol="pc",
            dimension=Unit.Dimension.COUNT,
            decimal_places=0,
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Payment Tools",
        )
        product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="Rake",
            sku="RAKE-1",
            purchase_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="settlement-api-staff",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.INVENTORY_STAFF),
        )
        self.purchase = post_purchase(
            purchase=create_draft_purchase(
                branch=self.branch,
                supplier=self.supplier,
                created_by=self.user,
                supplier_invoice_number="API-INV-1",
                items=[
                    {
                        "product": product,
                        "quantity": Decimal("2"),
                        "unit_cost": Decimal("50.00"),
                    }
                ],
            ),
            posted_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_payment_api_records_invoice_payment_and_reports_balance(self):
        root = f"/api/purchases/branches/{self.branch.pk}/"
        balances = self.client.get(f"{root}outstanding/", {"supplier": self.supplier.pk})
        self.assertEqual(balances.status_code, 200)
        self.assertEqual(balances.data[0]["outstanding_amount"], "100.00")

        response = self.client.post(
            f"{root}payments/",
            {
                "supplier": self.supplier.pk,
                "amount": "120.00",
                "payment_date": "2026-10-07",
                "payment_method": "Bank transfer",
                "reference": "BANK-API-1",
                "allocations": [
                    {"purchase": self.purchase.pk, "amount": "100.00"}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        payment_id = response.data["payment"]["id"]
        self.assertEqual(
            response.data["payment"]["payment_number"],
            f"SPAY-{payment_id:06d}",
        )
        self.assertEqual(response.data["payment"]["allocated_amount"], "100.00")
        self.assertEqual(response.data["payment"]["unallocated_amount"], "20.00")
        self.assertEqual(response.data["supplier_payable_balance"], "-20.00")

        outstanding = self.client.get(f"{root}outstanding/", {"supplier": self.supplier.pk})
        self.assertEqual(outstanding.status_code, 200)
        self.assertEqual(outstanding.data[0]["outstanding_amount"], "0.00")
        history = self.client.get(f"{root}payments/", {"supplier": self.supplier.pk})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data), 1)
        detail = self.client.get(
            f"{root}payments/{response.data['payment']['id']}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["reference"], "BANK-API-1")

    def test_payment_api_is_branch_scoped(self):
        response = self.client.get(
            f"/api/purchases/branches/{self.other_branch.pk}/payments/"
        )
        self.assertEqual(response.status_code, 403)


class PurchaseReturnTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Return Test Shop",
            slug="return-test-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.other_branch = Branch.objects.create(
            organization=self.organization,
            name="Other Shop",
            code="OTHER",
        )
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Return Supplier",
        )
        unit = Unit.objects.create(
            organization=self.organization,
            name="Piece",
            symbol="pc",
            dimension=Unit.Dimension.COUNT,
            decimal_places=0,
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Returns",
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="Return Tool",
            sku="RETURN-1",
            purchase_price=Decimal("10.00"),
            selling_price=Decimal("20.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="return-staff",
            password="a-strong-test-password",
        )
        draft = create_draft_purchase(
            branch=self.branch,
            supplier=self.supplier,
            created_by=self.user,
            supplier_invoice_number="RETURN-INV-1",
            items=[
                {
                    "product": self.product,
                    "quantity": Decimal("5"),
                    "unit_cost": Decimal("10.00"),
                }
            ],
        )
        self.purchase = post_purchase(purchase=draft, posted_by=self.user)
        self.purchase_line = self.purchase.items.get()

    def make_draft_return(self, quantity="2", credit="18.00"):
        return create_draft_purchase_return(
            branch=self.branch,
            purchase=self.purchase,
            created_by=self.user,
            supplier_credit_note_reference="CN-1",
            items=[
                {
                    "purchase_line": self.purchase_line,
                    "quantity": Decimal(quantity),
                    "credit_amount": Decimal(credit),
                }
            ],
        )

    def test_draft_return_has_no_effect_until_posted(self):
        draft = self.make_draft_return()
        balance = StockBalance.objects.get(
            branch=self.branch,
            product=self.product,
        )
        self.assertEqual(draft.status, PurchaseReturn.Status.DRAFT)
        self.assertEqual(draft.credit_total, Decimal("18.00"))
        self.assertEqual(balance.on_hand, Decimal("5"))
        self.assertEqual(
            SupplierLedgerEntry.objects.filter(
                entry_type=SupplierLedgerEntry.EntryType.RETURN
            ).count(),
            0,
        )

        posted = post_purchase_return(
            purchase_return=draft,
            posted_by=self.user,
        )
        balance.refresh_from_db()
        self.assertEqual(posted.status, PurchaseReturn.Status.POSTED)
        self.assertEqual(balance.on_hand, Decimal("3"))
        self.assertEqual(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SUPPLIER_RETURN
            ).count(),
            1,
        )
        ledger_entry = SupplierLedgerEntry.objects.get(
            entry_type=SupplierLedgerEntry.EntryType.RETURN
        )
        self.assertEqual(ledger_entry.amount, Decimal("18.00"))
        self.assertEqual(ledger_entry.reference, "CN-1")
        self.assertEqual(
            branch_supplier_invoice_balances(
                branch=self.branch,
                supplier=self.supplier,
            )[0]["outstanding_amount"],
            Decimal("32.00"),
        )

    def test_cumulative_return_quantity_is_capped(self):
        first_return = post_purchase_return(
            purchase_return=self.make_draft_return("3", "30.00"),
            posted_by=self.user,
        )
        with self.assertRaises(ValidationError):
            self.make_draft_return("3", "30.00")
        with self.assertRaises(ValidationError):
            post_purchase_return(
                purchase_return=first_return,
                posted_by=self.user,
            )

    def test_return_cannot_make_stock_negative(self):
        record_stock_movement(
            branch=self.branch,
            product=self.product,
            movement_type=StockMovement.MovementType.SALE,
            quantity=Decimal("4"),
            reason="Simulate four units sold",
            created_by=self.user,
        )
        draft = self.make_draft_return("2", "20.00")
        with self.assertRaises(InsufficientStockError):
            post_purchase_return(purchase_return=draft, posted_by=self.user)
        draft.refresh_from_db()
        self.assertEqual(draft.status, PurchaseReturn.Status.DRAFT)
        balance = StockBalance.objects.get(
            branch=self.branch,
            product=self.product,
        )
        self.assertEqual(balance.on_hand, Decimal("1"))
        self.assertFalse(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.SUPPLIER_RETURN,
                reference=draft.return_number,
            ).exists()
        )

    def test_return_credit_and_prior_payments_reduce_invoice_outstanding(self):
        payment = record_supplier_payment(
            branch=self.branch,
            supplier=self.supplier,
            amount=Decimal("25.00"),
            created_by=self.user,
            allocations=[
                {
                    "purchase": self.purchase,
                    "amount": Decimal("25.00"),
                }
            ],
        )
        self.assertEqual(payment.allocations.count(), 1)
        posted_return = post_purchase_return(
            purchase_return=self.make_draft_return("2", "20.00"),
            posted_by=self.user,
        )
        self.assertEqual(posted_return.status, PurchaseReturn.Status.POSTED)
        invoice_balance = branch_supplier_invoice_balances(
            branch=self.branch,
            supplier=self.supplier,
        )[0]
        self.assertEqual(invoice_balance["returned_amount"], Decimal("20.00"))
        self.assertEqual(invoice_balance["net_total"], Decimal("30.00"))
        self.assertEqual(invoice_balance["paid_amount"], Decimal("25.00"))
        self.assertEqual(invoice_balance["outstanding_amount"], Decimal("5.00"))

    def test_return_credit_after_paid_invoice_becomes_supplier_advance(self):
        record_supplier_payment(
            branch=self.branch,
            supplier=self.supplier,
            amount=Decimal("50.00"),
            created_by=self.user,
            allocations=[
                {"purchase": self.purchase, "amount": Decimal("50.00")}
            ],
        )
        post_purchase_return(
            purchase_return=self.make_draft_return("2", "20.00"),
            posted_by=self.user,
        )
        invoice_balance = branch_supplier_invoice_balances(
            branch=self.branch,
            supplier=self.supplier,
        )[0]
        self.assertEqual(invoice_balance["outstanding_amount"], Decimal("0.00"))
        self.assertEqual(
            supplier_branch_balance(supplier=self.supplier, branch=self.branch),
            Decimal("-20.00"),
        )

    def test_return_draft_can_be_edited_only_before_posting(self):
        draft = self.make_draft_return()
        draft = update_draft_purchase_return(
            purchase_return=draft,
            supplier_credit_note_reference="CN-UPDATED",
            items=[
                {
                    "purchase_line": self.purchase_line,
                    "quantity": Decimal("1"),
                    "credit_amount": Decimal("9.00"),
                }
            ],
        )
        self.assertEqual(draft.credit_total, Decimal("9.00"))
        post_purchase_return(purchase_return=draft, posted_by=self.user)
        with self.assertRaises(ValidationError):
            update_draft_purchase_return(
                purchase_return=draft,
                notes="Cannot edit posted return",
            )


class BranchPurchaseReturnApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Return API Shop",
            slug="return-api-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.other_branch = Branch.objects.create(
            organization=self.organization,
            name="Other Shop",
            code="OTHER",
        )
        self.supplier = Supplier.objects.create(
            organization=self.organization,
            name="Return API Supplier",
        )
        unit = Unit.objects.create(
            organization=self.organization,
            name="Piece",
            symbol="pc",
            dimension=Unit.Dimension.COUNT,
            decimal_places=0,
        )
        category = ProductCategory.objects.create(
            organization=self.organization,
            name="Return API Category",
        )
        product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="API Return Item",
            sku="RETURN-API-1",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("8.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="return-api-staff",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.INVENTORY_STAFF),
        )
        purchase = post_purchase(
            purchase=create_draft_purchase(
                branch=self.branch,
                supplier=self.supplier,
                created_by=self.user,
                items=[
                    {
                        "product": product,
                        "quantity": Decimal("3"),
                        "unit_cost": Decimal("5.00"),
                    }
                ],
            ),
            posted_by=self.user,
        )
        self.purchase = purchase
        self.purchase_line = purchase.items.get()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_return_api_drafts_edits_and_posts(self):
        root = f"/api/purchases/branches/{self.branch.pk}/returns/"
        created = self.client.post(
            root,
            {
                "purchase": self.purchase.pk,
                "supplier_credit_note_reference": "CN-API-1",
                "items": [
                    {
                        "purchase_line": self.purchase_line.pk,
                        "quantity": "1",
                        "credit_amount": "4.50",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], PurchaseReturn.Status.DRAFT)

        return_id = created.data["id"]
        updated = self.client.patch(
            f"{root}{return_id}/",
            {"notes": "Supplier approved return"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["notes"], "Supplier approved return")

        posted = self.client.post(
            f"{root}{return_id}/post/",
            {},
            format="json",
        )
        self.assertEqual(posted.status_code, 200, posted.data)
        self.assertEqual(posted.data["status"], PurchaseReturn.Status.POSTED)
        self.assertEqual(posted.data["return_number"], f"PRET-{return_id:06d}")
        self.assertEqual(
            StockBalance.objects.get(
                branch=self.branch,
                product=self.purchase_line.product,
            ).on_hand,
            Decimal("2"),
        )
        listed = self.client.get(root, {"purchase": self.purchase.pk})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

    def test_return_api_is_branch_scoped(self):
        response = self.client.get(
            f"/api/purchases/branches/{self.other_branch.pk}/returns/"
        )
        self.assertEqual(response.status_code, 403)
