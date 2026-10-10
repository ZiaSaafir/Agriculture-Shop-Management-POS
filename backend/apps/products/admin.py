from django.contrib import admin

from .models import Brand, Product, ProductCategory, ProductVariety, Unit


class OrganizationOwnedAdmin(admin.ModelAdmin):
    list_filter = ("organization", "is_active")
    search_fields = ("name",)


@admin.register(Unit)
class UnitAdmin(OrganizationOwnedAdmin):
    list_display = (
        "name",
        "symbol",
        "dimension",
        "organization",
        "decimal_places",
        "canonical_factor",
        "is_active",
    )
    list_filter = ("organization", "dimension", "is_active")


@admin.register(ProductCategory)
class ProductCategoryAdmin(OrganizationOwnedAdmin):
    list_display = ("name", "organization", "is_active")


@admin.register(Brand)
class BrandAdmin(OrganizationOwnedAdmin):
    list_display = ("name", "organization", "is_active")
    search_fields = ("name", "organization__name")


@admin.register(ProductVariety)
class ProductVarietyAdmin(OrganizationOwnedAdmin):
    list_display = ("name", "category", "organization", "is_active")
    list_filter = ("organization", "category", "is_active")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "base_unit",
        "selling_price",
        "allow_fractional_quantity",
        "is_active",
    )
    list_filter = ("organization", "category", "brand", "is_active")
    search_fields = ("name", "sku", "barcode", "brand__name", "variety__name")
    autocomplete_fields = ("organization", "category", "brand", "variety", "base_unit")
    readonly_fields = ("created_at", "updated_at")
