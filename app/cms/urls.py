from django.urls import include, path
from django.conf.urls.static import static
from django.conf import settings
from django_filters.views import FilterView
from cms.models import Accession
from cms.views import (
    accession_create, accession_edit, add_accession_row, AccessionRowDetailView,
    add_fieldslip_to_accession,
    AddCommentToAccessionView,
    AddGeologyToAccessionView,
    AddIdentificationToAccessionRowView,
    AddSpecimenToAccessionRowView,
    AddReferenceToAccessionView,
    create_fieldslip_for_accession, fieldslip_create, fieldslip_edit, FieldSlipDetailView, FieldSlipListView,
    fieldslip_export, fieldslip_import, generate_accession_batch_view,
    AccessionListView, AccessionDetailView,
    ReferenceListView, ReferenceDetailView, reference_create, reference_edit, LocalityListView,LocalityDetailView,locality_edit,
    upload_media,
    PreparationListView, PreparationDetailView, 
    PreparationCreateView, PreparationUpdateView, PreparationDeleteView, 
    PreparationApproveView
)
from .views import PreparationMediaUploadView

urlpatterns = [
    
    path('fieldslip/new/', fieldslip_create, name='fieldslip-create'),
    path('fieldslip/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip-detail'),
    path('fieldslip/<int:pk>/edit/', fieldslip_edit, name='fieldslip-edit'), 
    path('fieldslips/', FieldSlipListView.as_view(), name='fieldslip-list'),
    path('fieldslip/export/', fieldslip_export, name='fieldslip-export'),
    path('fieldslip/import/', fieldslip_import, name='fieldslip-import'),

    path('accessions/', AccessionListView.as_view(), name='accession-list'),
    path('accessions/new/', accession_create, name='accession-create'),
    path('accession/<int:pk>/', AccessionDetailView.as_view(), name='accession-detail'),
    path('accession/<int:pk>/edit/', accession_edit, name='accession-edit'),
    path('accession/<int:pk>/add-fieldslip/', add_fieldslip_to_accession, name='add-fieldslip-to-accession'),
    path('accession/<int:pk>/create-fieldslip/', create_fieldslip_for_accession, name='create-fieldslip-for-accession'),
    path('accession/<int:accession_id>/add_accession_row/', add_accession_row, name='add_accession_row'),
    path('accession/<int:accession_id>/add-comment/', AddCommentToAccessionView, name='add-comment'),
    path('accession/<int:accession_id>/add-geology/', AddGeologyToAccessionView, name='add-geology'),
    path('accession/<int:accession_id>/add-reference/', AddReferenceToAccessionView, name='add-reference'),
    path('accession/<int:accession_id>/upload_media/', upload_media, name='upload-media'),
    path('accessionrow/<int:pk>/', AccessionRowDetailView.as_view(), name='accessionrow-detail'),
    path('accessionrow/<int:accession_row_id>/add-specimen/', AddSpecimenToAccessionRowView, name='add-specimen'),
    path('accessionrow/<int:accession_row_id>/add-identification/', AddIdentificationToAccessionRowView, name='add-identification'),
    path("accession/generate-batch/", generate_accession_batch_view, name="generate-accession-batch"),

    path('reference/', ReferenceListView.as_view(), name='reference-list'),
    path('reference/<int:pk>/', ReferenceDetailView.as_view(), name='reference-detail'),
    path('reference/<int:pk>/edit/', reference_edit, name='reference-edit'),
    path('reference/new/', reference_create, name='reference-create'),
  
    path("select2/", include("django_select2.urls")),


    path('locality/', LocalityListView.as_view(), name='locality-list'),
    path('locality/<int:pk>/', LocalityDetailView.as_view(), name='locality-detail'),
    path('locality/<int:pk>/edit/', locality_edit, name='locality-edit'),


] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    path("preparations/", PreparationListView.as_view(), name="preparation-list"),
    path("preparation/<int:pk>/", PreparationDetailView.as_view(), name="preparation-detail"),
    path("preparation/new/", PreparationCreateView.as_view(), name="preparation-create"),
    path("preparation/<int:pk>/edit/", PreparationUpdateView.as_view(), name="preparation-edit"),
    path("preparation/<int:pk>/delete/", PreparationDeleteView.as_view(), name="preparation-delete"),
    path("preparation/<int:pk>/approve/", PreparationApproveView.as_view(), name="preparation-approve"),
]

urlpatterns += [
    path("preparation/<int:pk>/upload-media-form/", PreparationMediaUploadView.as_view(), name="preparation-upload-media-form"),
]
