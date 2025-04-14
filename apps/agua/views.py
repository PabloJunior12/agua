from django.shortcuts import render, get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.template.loader import render_to_string, get_template
from django.http import HttpResponse
from django.conf import settings
from django.utils.timezone import now
from django.db.models import Sum, Q, Count
from dateutil.relativedelta import relativedelta
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError

from .models import Year, Category, Zona, Calle, Expense, Reading, Cash, Invoice, PaymentMethod, Customer, InvoicePayment, Company, InvoiceReading, Service, Tariff, InvoiceService

from .serializers import CompanySerializer, YearSerializer, CashSerializer, PaymentMethodSerializer, CustomerSerializer, ReadingWriteSerializer, ReadingReadSerializer, InvoiceSerializer, CategorySerializer, ZonaSerializer, CalleSerializer, ServiceSerializer, TariffSerializer
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

class PaymentMethodViewSet(ModelViewSet):

    queryset = PaymentMethod.objects.all().order_by('id')
    serializer_class = PaymentMethodSerializer

class CustomerViewSet(ModelViewSet):

    queryset = Customer.objects.all().order_by('-id')
    serializer_class = CustomerSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]

    # Búsqueda exacta para DNI y Meter Code
    filterset_fields = ['state','has_meter','calle__zona']

    # Búsqueda parcial para Name
    search_fields = ['full_name','number']

    def get_queryset(self):
        
        queryset = super().get_queryset()  # Usa el queryset definido arriba
        debt_status = self.request.query_params.get('debt_status')

        if debt_status == "overdue":  # 📌 Deuda vencida
            queryset = queryset.filter(
                readings__due_date__lt=now().date(),
                readings__is_paid=False
            ).distinct()

        elif debt_status == "pending":  # 📌 Deuda pendiente pero no vencida
            queryset = queryset.filter(
                readings__due_date__gte=now().date(),
                readings__is_paid=False
            ).distinct()

        elif debt_status == "clear":  # 📌 Sin deuda
            queryset = queryset.exclude(
                readings__is_paid=False  # Filtra solo los que tienen todas sus lecturas pagadas
            )

        return queryset

    @action(detail=False, methods=['get'], url_path='balance-report')
    def balance_report(self, request):
        """
        Nuevo reporte de saldos (pagado/adeudado) por cliente
        """
        today = now().date()
        
        # 1. Obtener todos los clientes con lecturas
        customers = Customer.objects.annotate(
            total_paid=Sum('readings__total_amount', 
                          filter=Q(readings__is_paid=True)),
            total_pending=Sum('readings__total_amount',
                            filter=Q(readings__is_paid=False) & 
                                   Q(readings__due_date__gte=today)),
            total_overdue=Sum('readings__total_amount',
                            filter=Q(readings__is_paid=False) & 
                                   Q(readings__due_date__lt=today))
        ).exclude(
            total_paid__isnull=True,
            total_pending__isnull=True,
            total_overdue__isnull=True
        ).order_by('full_name')
        
        # 2. Preparar datos para el reporte
        report_data = []
        for customer in customers:
            report_data.append({
                'id': customer.id,
                'full_name': customer.full_name,
                'number': customer.number,
                'meter_code': customer.meter_code,
                'address': customer.address,
                'paid': customer.total_paid or 0,
                'pending': customer.total_pending or 0,
                'overdue': customer.total_overdue or 0,
                'total_debt': (customer.total_pending or 0) + 
                              (customer.total_overdue or 0)
            })
        
        # 3. Totales generales
        totals = {
            'paid': sum(c['paid'] for c in report_data),
            'pending': sum(c['pending'] for c in report_data),
            'overdue': sum(c['overdue'] for c in report_data),
            'total_debt': sum(c['total_debt'] for c in report_data),
            'customer_count': len(report_data)
        }
        
        # 4. Contexto para el template
        context = {
            'customers': report_data,
            'totals': totals,
            'report_date': today.strftime("%d/%m/%Y"),
            'title': "Reporte de Saldos de Clientes con Lecturas"
        }
        
        # 5. Generar PDF (similar a tu implementación actual)
        template = get_template('reports/customer_balances.html')
        html_string = template.render(context)
        
        pdf_buffer = BytesIO()
        HTML(string=html_string).write_pdf(pdf_buffer)
        
        pdf_buffer.seek(0)
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        filename = f"reporte_saldos_clientes_{today.strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):


        customer = self.get_object()
        
        # Parámetros
        months = int(request.GET.get('months', 12))  # Default: último año
        
        # Fechas para el filtro
        end_date = datetime.now()
        start_date = end_date - relativedelta(months=months)

        # 2. Obtener todos los pagos del cliente
        # Primero obtenemos las facturas del cliente
        invoices = Invoice.objects.filter(
            customer=customer,
            date_of_issue__range=[start_date, end_date]
        )

        # Luego obtenemos los pagos de esas facturas
        payments = InvoicePayment.objects.filter(
            invoice__in=invoices,
            invoice__date_of_issue__range=[start_date, end_date]
        ).order_by('invoice__date_of_issue')

        # 3. Generar historial combinado
        total_paid = payments.aggregate(total=Sum('total'))['total'] or 0
        
        # 5. Generar PDF
        context = {
            'customer': customer,
            'payments' : payments,
            'period': f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}",
            'title': f"Estado de Cuenta - {customer.full_name}",
            'total_paid': total_paid,
        }
        
        html_string = render_to_string('reports/account_statement.html', context)
        pdf = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"estado_cuenta_{customer.number}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
   
class ReadingViewSet(ModelViewSet):

    queryset = Reading.objects.all().order_by('reading_date')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['customer','is_paid','customer__meter_code']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ReadingWriteSerializer
        return ReadingReadSerializer

    def get_queryset(self):

        queryset = super().get_queryset()
        year = self.request.query_params.get('year')

        if year:

            queryset = queryset.filter(reading_date__year=year)

        payment_status = self.request.query_params.get('payment_status')

        if payment_status:

           today = now().date()

           if payment_status == 'paid':

              queryset = queryset.filter(is_paid=True)  

           elif payment_status == 'pending':

                queryset = queryset.filter(is_paid=False, due_date__gte=today)

           elif payment_status == 'overdue':
                
                queryset = queryset.filter(is_paid=False, due_date__lt=today)  

        return queryset
    
    @action(detail=False, methods=['get'], url_path='dni/(?P<dni>\w+)')
    def get_by_dni(self, request, dni=None):
        
        customer = get_object_or_404(Customer, number=dni)
        readings = Reading.objects.filter(customer=customer).order_by('reading_date')
        serializer = self.get_serializer(readings, many=True)
        customer_serializer = CustomerSerializer(customer)

        return Response({
            'readings': serializer.data,
            'customer': customer_serializer.data
        })
    
    @action(detail=False, methods=['get'], url_path='meter-code/(?P<meter_code>[^/]+)')
    def get_by_meter_code(self, request, meter_code=None):
        if not meter_code.isdigit():
            return Response(
                {'error': 'El código del medidor debe contener solo números.'},
                status=400
            )

        customer = get_object_or_404(Customer, meter_code=meter_code)
        year = request.GET.get('year')
        readings = Reading.objects.filter(customer=customer,reading_date__year=year).order_by('reading_date')
        serializer = self.get_serializer(readings, many=True)
        customer_serializer = CustomerSerializer(customer)

        return Response({
            'readings': serializer.data,
            'customer': customer_serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def pdf(self, request):
        # Obtener queryset base
        queryset = self.filter_queryset(self.get_queryset())
        
        # Aplicar filtro por año si existe
        year = request.query_params.get('year')
        if year:
            queryset = queryset.filter(reading_date__year=year)

        # Manejar el filtro por estado de pago
        payment_status = request.query_params.get('payment_status')
        payment_status_text = 'Todos'
        today = now().date()
        
        if payment_status:
            if payment_status == 'paid':
                payment_status_text = 'Pagado'
                queryset = queryset.filter(is_paid=True)  
            elif payment_status == 'pending':
                payment_status_text = 'Pendiente'
                queryset = queryset.filter(is_paid=False, due_date__gte=today)
            elif payment_status == 'overdue':
                payment_status_text = 'Vencida'
                queryset = queryset.filter(is_paid=False, due_date__lt=today) 
        
        # Optimizar la consulta
        queryset = queryset.select_related('customer').order_by('reading_date')
        
        # Serializar los datos
        serializer = self.get_serializer(queryset, many=True)
        serialized_data = serializer.data
        
        # Calcular totales
        total_amount = queryset.aggregate(total=Sum('total_amount'))['total'] or 0
        total_consumption = queryset.aggregate(total=Sum('consumption'))['total'] or 0

        # Preparar el contexto
        context = {
            'readings': serialized_data,  # Usamos los datos serializados
            'payment_status': payment_status_text,
            'total_amount': total_amount,
            'total_consumption': total_consumption,
            'report_date': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'title': f"Reporte de Lecturas - Estado: {payment_status_text}",
        }

        # Generar el PDF
        template = get_template('reports/reading.html')
        html_string = template.render(context)
        
        pdf_buffer = BytesIO()
        css_path = os.path.join(settings.BASE_DIR, "static/css/reports/reading.css")

        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(
            pdf_buffer, 
            stylesheets=[CSS(css_path)]
        )

        pdf_buffer.seek(0)
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        filename = f"reporte_lecturas_{payment_status or 'todos'}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response["Content-Disposition"] = f'inline; filename="{filename}"'

        return response
    
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
        
  
        payments_data = request.data.pop('readings', [])  # Extraer los pagos
        services_data = request.data.pop('services', [])  # Extraer los pagos
        invoice_payment_data = request.data.pop('invoice_payment', None)

  
        last_invoice = Invoice.objects.order_by('-id').first()
        next_correlative = f"{(int(last_invoice.correlative) + 1):06d}" if last_invoice and last_invoice.correlative else "000001"

        invoice = Invoice.objects.create(**serializer.validated_data, correlative = next_correlative)  # Crear la factura
        

        total_invoice_amount = 0  # Variable para acumular el total de la factura

        if request.data['invoice_type'] == 'receipt':

            for payment in payments_data:
                reading_id = payment.get('reading')
                amount_paid = Decimal(payment.get('amount_paid'))

                reading = get_object_or_404(Reading, id=reading_id)  # Obtener la lectura

                # Validar que el pago no exceda el monto total de la lectura
                total_paid = sum(p.amount_paid for p in reading.invoices.all()) + amount_paid
    
                if total_paid > reading.total_amount:
                    return Response(
                        {"error": f"El total pagado para el Reading {reading.id} excede el monto permitido."}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Crear InvoicePayment
                InvoiceReading.objects.create(
                    invoice=invoice,
                    reading=reading,
                    amount_paid=amount_paid
                )

                total_invoice_amount += amount_paid  # Sumar el pago al total de la factura

                # Actualizar estado de la lectura
                reading.is_paid = total_paid >= reading.total_amount
                reading.save()

        if request.data['invoice_type'] == 'other_charges':

            for service in services_data:

                service_id = service.get('service')
                quantity = service.get('quantity')
                price = Decimal(service.get('price'))
              
                service = get_object_or_404(Service, id=service_id)

                InvoiceService.objects.create(
                    invoice=invoice,
                    quantity=quantity,
                    service=service,
                    amount_paid=price
                )

                total_invoice_amount += price

        # Guardar el total de la factura
        invoice.total_amount = total_invoice_amount
        invoice.save()

        if invoice_payment_data:

           payment_method_id = invoice_payment_data.get('payment_method')
           cash_id = invoice_payment_data.get('cash')
           total = Decimal(invoice_payment_data.get('total'))

           InvoicePayment.objects.create(
               invoice=invoice,
               payment_method_id=payment_method_id,
               cash_id=cash_id,
               total=total
           )

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

class CategoryViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]

    queryset = Category.objects.all().order_by('id')
    serializer_class = CategorySerializer

class CashViewSet(ModelViewSet):
    
    # permission_classes = [IsAuthenticated]

    queryset = Cash.objects.all().order_by('id')
    serializer_class = CashSerializer
    pagination_class = CustomPagination

    def destroy(self, request, *args, **kwargs):

        cash = self.get_object()

        if InvoicePayment.objects.filter(cash=cash).exists():

           raise ValidationError({'error':'No se puede eliminar la caja porque tiene pagos asociados'})
        
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def close(self, request, pk=None):

        cash = self.get_object()

        if cash.date_closed:
           
           return Respones({'error':'La caja ya esta cerrada'}, status=status.HTTP_400_BAD_REQUEST)
        
        total = InvoicePayment.objects.filter(cash=cash).aggregate(total=Sum('total'))['total'] or 0

        cash.income = total
        cash.final_balance = cash.beginning_balance + total
        cash.date_closed = now()
        cash.state = False
        cash.save()

        return Response({'message':'Caja cerrada'})

    @action(detail=True, methods=['get'])
    def report(self, request, *args, **kwargs):
        
        cash = self.get_object()

        report_type = request.GET.get('type', 'daily')  # daily, monthly, custom

        if report_type == 'daily':

            report_date = request.GET.get('date')

            date_obj = datetime.strptime(report_date, '%Y-%m-%d').date()
            payments = InvoicePayment.objects.filter(
                cash=cash,
                invoice__date_of_issue = report_date

            ).select_related('invoice', 'payment_method')

            # Agrupar ingresos por concepto (tipo de pago)
            income_by_concept = payments.values(
                'payment_method__description'
            ).annotate(
                total=Sum('total')
            ).order_by('payment_method__description')

            # Calcular totales
            total_income = payments.aggregate(total=Sum('total'))['total'] or 0
            calculated_balance = cash.beginning_balance + total_income
            
            context = {
                'payments' : payments,
                'date': date_obj,
                'opening_balance': float(cash.beginning_balance),
                'income_by_concept': list(income_by_concept),
                'total_income': float(total_income),
                'calculated_balance': float(calculated_balance),
                'final_balance': float(cash.final_balance) if cash.final_balance else None,
                # 'is_closed': cash.state,
                'reference_number': cash.reference_number,
            }
    
            
            html_string = render_to_string('reports/daily_balance.html', context)
            pdf = HTML(string=html_string).write_pdf()
            
            response = HttpResponse(pdf, content_type='application/pdf')
            filename = f"deudas_clientes_{datetime.now().strftime('%Y%m%d')}.pdf"
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response

        elif report_type == 'range':
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')

         
            # Validar que ambas fechas existan
            if not start_date or not end_date:
                return Response({'error': 'Debe proporcionar start_date y end_date'}, status=400)

            # Convertir a objetos fecha
            start_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_obj = datetime.strptime(end_date, '%Y-%m-%d').date()

            # Filtrar los pagos dentro del rango
            payments = InvoicePayment.objects.filter(
                cash=cash,
                invoice__date_of_issue__range=(start_obj, end_obj)
            ).select_related('invoice', 'payment_method')

            # Agrupar por método de pago
            income_by_concept = payments.values(
                'payment_method__description'
            ).annotate(
                total=Sum('total')
            ).order_by('payment_method__description')

            total_income = payments.aggregate(total=Sum('total'))['total'] or 0
            calculated_balance = cash.beginning_balance + total_income

            # Formateo bonito del rango

            context = {
                'report_type' : report_type,
                'payments': payments,
                'date': start_obj,
                'end_date': end_obj,
                'opening_balance': float(cash.beginning_balance),
                'income_by_concept': list(income_by_concept),
                'total_income': float(total_income),
                'calculated_balance': float(calculated_balance),
                'final_balance': float(cash.final_balance) if cash.final_balance else None,
                'is_closed': cash.date_closed is not None,
                'reference_number': cash.reference_number,
            }

            html_string = render_to_string('reports/daily_balance.html', context)
            pdf = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

            response = HttpResponse(pdf, content_type='application/pdf')
            filename = f"reporte_caja_{datetime.now().strftime('%Y%m%d')}.pdf"
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response

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

class TariffViewSet(ModelViewSet):
    
    queryset = Tariff.objects.all()
    serializer_class = TariffSerializer

# REPORTE

class PDFRecibosPorCalleApiView(APIView):

    def get(self, request, pk, periodo, *args, **kwargs):

        company = Company.objects.first()
        css_path = os.path.join(settings.BASE_DIR, "static/css/invoice_style.css")

        calle = Calle.objects.get(pk = pk)
        periodo_date = datetime.strptime(periodo, "%Y-%m")
        mes = periodo_date.month
        anio = periodo_date.year
        readings = Reading.objects.filter(customer__calle=calle,issue_date__month=mes,issue_date__year=anio)
      
        combined_html = ""
        template = get_template("agua/invoice_template.html")

        for reading in readings:
          
            previous_reading = Reading.objects.filter(
                customer=reading.customer,
                reading_date__lt=reading.reading_date
            ).order_by('-reading_date').first()

            unpaid_readings = Reading.objects.filter(
                customer=reading.customer,
                is_paid=False,
                due_date__lt=reading.reading_date
            ).exclude(id=reading.id)
            
            consumption_excess = max(0, reading.consumption - reading.customer.tariff.max_consumption)
            total_excess_charge = consumption_excess * reading.customer.tariff.extra_rate
            total_due = sum(r.total_amount for r in unpaid_readings)
            total = reading.total_amount + total_due

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

            html_string = template.render(context)
            combined_html += html_string + '<p style="page-break-after: always;"></p>'  # salto de página

        # Generar PDF combinado
        pdf_buffer = BytesIO()
        HTML(string=combined_html, base_url=request.build_absolute_uri()).write_pdf(
            pdf_buffer, stylesheets=[CSS(css_path)]
        )
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="recibos_{calle.name}.pdf"'
        return response

class PDFGeneratorAPIView(APIView):

    def get(self, request, invoice_id, *args, **kwargs):
        
        invoice = get_object_or_404(Invoice, id=invoice_id)
        company = Company.objects.first()
        customer = invoice.customer
        payments = InvoiceReading.objects.filter(invoice=invoice).order_by('reading__reading_date')

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
        consumption_excess = max(0, reading.consumption - reading.customer.tariff.max_consumption)
        total_excess_charge = consumption_excess * reading.customer.tariff.extra_rate

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
    
class DebtReportViewSet(APIView):

    def get(self, request):
  
        # Parámetros de filtrado
        months = request.query_params.get('months', 6)  # Default: últimos 6 meses
        zona = request.query_params.get('zona', None)
        
        # Calculamos fecha de corte
        from dateutil.relativedelta import relativedelta
        cutoff_date = datetime.now() - relativedelta(months=int(months))
        
        # Consulta optimizada
        customers = Customer.objects.annotate(
            total_debt=Sum('readings__total_amount',
                          filter=Q(readings__is_paid=False) &
                                 Q(readings__reading_date__gte=cutoff_date)),
            debt_months=Count('readings__reading_date__month',
                             distinct=True,
                             filter=Q(readings__is_paid=False) &
                                     Q(readings__reading_date__gte=cutoff_date))
        ).filter(total_debt__gt=0).order_by('full_name')
        
        if zona:
            customers = customers.filter(calle__zona__id=zona)
        
        # Preparar datos para el template
        report_data = []
        for customer in customers:
            # Obtener meses adeudados
            unpaid_months = Reading.objects.filter(
                customer=customer,
                is_paid=False,
                reading_date__gte=cutoff_date
            ).dates('reading_date', 'month', order='ASC')
            
            report_data.append({
                'id': customer.id,
                'name': customer.full_name,
                'address': customer.address,
                'zone': customer.calle.zona.name if customer.calle.zona else '',
                'total_debt': customer.total_debt,
                'debt_months': customer.debt_months,
                'months_list': [date.strftime("%b-%Y") for date in unpaid_months]
            })
        
        # Generar PDF
        context = {
            'customers': report_data,
            'report_date': datetime.now().strftime("%d/%m/%Y"),
            'cutoff_date': cutoff_date.strftime("%d/%m/%Y"),
            'title': f"Reporte de Deudas (Últimos {months} meses)"
        }
        
        html_string = render_to_string('reports/debt_report.html', context)
        pdf = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"deudas_clientes_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    
# GLOBAL API VIEW

class TotalDashboard(APIView):

    def get(self, request):

        total_invoices = Invoice.objects.count()
        total_sum = Invoice.objects.aggregate(total_sum=Sum('total_amount'))['total_sum'] or 0

        total_customers = Customer.objects.count()
        total_readings = Reading.objects.count()

        return Response({
            "total_invoices": total_invoices,
            "total_sum": float(total_sum),
            "total_customers": total_customers,
            "total_readings": total_readings,
        })

class FinancialSummaryAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        
        year = int(request.query_params.get('year', datetime.now().year))

        ingresos = InvoicePayment.objects.filter(invoice__date_of_issue__year=year).aggregate(total=Sum('total'))['total'] or 0
        egresos = Expense.objects.filter(date_of_issue__year=year).aggregate(total=Sum('total'))['total'] or 0
        utilidad = ingresos - egresos

        data = [

            {
                "name": "ingresos",
                "value": ingresos,
            },
            {
                "name": "egresos",
                "value": egresos,
            },
            {
                "name": "utilidad",
                "value": utilidad,
            }

        ]

        return Response(data)