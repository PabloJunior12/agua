# Generated by Django 5.1.3 on 2025-02-22 18:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agua', '0009_remove_invoicepayment_amount_paid'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoicepayment',
            name='amount_paid',
            field=models.DecimalField(decimal_places=2, default=1, max_digits=10, verbose_name='Amount Paid'),
            preserve_default=False,
        ),
    ]
