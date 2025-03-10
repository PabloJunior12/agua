from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from .models import Year, Category, Zona, Calle, Reading, Invoice, Customer, Company, InvoicePayment, Service
from .utils import next_month_date
from django.db import transaction

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
        instance.address = validated_data.get("address", instance.address)

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
        
        customer = data.get('customer', self.instance.customer if self.instance else None)
        reading_date = data.get('reading_date', self.instance.reading_date if self.instance else None)
        current_reading = data.get('current_reading', self.instance.current_reading if self.instance else None)

        if not customer or not reading_date:
            return data

        # 1) Evitar lecturas duplicadas en el mismo mes y cliente
        qs = Reading.objects.filter(
            customer=customer,
            reading_date__year=reading_date.year,
            reading_date__month=reading_date.month
        )
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe una lectura registrada para este cliente en el mismo mes."
            )

        # 2) Evitar registrar un mes anterior si ya existe uno posterior
        future_qs = Reading.objects.filter(
            customer=customer,
            reading_date__gt=reading_date
        )
        if future_qs.exists():
            raise serializers.ValidationError(
                "No se puede registrar una lectura en un mes anterior a una ya existente."
            )

        # 3) Verificar que no se salten meses.
        #    Obtenemos la última lectura (mes anterior) y comprobamos que la nueva sea el mes siguiente.
        last_reading = Reading.objects.filter(
            customer=customer,
            reading_date__lt=reading_date
        ).order_by('-reading_date').first()

        if last_reading:
            # Calculamos la fecha del "próximo mes" a partir de la última lectura
            expected_next_date = next_month_date(last_reading.reading_date)

            # Comparamos solo año y mes (en caso de que no uses día=1):
            if (reading_date.year != expected_next_date.year) or (reading_date.month != expected_next_date.month):
                raise serializers.ValidationError(
                    "Debes registrar el mes consecutivo. El siguiente mes esperado es: "
                    f"{expected_next_date.strftime('%B %Y')}"
                )

            # (Opcional) Verificar que current_reading >= last_reading.current_reading
            if current_reading < last_reading.current_reading:
                raise serializers.ValidationError(
                    "La lectura actual no puede ser menor que la última lectura registrada."
                )
        else:
            # Si no hay lecturas previas, esta es la primera: no hay mes anterior que validar.
            pass

        return data

class InvoiceSerializer(serializers.ModelSerializer):

    payments = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField()
        ), write_only=True
    )

    class Meta:
        model = Invoice
        fields = '__all__'

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

class ServiceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Service
        fields = '__all__'