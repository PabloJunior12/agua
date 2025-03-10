from django.shortcuts import render, get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.template.loader import render_to_string, get_template
from django.http import HttpResponse
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import Year, Category, Zona, Calle, Reading, Invoice, Customer,Company, InvoicePayment, Service
from .serializers import CompanySerializer, YearSerializer, CustomerSerializer, ReadingSerializer, InvoiceSerializer, CategorySerializer, ZonaSerializer, CalleSerializer, ServiceSerializer
from datetime import datetime
from weasyprint import HTML, CSS
from io import BytesIO
from decimal import Decimal

import os
import tempfile

class CompanyViewSet(ModelViewSet):

    queryset = Company.objects.all()
    serializer_class = CompanySerializer

class CustomPagination(PageNumberPagination):

    page_size = 5  # Número de registros por página
    page_size_query_param = 'page_size'  # Permite cambiar el tamaño desde la URL
    max_page_size = 100  # Tamaño máximo permitido

class YearViewSet(ModelViewSet):

    queryset = Year.objects.all().order_by('-id')
    serializer_class = YearSerializer

class CustomerViewSet(ModelViewSet):

    queryset = Customer.objects.all().order_by('-id')
    serializer_class = CustomerSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    # Búsqueda exacta para DNI y Meter Code
    # filterset_fields = ['dni', 'meter_code']

    # Búsqueda parcial para Name
    search_fields = ['full_name','dni']

class ReadingViewSet(ModelViewSet):

    queryset = Reading.objects.all().order_by('reading_date')
    serializer_class = ReadingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['customer','is_paid']

    def get_queryset(self):

        queryset = super().get_queryset()
        year = self.request.query_params.get('year')

        if year:

            queryset = queryset.filter(reading_date__year=year)

        return queryset
    
    @action(detail=False, methods=['get'], url_path='dni/(?P<dni>\w+)')
    def get_by_dni(self, request, dni=None):
        
        customer = get_object_or_404(Customer, dni=dni)
        readings = Reading.objects.filter(customer=customer).order_by('reading_date')
        serializer = self.get_serializer(readings, many=True)
        customer_serializer = CustomerSerializer(customer)

        return Response({
            'readings': serializer.data,
            'customer': customer_serializer.data
        })
    
    def destroy(self, request, *args, **kwargs):

        instance = self.get_object()

        # VERIFICAR SI HAY UNA LECTURA MAS RECIENTE PARA EL MISMO CLIENTE

        has_newer_reading = Reading.objects.filter(
            customer = instance.customer,
            reading_date__gt = instance.reading_date
        ).exists()

        if has_newer_reading:

           return Response({"error":"No se puede eliminar"}, status=status.HTTP_400_BAD_REQUEST)
        
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

class InvoiceViewSet(ModelViewSet):

    queryset = Invoice.objects.all().order_by('-id')
    serializer_class = InvoiceSerializer
    pagination_class = CustomPagination

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        payments_data = serializer.validated_data.pop('payments', [])  # Extraer los pagos

        last_invoice = Invoice.objects.order_by('-id').first()
        next_correlative = f"{(int(last_invoice.correlative) + 1):06d}" if last_invoice and last_invoice.correlative else "000001"

        invoice = Invoice.objects.create(**serializer.validated_data, correlative = next_correlative)  # Crear la factura

        total_invoice_amount = 0  # Variable para acumular el total de la factura

        for payment in payments_data:
            reading_id = payment.get('reading')
            amount_paid = Decimal(payment.get('amount_paid'))

            reading = get_object_or_404(Reading, id=reading_id)  # Obtener la lectura

            # Validar que el pago no exceda el monto total de la lectura
            total_paid = sum(p.amount_paid for p in reading.payments.all()) + amount_paid
 
            if total_paid > reading.total_amount:
                return Response(
                    {"error": f"El total pagado para el Reading {reading.id} excede el monto permitido."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

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

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class CategoryViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]

    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer

class ZonaViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    queryset = Zona.objects.all().order_by('id')
    serializer_class = ZonaSerializer

class ServiceViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    queryset = Service.objects.all().order_by('id')
    serializer_class = ServiceSerializer

class CalleViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]

    queryset = Calle.objects.all().order_by('id')
    serializer_class = CalleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

class CustomerUnpaidInvoicesView(APIView):
    
    def get(self, request, dni):
        try:
            # Buscar al cliente por DNI
            customer = Customer.objects.get(dni=dni)

            # Obtener facturas impagas
            unpaid_invoices = Invoice.objects.filter(reading__customer=customer, is_paid=False)

            # Obtener pagos realizados
            # payments = Payment.objects.filter(invoice__reading__customer=customer)

            # Serializar datos
            customer_data = CustomerSerializer(customer).data
            unpaid_invoices_data = InvoiceSerializer(unpaid_invoices, many=True).data
            # payments_data = PaymentSerializer(payments, many=True).data

            return Response({
                'customer': customer_data,
                'unpaid_invoices': unpaid_invoices_data,
                # 'payments': payments_data
            }, status=status.HTTP_200_OK)
        
        except Customer.DoesNotExist:
            return Response({'error': 'Cliente no encontrado'}, status=status.HTTP_404_NOT_FOUND)

# REPORTE

class PDFGeneratorAPIView(APIView):

    def get(self, request, invoice_id, *args, **kwargs):
        invoice = get_object_or_404(Invoice, id=invoice_id)
        company = Company.objects.first()
        customer = invoice.customer
        payments = InvoicePayment.objects.filter(invoice=invoice).order_by('reading__reading_date')

        context = {
            "invoice": invoice,
            "customer": customer,
            "payments": payments,
            "total_paid": sum((p.amount_paid for p in payments), 0),
            "company_name": company.name if company else "Empresa",
            "company_ruc": company.ruc if company else "99999999999",
            "company_logo": request.build_absolute_uri(company.logo.url) if company and company.logo else None
        }

        template = get_template('agua/hola.html')
        html_string = template.render(context)

        pdf_buffer = BytesIO()
        css_path = os.path.join(settings.BASE_DIR, "static/css/ticket.css")

        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(pdf_buffer, stylesheets=[CSS(css_path)])

        pdf_buffer.seek(0)
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="invoice_ticket.pdf"'
        return response

class PDFReciboApiView(APIView):

    def get(self, request, reading_id, *args, **kwargs):   
        reading = Reading.objects.get(id=reading_id)
        company = Company.objects.first()  # Suponiendo que hay una sola empresa

        # Obtener la lectura anterior de este cliente
        previous_reading = Reading.objects.filter(
            customer=reading.customer,
            reading_date__lt=reading.reading_date
        ).order_by('-reading_date').first()

        # Cálculo del consumo excedente
        consumption_excess = max(0, reading.consumption - reading.service.max_cubico)
        total_excess_charge = consumption_excess * reading.service.extra_rate

        # Buscar lecturas impagas anteriores del cliente
        unpaid_readings = Reading.objects.filter(
            customer=reading.customer,
            is_paid=False,
            due_date__lt=reading.reading_date
        ).exclude(id=reading.id)
        
        total_due = sum(r.total_amount for r in unpaid_readings)

        total =  reading.total_amount + total_due

        context = {
            "company": company,
            "customer": reading.customer,
            "reading": reading,
            "previous_reading": previous_reading,

            "consumption_excess": consumption_excess,
            "total_excess_charge": total_excess_charge,
            
            "unpaid_readings": unpaid_readings,
            "total_due": total_due,
            "total" : total,

            "company_logo": request.build_absolute_uri(company.logo.url) if company and company.logo else None
        }
        template = get_template("agua/invoice_template.html")
        html_string = template.render(context)

        pdf_buffer = BytesIO()
        css_path = os.path.join(settings.BASE_DIR, "static/css/invoice_style.css")

        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(pdf_buffer, stylesheets=[CSS(css_path)])

        pdf_buffer.seek(0)
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="invoice.pdf"'
        return response