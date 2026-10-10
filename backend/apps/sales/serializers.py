from decimal import Decimal

from rest_framework import serializers

from apps.customers.models import Customer
from apps.products.models import Product, Unit

from .models import Sale, SaleLine, SalesReturn, SalesReturnLine


class SaleLineInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    transaction_unit = serializers.PrimaryKeyRelatedField(
        queryset=Unit.objects.all(),
        required=False,
    )
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        min_value=Decimal("0.000001"),
    )
    unit_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
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

    def validate(self, attrs):
        product = attrs["product"]
        unit = attrs.get("transaction_unit", product.base_unit)
        if unit.organization_id != product.organization_id or not unit.is_active:
            raise serializers.ValidationError(
                {"transaction_unit": "Choose an active unit from this organization."}
            )
        if unit.pk != product.base_unit_id and (
            unit.dimension != product.base_unit.dimension
            or unit.canonical_factor is None
            or product.base_unit.canonical_factor is None
        ):
            raise serializers.ValidationError(
                {
                    "transaction_unit": (
                        "This unit has no verified conversion to the product's base unit."
                    )
                }
            )
        attrs["transaction_unit"] = unit
        return attrs


class SaleItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = SaleLine
        fields = (
            "id",
            "product",
            "product_name_snapshot",
            "sku_snapshot",
            "unit_symbol_snapshot",
            "quantity",
            "base_quantity",
            "transaction_unit",
            "unit_price",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total",
        )
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    sale_number = serializers.CharField(read_only=True)
    branch = serializers.IntegerField(source="branch_id", read_only=True)
    customer = serializers.IntegerField(
        source="customer_id",
        read_only=True,
        allow_null=True,
    )
    created_by = serializers.CharField(source="created_by.username", read_only=True)
    completed_by = serializers.CharField(
        source="completed_by.username",
        read_only=True,
        allow_null=True,
    )
    balance_due = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )
    change_due = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )
    customer_advance_amount = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )
    items = SaleItemSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    organization_name = serializers.CharField(
        source="branch.organization.name",
        read_only=True,
    )
    customer_phone = serializers.CharField(
        source="customer.phone",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Sale
        fields = (
            "id",
            "sale_number",
            "branch",
            "branch_name",
            "organization_name",
            "customer",
            "customer_phone",
            "customer_name_snapshot",
            "sale_date",
            "notes",
            "status",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "amount_paid",
            "balance_due",
            "change_due",
            "customer_advance_amount",
            "payment_method",
            "payment_reference",
            "items",
            "created_by",
            "completed_by",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SaleDraftInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True,
    )
    sale_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = SaleLineInputSerializer(many=True, min_length=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["customer"].queryset = Customer.objects.filter(
            organization_id=branch.organization_id,
            is_active=True,
        )


class SaleDraftPatchInputSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True,
    )
    sale_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = SaleLineInputSerializer(many=True, min_length=1, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        self.fields["customer"].queryset = Customer.objects.filter(
            organization_id=branch.organization_id,
            is_active=True,
        )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class SaleCheckoutInputSerializer(serializers.Serializer):
    amount_paid = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    payment_method = serializers.CharField(
        max_length=40,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    payment_reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )


class SalesReturnLineInputSerializer(serializers.Serializer):
    sale_line = serializers.PrimaryKeyRelatedField(queryset=SaleLine.objects.all())
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        min_value=Decimal("0.000001"),
    )


class SalesReturnInputSerializer(serializers.Serializer):
    disposition = serializers.ChoiceField(choices=SalesReturn.Disposition.choices)
    return_date = serializers.DateField(required=False)
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    items = SalesReturnLineInputSerializer(many=True, min_length=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.context["branch"]
        sale_id = self.context["sale_id"]
        self.fields["items"].child.fields["sale_line"].queryset = SaleLine.objects.filter(
            sale_id=sale_id,
            sale__branch=branch,
            sale__status=Sale.Status.COMPLETED,
        )


class SalesReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesReturnLine
        fields = (
            "id",
            "sale_line",
            "product",
            "product_name_snapshot",
            "sku_snapshot",
            "unit_symbol_snapshot",
            "quantity",
            "base_quantity",
            "credit_amount",
        )
        read_only_fields = fields


class SalesReturnSerializer(serializers.ModelSerializer):
    return_number = serializers.CharField(read_only=True)
    sale_number = serializers.CharField(source="sale.sale_number", read_only=True)
    items = SalesReturnLineSerializer(many=True, read_only=True)
    disposition_label = serializers.CharField(
        source="get_disposition_display",
        read_only=True,
    )
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = SalesReturn
        fields = (
            "id",
            "return_number",
            "sale",
            "sale_number",
            "disposition",
            "disposition_label",
            "return_date",
            "total",
            "notes",
            "created_by",
            "created_at",
            "items",
        )
        read_only_fields = fields
