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

from .models import Year, Category, Zona, Calle, Reading, Invoice, Customer,Company, InvoicePayment
from .serializers import CompanySerializer, YearSerializer, CustomerSerializer, ReadingSerializer, InvoiceSerializer, CategorySerializer, ZonaSerializer, CalleSerializer 
from datetime import datetime
from weasyprint import HTML, CSS
from io import BytesIO


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

     
class InvoiceViewSet(ModelViewSet):

    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    pagination_class = CustomPagination

class CategoryViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]

    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer

class ZonaViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]

    queryset = Zona.objects.all().order_by('id')
    serializer_class = ZonaSerializer

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
        payments = InvoicePayment.objects.filter(invoice=invoice)

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

        context = {
            "company": company,
            "customer": reading.customer,
            "reading": reading,
            # "payments": invoice.payments.all(),
            # "total_paid": sum(p.amount_paid for p in invoice.payments.all()),
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