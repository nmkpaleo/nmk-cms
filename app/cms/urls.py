from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from cms.views import fieldslip_create, fieldslip_edit, FieldSlipDetailView,FieldSlipListView,AccessionListView,AccessionDetailView,fieldslip_export, fieldslip_import, ReferenceListView, upload_media
#from .views import fieldslip_create, FieldSlipDetailView, FieldSlipListView

urlpatterns = [
    
    path('fieldslip/new/', fieldslip_create, name='fieldslip-create'),
    
    path('fieldslip/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip-detail'),
    path('fieldslip/<int:pk>/edit/', fieldslip_edit, name='fieldslip-edit'), 
    path('fieldslips/', FieldSlipListView.as_view(), name='fieldslip-list'),
    path('fieldslip/export/', fieldslip_export, name='fieldslip-export'),  # Add export URL
    path('fieldslip/import/', fieldslip_import, name='fieldslip-import'),  # Add import URL

    path('accessions/', AccessionListView.as_view(), name='accession-list'),
    path('accession/<int:pk>/', AccessionDetailView.as_view(), name='accession-detail'),
    path('accession/<int:accession_id>/upload_media/', upload_media, name='upload-media'),
    path('reference/', ReferenceListView.as_view(), name='reference-list')

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

