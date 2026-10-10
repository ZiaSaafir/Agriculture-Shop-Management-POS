from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.customers.models import Customer, CustomerLedgerEntry
from apps.customers.services import customer_branch_balance
from apps.inventory.models import StockBalance, StockMovement
from apps.organizations.models import Branch, BranchMembership, Organization
from apps.products.models import Product, ProductCategory, Unit

from .models import Sale, SaleLine, SalesReturn, SalesReturnLine
from .return_services import create_sales_return
from .services import (
    InsufficientStockError,
    complete_sale,
    create_draft_sale,
    update_draft_sale,
)


class SaleCheckoutTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Sales Test Shop",
            slug="sales-test-shop",
        )
        self.branch = Branch.objects.create(
            organization=self.organization,
            name="Main Shop",
            code="MAIN",
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Sale Customer",
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
            name="Sales Products",
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="Sales Product",
            sku="SALE-001",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("12.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="sales-cashier",
            password="a-strong-test-password",
        )
        self.item = {
            "product": self.product,
            "quantity": Decimal("3"),
            "unit_price": Decimal("12.00"),
            "discount_amount": Decimal("2.00"),
            "tax_amount": Decimal("1.00"),
        }
        from apps.inventory.services import record_stock_movement
        from apps.inventory.models import StockMovement

        record_stock_movement(
            branch=self.branch,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING_STOCK,
            quantity=Decimal("10"),
            reason="Prepare stock for sale tests",
            created_by=self.user,
        )

    def test_draft_does_not_change_stock_or_customer_balance_until_checkout(self):
        sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        self.assertEqual(sale.total, Decimal("35.00"))
        self.assertEqual(
            StockBalance.objects.get(
                branch=self.branch,
                product=self.product,
            ).on_hand,
            Decimal("10"),
        )
        self.assertFalse(
            CustomerLedgerEntry.objects.filter(customer=self.customer).exists()
        )

        sale = complete_sale(
            sale=sale,
            completed_by=self.user,
            amount_paid=Decimal("20.00"),
            payment_method="Cash",
            payment_reference="POS-REC-1",
        )
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(sale.balance_due, Decimal("15.00"))
        self.assertEqual(sale.change_due, Decimal("0.00"))
        self.assertEqual(
            customer_branch_balance(customer=self.customer, branch=self.branch),
            Decimal("15.00"),
        )
        balance = StockBalance.objects.get(
            branch=self.branch,
            product=self.product,
        )
        self.assertEqual(balance.on_hand, Decimal("7"))
        movements = StockMovement.objects.filter(
            branch=self.branch,
            product=self.product,
            movement_type=StockMovement.MovementType.SALE,
        )
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.get().reference, sale.sale_number)
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(
                customer=self.customer,
                entry_type=CustomerLedgerEntry.EntryType.SALE,
            ).get().amount,
            Decimal("35.00"),
        )
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(
                customer=self.customer,
                entry_type=CustomerLedgerEntry.EntryType.PAYMENT,
            ).get().amount,
            Decimal("20.00"),
        )

    def test_customer_overpayment_becomes_advance_and_walkin_gets_change(self):
        customer_sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        customer_sale = complete_sale(
            sale=customer_sale,
            completed_by=self.user,
            amount_paid=Decimal("40.00"),
            payment_method="Mobile wallet",
        )
        self.assertEqual(customer_sale.change_due, Decimal("0.00"))
        self.assertEqual(customer_sale.customer_advance_amount, Decimal("5.00"))
        self.assertEqual(
            customer_branch_balance(customer=self.customer, branch=self.branch),
            Decimal("-5.00"),
        )

        walkin_sale = create_draft_sale(
            branch=self.branch,
            items=[self.item],
            created_by=self.user,
        )
        walkin_sale = complete_sale(
            sale=walkin_sale,
            completed_by=self.user,
            amount_paid=Decimal("40.00"),
            payment_method="Cash",
        )
        self.assertEqual(walkin_sale.customer_name_snapshot, "Walk-in")
        self.assertEqual(walkin_sale.change_due, Decimal("5.00"))
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(
                reference=walkin_sale.sale_number,
            ).count(),
            0,
        )

    def test_walkin_cannot_complete_on_credit(self):
        sale = create_draft_sale(
            branch=self.branch,
            items=[self.item],
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            complete_sale(
                sale=sale,
                completed_by=self.user,
                amount_paid=Decimal("1.00"),
            )
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.DRAFT)
        self.assertEqual(
            StockBalance.objects.get(
                branch=self.branch,
                product=self.product,
            ).on_hand,
            Decimal("10"),
        )

    def test_insufficient_stock_rolls_back_sale_and_ledger(self):
        from apps.inventory.services import record_stock_movement

        record_stock_movement(
            branch=self.branch,
            product=self.product,
            movement_type=StockMovement.MovementType.SALE,
            quantity=Decimal("8"),
            reason="Reduce available stock",
            created_by=self.user,
        )
        sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        with self.assertRaises(InsufficientStockError):
            complete_sale(
                sale=sale,
                completed_by=self.user,
                amount_paid=Decimal("0"),
            )
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.DRAFT)
        self.assertEqual(
            StockMovement.objects.filter(
                branch=self.branch,
                product=self.product,
                movement_type=StockMovement.MovementType.SALE,
            ).count(),
            1,
        )
        self.assertFalse(CustomerLedgerEntry.objects.filter(customer=self.customer).exists())

    def test_completed_sale_and_lines_are_immutable_and_cannot_checkout_twice(self):
        sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        complete_sale(
            sale=sale,
            completed_by=self.user,
            amount_paid=Decimal("35.00"),
            payment_method="Cash",
        )
        sale.refresh_from_db()
        with self.assertRaises(ValueError):
            sale.notes = "Modify sale"
            sale.save()
        line = SaleLine.objects.get(sale=sale)
        with self.assertRaises(ValueError):
            line.delete()
        with self.assertRaises(ValidationError):
            complete_sale(
                sale=sale,
                completed_by=self.user,
                amount_paid=Decimal("35"),
                payment_method="Cash",
            )
        self.assertEqual(
            StockMovement.objects.filter(
                branch=self.branch,
                movement_type=StockMovement.MovementType.SALE,
            ).count(),
            1,
        )

    def test_draft_can_update_customer_and_replace_items(self):
        sale = create_draft_sale(
            branch=self.branch,
            items=[self.item],
            created_by=self.user,
        )
        sale = update_draft_sale(
            sale=sale,
            customer=self.customer,
            update_customer=True,
            items=[
                {
                    **self.item,
                    "quantity": Decimal("2"),
                    "unit_price": Decimal("10.00"),
                }
            ],
        )
        self.assertEqual(sale.customer_id, self.customer.pk)
        self.assertEqual(sale.total, Decimal("19.00"))
        self.assertEqual(sale.items.count(), 1)
        self.assertFalse(CustomerLedgerEntry.objects.filter(customer=self.customer).exists())

    def test_partial_return_restores_stock_and_posts_store_credit(self):
        sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        complete_sale(
            sale=sale,
            completed_by=self.user,
            amount_paid=Decimal("20.00"),
            payment_method="Cash",
        )
        line = SaleLine.objects.get(sale=sale)

        sales_return = create_sales_return(
            branch=self.branch,
            sale=sale,
            items=[{"sale_line": line, "quantity": Decimal("1")}],
            disposition=SalesReturn.Disposition.STORE_CREDIT,
            created_by=self.user,
        )

        self.assertEqual(sales_return.total, Decimal("11.67"))
        self.assertEqual(sales_return.items.get().base_quantity, Decimal("1"))
        self.assertEqual(
            StockBalance.objects.get(branch=self.branch, product=self.product).on_hand,
            Decimal("8"),
        )
        self.assertEqual(
            customer_branch_balance(customer=self.customer, branch=self.branch),
            Decimal("3.33"),
        )

    def test_cash_refund_is_audited_without_changing_customer_balance(self):
        sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        complete_sale(
            sale=sale,
            completed_by=self.user,
            amount_paid=Decimal("35.00"),
            payment_method="Cash",
        )
        line = SaleLine.objects.get(sale=sale)

        sales_return = create_sales_return(
            branch=self.branch,
            sale=sale,
            items=[{"sale_line": line, "quantity": Decimal("1")}],
            disposition=SalesReturn.Disposition.CASH_REFUND,
            created_by=self.user,
        )

        self.assertEqual(sales_return.disposition, SalesReturn.Disposition.CASH_REFUND)
        self.assertEqual(
            customer_branch_balance(customer=self.customer, branch=self.branch),
            Decimal("0.00"),
        )
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(
                reference=sales_return.return_number,
                entry_type=CustomerLedgerEntry.EntryType.ADJUSTMENT_DEBIT,
            ).get().amount,
            sales_return.total,
        )

    def test_return_cannot_exceed_original_quantity_or_customer_debt(self):
        sale = create_draft_sale(
            branch=self.branch,
            customer=self.customer,
            items=[self.item],
            created_by=self.user,
        )
        complete_sale(
            sale=sale,
            completed_by=self.user,
            amount_paid=Decimal("20.00"),
            payment_method="Cash",
        )
        line = SaleLine.objects.get(sale=sale)
        with self.assertRaises(ValidationError):
            create_sales_return(
                branch=self.branch,
                sale=sale,
                items=[{"sale_line": line, "quantity": Decimal("2")}],
                disposition=SalesReturn.Disposition.DEBT_REDUCTION,
                created_by=self.user,
            )
        self.assertFalse(SalesReturn.objects.filter(sale=sale).exists())
        self.assertEqual(
            StockBalance.objects.get(branch=self.branch, product=self.product).on_hand,
            Decimal("7"),
        )

    def test_sale_quantity_in_verified_alternate_unit_uses_base_stock(self):
        kilogram = Unit.objects.create(
            organization=self.organization,
            name="Kilogram",
            symbol="kg",
            dimension=Unit.Dimension.MASS,
            decimal_places=3,
            canonical_factor=Decimal("1000"),
        )
        gram = Unit.objects.create(
            organization=self.organization,
            name="Gram",
            symbol="g",
            dimension=Unit.Dimension.MASS,
            decimal_places=0,
            canonical_factor=Decimal("1"),
        )
        product = Product.objects.create(
            organization=self.organization,
            category=self.product.category,
            base_unit=kilogram,
            name="Converted Product",
            sku="SALE-CONVERTED",
            purchase_price=Decimal("800.00"),
            selling_price=Decimal("1000.00"),
            allow_fractional_quantity=True,
        )
        from apps.inventory.services import record_stock_movement

        record_stock_movement(
            branch=self.branch,
            product=product,
            movement_type=StockMovement.MovementType.OPENING_STOCK,
            quantity=Decimal("2"),
            reason="Prepare converted sale",
            created_by=self.user,
        )
        sale = create_draft_sale(
            branch=self.branch,
            items=[
                {
                    "product": product,
                    "transaction_unit": gram,
                    "quantity": Decimal("500"),
                    "unit_price": Decimal("1.00"),
                }
            ],
            created_by=self.user,
        )
        line = sale.items.get()
        self.assertEqual(line.base_quantity, Decimal("0.500000"))
        self.assertEqual(line.unit_to_base_factor, Decimal("0.001000000000"))
        complete_sale(
            sale=sale,
            completed_by=self.user,
            amount_paid=Decimal("500.00"),
            payment_method="Cash",
        )
        self.assertEqual(
            StockBalance.objects.get(branch=self.branch, product=product).on_hand,
            Decimal("1.500000"),
        )


class BranchSaleApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Sales API Shop",
            slug="sales-api-shop",
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
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="POS Customer",
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
            name="POS Category",
        )
        self.product = Product.objects.create(
            organization=self.organization,
            category=category,
            base_unit=unit,
            name="POS Tool",
            sku="POS-001",
            purchase_price=Decimal("5.00"),
            selling_price=Decimal("20.00"),
        )
        self.user = get_user_model().objects.create_user(
            username="sales-api-cashier",
            password="a-strong-test-password",
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=Group.objects.get(name=Role.CASHIER),
        )
        from apps.inventory.services import record_stock_movement

        record_stock_movement(
            branch=self.branch,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING_STOCK,
            quantity=Decimal("5"),
            reason="Prepare POS API stock",
            created_by=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_cashier_can_create_edit_and_checkout_customer_sale(self):
        root = f"/api/sales/branches/{self.branch.pk}/"
        created = self.client.post(
            root,
            {
                "customer": self.customer.pk,
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": "2",
                        "unit_price": "18.00",
                        "discount_amount": "1.00",
                        "tax_amount": "2.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], Sale.Status.DRAFT)
        self.assertEqual(created.data["total"], "37.00")

        sale_id = created.data["id"]
        patched = self.client.patch(
            f"{root}{sale_id}/",
            {"notes": "POS draft"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)

        completed = self.client.post(
            f"{root}{sale_id}/checkout/",
            {
                "amount_paid": "40.00",
                "payment_method": "Cash",
                "payment_reference": "POS-API-1",
            },
            format="json",
        )
        self.assertEqual(completed.status_code, 200, completed.data)
        self.assertEqual(completed.data["status"], Sale.Status.COMPLETED)
        self.assertEqual(completed.data["balance_due"], "0.00")
        self.assertEqual(completed.data["change_due"], "0.00")
        self.assertEqual(completed.data["customer_advance_amount"], "3.00")
        listing = self.client.get(root, {"status": "completed", "search": "POS"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 1)

    def test_walkin_checkout_requires_full_payment(self):
        root = f"/api/sales/branches/{self.branch.pk}/"
        created = self.client.post(
            root,
            {
                "items": [
                    {
                        "product": self.product.pk,
                        "quantity": "1",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        incomplete = self.client.post(
            f"{root}{created.data['id']}/checkout/",
            {"amount_paid": "1.00"},
            format="json",
        )
        self.assertEqual(incomplete.status_code, 400, incomplete.data)
        complete = self.client.post(
            f"{root}{created.data['id']}/checkout/",
            {"amount_paid": "20.00", "payment_method": "Cash"},
            format="json",
        )
        self.assertEqual(complete.status_code, 200, complete.data)

    def test_sales_api_requires_membership_in_requested_branch(self):
        response = self.client.get(
            f"/api/sales/branches/{self.other_branch.pk}/"
        )
        self.assertEqual(response.status_code, 403)

    def test_branch_options_only_lists_sales_accessible_branches(self):
        response = self.client.get("/api/sales/branches/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            [
                {
                    "id": self.branch.pk,
                    "name": self.branch.name,
                    "organization": self.organization.name,
                }
            ],
        )
