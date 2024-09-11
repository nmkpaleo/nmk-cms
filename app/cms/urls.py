from django.urls import path
from cms.views import fieldslip_create, FieldSlipDetailView,FieldSlipListView
#from .views import fieldslip_create, FieldSlipDetailView, FieldSlipListView

urlpatterns = [
    path('fieldslip/new/', fieldslip_create, name='fieldslip-create'),
    path('fieldslip/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip-detail'),
    path('fieldslips/', FieldSlipListView.as_view(), name='fieldslip-list'),
]
