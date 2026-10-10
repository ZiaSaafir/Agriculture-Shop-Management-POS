from decimal import Decimal

from django.db import migrations


VERIFIED_FACTORS = {
    "mass": {
        "mg": Decimal("0.001"),
        "milligram": Decimal("0.001"),
        "milligrams": Decimal("0.001"),
        "g": Decimal("1"),
        "gram": Decimal("1"),
        "grams": Decimal("1"),
        "kg": Decimal("1000"),
        "kilogram": Decimal("1000"),
        "kilograms": Decimal("1000"),
        "t": Decimal("1000000"),
        "tonne": Decimal("1000000"),
        "tonnes": Decimal("1000000"),
    },
    "volume": {
        "ml": Decimal("1"),
        "millilitre": Decimal("1"),
        "millilitres": Decimal("1"),
        "milliliter": Decimal("1"),
        "milliliters": Decimal("1"),
        "l": Decimal("1000"),
        "litre": Decimal("1000"),
        "litres": Decimal("1000"),
        "liter": Decimal("1000"),
        "liters": Decimal("1000"),
    },
    "count": {
        "each": Decimal("1"),
        "ea": Decimal("1"),
        "pc": Decimal("1"),
        "pcs": Decimal("1"),
        "piece": Decimal("1"),
        "pieces": Decimal("1"),
        "pair": Decimal("2"),
        "dozen": Decimal("12"),
    },
}


def set_verified_factors(apps, schema_editor):
    Unit = apps.get_model("products", "Unit")
    database = schema_editor.connection.alias
    for unit in Unit.objects.using(database).filter(canonical_factor__isnull=True):
        candidates = (unit.symbol.strip().casefold(), unit.name.strip().casefold())
        factor = next(
            (
                VERIFIED_FACTORS.get(unit.dimension, {}).get(candidate)
                for candidate in candidates
                if VERIFIED_FACTORS.get(unit.dimension, {}).get(candidate) is not None
            ),
            None,
        )
        if factor is not None:
            Unit.objects.using(database).filter(pk=unit.pk).update(
                canonical_factor=factor
            )


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_product_allow_fractional_quantity_and_more"),
    ]

    operations = [
        migrations.RunPython(set_verified_factors, migrations.RunPython.noop),
    ]
