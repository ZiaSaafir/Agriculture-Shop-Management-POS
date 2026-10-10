import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0003_backfill_sale_base_units"),
    ]

    operations = [
        migrations.AlterField(
            model_name="saleline",
            name="base_quantity",
            field=models.DecimalField(
                decimal_places=6,
                max_digits=18,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.000001"))
                ],
            ),
        ),
        migrations.AlterField(
            model_name="saleline",
            name="transaction_unit",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sale_lines",
                to="products.unit",
            ),
        ),
    ]
