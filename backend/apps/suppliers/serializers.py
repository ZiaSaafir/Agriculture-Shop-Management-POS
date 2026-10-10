from rest_framework import serializers

from .models import Supplier, SupplierLedgerEntry


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            "id",
            "name",
            "phone",
            "address",
            "account_reference",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Supplier name is required.")
        return value


class SupplierLedgerEntrySerializer(serializers.ModelSerializer):
    signed_amount = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        read_only=True,
    )
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = SupplierLedgerEntry
        fields = (
            "id",
            "branch",
            "supplier",
            "supplier_name_snapshot",
            "entry_type",
            "amount",
            "signed_amount",
            "reason",
            "reference",
            "created_by",
            "created_at",
        )
        read_only_fields = fields
