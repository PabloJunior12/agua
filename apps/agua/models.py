from django.db import models
from apps.base.models import BaseModel
from django.core.exceptions import ValidationError
from decimal import Decimal

class Company(models.Model):

    name = models.CharField(max_length=255, verbose_name="Nombre de la empresa")
    ruc = models.CharField(max_length=11, unique=True, verbose_name="RUC")
    address = models.CharField(max_length=255, verbose_name="Dirección", null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name="Teléfono", null=True, blank=True)
    email = models.EmailField(verbose_name="Correo electrónico", null=True, blank=True)
    logo = models.ImageField(upload_to="logos/", verbose_name="Logo", null=True, blank=True)

    def __str__(self):
        return self.name

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

class Category(models.Model):
    
    name = models.CharField(max_length=255, verbose_name="Nombre")
    water_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Tarifa de agua")
    sewer_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,  verbose_name="Tarifa de alcantarilla")
    mora = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Mora")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

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

class Customer(BaseModel):

    full_name = models.CharField(max_length=100, verbose_name="Full Name")
    address = models.CharField(max_length=200, verbose_name="Address")
    dni = models.CharField(max_length=8, unique=True, verbose_name="DNI")
    ruc = models.CharField(max_length=11, unique=True, blank=True, null=True, verbose_name="RUC")
    phone = models.CharField(max_length=15, verbose_name="Phone Number", null=True, blank=True)
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    has_meter = models.BooleanField(default=False)
    installation_date = models.DateField(verbose_name="Reading Date")
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    water_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Tarifa de agua")
    sewer_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00,  verbose_name="Tarifa de alcantarilla")
    calle = models.ForeignKey(Calle, on_delete=models.CASCADE)
    meter_code = models.CharField(max_length=50, unique=True, verbose_name="Meter Code")

    def __str__(self):
        return f"{self.full_name} ({self.dni})"

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

class Reading(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='readings')
    reading_date = models.DateField()
    current_reading = models.DecimalField(max_digits=10, decimal_places=2)
    previous_reading = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    consumption = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # 💰 Monto a pagar
    is_paid = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Calcular consumo
        previous_reading = Reading.objects.filter(
            customer=self.customer,
            reading_date__lt=self.reading_date
        ).order_by('-reading_date').first()

        if previous_reading:
            self.previous_reading = previous_reading.current_reading
            self.consumption = self.current_reading - previous_reading.current_reading
        else:
            self.previous_reading = 0
            self.consumption = self.current_reading  # Primera lectura

        # Calcular monto a pagar
        tarifa_por_m3 = self.customer.water_fee
        self.total_amount = self.consumption * tarifa_por_m3 if self.consumption else 0

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Reading {self.id} - {self.customer.full_name} - Total: {self.total_amount}"

class Invoice(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_of_issue = models.DateField(auto_now=True)

    def __str__(self):
        return f"Invoice {self.id} - {self.customer.full_name} - Total: {self.total_amount}"

class InvoicePayment(models.Model):

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    reading = models.ForeignKey(Reading, on_delete=models.CASCADE, related_name='payments')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Amount Paid")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_reading_status()

    def update_reading_status(self):
        """Actualizar el estado del reading dependiendo de los pagos."""
        total_paid = sum(payment.amount_paid for payment in self.reading.payments.all())
        if total_paid >= self.reading.total_amount:
            self.reading.is_paid = True
        else:
            self.reading.is_paid = False
        self.reading.save()

    def __str__(self):
        return f"Payment {self.id} - Invoice {self.invoice.id} - Reading {self.reading.id}"
