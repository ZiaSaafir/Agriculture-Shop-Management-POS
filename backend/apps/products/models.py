from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.organizations.models import Organization


class Unit(models.Model):
    class Dimension(models.TextChoices):
        MASS = "mass", _("Mass")
        VOLUME = "volume", _("Volume")
        COUNT = "count", _("Count")
        PACKAGING = "packaging", _("Packaging")
        OTHER = "other", _("Other")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="units",
    )
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=24)
    dimension = models.CharField(max_length=16, choices=Dimension.choices)
    decimal_places = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(0)],
        help_text="Maximum quantity precision to display; 0 through 6.",
    )
    canonical_factor = models.DecimalField(
        max_digits=24,
        decimal_places=12,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=(
            "Positive conversion factor to this dimension's organization-wide "
            "canonical unit. Leave blank when conversion is not verified."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="unique_unit_name_per_organization",
            ),
            models.UniqueConstraint(
                fields=("organization", "symbol"),
                name="unique_unit_symbol_per_organization",
            ),
            models.CheckConstraint(
                condition=Q(decimal_places__lte=6),
                name="unit_decimal_places_at_most_six",
            ),
            models.CheckConstraint(
                condition=Q(canonical_factor__isnull=True)
                | Q(canonical_factor__gt=0),
                name="unit_canonical_factor_positive",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class ProductCategory(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="product_categories",
    )
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name_plural = "product categories"
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="unique_product_category_per_organization",
            ),
        ]

    def __str__(self):
        return self.name


class Brand(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="product_brands",
    )
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = "company / brand"
        verbose_name_plural = "companies / brands"
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="unique_brand_per_organization",
            ),
        ]

    def __str__(self):
        return self.name


class ProductVariety(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="product_varieties",
    )
    name = models.CharField(max_length=160)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="varieties",
        null=True,
        blank=True,
        help_text="Optional category scope for this variety.",
    )
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="unique_variety_per_organization",
            ),
        ]

    def clean(self):
        super().clean()
        category_organization_id = (
            ProductCategory.objects.filter(pk=self.category_id)
            .values_list("organization_id", flat=True)
            .first()
            if self.category_id
            else None
        )
        if (
            category_organization_id is not None
            and self.organization_id is not None
            and category_organization_id != self.organization_id
        ):
            raise ValidationError(
                {"category": "The category must belong to this organization."}
            )

    def __str__(self):
        return self.name


class Product(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="products",
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    variety = models.ForeignKey(
        ProductVariety,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    base_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64)
    barcode = models.CharField(max_length=64, blank=True)
    description = models.TextField(blank=True)
    purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    low_stock_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
    )
    allow_fractional_quantity = models.BooleanField(
        default=False,
        help_text="Allow selling this product in fractional quantities.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "sku"),
                name="unique_product_sku_per_organization",
            ),
            models.UniqueConstraint(
                fields=("organization", "barcode"),
                condition=~Q(barcode=""),
                name="unique_product_barcode_per_organization",
            ),
            models.CheckConstraint(
                condition=Q(purchase_price__gte=0),
                name="product_purchase_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(selling_price__gte=0),
                name="product_selling_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(low_stock_threshold__gte=0),
                name="product_low_stock_threshold_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "is_active", "name"),
                name="product_org_active_name_idx",
            ),
        ]

    def clean(self):
        super().clean()
        related_models = {
            "category": ProductCategory,
            "brand": Brand,
            "variety": ProductVariety,
            "base_unit": Unit,
        }
        errors = {}
        if self.pk:
            previous_base_unit_id = (
                type(self).objects.filter(pk=self.pk)
                .values_list("base_unit_id", flat=True)
                .first()
            )
            if (
                previous_base_unit_id is not None
                and previous_base_unit_id != self.base_unit_id
            ):
                errors["base_unit"] = (
                    "A product's base unit cannot change after creation. "
                    "Create a replacement product and adjust stock instead."
                )
        if self.organization_id:
            for field, model in related_models.items():
                related_id = getattr(self, f"{field}_id")
                if not related_id:
                    continue
                related_organization_id = (
                    model.objects.filter(pk=related_id)
                    .values_list("organization_id", flat=True)
                    .first()
                )
                if (
                    related_organization_id is not None
                    and related_organization_id != self.organization_id
                ):
                    errors[field] = (
                        "This record must belong to the product's organization."
                    )
        if (
            self.variety_id
            and self.category_id
        ):
            variety_category_id = (
                ProductVariety.objects.filter(pk=self.variety_id)
                .values_list("category_id", flat=True)
                .first()
            )
            if variety_category_id and variety_category_id != self.category_id:
                errors["variety"] = "The variety is scoped to a different category."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.sku})"
