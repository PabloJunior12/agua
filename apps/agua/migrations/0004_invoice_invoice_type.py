# Generated by Django 5.1.3 on 2025-03-20 21:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agua', '0003_servicepayment'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='invoice_type',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
    ]
