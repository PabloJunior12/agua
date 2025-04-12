from django.db import models
from apps.base.models import BaseModel
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta, date
from dateutil.relativedelta import relativedelta

class Company(models.Model):

    name = models.CharField(max_length=255, verbose_name="Nombre de la empresa")
    ruc = models.CharField(max_length=11, unique=True, verbose_name="RUC")
    address = models.CharField(max_length=255, verbose_name="Dirección", null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name="Teléfono", null=True, blank=True)
    email = models.EmailField(verbose_name="Correo electrónico", null=True, blank=True)
    logo = models.ImageField(upload_to="logos/", verbose_name="Logo", null=True, blank=True)

    def __str__(self):
        return self.name

class PaymentMethod(models.Model):

    state = models.BooleanField(default=True)
    description = models.CharField(max_length=200)

    class Meta:

        verbose_name_plural = "Tipo de metodo de pago"
        verbose_name = "Tipos de metodos de pagos"

    def __str__(self):

        return self.description

class Year(models.Model):

    """
    Representa un año (ej. 2025) para que el usuario seleccione en cuál trabajar.
    Puedes añadir campos extra si quieres manejar más información.
    """
    year = models.PositiveSmallIntegerField(unique=True)
    # Ejemplo: bandera para saber si está activo o cerrado
    state = models.BooleanField(default=True)

    def __str__(self):
        return str(self.year)

    class Meta:
        ordering = ['year']
        verbose_name = "Year Period"
        verbose_name_plural = "Year Periods"

class Zona(models.Model):

    name = models.CharField(max_length=100, verbose_name="Nombre de la Zona")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"

class Calle(models.Model):
    
    codigo = models.CharField(max_length=4, unique=True, editable=False)
    name = models.CharField(max_length=100, verbose_name="Nombre de la Calle")
    zona = models.ForeignKey(Zona, on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        if not self.codigo:
            last_calle = Calle.objects.order_by('-codigo').first()
            if last_calle and last_calle.codigo.isdigit():
                self.codigo = f"{int(last_calle.codigo) + 1:04d}"
            else:
                self.codigo = "0001"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} - {self.name} ({self.zona.name})"

    class Meta:
        verbose_name = "Calle"
        verbose_name_plural = "Calles"

class Service(models.Model):

    name = models.CharField(max_length=100, verbose_name="Nombre")
    unit = models.CharField(max_length=20, verbose_name="Unidad", blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio", default=0.0)

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"

class Category(models.Model):
    
    name = models.CharField(max_length=255, verbose_name="Nombre")
   
    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

class Tariff(models.Model):
    
    service = models.ForeignKey(Service, on_delete=models.CASCADE, verbose_name="Servicio")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name="Categoría")
    min_consumption = models.IntegerField(null=True, blank=True, verbose_name="Consumo Mínimo (m³)")
    max_consumption = models.IntegerField(null=True, blank=True, verbose_name="Consumo Máximo (m³)")
    price_water = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de agua")
    price_sewer = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de alcantarillado")
    extra_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_fixed = models.BooleanField(default=False, verbose_name="Tarifa Fija")
    

    def __str__(self):
        return f"{self.service.name} - {self.category.name} - {self.price_water}"

    class Meta:
        verbose_name = "Tarifa"
        verbose_name_plural = "Tarifas"

class Cash(BaseModel):

    date_opening = models.DateTimeField(null=True, blank=True, auto_now=False, auto_now_add=True)
    date_closed = models.DateTimeField(null=True, blank=True)
    beginning_balance = models.DecimalField(max_digits=13, decimal_places=2)
    final_balance = models.DecimalField(max_digits=13, decimal_places=2, default=0.0, null=True, blank=True)
    income = models.DecimalField(max_digits=13, decimal_places=2, default=0.0, null=True, blank=True)
    reference_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:

        ordering = ["id"]

    def __str__(self):

        return self.id

class Customer(models.Model):

    ESTADOS = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('suspendido', 'Suspendido'),
        ('cortado', 'Cortado'),
    ]

    state = models.CharField(max_length=10, choices=ESTADOS, default='activo')
    full_name = models.CharField(max_length=100, verbose_name="Nombre completo")
    address = models.CharField(max_length=200, verbose_name="Dirección")
    number = models.CharField(max_length=11, unique=True, blank=True, null=True, verbose_name="RUC")
    phone = models.CharField(max_length=15, verbose_name="Teléfono/Celular", null=True, blank=True)
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    has_meter = models.BooleanField(default=False, verbose_name="¿Tiene medidor?")
    calle = models.ForeignKey(Calle, on_delete=models.CASCADE)
    installation_date = models.DateField(verbose_name="Fecha de instalación")
    meter_code = models.CharField(max_length=50, unique=True, verbose_name="Código de medidor", blank=True, null=True)
  
    tariff = models.ForeignKey(Tariff, on_delete=models.SET_NULL, null=True, blank=True, related_name='customers_tariff')
    cutoff_date = models.DateField(null=True, blank=True, verbose_name="Fecha de corte")

    def __str__(self):
        return f"{self.full_name} ({self.number})"

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

class Reading(models.Model):

    correlative = models.CharField(max_length=10, unique=True, blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='readings')
    issue_date = models.DateField(auto_now_add=True)  # Fecha de emisión
    due_date = models.DateField(null=True, blank=True)  # Fecha de vencimiento
    cut_off_date = models.DateField(null=True, blank=True)  # Fecha de corte por impago
    
    reading_date = models.DateField()
    current_reading = models.IntegerField()  # Cambiado a IntegerField
    previous_reading = models.IntegerField(blank=True, null=True)  # Cambiado a IntegerField
    consumption = models.IntegerField(blank=True, null=True)  # Cambiado a IntegerField

    total_water = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_sewer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fixed_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Se calcula al guardar

    is_paid = models.BooleanField(default=False)

    def calculate_total(self):
        if self.consumption is None:
            self.consumption = max(0, (self.current_reading or 0) - (self.previous_reading or 0))

        tariff = self.customer.tariff

        if tariff.category.name == 'INDUSTRIAL':
            self.total_water = self._calculate_industrial_tariff(tariff)
        else:
            self.total_water = self.consumption * tariff.price_water
        
        self.total_sewer = tariff.price_sewer
        self.fixed_charge = tariff.service.price
        self.total_amount = self.total_water + self.total_sewer + self.fixed_charge 
       
        return self.total_amount

    def _calculate_industrial_tariff(self, tariff):
        """Calcula la tarifa para categoría INDUSTRIAL"""
        consumo_base = min(self.consumption, tariff.max_consumption)
        exceso = max(0, self.consumption - tariff.max_consumption)

        return (consumo_base * tariff.price_water) + (exceso * tariff.extra_rate)

    def save(self, *args, **kwargs):

        if not self.correlative:

           last_reading = Reading.objects.order_by('-id').first()
           
           if last_reading and last_reading.correlative:
                self.correlative = f"{int(last_reading.correlative) + 1:06d}"  # Formato 000001, 000002...
           else:
                self.correlative = "000001"  # Primer registro

        # Calcular consumo a partir de la lectura anterior
        previous = Reading.objects.filter(
            customer=self.customer,
            reading_date__lt=self.reading_date
        ).order_by('-reading_date').first()

        if previous:
            self.previous_reading = previous.current_reading
            self.consumption = self.current_reading - previous.current_reading
        else:
            self.previous_reading = 0
            self.consumption = self.current_reading

        # Calcular el total_amount antes de guardar
        self.calculate_total()
  
        if not self.issue_date:
            
            self.issue_date = date.today()
            # self.issue_date = self.reading_date

        # Calcular la fecha de vencimiento y corte si no están definidas
        if not self.due_date:
            self.due_date = self.reading_date + relativedelta(months=1)  # 15 días después de emisión

        if not self.cut_off_date:
            self.cut_off_date = self.due_date + timedelta(days=2) # Ejemplo: Corte 10 días después del vencimiento

        super().save(*args, **kwargs)

    def __str__(self):

        return f"Reading {self.id} - {self.customer.full_name} - {self.reading_date} - Total: {self.total_amount}"

class Invoice(models.Model):
    
    correlative = models.CharField(max_length=10, unique=True, blank=True, null=True)
    invoice_type = models.CharField(max_length=20, blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_of_issue = models.DateField(auto_now=True)

    def delete(self, *args, **kwargs):
        """Actualizar is_paid de los readings si se elimina una factura de tipo recibo."""
        if self.invoice_type == 'receipt':
            for payment in self.readings.all():  # Accedemos con related_name
                reading = payment.reading
                reading.is_paid = False
                reading.save()
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.id} - {self.customer.full_name} - Total: {self.total_amount}"

class InvoiceReading(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='readings')  # Cambio aquí
    reading = models.ForeignKey(Reading, on_delete=models.CASCADE, related_name='invoices')  # Cambio aquí
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Amount Paid")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_reading_status()

    def update_reading_status(self):
        """Actualizar el estado del reading dependiendo de los pagos."""
        total_paid = sum(payment.amount_paid for payment in self.reading.invoices.all())
        self.reading.is_paid = total_paid >= self.reading.total_amount
        self.reading.save()

    def __str__(self):
        return f"InvoiceReading {self.id} - Invoice {self.invoice.id} - Reading {self.reading.id}"

class InvoiceService(models.Model):

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='services')
    quantity = models.IntegerField()
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='invoices')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Amount Paid")

    def __str__(self):
        return f"Servicio {self.id} - Invoice {self.invoice.id} - Servicio {self.service.id}"
    
class InvoicePayment(models.Model):

    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')  # Cambio aquí
    cash = models.ForeignKey(Cash, on_delete=models.PROTECT)  # Relación con caja de pago
    total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"InvoicePayment {self.id} - Invoice {self.invoice.id} - Amount {self.total}"

class Expense(models.Model):

    CATEGORY_CHOICES = [
        ("salary", "Sueldos"),
        ("maintenance", "Mantenimiento"),
        ("supplies", "Suministros"),
        ("services", "Servicios"),
        ("other", "Otros"),
    ]

    date_of_issue = models.DateField()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(null=True,blank=True)

    def __str__(self):
        return f"{self.total} - {self.date_of_issue}"
