# Generated by Django 5.1.3 on 2025-03-26 00:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agua', '0008_alter_invoicereading_invoice_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentMethodType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.BooleanField(default=True)),
                ('description', models.CharField(max_length=200)),
            ],
            options={
                'verbose_name': 'Tipos de metodos de pagos',
                'verbose_name_plural': 'Tipo de metodo de pago',
            },
        ),
    ]
