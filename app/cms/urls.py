from django.urls import include, path
from django.conf.urls.static import static
from django.conf import settings
from django_filters.views import FilterView
from cms.models import Accession
from cms.views import (
    accession_create, accession_edit, add_accession_row, AccessionRowDetailView,
    add_fieldslip_to_accession,
    add_comment_to_accession,
    add_geology_to_accession,
    add_identification_to_accession_row,
    add_specimen_to_accession_row,
    add_reference_to_accession,
    create_fieldslip_for_accession, fieldslip_create, fieldslip_edit, FieldSlipDetailView, FieldSlipListView,
    fieldslip_export, fieldslip_import, generate_accession_batch,
    AccessionListView, AccessionDetailView,
    ReferenceListView, ReferenceDetailView, reference_create, reference_edit, LocalityListView,LocalityDetailView,locality_edit,
    upload_media,
    PreparationListView, PreparationDetailView,
    PreparationCreateView, PreparationUpdateView, PreparationDeleteView,
    PreparationApproveView,
    dashboard,
)
from .views import PreparationMediaUploadView
from .views import FieldSlipAutocomplete

from cms.forms import (AccessionForm,
                       AccessionNumberSelectForm,
                       SpecimenCompositeForm)
from cms.views import AccessionWizard

from django_select2.views import AutoResponseView

urlpatterns = [
    
    path('fieldslips/new/', fieldslip_create, name='fieldslip_create'),
    path('fieldslips/<int:pk>/', FieldSlipDetailView.as_view(), name='fieldslip_detail'),
    path('fieldslips/<int:pk>/edit/', fieldslip_edit, name='fieldslip_edit'),
    path('fieldslips/', FieldSlipListView.as_view(), name='fieldslip_list'),
    path('fieldslips/export/', fieldslip_export, name='fieldslip_export'),
    path('fieldslips/import/', fieldslip_import, name='fieldslip_import'),

    path('accessions/', AccessionListView.as_view(), name='accession_list'),
    path('accessions/new/', accession_create, name='accession_create'),
    path('accessions/<int:pk>/', AccessionDetailView.as_view(), name='accession_detail'),
    path('accessions/<int:pk>/edit/', accession_edit, name='accession_edit'),
    path('accessions/<int:pk>/add-fieldslip/', add_fieldslip_to_accession, name='accession_add_fieldslip'),
    path('accessions/<int:pk>/create-fieldslip/', create_fieldslip_for_accession, name='accession_create_fieldslip'),
    path('accessions/<int:accession_id>/add-row/', add_accession_row, name='accession_add_row'),
    path('accessions/<int:accession_id>/add-comment/', add_comment_to_accession, name='accession_add_comment'),
    path('accessions/<int:accession_id>/add-geology/', add_geology_to_accession, name='accession_add_geology'),
    path('accessions/<int:accession_id>/add-reference/', add_reference_to_accession, name='accession_add_reference'),
    path('accessions/<int:accession_id>/upload-media/', upload_media, name='accession_upload_media'),
    path('accessionrows/<int:pk>/', AccessionRowDetailView.as_view(), name='accessionrow_detail'),
    path('accessionrows/<int:accession_row_id>/add-specimen/', add_specimen_to_accession_row, name='accessionrow_add_specimen'),
    path('accessionrows/<int:accession_row_id>/add-identification/', add_identification_to_accession_row, name='accessionrow_add_identification'),
    path("accessions/generate-batch/", generate_accession_batch, name="accession_generate_batch"),
    path('accession-wizard/', AccessionWizard.as_view([AccessionNumberSelectForm, AccessionForm,
                                                       SpecimenCompositeForm]), name='accession-wizard'),
    path('references/', ReferenceListView.as_view(), name='reference_list'),
    path('references/<int:pk>/', ReferenceDetailView.as_view(), name='reference_detail'),
    path('references/<int:pk>/edit/', reference_edit, name='reference_edit'),
    path('references/new/', reference_create, name='reference_create'),
  
    path("select2/", include("django_select2.urls")),


    path('localities/', LocalityListView.as_view(), name='locality_list'),
    path('localities/<int:pk>/', LocalityDetailView.as_view(), name='locality_detail'),
    path('localities/<int:pk>/edit/', locality_edit, name='locality_edit'),


] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    path("preparations/", PreparationListView.as_view(), name="preparation_list"),
    path("preparations/<int:pk>/", PreparationDetailView.as_view(), name="preparation_detail"),
    path("preparations/new/", PreparationCreateView.as_view(), name="preparation_create"),
    path("preparations/<int:pk>/edit/", PreparationUpdateView.as_view(), name="preparation_edit"),
    path("preparations/<int:pk>/delete/", PreparationDeleteView.as_view(), name="preparation_delete"),
    path("preparations/<int:pk>/approve/", PreparationApproveView.as_view(), name="preparation_approve"),
]

urlpatterns += [
    path("preparations/<int:pk>/upload-media-form/", PreparationMediaUploadView.as_view(), name="preparation_upload_media_form"),
]

urlpatterns += [
    path("autocomplete/fieldslip/", FieldSlipAutocomplete.as_view(), name="fieldslip-autocomplete"),
]

urlpatterns += [
    path("dashboard/", dashboard, name="dashboard"),
]