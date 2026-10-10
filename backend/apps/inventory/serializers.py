from decimal import Decimal

from rest_framework import serializers

from apps.products.models import Product

from .models import StockMovement


class ProductStockSerializer(serializers.ModelSerializer):
    base_unit = serializers.IntegerField(source="base_unit_id", read_only=True)
    unit = serializers.CharField(source="base_unit.symbol", read_only=True)
    quantity_decimal_places = serializers.IntegerField(
        source="base_unit.decimal_places",
        read_only=True,
    )
    selling_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    low_stock_threshold = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
    )
    on_hand = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        read_only=True,
    )
    fractional_quantity = serializers.BooleanField(
        source="allow_fractional_quantity",
        read_only=True,
    )
    available_units = serializers.SerializerMethodField()

    def get_available_units(self, product):
        units = [
            unit
            for unit in product.organization.units.all()
            if unit.is_active
        ]
        result = []
        base_unit = product.base_unit
        for unit in units:
            if unit.pk == base_unit.pk:
                multiplier = Decimal("1")
            elif (
                unit.dimension != base_unit.dimension
                or unit.canonical_factor is None
                or base_unit.canonical_factor is None
            ):
                continue
            else:
                multiplier = unit.canonical_factor / base_unit.canonical_factor
            result.append(
                {
                    "id": unit.pk,
                    "name": unit.name,
                    "symbol": unit.symbol,
                    "decimal_places": unit.decimal_places,
                    "base_multiplier": format(multiplier, "f"),
                }
            )
        return result

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "sku",
            "unit",
            "base_unit",
            "quantity_decimal_places",
            "selling_price",
            "low_stock_threshold",
            "on_hand",
            "fractional_quantity",
            "available_units",
            "is_active",
        )


class StockMovementSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "branch",
            "product",
            "product_name_snapshot",
            "unit_symbol_snapshot",
            "movement_type",
            "quantity",
            "reason",
            "reference",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class ManualStockMovementInputSerializer(serializers.Serializer):
    MANUAL_TYPES = (
        StockMovement.MovementType.OPENING_STOCK,
        StockMovement.MovementType.DAMAGE,
        StockMovement.MovementType.LOSS,
        StockMovement.MovementType.ADJUSTMENT_IN,
        StockMovement.MovementType.ADJUSTMENT_OUT,
    )

    product = serializers.IntegerField(min_value=1)
    movement_type = serializers.ChoiceField(choices=MANUAL_TYPES)
    quantity = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        min_value=Decimal("0.000001"),
    )
    reason = serializers.CharField(max_length=500, trim_whitespace=True)
    reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_reason(self, value):
        if not value:
            raise serializers.ValidationError("A reason is required.")
        return value

    def validate_product(self, product_id):
        branch = self.context["branch"]
        try:
            return Product.objects.get(
                pk=product_id,
                organization_id=branch.organization_id,
            )
        except Product.DoesNotExist as exc:
            raise serializers.ValidationError(
                "Choose a product from this branch's organization."
            ) from exc
