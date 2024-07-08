from django.urls import path
from cms.views import fieldslip_create, FieldSlipDetailView

urlpatterns = [
    path('fieldslip/new/', fieldslip_create, name='fieldslip-create'),
    path('fieldslip/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip-detail'),
]
