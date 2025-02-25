from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from .models import Year, Category, Zona, Calle, Reading, Invoice, Customer, Company, InvoicePayment
import os

class CompanySerializer(serializers.ModelSerializer):

    class Meta:
        model = Company
        fields = '__all__'

    def update(self, instance, validated_data):
        # Verificar si hay un nuevo logo
        new_logo = validated_data.get("logo", None)
        if new_logo and instance.logo:
            # Eliminar el logo anterior del sistema de archivos
            old_logo_path = os.path.join(settings.MEDIA_ROOT, str(instance.logo))
            if os.path.exists(old_logo_path):
                os.remove(old_logo_path)

        instance.logo = new_logo if new_logo else instance.logo  # Mantener el anterior si no se envía nuevo
        instance.name = validated_data.get("name", instance.name)
        instance.ruc = validated_data.get("ruc", instance.ruc)
      
        instance.save()
        return instance

class YearSerializer(serializers.ModelSerializer):

    class Meta:
        
        model = Year
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        
        model = Category
        fields = '__all__'

class ZonaSerializer(serializers.ModelSerializer):

    class Meta:
        model = Zona
        fields = '__all__'

class CalleSerializer(serializers.ModelSerializer):
    
    class Meta:

        model = Calle
        fields = '__all__'

    def to_representation(self, instance):

        representation = super().to_representation(instance)

        if instance.zona:

            representation['zona'] = {
                'id': instance.zona.id,
                'name': instance.zona.name
            }

        return representation

class CustomerSerializer(serializers.ModelSerializer):

    class Meta:
        model = Customer
        fields = '__all__'
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.calle:
            data['calle'] = {
                'id': instance.calle.id,
                'name': instance.calle.name,
                'codigo' : instance.calle.codigo,
                'zona': {
                    'id': instance.calle.zona.id,
                    'name': instance.calle.zona.name
                }
            }
        return data

class ReadingSerializer(serializers.ModelSerializer):

    class Meta:
        model = Reading
        fields = '__all__'

    def validate(self, data):
        # Obtenemos el customer desde el request o de la instancia en caso de actualización
        customer = data.get('customer', self.instance.customer if self.instance else None)
        reading_date = data.get('reading_date', self.instance.reading_date if self.instance else None)

        # Validamos que no exista una lectura duplicada para el mismo mes y cliente
        if self.instance:  # Actualización
            existing_reading = Reading.objects.filter(
                customer=customer,
                reading_date__year=reading_date.year,
                reading_date__month=reading_date.month
            ).exclude(id=self.instance.id).exists()
        else:  # Creación
            existing_reading = Reading.objects.filter(
                customer=customer,
                reading_date__year=reading_date.year,
                reading_date__month=reading_date.month
            ).exists()

        if existing_reading:
            raise serializers.ValidationError("Ya existe una lectura para este mes y cliente.")

        return data

class InvoiceSerializer(serializers.ModelSerializer):

    payments = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField()
        ), write_only=True
    )

    class Meta:
        model = Invoice
        fields = ['id', 'customer', 'total_amount', 'date_of_issue', 'payments']

    def create(self, validated_data):
        payments_data = validated_data.pop('payments', [])  # Lista de pagos enviados
        invoice = Invoice.objects.create(**validated_data)  # Crear la factura sin asociar readings aún

        total_invoice_amount = 0  # Variable para calcular el total de la factura

        for payment in payments_data:
            reading_id = payment.get('reading')
            amount_paid = payment.get('amount_paid')

            reading = Reading.objects.get(id=reading_id)  # Obtener el Reading

            # Validar que no se pague más de lo que cuesta la lectura
            total_paid = sum(p.amount_paid for p in reading.payments.all()) + amount_paid
            if total_paid > reading.total_amount:
                raise serializers.ValidationError(f"El total pagado para el Reading {reading.id} excede el monto permitido.")

            # Crear InvoicePayment
            InvoicePayment.objects.create(
                invoice=invoice,
                reading=reading,
                amount_paid=amount_paid
            )

            total_invoice_amount += amount_paid  # Sumar el pago al total de la factura

            # Actualizar estado de la lectura
            reading.is_paid = total_paid >= reading.total_amount
            reading.save()

        # Guardar el total de la factura
        invoice.total_amount = total_invoice_amount
        invoice.save()

        return invoice

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.customer:
            data['customer'] = {
                'id': instance.customer.id,
                'full_name': instance.customer.full_name,
                'dni' : instance.customer.dni,
                'meter_code' : instance.customer.meter_code,
            }
        return data


