from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from cms.views import fieldslip_create, fieldslip_edit, FieldSlipDetailView,FieldSlipListView,AccessionListView,AccessionDetailView,fieldslip_export, fieldslip_import, ReferenceListView,ReferenceDetailView,reference_edit,upload_media,add_accession_row

urlpatterns = [
    
    path('fieldslip/new/', fieldslip_create, name='fieldslip-create'),
    
    path('fieldslip/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip-detail'),
    path('fieldslip/<int:pk>/edit/', fieldslip_edit, name='fieldslip-edit'), 
    path('fieldslips/', FieldSlipListView.as_view(), name='fieldslip-list'),
    path('fieldslip/export/', fieldslip_export, name='fieldslip-export'),  # Add export URL
    path('fieldslip/import/', fieldslip_import, name='fieldslip-import'),  # Add import URL

    path('accessions/', AccessionListView.as_view(), name='accession-list'),
    path('accession/<int:pk>/', AccessionDetailView.as_view(), name='accession-detail'),

    path('reference/', ReferenceListView.as_view(), name='reference-list'),
    path('reference/<int:pk>/', ReferenceDetailView.as_view(), name='reference-detail'),
    path('reference/<int:pk>/edit/', reference_edit, name='reference-edit'),
  
    path('accession/<int:accession_id>/upload_media/', upload_media, name='upload-media'),

    path('accession/<int:accession_id>/add_accession_row/', add_accession_row, name='add_accession_row'),



] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

