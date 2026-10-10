from rest_framework import serializers

from .models import Brand, Product, ProductCategory, ProductVariety, Unit


class OrganizationOwnedSerializer(serializers.ModelSerializer):
    class Meta:
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class UnitSerializer(OrganizationOwnedSerializer):
    class Meta(OrganizationOwnedSerializer.Meta):
        model = Unit


class ProductCategorySerializer(OrganizationOwnedSerializer):
    class Meta(OrganizationOwnedSerializer.Meta):
        model = ProductCategory


class BrandSerializer(OrganizationOwnedSerializer):
    class Meta(OrganizationOwnedSerializer.Meta):
        model = Brand


class ProductVarietySerializer(OrganizationOwnedSerializer):
    class Meta(OrganizationOwnedSerializer.Meta):
        model = ProductVariety

    def validate(self, attrs):
        attrs = super().validate(attrs)
        organization = attrs.get(
            "organization",
            getattr(self.instance, "organization", None),
        )
        category = attrs.get("category", getattr(self.instance, "category", None))
        if category and organization and category.organization_id != organization.id:
            raise serializers.ValidationError(
                {"category": "The category must belong to this organization."}
            )
        return attrs


class ProductSerializer(OrganizationOwnedSerializer):
    class Meta(OrganizationOwnedSerializer.Meta):
        model = Product

    def validate(self, attrs):
        attrs = super().validate(attrs)
        organization = attrs.get(
            "organization",
            getattr(self.instance, "organization", None),
        )
        relations = {
            "category": attrs.get(
                "category",
                getattr(self.instance, "category", None),
            ),
            "brand": attrs.get("brand", getattr(self.instance, "brand", None)),
            "variety": attrs.get(
                "variety",
                getattr(self.instance, "variety", None),
            ),
            "base_unit": attrs.get(
                "base_unit",
                getattr(self.instance, "base_unit", None),
            ),
        }

        if organization:
            for field, related in relations.items():
                if related and related.organization_id != organization.id:
                    raise serializers.ValidationError(
                        {
                            field: (
                                "This record must belong to the product's "
                                "organization."
                            )
                        }
                    )

        variety = relations["variety"]
        category = relations["category"]
        if (
            variety
            and category
            and variety.category_id
            and variety.category_id != category.id
        ):
            raise serializers.ValidationError(
                {"variety": "The variety is scoped to a different category."}
            )
        return attrs


class ProductApiSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "organization",
            "category",
            "brand",
            "variety",
            "base_unit",
            "name",
            "sku",
            "barcode",
            "description",
            "purchase_price",
            "selling_price",
            "low_stock_threshold",
            "allow_fractional_quantity",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organization = self.context["organization"]
        for field, model in (
            ("category", ProductCategory),
            ("brand", Brand),
            ("variety", ProductVariety),
            ("base_unit", Unit),
        ):
            self.fields[field].queryset = model.objects.filter(
                organization=organization,
                is_active=True,
            )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        variety = attrs.get("variety", getattr(self.instance, "variety", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        if (
            variety
            and variety.category_id
            and category
            and variety.category_id != category.pk
        ):
            raise serializers.ValidationError(
                {"variety": "Choose a variety for the selected category."}
            )
        return attrs

    def create(self, validated_data):
        organization = validated_data.pop(
            "organization",
            self.context["organization"],
        )
        product = Product(organization=organization, **validated_data)
        product.full_clean()
        product.save(force_insert=True)
        return product

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance
