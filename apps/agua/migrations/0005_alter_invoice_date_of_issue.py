# Generated by Django 5.1.3 on 2025-02-22 18:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agua', '0004_invoice_customer_invoice_date_of_issue_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='date_of_issue',
            field=models.DateField(auto_now=True),
        ),
    ]
