from django.urls import include, path
from django.conf.urls.static import static
from django.conf import settings
from django_filters.views import FilterView
from cms.models import Accession
from cms.views import (
    accession_create,
    accession_edit,
    add_accession_row,
    AccessionRowDetailView,
    AccessionRowUpdateView,
    add_fieldslip_to_accession,
    add_comment_to_accession,
    add_geology_to_accession,
    add_identification_to_accession_row,
    add_specimen_to_accession_row,
    add_reference_to_accession,
    create_fieldslip_for_accession,
    fieldslip_create,
    fieldslip_edit,
    FieldSlipDetailView,
    FieldSlipListView,
    fieldslip_export,
    fieldslip_import,
    generate_accession_batch,
    AccessionListView,
    AccessionDetailView,
    ReferenceListView,
    ReferenceDetailView,
    reference_create,
    reference_edit,
    LocalityListView,
    LocalityDetailView,
    locality_create,
    locality_edit,
    PlaceListView,
    PlaceDetailView,
    place_create,
    place_edit,
    upload_media,
    upload_scan,
    MediaInternQCWizard,
    MediaExpertQCWizard,
    PreparationListView,
    PreparationDetailView,
    PreparationCreateView,
    PreparationUpdateView,
    PreparationDeleteView,
    PreparationApproveView,
    dashboard,
    MediaPendingInternQueueView,
    MediaNeedsExpertAttentionQueueView,
    MediaReturnedForFixesQueueView,
    MediaRowsRearrangedQueueView,
    MediaWithCommentsQueueView,
    MediaQCHistoryView,
    inventory_start, inventory_update, inventory_reset, inventory_clear, inventory_log_unexpected,
    DrawerRegisterListView, DrawerRegisterDetailView, DrawerRegisterCreateView, DrawerRegisterUpdateView, start_scan, stop_scan,
    inventory_start,
    inventory_update,
    inventory_reset,
    inventory_clear,
    inventory_log_unexpected,
    DrawerRegisterListView,
    DrawerRegisterDetailView,
    DrawerRegisterCreateView,
    DrawerRegisterUpdateView,
    DrawerRegisterReorderView,
    StorageListView,
    StorageDetailView,
    StorageCreateView,
    StorageUpdateView,
)
from .views import PreparationMediaUploadView
from .views import FieldSlipAutocomplete, ReferenceAutocomplete

from cms.forms import (AccessionForm,
                       AccessionNumberSelectForm,
                       SpecimenCompositeForm)
from cms.views import AccessionWizard

urlpatterns = [
    path('inventory/', inventory_start, name='inventory_start'),
    path('inventory/update/', inventory_update, name='inventory_update'),
    path('inventory/reset/', inventory_reset, name='inventory_reset'),
    path('inventory/clear/', inventory_clear, name='inventory_clear'),
    path('inventory/log-unexpected/', inventory_log_unexpected, name='inventory_log_unexpected'),
    path('qc/intern/<uuid:pk>/', MediaInternQCWizard, name='media_intern_qc'),
    path('qc/expert/<uuid:pk>/', MediaExpertQCWizard, name='media_expert_qc'),
    path('qc/queue/pending-intern/', MediaPendingInternQueueView.as_view(), name='media_qc_pending_intern'),
    path('qc/queue/pending-expert/', MediaNeedsExpertAttentionQueueView.as_view(), name='media_qc_pending_expert'),
    path('qc/queue/returned/', MediaReturnedForFixesQueueView.as_view(), name='media_qc_returned'),
    path('qc/queue/rows-rearranged/', MediaRowsRearrangedQueueView.as_view(), name='media_qc_rows_rearranged'),
    path('qc/queue/with-comments/', MediaWithCommentsQueueView.as_view(), name='media_qc_with_comments'),
    path('qc/history/', MediaQCHistoryView.as_view(), name='media_qc_history'),
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
    path('accessionrows/<int:pk>/edit/', AccessionRowUpdateView.as_view(), name='accessionrow_edit'),
    path('accessionrows/<int:accession_row_id>/add-specimen/', add_specimen_to_accession_row, name='accessionrow_add_specimen'),
    path('accessionrows/<int:accession_row_id>/add-identification/', add_identification_to_accession_row, name='accessionrow_add_identification'),
    path("accessions/generate-batch/", generate_accession_batch, name="accession_generate_batch"),
    path('accession-wizard/', AccessionWizard.as_view([AccessionNumberSelectForm, AccessionForm,
                                                       SpecimenCompositeForm]), name='accession-wizard'),
    path('references/', ReferenceListView.as_view(), name='reference_list'),
    path('references/<int:pk>/', ReferenceDetailView.as_view(), name='reference_detail'),
    path('references/<int:pk>/edit/', reference_edit, name='reference_edit'),
    path('references/new/', reference_create, name='reference_create'),
    path('references/autocomplete/', ReferenceAutocomplete.as_view(), name='reference-autocomplete'),

    path("select2/", include("django_select2.urls")),


    path('localities/', LocalityListView.as_view(), name='locality_list'),
    path('localities/new/', locality_create, name='locality_create'),
    path('localities/<int:pk>/', LocalityDetailView.as_view(), name='locality_detail'),
    path('localities/<int:pk>/edit/', locality_edit, name='locality_edit'),

    path('places/', PlaceListView.as_view(), name='place_list'),
    path('places/new/', place_create, name='place_create'),
    path('places/<int:pk>/', PlaceDetailView.as_view(), name='place_detail'),
    path('places/<int:pk>/edit/', place_edit, name='place_edit'),

    path('drawers/', DrawerRegisterListView.as_view(), name='drawerregister_list'),
    path('drawers/new/', DrawerRegisterCreateView.as_view(), name='drawerregister_create'),
    path('drawers/<int:pk>/', DrawerRegisterDetailView.as_view(), name='drawerregister_detail'),
    path('drawers/<int:pk>/edit/', DrawerRegisterUpdateView.as_view(), name='drawerregister_edit'),
    path('drawers/<int:pk>/start/', start_scan, name='drawer_start_scan'),
    path('drawers/<int:pk>/stop/', stop_scan, name='drawer_stop_scan'),
    path('drawers/reorder/', DrawerRegisterReorderView.as_view(), name='drawerregister_reorder'),

    path('storages/', StorageListView.as_view(), name='storage_list'),
    path('storages/new/', StorageCreateView.as_view(), name='storage_create'),
    path('storages/<int:pk>/', StorageDetailView.as_view(), name='storage_detail'),
    path('storages/<int:pk>/edit/', StorageUpdateView.as_view(), name='storage_edit'),


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