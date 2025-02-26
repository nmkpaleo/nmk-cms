from django.urls import include, path
from django.conf.urls.static import static
from django.conf import settings
from cms.views import add_accession_row, AddCommentToAccessionView, AddGeologyToAccessionView, AddIdentificationToAccessionRowView, AddSpecimenToAccessionRowView, AddReferenceToAccessionView, AccessionRowDetailView, fieldslip_create, fieldslip_edit, FieldSlipDetailView,FieldSlipListView,AccessionListView,AccessionDetailView,fieldslip_export, fieldslip_import, NatureOfSpecimenCreateView, ReferenceListView,ReferenceDetailView,reference_edit,upload_media

urlpatterns = [
    
    path('fieldslip/new/', fieldslip_create, name='fieldslip-create'),
    
    path('fieldslip/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip-detail'),
    path('fieldslip/<int:pk>/edit/', fieldslip_edit, name='fieldslip-edit'), 
    path('fieldslips/', FieldSlipListView.as_view(), name='fieldslip-list'),
    path('fieldslip/export/', fieldslip_export, name='fieldslip-export'),
    path('fieldslip/import/', fieldslip_import, name='fieldslip-import'),

    path('accessions/', AccessionListView.as_view(), name='accession-list'),
    path('accession/<int:pk>/', AccessionDetailView.as_view(), name='accession-detail'),
    path('accession/<int:accession_id>/add_accession_row/', add_accession_row, name='add_accession_row'),
    path('accession/<int:accession_id>/add-comment/', AddCommentToAccessionView, name='add-comment'),
    path('accession/<int:accession_id>/add-reference/', AddReferenceToAccessionView, name='add-reference'),
    path('accession/<int:accession_id>/upload_media/', upload_media, name='upload-media'),
    path('accessionrow/<int:pk>/', AccessionRowDetailView.as_view(), name='accessionrow-detail'),
    #path('accessionrow/<int:accession_row_id>/add-specimen/', NatureOfSpecimenCreateView.as_view(), name='natureofspecimen-create'),
    path('accessionrow/<int:accession_row_id>/add-specimen/', AddSpecimenToAccessionRowView, name='add-specimen'),
    path('accessionrow/<int:accession_row_id>/add-identification/', AddIdentificationToAccessionRowView, name='add-identification'),

    path('reference/', ReferenceListView.as_view(), name='reference-list'),
    path('reference/<int:pk>/', ReferenceDetailView.as_view(), name='reference-detail'),
    path('reference/<int:pk>/edit/', reference_edit, name='reference-edit'),
  
    path("select2/", include("django_select2.urls")),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)