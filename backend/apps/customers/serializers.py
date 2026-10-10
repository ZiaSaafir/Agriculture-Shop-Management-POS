from rest_framework import serializers

from .models import Customer, CustomerLedgerEntry


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "id",
            "name",
            "phone",
            "address",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Customer name is required.")
        return value


class CustomerLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerLedgerEntry
        fields = (
            "id",
            "branch",
            "customer",
            "customer_name_snapshot",
            "entry_type",
            "amount",
            "signed_amount",
            "reason",
            "reference",
            "created_by",
            "created_at",
        )
        read_only_fields = fields

    signed_amount = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        read_only=True,
    )
    created_by = serializers.CharField(source="created_by.username", read_only=True)
