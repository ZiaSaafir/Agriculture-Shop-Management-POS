from decimal import Decimal

from rest_framework import serializers

from apps.products.models import Product
from apps.suppliers.models import Supplier

from .models import (
    Purchase,
    PurchaseLine,
    PurchaseReturn,
    PurchaseReturnLine,
    SupplierPayment,
    SupplierPaymentAllocation,
)


class PurchaseLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        min_value=Decimal("0.000001"),
    )
    unit_cost = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    discount_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )
    tax_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )

    def validate_product(self, product):
        branch = self.context["branch"]
        if (
            product.organization_id != branch.organization_id
            or not product.is_active
            or not product.base_unit.is_active
        ):
            raise serializers.ValidationError(
                "Choose an active product from this branch's organization."
            )
        return product


class PurchaseItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PurchaseLine
        fields = (
            "id",
            "product",
            "product_name_snapshot",
            "sku_snapshot",
            "unit_symbol_snapshot",
            "quantity",
            "unit_cost",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total",
        )
        read_only_fields = fields


class PurchaseSerializer(serializers.ModelSerializer):
    purchase_number = serializers.CharField(read_only=True)
    supplier = serializers.IntegerField(source="supplier_id", read_only=True)
    branch = serializers.IntegerField(source="branch_id", read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    posted_by = serializers.CharField(
        source="posted_by.username",
        read_only=True,
        allow_null=True,
    )
    items = PurchaseItemSerializer(many=True, read_only=True)

    class Meta:
        model = Purchase
        fields = (
            "id",
            "purchase_number",
            "branch",
            "supplier",
            "supplier_name_snapshot",
            "supplier_invoice_number",
            "purchase_date",
            "notes",
            "status",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "items",
            "created_by",
            "posted_by",
            "posted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PurchaseDraftInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.none())
    supplier_invoice_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    purchase_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = PurchaseLineInputSerializer(many=True, min_length=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["supplier"].queryset = Supplier.objects.filter(
            organization_id=branch.organization_id,
            is_active=True,
        )


class PurchaseDraftPatchInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.none(),
        required=False,
    )
    supplier_invoice_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    purchase_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = PurchaseLineInputSerializer(many=True, min_length=1, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["supplier"].queryset = Supplier.objects.filter(
            organization_id=branch.organization_id,
            is_active=True,
        )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class SupplierPaymentAllocationInputSerializer(serializers.Serializer):
    purchase = serializers.PrimaryKeyRelatedField(queryset=Purchase.objects.all())
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate_purchase(self, purchase):
        branch = self.context["branch"]
        if (
            purchase.organization_id != branch.organization_id
            or purchase.branch_id != branch.pk
            or purchase.status != Purchase.Status.POSTED
        ):
            raise serializers.ValidationError(
                "Choose a posted invoice from this branch."
            )
        return purchase


class SupplierPaymentInputSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    payment_date = serializers.DateField(required=False)
    payment_method = serializers.CharField(
        max_length=40,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    allocations = SupplierPaymentAllocationInputSerializer(
        many=True,
        required=False,
        default=list,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["supplier"].queryset = Supplier.objects.filter(
            organization_id=branch.organization_id,
            is_active=True,
        )
        self.fields["allocations"].child.fields["purchase"].queryset = (
            Purchase.objects.filter(
                organization_id=branch.organization_id,
                branch=branch,
                status=Purchase.Status.POSTED,
            )
        )

    def validate_supplier(self, supplier):
        branch = self.context["branch"]
        if (
            supplier.organization_id != branch.organization_id
            or not supplier.is_active
        ):
            raise serializers.ValidationError(
                "Choose an active supplier from this branch's organization."
            )
        return supplier

    def validate(self, attrs):
        supplier = attrs.get("supplier")
        allocations = attrs.get("allocations", [])
        if supplier is not None and any(
            allocation["purchase"].supplier_id != supplier.pk
            for allocation in allocations
        ):
            raise serializers.ValidationError(
                {"allocations": "Invoices must belong to the selected supplier."}
            )
        purchase_ids = [item["purchase"].pk for item in allocations]
        if len(purchase_ids) != len(set(purchase_ids)):
            raise serializers.ValidationError(
                {"allocations": "Each purchase invoice may be allocated only once."}
            )
        return attrs


class SupplierPaymentAllocationSerializer(serializers.ModelSerializer):
    purchase = serializers.IntegerField(source="purchase_id", read_only=True)

    class Meta:
        model = SupplierPaymentAllocation
        fields = ("purchase", "purchase_number_snapshot", "amount")
        read_only_fields = fields


class SupplierPaymentSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(read_only=True)
    supplier = serializers.IntegerField(source="supplier_id", read_only=True)
    branch = serializers.IntegerField(source="branch_id", read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    allocations = SupplierPaymentAllocationSerializer(many=True, read_only=True)
    allocated_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    unallocated_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = SupplierPayment
        fields = (
            "id",
            "payment_number",
            "branch",
            "supplier",
            "supplier_name_snapshot",
            "amount",
            "allocated_amount",
            "unallocated_amount",
            "payment_date",
            "payment_method",
            "reference",
            "notes",
            "allocations",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class SupplierInvoiceBalanceSerializer(serializers.Serializer):
    purchase_id = serializers.IntegerField(source="purchase.id")
    purchase_number = serializers.CharField(source="purchase.purchase_number")
    supplier_invoice_number = serializers.CharField(
        source="purchase.supplier_invoice_number"
    )
    supplier_name = serializers.CharField(source="purchase.supplier_name_snapshot")
    purchase_date = serializers.DateField(source="purchase.purchase_date")
    total = serializers.DecimalField(
        source="purchase.total",
        max_digits=16,
        decimal_places=2,
    )
    returned_amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    net_total = serializers.DecimalField(max_digits=16, decimal_places=2)
    paid_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    outstanding_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class PurchaseReturnLineInputSerializer(serializers.Serializer):
    purchase_line = serializers.PrimaryKeyRelatedField(
        queryset=PurchaseLine.objects.all(),
    )
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        min_value=Decimal("0.000001"),
    )
    credit_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class PurchaseReturnInputSerializer(serializers.Serializer):
    purchase = serializers.PrimaryKeyRelatedField(queryset=Purchase.objects.all())
    supplier_credit_note_reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    return_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = PurchaseReturnLineInputSerializer(many=True, min_length=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["purchase"].queryset = Purchase.objects.filter(
            organization_id=branch.organization_id,
            branch=branch,
            status=Purchase.Status.POSTED,
        )
        self.fields["items"].child.fields["purchase_line"].queryset = (
            PurchaseLine.objects.filter(
                purchase__organization_id=branch.organization_id,
                purchase__branch=branch,
                purchase__status=Purchase.Status.POSTED,
            )
        )

    def validate(self, attrs):
        purchase = attrs["purchase"]
        if any(
            item["purchase_line"].purchase_id != purchase.pk
            for item in attrs["items"]
        ):
            raise serializers.ValidationError(
                {"items": "Return lines must belong to the selected purchase."}
            )
        line_ids = [item["purchase_line"].pk for item in attrs["items"]]
        if len(line_ids) != len(set(line_ids)):
            raise serializers.ValidationError(
                {"items": "Each purchase line may appear only once per return."}
            )
        return attrs


class PurchaseReturnPatchInputSerializer(serializers.Serializer):
    supplier_credit_note_reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    return_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = PurchaseReturnLineInputSerializer(many=True, min_length=1, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["items"].child.fields["purchase_line"].queryset = (
            PurchaseLine.objects.filter(
                purchase__organization_id=branch.organization_id,
                purchase__branch=branch,
                purchase__status=Purchase.Status.POSTED,
            )
        )

    def validate(self, attrs):
        purchase = self.context["purchase"]
        if any(
            item["purchase_line"].purchase_id != purchase.pk
            for item in attrs.get("items", [])
        ):
            raise serializers.ValidationError(
                {"items": "Return lines must belong to the original purchase."}
            )
        line_ids = [
            item["purchase_line"].pk for item in attrs.get("items", [])
        ]
        if len(line_ids) != len(set(line_ids)):
            raise serializers.ValidationError(
                {"items": "Each purchase line may appear only once per return."}
            )
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class PurchaseReturnItemSerializer(serializers.ModelSerializer):
    purchase_line = serializers.IntegerField(source="purchase_line_id", read_only=True)

    class Meta:
        model = PurchaseReturnLine
        fields = (
            "id",
            "purchase_line",
            "product_name_snapshot",
            "sku_snapshot",
            "unit_symbol_snapshot",
            "quantity",
            "credit_amount",
        )
        read_only_fields = fields


class PurchaseReturnSerializer(serializers.ModelSerializer):
    return_number = serializers.CharField(read_only=True)
    purchase = serializers.IntegerField(source="purchase_id", read_only=True)
    branch = serializers.IntegerField(source="branch_id", read_only=True)
    supplier = serializers.IntegerField(source="supplier_id", read_only=True)
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    posted_by = serializers.CharField(
        source="posted_by.username",
        read_only=True,
        allow_null=True,
    )
    items = PurchaseReturnItemSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = (
            "id",
            "return_number",
            "purchase",
            "branch",
            "supplier",
            "supplier_name_snapshot",
            "supplier_credit_note_reference",
            "return_date",
            "notes",
            "status",
            "credit_total",
            "items",
            "created_by",
            "posted_by",
            "posted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
