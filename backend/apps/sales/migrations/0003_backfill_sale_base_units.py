from django.db import migrations, models
from decimal import Decimal


def backfill_sale_line_units(apps, schema_editor):
    SaleLine = apps.get_model("sales", "SaleLine")
    database = schema_editor.connection.alias
    for line in SaleLine.objects.using(database).select_related("product").iterator():
        SaleLine.objects.using(database).filter(pk=line.pk).update(
            base_quantity=line.quantity,
            transaction_unit_id=line.product.base_unit_id,
            unit_to_base_factor=Decimal("1"),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_salesreturn_salesreturnline_saleline_base_quantity_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_sale_line_units, migrations.RunPython.noop),
    ]
