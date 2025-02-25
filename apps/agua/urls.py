from rest_framework import routers
from django.urls import path
from .views import CompanyViewSet, YearViewSet, CustomerViewSet, ReadingViewSet, InvoiceViewSet, CategoryViewSet, ZonaViewSet, CalleViewSet, PDFGeneratorAPIView, PDFReciboApiView, CustomerUnpaidInvoicesView

router = routers.DefaultRouter()

router.register("company", CompanyViewSet)
router.register("year", YearViewSet)
router.register("customer", CustomerViewSet)
router.register("reading", ReadingViewSet)
router.register("invoice", InvoiceViewSet)
router.register("category", CategoryViewSet)
router.register("zona", ZonaViewSet)
router.register("calle", CalleViewSet)

urlpatterns = [
 path('customer/<str:dni>/unpaid-invoices/', CustomerUnpaidInvoicesView.as_view(), name='customer-unpaid-invoices'),
 path('pdf/<int:invoice_id>', PDFGeneratorAPIView.as_view(), name='api_pdf'),
 path('recibo/pdf/<int:reading_id>', PDFReciboApiView.as_view(), name='recibo_api_pdf')

] + router.urls