import copy
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from dal import autocomplete
from django import forms
from django.db import transaction
from django.db.models import Value, CharField, Count, Q, Max, Prefetch, OuterRef, Subquery
from django.db.models.functions import Concat, Greatest
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_filters.views import FilterView
from .filters import (
    AccessionFilter,
    PreparationFilter,
    ReferenceFilter,
    FieldSlipFilter,
    LocalityFilter,
    PlaceFilter,
    DrawerRegisterFilter,
    StorageFilter,
)


from django.views.generic import DetailView
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.conf import settings

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory, modelformset_factory
from django.forms.widgets import Media as FormsMedia
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy, reverse
from django.utils.timezone import now
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView

from cms.forms import (AccessionBatchForm, AccessionCommentForm,
                    AccessionForm, AccessionFieldSlipForm, AccessionGeologyForm,
                    AccessionNumberSelectForm,
                    AccessionRowIdentificationForm, AccessionMediaUploadForm,
                    AccessionRowSpecimenForm, AccessionRowUpdateForm,
                    AccessionReferenceForm, AddAccessionRowForm, FieldSlipForm,
                    MediaUploadForm, NatureOfSpecimenForm, PreparationForm,
                    PreparationApprovalForm, PreparationMediaUploadForm,
                    SpecimenCompositeForm, ReferenceForm, LocalityForm,
                    PlaceForm, DrawerRegisterForm, StorageForm, ScanUploadForm,
                    ReferenceWidget)

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionFieldSlip,
    AccessionReference,
    AccessionRow,
    Collection,
    Comment,
    FieldSlip,
    Media,
    NatureOfSpecimen,
    Identification,
    Preparation,
    PreparationMedia,
    Reference,
    SpecimenGeology,
    Storage,
    Taxon,
    Locality,
    Place,
    PlaceRelation,
    PreparationStatus,
    InventoryStatus,
    UnexpectedSpecimen,
    DrawerRegister,
    Scanning,
    Element,
    Person,
    MediaQCLog,
    MediaQCComment,
)
from django.shortcuts import render
from .models import Media
import plotly.express as px
import pandas as pd
from plotly.io import to_html
import plotly.graph_objects as go
from datetime import datetime, timedelta
from django.utils import timezone



from cms.resources import FieldSlipResource
from .utils import build_history_entries
from cms.utils import generate_accessions_from_series
from cms.upload_processing import process_file
from cms.ocr_processing import process_pending_scans, describe_accession_conflicts
from cms.qc import (
    build_preview_accession,
    diff_media_payload,
    ident_payload_has_meaningful_data as qc_ident_payload_has_meaningful_data,
    interpreted_value as qc_interpreted_value,
)
from cms import scanning_utils
from formtools.wizard.views import SessionWizardView

_ident_payload_has_meaningful_data = qc_ident_payload_has_meaningful_data
_interpreted_value = qc_interpreted_value

def media_report_view(request):
    # Fetch OCR status data
    data = Media.objects.values('ocr_status', 'created_on')
    df = pd.DataFrame.from_records(data)

    # Handle empty dataset
    if df.empty or 'ocr_status' not in df.columns:
        context = {
            'chart_html': None,
            'daily_chart_html': None,
            'summary': None,
            'message': 'No media data available for reporting yet.'
        }
        return render(request, 'reports/media_report.html', context)

    # ======== OCR STATUS SUMMARY =========
    counts = df['ocr_status'].value_counts().reset_index()
    counts.columns = ['OCR Status', 'Count']

    #  labels
    status_labels = {
        'pending': 'Pending OCR',
        'completed': 'Completed',
        'failed': 'Failed',
    }
    counts['OCR Status'] = counts['OCR Status'].map(lambda x: status_labels.get(x.lower(), x.title()))

    total_files = counts['Count'].sum()
    completed = counts.loc[counts['OCR Status'] == 'Completed', 'Count'].sum()
    completion_rate = (completed / total_files * 100) if total_files > 0 else 0

    # Build OCR summary chart
    fig1 = px.bar(
        counts,
        x='OCR Status',
        y='Count',
        title="OCR Status Summary of Media Files",
        color='OCR Status',
        text='Count',
        color_discrete_sequence=px.colors.qualitative.Vivid
    )
    fig1.update_traces(textposition='outside')
    fig1.update_layout(
        plot_bgcolor='#ffffff',
        paper_bgcolor='#ffffff',
        title_font_size=22,
        title_font_color='#2c3e50',
        font=dict(size=14),
        xaxis_title="OCR Status",
        yaxis_title="Number of Files",
        xaxis_tickangle=-15,
        showlegend=False
    )
    chart_html = to_html(fig1, full_html=False, include_plotlyjs='cdn')

    # ======== DAILY UPLOAD PROGRESS (MON-SUN) =========
    if 'created_on' in df.columns:
        df['created_on'] = pd.to_datetime(df['created_on'], errors='coerce')
        df = df.dropna(subset=['created_on'])
        df['day_of_week'] = df['created_on'].dt.day_name()

        # Ensure week order
        week_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily_counts = df['day_of_week'].value_counts().reindex(week_order, fill_value=0)

        # Force integers only
        daily_counts = daily_counts.astype(int)

        # Build line/bar chart for daily uploads
        fig2 = go.Figure(data=go.Bar(
            x=daily_counts.index,
            y=daily_counts.values,
            text=daily_counts.values,
            textposition='outside',
            marker_color='rgba(46, 204, 113, 0.8)'
        ))

        fig2.update_layout(
            title="Weekly Upload Progress (Monday - Sunday)",
            xaxis_title="Day of Week",
            yaxis_title="Number of Uploads",
            plot_bgcolor='#ffffff',
            paper_bgcolor='#ffffff',
            font=dict(size=14),
            showlegend=False,
            yaxis=dict(dtick=1),  # ensure whole numbers
            margin=dict(l=40, r=40, t=60, b=40)
        )
        daily_chart_html = to_html(fig2, full_html=False, include_plotlyjs=False)
    else:
        daily_chart_html = None

    context = {
        'chart_html': chart_html,
        'daily_chart_html': daily_chart_html,
        'summary': {
            'total': total_files,
            'completed': completed,
            'completion_rate': round(completion_rate, 2)
        },
    }
    return render(request, 'reports/media_report.html', context)








class FieldSlipAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = FieldSlip.objects.all()
        if self.q:
            qs = qs.filter(
                field_number__icontains=self.q
            ) | qs.filter(
                verbatim_locality__icontains=self.q
            )
        return qs


class ReferenceAutocomplete(LoginRequiredMixin, View):
    """Serve reference choices for Select2 widgets without relying on cache."""

    http_method_names = ["get"]
    raise_exception = True

    def get(self, request, *args, **kwargs):
        widget = ReferenceWidget()
        term = (request.GET.get("term") or "").strip()

        queryset = widget.filter_queryset(request, term, widget.get_queryset())
        limit = getattr(widget, "max_results", 25)

        objects = list(queryset[: limit + 1])
        has_more = len(objects) > limit
        if has_more:
            objects = objects[:limit]

        results = [
            {"id": obj.pk, "text": widget.label_from_instance(obj)}
            for obj in objects
        ]

        return JsonResponse({"results": results, "more": has_more})

class PreparationAccessMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser or
            user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        )

# Helper function to check if user can manage collection content
def is_collection_manager(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or user.groups.filter(name="Collection Managers").exists()


def is_intern(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name="Interns").exists()


def is_qc_expert(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or user.groups.filter(
        name__in=["Curators", "Collection Managers"]
    ).exists()


def can_manage_places(user):
    return user.is_superuser or user.groups.filter(name="Collection Managers").exists()


def is_public_user(user):
    if not user.is_authenticated:
        return True
    return user.groups.filter(name__iexact="Public").exists()


def prefetch_accession_related(qs):
    """Prefetch accession row data needed for taxon and element summaries."""
    accession_row_prefetch = Prefetch(
        'accessionrow_set',
        queryset=AccessionRow.objects.prefetch_related(
            Prefetch(
                'natureofspecimen_set',
                queryset=NatureOfSpecimen.objects.select_related('element')
            ),
            Prefetch(
                'identification_set',
                queryset=Identification.objects.all().order_by('-date_identified', '-id')
            ),
        )
    )

    return (
        qs.select_related('collection', 'specimen_prefix')
        .prefetch_related(accession_row_prefetch)
        .distinct()
    )


def attach_accession_summaries(accessions):
    """Attach taxon and element summaries to each accession in the iterable."""
    if accessions is None:
        return

    accession_list = getattr(accessions, 'object_list', accessions)

    for accession in accession_list:
        taxa = set()
        elements = set()

        for row in accession.accessionrow_set.all():
            for identification in row.identification_set.all():
                taxon = (identification.taxon or "").strip()
                if taxon:
                    taxa.add(taxon)
            for specimen in row.natureofspecimen_set.all():
                element = getattr(specimen, 'element', None)
                if element and element.name:
                    elements.add(element.name)

        accession.taxa_list = sorted(taxa)
        accession.element_list = sorted(elements)

def add_fieldslip_to_accession(request, pk):
    """
    Adds an existing FieldSlip to an Accession.
    """
    accession = get_object_or_404(Accession, pk=pk)
    
    if request.method == "POST":
        form = AccessionFieldSlipForm(request.POST)
        if form.is_valid():
            relation = form.save(commit=False)
            relation.accession = accession
            relation.save()
            messages.success(request, "FieldSlip added successfully!")
            return redirect("accession_detail", pk=accession.pk)

    messages.error(request, "Error adding FieldSlip.")
    return redirect("accession_detail", pk=accession.pk)

def create_fieldslip_for_accession(request, pk):
    """ Opens a modal for FieldSlip creation and links it to an Accession """
    accession = get_object_or_404(Accession, pk=pk)

    if request.method == "POST":
        form = FieldSlipForm(request.POST)
        if form.is_valid():
            fieldslip = form.save()
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=fieldslip)
            messages.success(request, "New FieldSlip created and linked successfully!")

            # Instead of closing a pop-up window, return a script to close the modal
            return HttpResponse('<script>window.parent.closeModalAndRefresh();</script>')

        else:
            messages.error(request, "There were errors in your submission. Please correct them.")

    else:
        form = FieldSlipForm()

    return render(request, "includes/base_form.html", {
        "form": form,
        "action": request.path,
        "title": "New FieldSlip",
        "submit_label": "Create FieldSlip",
    })

def fieldslip_export(request):
    # Create a CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="fieldslips.csv"'

    writer = csv.writer(response)
    writer.writerow(['Field Number', 'Discoverer', 'Collector', 'Collection Date', 'Verbatim Locality',
                     'Verbatim Taxon', 'Verbatim Element', 'Verbatim Horizon', 'Aerial Photo'])  # Header row

    for fieldslip in FieldSlip.objects.all():
        writer.writerow([fieldslip.field_number, fieldslip.discoverer, fieldslip.collector,
                         fieldslip.collection_date, fieldslip.verbatim_locality,
                         fieldslip.verbatim_taxon, fieldslip.verbatim_element,
                         fieldslip.verbatim_horizon, fieldslip.aerial_photo.url if fieldslip.aerial_photo else ''])

    return response

def fieldslip_import(request):
    if request.method == 'POST':
        resource = FieldSlipResource()
        dataset = request.FILES['import_file']
        result = resource.import_data(dataset, dry_run=True)  # Perform a dry run

        if not result.has_errors():
            resource.import_data(dataset, dry_run=False)  #  import now
            return redirect('fieldslip_list')  # Redirect after successful import

    return render(request, 'cms/fieldslip_import.html')  # Render the import form

@login_required
def dashboard(request):
    """Landing page that adapts content based on user roles."""
    user = request.user
    context = {}
    role_context_added = False

    if user.groups.filter(name="Preparators").exists():
        my_preparations_qs = Preparation.objects.filter(
            preparator=user
        ).exclude(status=PreparationStatus.COMPLETED)
        my_preparations = my_preparations_qs.order_by("-started_on")[:10]

        priority_threshold = now().date() - timedelta(days=7)
        priority_tasks = (
            my_preparations_qs.filter(started_on__lte=priority_threshold)
            .order_by("-started_on")[:10]
        )

        context.update(
            {
                "is_preparator": True,
                "my_preparations": my_preparations,
                "priority_tasks": priority_tasks,
            }
        )
        role_context_added = True

    if user.groups.filter(name="Curators").exists():
        completed_preparations = (
            Preparation.objects.filter(
                status=PreparationStatus.COMPLETED,
                curator=user,
            )
            .order_by("-completed_on")[:10]
        )

        context.update(
            {
                "is_curator": True,
                "completed_preparations": completed_preparations,
            }
        )
        role_context_added = True

    if user.groups.filter(name="Collection Managers").exists():
        has_active_series = AccessionNumberSeries.objects.filter(
            user=user, is_active=True
        ).exists()
        unassigned_accessions = (
            Accession.objects.filter(accessioned_by=user)
            .annotate(row_count=Count("accessionrow"))
            .filter(row_count=0)
            .order_by("-created_on")[:10]
        )
        latest_accessions = (
            Accession.objects.filter(
                Q(created_by=user)
                | Q(modified_by=user)
                | Q(accessionrow__created_by=user)
                | Q(accessionrow__modified_by=user)
            )
            .annotate(
                last_activity=Greatest(
                    "modified_on", Max("accessionrow__modified_on")
                )
            )
            .order_by("-last_activity")
            .distinct()[:10]
        )

        context.update(
            {
                "is_collection_manager": True,
                "has_active_series": has_active_series,
                "unassigned_accessions": unassigned_accessions,
                "latest_accessions": latest_accessions,
            }
        )
        role_context_added = True

    is_expert_user = is_qc_expert(user)
    if is_expert_user:
        context["is_expert"] = True

    intern_member = is_intern(user)
    if intern_member:
        scanning_utils.auto_complete_scans(
            Scanning.objects.filter(user=user, end_time__isnull=True)
        )
        active_scan_id_subquery = Scanning.objects.filter(
            drawer=OuterRef("pk"), user=user, end_time__isnull=True
        ).values("id")[:1]
        active_scan_start_subquery = Scanning.objects.filter(
            drawer=OuterRef("pk"), user=user, end_time__isnull=True
        ).values("start_time")[:1]
        my_drawers_qs = (
            DrawerRegister.objects.filter(
                scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
                scanning_users=user,
            )
            .annotate(active_scan_id=Subquery(active_scan_id_subquery))
            .annotate(active_scan_start=Subquery(active_scan_start_subquery))
            .order_by("-priority", "code")
        )
        my_drawers = list(my_drawers_qs[:1])

        for drawer in my_drawers:
            drawer.active_scan_start = scanning_utils.to_nairobi(
                getattr(drawer, "active_scan_start", None)
            )

        context.update(
            {
                "is_intern": True,
                "my_drawers": my_drawers,
            }
        )
        role_context_added = True

    qc_sections: list[dict] = []
    section_limit = 10
    base_qc_qs = Media.objects.select_related("accession", "accession_row").annotate(
        comment_count=Count("qc_logs__comments", distinct=True)
    )

    queue_definitions = [
        {
            "key": "pending_intern",
            "label": "Pending intern review",
            "filters": {
                "qc_status": Media.QCStatus.PENDING_INTERN,
                "ocr_status": Media.OCRStatus.COMPLETED,
                "media_location__startswith": "uploads/ocr/",
            },
            "action_url_name": "media_intern_qc",
            "cta_label": "Review",
            "empty_message": "No media awaiting intern review.",
            "list_view_name": "media_qc_pending_intern",
            "roles": {"intern", "expert"},
        },
        {
            "key": "pending_expert",
            "label": "Needs expert attention",
            "filters": {"qc_status": Media.QCStatus.PENDING_EXPERT},
            "action_url_name": "media_expert_qc",
            "cta_label": "Open Expert QC",
            "empty_message": "No media awaiting expert review.",
            "list_view_name": "media_qc_pending_expert",
            "roles": {"expert"},
        },
        {
            "key": "returned",
            "label": "Returned for fixes",
            "filters": {"qc_status": Media.QCStatus.REJECTED},
            "action_url_name": "media_intern_qc",
            "cta_label": "Review fixes",
            "empty_message": "No media returned for fixes.",
            "list_view_name": "media_qc_returned",
            "roles": {"intern", "expert"},
        },
    ]

    def user_has_role(roles: set[str]) -> bool:
        if not roles:
            return True
        return any(
            [
                "expert" in roles and is_expert_user,
                "intern" in roles and intern_member,
            ]
        )

    for definition in queue_definitions:
        roles = definition.get("roles", set())
        if not user_has_role(roles):
            continue

        queryset = base_qc_qs.filter(**definition["filters"]).order_by("-modified_on")
        entries = list(queryset[: section_limit + 1])
        has_more = len(entries) > section_limit
        entries = entries[:section_limit]
        if entries or definition.get("show_when_empty", True):
            qc_sections.append(
                {
                    "key": definition["key"],
                    "label": definition["label"],
                    "entries": entries,
                    "has_more": has_more,
                    "action_url_name": definition["action_url_name"],
                    "cta_label": definition["cta_label"],
                    "empty_message": definition["empty_message"],
                    "view_all_url": reverse(definition["list_view_name"]),
                }
            )

    qc_extra_links: list[dict] = []
    if is_expert_user:
        qc_extra_links.extend(
            [
                {
                    "label": "Media with rearranged rows",
                    "url": reverse("media_qc_rows_rearranged"),
                },
                {
                    "label": "Media with QC comments",
                    "url": reverse("media_qc_with_comments"),
                },
            ]
        )

    context["qc_sections"] = qc_sections
    context["qc_extra_links"] = qc_extra_links

    if not role_context_added and not qc_sections:
        context["no_role"] = True

    return render(request, "cms/dashboard.html", context)


class MediaQCQueueView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Base list view for filtered media QC queues."""

    model = Media
    template_name = "cms/qc/media_queue_list.html"
    context_object_name = "media_list"
    paginate_by = 50
    raise_exception = True
    ordering = ("-modified_on", "-pk")
    filters: dict[str, object] = {}
    allowed_roles: set[str] | None = None
    queue_title: str = ""
    queue_description: str | None = None
    queue_action_url_name: str | None = None
    queue_action_label: str = "Open QC"
    queue_empty_message: str = "No media match this queue."
    distinct: bool = True

    def get_filters(self) -> dict[str, object]:
        return dict(self.filters)

    def get_ordering(self):
        return self.ordering

    def test_func(self) -> bool:
        user = self.request.user
        role_checks = {
            "expert": is_qc_expert,
            "intern": is_intern,
        }
        allowed_roles = self.allowed_roles or {"expert"}
        for role in allowed_roles:
            check = role_checks.get(role)
            if check and check(user):
                return True
        return False

    def get_queryset(self):
        queryset = Media.objects.filter(**self.get_filters()).select_related(
            "accession", "accession_row"
        ).annotate(comment_count=Count("qc_logs__comments", distinct=True))

        if self.distinct:
            queryset = queryset.distinct()

        ordering = self.get_ordering()
        if ordering:
            if isinstance(ordering, (list, tuple)):
                queryset = queryset.order_by(*ordering)
            else:
                queryset = queryset.order_by(ordering)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "queue_title": self.queue_title,
                "queue_description": self.queue_description,
                "queue_action_url_name": self.queue_action_url_name,
                "queue_action_label": self.queue_action_label,
                "queue_empty_message": self.queue_empty_message,
            }
        )
        return context


class MediaPendingInternQueueView(MediaQCQueueView):
    filters = {
        "qc_status": Media.QCStatus.PENDING_INTERN,
        "ocr_status": Media.OCRStatus.COMPLETED,
        "media_location__startswith": "uploads/ocr/",
    }
    allowed_roles = {"intern", "expert"}
    queue_title = "Pending intern review"
    queue_action_url_name = "media_intern_qc"
    queue_action_label = "Review"
    queue_empty_message = "No media awaiting intern review."


class MediaReturnedForFixesQueueView(MediaQCQueueView):
    filters = {"qc_status": Media.QCStatus.REJECTED}
    allowed_roles = {"intern", "expert"}
    queue_title = "Returned for fixes"
    queue_action_url_name = "media_intern_qc"
    queue_action_label = "Review fixes"
    queue_empty_message = "No media have been returned for fixes."


class MediaNeedsExpertAttentionQueueView(MediaQCQueueView):
    filters = {"qc_status": Media.QCStatus.PENDING_EXPERT}
    allowed_roles = {"expert"}
    queue_title = "Needs expert attention"
    queue_action_url_name = "media_expert_qc"
    queue_action_label = "Open Expert QC"
    queue_empty_message = "No media awaiting expert review."


class MediaRowsRearrangedQueueView(MediaQCQueueView):
    filters = {"rows_rearranged": True}
    allowed_roles = {"expert"}
    queue_title = "Media with rearranged rows"
    queue_description = "Media flagged during QC because the accession rows were rearranged."
    queue_action_url_name = "media_expert_qc"
    queue_action_label = "Open Expert QC"
    queue_empty_message = "No media are currently flagged for row rearrangements."


class MediaWithCommentsQueueView(MediaQCQueueView):
    filters = {"qc_logs__comments__isnull": False}
    allowed_roles = {"expert"}
    queue_title = "Media with QC comments"
    queue_description = "Items that have at least one QC discussion comment."
    queue_action_url_name = "media_expert_qc"
    queue_action_label = "Open Expert QC"
    queue_empty_message = "No media entries have QC comments yet."


class MediaQCHistoryView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Display a paginated timeline of media QC activity."""

    model = MediaQCLog
    template_name = "cms/qc/history.html"
    context_object_name = "qc_logs"
    paginate_by = 25
    raise_exception = True
    filter_media: Media | None = None

    def test_func(self) -> bool:
        user = self.request.user
        return user.is_superuser or user.is_staff

    def get_queryset(self):
        queryset = (
            MediaQCLog.objects.select_related("media", "changed_by")
            .prefetch_related(_QC_COMMENT_PREFETCH)
            .order_by("-created_on")
        )
        media_uuid = self.request.GET.get("media")
        self.filter_media = None
        if media_uuid:
            queryset = queryset.filter(media__uuid=media_uuid)
            self.filter_media = Media.objects.filter(uuid=media_uuid).first()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_media"] = self.filter_media
        context["page_title"] = "Media QC History"
        return context


def index(request):
    """View function for home page of site."""
    if request.user.is_authenticated:
        return dashboard(request)
    return render(request, 'index.html')

def base_generic(request):
    return render(request, 'base_generic.html')

def fieldslip_create(request):
    if request.method == 'POST':
        form = FieldSlipForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('fieldslip_list')  #  to redirect to the list view
    else:
        form = FieldSlipForm()
    return render(request, 'cms/fieldslip_form.html', {'form': form})

def fieldslip_edit(request, pk):
    fieldslip = get_object_or_404(FieldSlip, pk=pk)
    if request.method == 'POST':
        form = FieldSlipForm(request.POST, request.FILES, instance=fieldslip)
        if form.is_valid():
            form.save()
            return redirect('fieldslip_detail', pk=fieldslip.pk)  # Redirect to the detail view
    else:
        form = FieldSlipForm(instance=fieldslip)
    return render(request, 'cms/fieldslip_form.html', {'form': form})

@staff_member_required
def generate_accession_batch(request):
    form = AccessionBatchForm(request.POST or None)
    series_remaining = None
    series_range = None

    if request.method == "POST" and form.is_valid():
        user = form.cleaned_data['user']
        try:
            # Get user's active accession number series
            series = AccessionNumberSeries.objects.get(user=user, is_active=True)
            series_remaining = series.end_at - series.current_number + 1
            series_range = f"from {series.current_number} to {series.end_at}"

            # Try to generate accessions
            try:
                accessions = generate_accessions_from_series(
                    series_user=user,
                    count=form.cleaned_data['count'],
                    collection=form.cleaned_data['collection'],
                    specimen_prefix=form.cleaned_data['specimen_prefix'],
                    creator_user=request.user
                )
                messages.success(
                    request,
                    f"Successfully created {len(accessions)} accessions for {user}."
                )
                return redirect("accession_list")

            except ValueError as ve:
                form.add_error('count', f"{ve} (Available range: {series_range})")

        except AccessionNumberSeries.DoesNotExist:
            form.add_error('user', "No active accession number series found for this user.")

    return render(request, "cms/accession_batch_form.html", {
        "form": form,
        "series_remaining": series_remaining,
        "series_range": series_range,
        "title": "Accession Numbers",
        "method": "post",
        "action": request.path,
    })

def reference_create(request):
    if request.method == 'POST':
        form = ReferenceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('reference_list')  #  to redirect to the list view
    else:
        form = ReferenceForm()
    return render(request, 'cms/reference_form.html', {'form': form})


@login_required
@user_passes_test(is_collection_manager)
def locality_create(request):
    if request.method == 'POST':
        form = LocalityForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('locality_list')
    else:
        form = LocalityForm()

    return render(request, 'cms/locality_form.html', {'form': form})


def reference_edit(request, pk):

    reference = get_object_or_404(Reference, pk=pk)
    if request.method == 'POST':
        form = ReferenceForm(request.POST, request.FILES, instance=reference)
        if form.is_valid():
            form.save()
            return redirect('reference_detail', pk=reference.pk)  # Redirect to the detail view
    else:
        form = ReferenceForm(instance=reference)
    return render(request, 'cms/reference_form.html', {'form': form})


def locality_edit(request, pk):
    
    locality = get_object_or_404(Locality, pk=pk)
    if request.method == 'POST':
        form = LocalityForm(request.POST, request.FILES, instance=locality)
        if form.is_valid():
            form.save()
            return redirect('locality_detail', pk=locality.pk)  # Redirect to the detail view
    else:
        form = LocalityForm(instance=locality)
    return render(request, 'cms/locality_form.html', {'form': form})


@login_required
@user_passes_test(can_manage_places)
def place_create(request):
    if request.method == 'POST':
        form = PlaceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('place_list')
    else:
        form = PlaceForm()
    return render(request, 'cms/place_form.html', {'form': form})


@login_required
@user_passes_test(can_manage_places)
def place_edit(request, pk):
    place = get_object_or_404(Place, pk=pk)
    if request.method == 'POST':
        form = PlaceForm(request.POST, instance=place)
        if form.is_valid():
            form.save()
            return redirect('place_detail', pk=place.pk)
    else:
        form = PlaceForm(instance=place)
    return render(request, 'cms/place_form.html', {'form': form})


class FieldSlipDetailView(DetailView):
    model = FieldSlip
    template_name = 'cms/fieldslip_detail.html'
    context_object_name = 'fieldslip'

class FieldSlipListView(LoginRequiredMixin, UserPassesTestMixin, FilterView):
    model = FieldSlip
    template_name = 'cms/fieldslip_list.html'
    context_object_name = 'fieldslips'
    paginate_by = 10

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.groups.filter(name="Collection Managers").exists()

class AccessionDetailView(DetailView):
    model = Accession
    template_name = 'cms/accession_detail.html'
    context_object_name = 'accession'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and (
            user.is_superuser or
            user.groups.filter(name__in=["Collection Managers", "Curators"]).exists()
        ):
            return qs
        return qs.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["related_fieldslips"] = self.object.fieldslip_links.all()
        context['references'] = AccessionReference.objects.filter(accession=self.object).select_related('reference')
        context['geologies'] = SpecimenGeology.objects.filter(accession=self.object)
        context['comments'] = Comment.objects.filter(specimen_no=self.object)
        accession_rows = AccessionRow.objects.filter(accession=self.object).prefetch_related(
            Prefetch(
                'natureofspecimen_set',
                queryset=NatureOfSpecimen.objects.select_related('element'),
            )
        )
        # Form for adding existing FieldSlips
        context["add_fieldslip_form"] = AccessionFieldSlipForm()

        # Store first identification and identification count per accession row
        first_identifications = {}
        identification_counts = {}
        taxonomy_dict = {}

        for accession_row in accession_rows:
            # Get all identifications for this accession row (already sorted)
            row_identifications = Identification.objects.filter(accession_row=accession_row).order_by('-date_identified')

            # Store the first identification if available
            first_identification = row_identifications.first()
            if first_identification:
                first_identifications[accession_row.id] = first_identification
                identification_counts[accession_row.id] = row_identifications.count()

                # Retrieve taxonomy based on taxon_name
                taxon_name = first_identification.taxon
                if taxon_name:
                    taxonomy_dict[first_identification.id] = Taxon.objects.filter(taxon_name__iexact=taxon_name).first()

        # Pass filtered data to template
        context['accession_rows'] = accession_rows
        context['first_identifications'] = first_identifications  # First identifications per accession row
        context['identification_counts'] = identification_counts  # Number of identifications per accession row
        context['taxonomy'] = taxonomy_dict  # Maps first identifications to Taxon objects
        
        return context

from django.contrib.auth.mixins import LoginRequiredMixin

from django.views.generic import ListView
from django_filters.views import FilterView

class AccessionListView(FilterView):
    model = Accession
    context_object_name = 'accessions'
    template_name = 'cms/accession_list.html'
    paginate_by = 10
    filterset_class = AccessionFilter

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if not (
            user.is_authenticated
            and (
                user.is_superuser
                or user.groups.filter(name__in=["Collection Managers", "Curators"]).exists()
            )
        ):
            qs = qs.filter(is_published=True)

        return prefetch_accession_related(qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        accessions = context.get('accessions')
        if accessions is not None:
            attach_accession_summaries(accessions)

        return context

class AccessionRowDetailView(DetailView):
    model = AccessionRow
    template_name = 'cms/accession_row_detail.html'
    context_object_name = 'accessionrow'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['natureofspecimens'] = NatureOfSpecimen.objects.filter(accession_row=self.object)
        context['identifications'] = Identification.objects.filter(accession_row=self.object)
        context['can_edit'] = (
            self.request.user.is_superuser or is_collection_manager(self.request.user)
        )
        context['can_manage'] = context['can_edit']
        context['show_inventory_status'] = not is_public_user(self.request.user)
        return context


class AccessionRowUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = AccessionRow
    form_class = AccessionRowUpdateForm
    template_name = 'cms/accession_row_form.html'
    context_object_name = 'accessionrow'

    def test_func(self):
        return self.request.user.is_superuser or is_collection_manager(self.request.user)

    def get_success_url(self):
        return self.object.get_absolute_url()

class AccessionWizard(SessionWizardView):
    file_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    form_list = [AccessionNumberSelectForm, AccessionForm, SpecimenCompositeForm]
    template_name = 'cms/accession_wizard.html'


    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        if step == '0' or step == 0:
            user = self.request.user
            try:
                series = AccessionNumberSeries.objects.get(user=user, is_active=True)
                used = set(
                    Accession.objects.filter(
                        accessioned_by=user,
                        specimen_no__gte=series.start_from,
                        specimen_no__lte=series.end_at
                    ).values_list('specimen_no', flat=True)
                )
                available = [
                    n for n in range(series.start_from, series.end_at + 1)
                    if n not in used
                ][:10]  # Limit to 10 available numbers
            except AccessionNumberSeries.DoesNotExist:
                available = []
            kwargs["available_numbers"] = available
        return kwargs

    def get_form_initial(self, step):
        initial = super().get_form_initial(step) or {}
        # Pass accession_number from step 0 to step 1
        if step == '1':
            step0_data = self.get_cleaned_data_for_step('0') or {}
            if 'accession_number' in step0_data:
                initial['specimen_no'] = step0_data['accession_number']
        # Pass specimen_no from step 1 to step 2 if needed
        if step == '2':
            step1_data = self.get_cleaned_data_for_step('1') or {}
            if 'specimen_no' in step1_data:
                initial['specimen_no'] = step1_data['specimen_no']
        return initial

    def process_step(self, form):
        """
        Save cleaned data for each step in storage.
        """
        step = self.steps.current
        cleaned = {}
        for key, value in form.cleaned_data.items():
            # Store PK for model instances, else value
            if hasattr(value, 'pk'):
                cleaned[key] = value.pk
            else:
                cleaned[key] = value
        self.storage.extra_data[f"step_{step}_data"] = cleaned
        return super().process_step(form)

    def get_form(self, step=None, data=None, files=None):
        """
        Restore initial values for fields from storage if available.
        """
        form = super().get_form(step, data, files)
        if step and data is None:
            initial = self.get_form_initial(step)
            if initial:
                for key, value in initial.items():
                    if key in form.fields:
                        field = form.fields[key]
                        if isinstance(field, forms.ModelChoiceField):
                            try:
                                form.fields[key].initial = field.queryset.get(pk=value)
                            except field.queryset.model.DoesNotExist:
                                pass
                        else:
                            form.fields[key].initial = value
        return form

    def done(self, form_list, **kwargs):
        """
        Finalize wizard: create Accession, AccessionRow, NatureOfSpecimen, and Identification.
        """
        select_form = form_list[0]
        accession_form = form_list[1]
        specimen_form = form_list[2]
        user = self.request.user
        accession_number = select_form.cleaned_data['accession_number']
        with transaction.atomic():

            accession = accession_form.save(commit=False)
            accession.accessioned_by = user
            accession.specimen_no = accession_number  # <-- Set value from wizard step 1!
            accession.save()
    
            storage = specimen_form.cleaned_data.get('storage')

            row = AccessionRow.objects.create(
                accession=accession,
                storage=storage
            )

            NatureOfSpecimen.objects.create(
                accession_row=row,
                element=specimen_form.cleaned_data['element'],
                side=specimen_form.cleaned_data['side'],
                condition=specimen_form.cleaned_data['condition'],
                fragments=specimen_form.cleaned_data.get('fragments') or 0,
            )

            Identification.objects.create(
                accession_row=row,
                taxon=specimen_form.cleaned_data['taxon'],
                identified_by=specimen_form.cleaned_data['identified_by'],
            )

        return redirect('accession-detail', pk=accession.pk)
    
class ReferenceDetailView(DetailView):
    model = Reference
    template_name = 'cms/reference_detail.html'
    context_object_name = 'reference'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        accession_references = self.object.accessionreference_set.select_related(
            "accession__collection",
            "accession__specimen_prefix",
            "accession__accessioned_by",
        ).order_by(
            "accession__collection__abbreviation",
            "accession__specimen_prefix__abbreviation",
            "accession__specimen_no",
            "accession__instance_number",
        )

        if not (
            user.is_authenticated
            and (
                user.is_superuser
                or user.groups.filter(name__in=["Collection Managers", "Curators"]).exists()
            )
        ):
            accession_references = accession_references.filter(accession__is_published=True)

        accession_ids = list(
            dict.fromkeys(accession_references.values_list("accession_id", flat=True))
        )

        accession_entries = []
        if accession_ids:
            accessions = list(
                prefetch_accession_related(
                    Accession.objects.filter(id__in=accession_ids)
                )
            )
            attach_accession_summaries(accessions)
            accession_map = {accession.id: accession for accession in accessions}

            for accession_reference in accession_references:
                accession = accession_map.get(accession_reference.accession_id)
                if accession is not None:
                    accession_entries.append((accession, accession_reference.page))

        doi_value = (self.object.doi or "").strip()
        if doi_value:
            if doi_value.lower().startswith("http"):
                context["doi_url"] = doi_value
            else:
                context["doi_url"] = f"https://doi.org/{doi_value}"

        context["accession_entries"] = accession_entries
        return context

class ReferenceListView(FilterView):
    model = Reference
    template_name = 'cms/reference_list.html'
    context_object_name = 'references'
    paginate_by = 10
    filterset_class = ReferenceFilter

    ordering_fields = {
        "first_author": "first_author",
        "year": "year",
        "title": "title",
        "accessions": "accession_count",
    }
    default_order = "first_author"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if is_public_user(user):
            queryset = queryset.annotate(
                accession_count=Count(
                    "accessionreference",
                    filter=Q(accessionreference__accession__is_published=True),
                    distinct=True,
                )
            ).filter(accession_count__gt=0)
        else:
            queryset = queryset.annotate(
                accession_count=Count("accessionreference", distinct=True)
            )

        sort_key = self.request.GET.get("sort") or self.default_order
        direction = self.request.GET.get("direction", "asc")

        if sort_key not in self.ordering_fields:
            sort_key = self.default_order
        if direction not in {"asc", "desc"}:
            direction = "asc"

        order_expression = self.ordering_fields[sort_key]
        if direction == "desc":
            order_expression = f"-{order_expression}"

        return queryset.order_by(order_expression, "title")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sort_key = self.request.GET.get("sort") or self.default_order
        direction = self.request.GET.get("direction", "asc")

        if sort_key not in self.ordering_fields:
            sort_key = self.default_order
        if direction not in {"asc", "desc"}:
            direction = "asc"

        context["current_sort"] = sort_key
        context["current_direction"] = direction
        context["sort_directions"] = {
            field: "desc" if sort_key == field and direction == "asc" else "asc"
            for field in self.ordering_fields
        }
        return context


class AccessionRowQCForm(AccessionRowUpdateForm):
    row_id = forms.CharField(widget=forms.HiddenInput())
    order = forms.IntegerField(widget=forms.HiddenInput())
    storage_datalist_id = "qc-storage-options"

    def __init__(self, *args, **kwargs):
        initial = kwargs.get('initial') or {}
        storage_display = initial.get('storage_display')

        super().__init__(*args, **kwargs)

        suffixes = [('-', '-')] + [
            (suffix, suffix) for suffix in AccessionRow().generate_valid_suffixes()
        ]
        self.fields['specimen_suffix'].choices = suffixes

        original_storage_field = self.fields['storage']
        original_attrs = dict(original_storage_field.widget.attrs)
        original_attrs['list'] = self.storage_datalist_id
        original_attrs.setdefault('autocomplete', 'off')

        storage_initial = storage_display
        if not storage_initial:
            storage_pk = self.initial.get('storage')
            storage_obj = None
            if storage_pk:
                try:
                    storage_obj = Storage.objects.filter(pk=storage_pk).first()
                except (TypeError, ValueError):
                    storage_obj = None
            if storage_obj:
                storage_initial = storage_obj.area
            elif isinstance(storage_pk, str):
                storage_initial = storage_pk

        self.fields['storage'] = forms.CharField(
            label=original_storage_field.label,
            required=False,
            help_text=original_storage_field.help_text,
            max_length=255,
            widget=forms.TextInput(attrs=original_attrs),
        )

        if not self.is_bound:
            if storage_initial:
                self.initial['storage'] = storage_initial
            else:
                self.initial.pop('storage', None)
        self.initial.pop('storage_display', None)

        self.fields['status'].required = False
        self.fields['status'].widget = forms.HiddenInput()
        if not self.initial.get('status'):
            self.initial['status'] = InventoryStatus.UNKNOWN

    def clean_storage(self):
        value = self.cleaned_data.get('storage')
        if isinstance(value, str):
            value = value.strip()
        return value or None

    def _post_clean(self):  # type: ignore[override]
        """Skip model instance assignment so free-form storage strings validate."""
        return None


class HiddenDeleteFormSetMixin:
    def add_fields(self, form, index):
        super().add_fields(form, index)
        if not getattr(self, "can_delete", False):
            return
        delete_field = form.fields.get("DELETE")
        if delete_field is not None:
            delete_field.widget = forms.HiddenInput()
            delete_field.label = ""
            delete_field.help_text = ""


class HiddenDeleteFormSet(HiddenDeleteFormSetMixin, BaseFormSet):
    pass


class AccessionRowIdentificationQCForm(AccessionRowIdentificationForm):
    row_id = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in (
            'identified_by',
            'reference',
            'taxon',
            'identification_qualifier',
            'verbatim_identification',
            'identification_remarks',
            'date_identified',
        ):
            field = self.fields.get(field_name)
            if field is not None:
                field.required = False


class AccessionRowSpecimenQCForm(AccessionRowSpecimenForm):
    row_id = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in (
            'element',
            'side',
            'condition',
            'verbatim_element',
            'portion',
            'fragments',
        ):
                field = self.fields.get(field_name)
                if field is not None:
                    field.required = False


AccessionRowFormSet = formset_factory(AccessionRowQCForm, extra=0, can_delete=False)
IdentificationQCFormSet = formset_factory(
    AccessionRowIdentificationQCForm, extra=0, can_delete=True, formset=HiddenDeleteFormSet
)
SpecimenQCFormSet = formset_factory(
    AccessionRowSpecimenQCForm, extra=0, can_delete=True, formset=HiddenDeleteFormSet
)


class AccessionReferenceQCForm(forms.Form):
    ref_id = forms.CharField(required=False, widget=forms.HiddenInput())
    order = forms.IntegerField(required=False, widget=forms.HiddenInput())
    first_author = forms.CharField(label="First author", required=False, max_length=255)
    title = forms.CharField(label="Title", required=False, max_length=255)
    year = forms.CharField(label="Year", required=False, max_length=32)
    page = forms.CharField(label="Page", required=False, max_length=255)


class FieldSlipQCForm(forms.Form):
    slip_id = forms.CharField(widget=forms.HiddenInput())
    order = forms.IntegerField(widget=forms.HiddenInput())
    field_number = forms.CharField(label="Field number", required=False, max_length=255)
    verbatim_locality = forms.CharField(
        label="Verbatim locality",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    verbatim_taxon = forms.CharField(
        label="Verbatim taxon",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    verbatim_element = forms.CharField(
        label="Verbatim element",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    horizon_formation = forms.CharField(label="Formation", required=False, max_length=255)
    horizon_member = forms.CharField(label="Member", required=False, max_length=255)
    horizon_bed = forms.CharField(label="Bed or horizon", required=False, max_length=255)
    horizon_chronostratigraphy = forms.CharField(label="Chronostratigraphy", required=False, max_length=255)
    aerial_photo = forms.CharField(label="Aerial photo", required=False, max_length=255)
    verbatim_latitude = forms.CharField(label="Verbatim latitude", required=False, max_length=255)
    verbatim_longitude = forms.CharField(label="Verbatim longitude", required=False, max_length=255)
    verbatim_elevation = forms.CharField(label="Verbatim elevation", required=False, max_length=255)


ReferenceQCFormSet = formset_factory(AccessionReferenceQCForm, extra=0, can_delete=False)
FieldSlipQCFormSet = formset_factory(FieldSlipQCForm, extra=0, can_delete=False)


def _form_row_id(form):
    value = form['row_id'].value()
    if value in (None, ''):
        value = form.initial.get('row_id')
    return str(value or '')


def _form_order_value(form):
    value = form['order'].value()
    if value in (None, ''):
        value = form.initial.get('order')
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ident_payload_has_explicit_fields(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    for value in entry.values():
        if isinstance(value, dict) and 'interpreted' in value:
            return True
    return bool(entry)


def _natures_payload_has_meaningful_data(natures: list[dict]) -> bool:
    for nature in natures or []:
        if not isinstance(nature, dict):
            continue
        for key in (
            'element_name',
            'side',
            'condition',
            'verbatim_element',
            'portion',
            'fragments',
        ):
            interpreted = _interpreted_value(nature.get(key))
            if interpreted not in (None, ''):
                return True
            if key == 'fragments' and interpreted == 0:
                return True
    return False


def _set_interpreted(container: dict, key: str, value):
    existing = container.get(key)
    if not isinstance(existing, dict):
        existing = {}
    new_field = dict(existing)
    if isinstance(value, str):
        value = value.strip() or None
    elif isinstance(value, (date, datetime)):
        value = value.isoformat()
    if value in ('', None):
        new_field['interpreted'] = None
    else:
        new_field['interpreted'] = value
    container[key] = new_field
    return new_field


def _build_row_contexts(row_formset, ident_formset, specimen_formset):
    ident_map: dict[str, list] = {}
    for form in ident_formset.forms:
        row_id = _form_row_id(form)
        if not row_id:
            continue
        ident_map.setdefault(row_id, []).append(form)
    specimen_map: dict[str, list] = {}
    for form in specimen_formset.forms:
        row_id = _form_row_id(form)
        if not row_id:
            continue
        specimen_map.setdefault(row_id, []).append(form)
    contexts = []
    for form in row_formset.forms:
        row_id = _form_row_id(form)
        ident_forms = ident_map.get(row_id, [])
        specimens = specimen_map.get(row_id, [])
        contexts.append(
            {
                'row_form': form,
                'ident_forms': ident_forms,
                'specimen_forms': specimens,
                'row_id': row_id,
                'order': _form_order_value(form),
            }
        )
    contexts.sort(key=lambda item: item['order'])
    return contexts


def _collect_validation_messages(error: ValidationError) -> list[str]:
    if hasattr(error, "message_dict"):
        messages_list: list[str] = []
        for errors in error.message_dict.values():
            messages_list.extend(errors)
        return messages_list
    return list(getattr(error, "messages", [str(error)]))


def _create_qc_comment(media: Media, comment: str | None, user) -> MediaQCComment | None:
    if not comment:
        return None
    log = (
        MediaQCLog.objects.filter(
            media=media, change_type=MediaQCLog.ChangeType.STATUS
        )
        .order_by("-created_on")
        .first()
    )
    if not log:
        return None
    return MediaQCComment.objects.create(log=log, comment=comment, created_by=user)


def _get_qc_comments(media: Media) -> list[MediaQCComment]:
    return list(
        MediaQCComment.objects.filter(log__media=media)
        .select_related("created_by", "log")
        .order_by("created_on")
    )


_QC_COMMENT_PREFETCH = Prefetch(
    "comments",
    queryset=MediaQCComment.objects.select_related("created_by").order_by("created_on"),
)


def _get_qc_history(media: Media, limit: int | None = None) -> list[MediaQCLog]:
    queryset = (
        MediaQCLog.objects.filter(media=media)
        .select_related("changed_by", "media")
        .prefetch_related(_QC_COMMENT_PREFETCH)
        .order_by("-created_on")
    )
    if limit is not None:
        return list(queryset[:limit])
    return list(queryset)


class MediaQCFormManager:
    """Prepare and persist media QC forms shared by intern and expert wizards."""

    def __init__(self, request, media: Media):
        self.request = request
        self.media = media

        stored_data = copy.deepcopy(media.ocr_data or {})
        snapshot_source = stored_data.get("_original_snapshot")
        if snapshot_source is None:
            snapshot_source = copy.deepcopy(stored_data)
            stored_data["_original_snapshot"] = copy.deepcopy(snapshot_source)
            media.ocr_data = stored_data
            media.save(update_fields=["ocr_data"])
        self.original_data = copy.deepcopy(snapshot_source)
        self.data = copy.deepcopy(media.ocr_data or stored_data)
        accessions = self.data.setdefault("accessions", [])
        if not accessions:
            accessions.append({})
        self.accession_payload = accessions[0]
        self.rows_payload = list(self.accession_payload.get("rows") or [])
        self.storage_suggestions = list(
            Storage.objects.order_by("area").values_list("area", flat=True)
        )
        ident_payload = list(self.accession_payload.get("identifications") or [])
        if len(ident_payload) < len(self.rows_payload):
            ident_payload.extend(
                {} for _ in range(len(self.rows_payload) - len(ident_payload))
            )
        propagated_ident_payload: list[dict] = []
        last_ident_snapshot: dict | None = None
        for entry in ident_payload:
            entry = entry or {}
            if _ident_payload_has_meaningful_data(entry):
                last_ident_snapshot = copy.deepcopy(entry)
                propagated_ident_payload.append(entry)
            elif last_ident_snapshot and not _ident_payload_has_explicit_fields(entry):
                propagated_ident_payload.append(copy.deepcopy(last_ident_snapshot))
            else:
                propagated_ident_payload.append(entry)
        ident_payload = propagated_ident_payload
        self.ident_payload = ident_payload
        self.row_initial: list[dict] = []
        self.ident_initial: list[dict] = []
        self.specimen_initial: list[dict] = []
        self.reference_initial: list[dict] = []
        self.fieldslip_initial: list[dict] = []
        self.row_payload_map: dict[str, dict] = {}
        self.ident_payload_map: dict[str, dict] = {}
        self.reference_payload_map: dict[str, dict] = {}
        self.fieldslip_payload_map: dict[str, dict] = {}
        self.original_row_ids: list[str] = []

        last_natures_snapshot: list[dict] = []

        for index, row_payload in enumerate(self.rows_payload):
            row_id = (
                row_payload.get("_row_id")
                or row_payload.get("row_id")
                or f"row-{index}"
            )
            self.original_row_ids.append(row_id)
            self.row_payload_map[row_id] = row_payload
            ident_entry = ident_payload[index] if index < len(ident_payload) else {}
            self.ident_payload_map[row_id] = ident_entry

            suffix = (row_payload.get("specimen_suffix") or {}).get("interpreted") or "-"
            storage_name = (row_payload.get("storage_area") or {}).get("interpreted")
            if storage_name:
                self.storage_suggestions.append(storage_name)
            storage_obj = (
                Storage.objects.filter(area=storage_name).first()
                if storage_name
                else None
            )
            self.row_initial.append(
                {
                    "row_id": row_id,
                    "order": index,
                    "specimen_suffix": suffix,
                    "storage": storage_obj.pk if storage_obj else None,
                    "storage_display": storage_name,
                    "status": InventoryStatus.UNKNOWN,
                }
            )

            ident_data = self.ident_payload_map[row_id]
            identified_by_id = (ident_data.get("identified_by") or {}).get("interpreted")
            identified_by = (
                Person.objects.filter(pk=identified_by_id).first()
                if identified_by_id
                else None
            )
            reference_id = (ident_data.get("reference") or {}).get("interpreted")
            reference_obj = (
                Reference.objects.filter(pk=reference_id).first()
                if reference_id
                else None
            )
            self.ident_initial.append(
                {
                    "row_id": row_id,
                    "taxon": (ident_data.get("taxon") or {}).get("interpreted"),
                    "identification_qualifier": (
                        ident_data.get("identification_qualifier") or {}
                    ).get("interpreted"),
                    "verbatim_identification": (
                        ident_data.get("verbatim_identification") or {}
                    ).get("interpreted"),
                    "identification_remarks": (
                        ident_data.get("identification_remarks") or {}
                    ).get("interpreted"),
                    "identified_by": identified_by.pk if identified_by else None,
                    "reference": reference_obj.pk if reference_obj else None,
                    "date_identified": (
                        ident_data.get("date_identified") or {}
                    ).get("interpreted"),
                }
            )

            natures_payload = row_payload.get("natures")
            if not isinstance(natures_payload, list):
                natures_payload = []
            if _natures_payload_has_meaningful_data(natures_payload):
                last_natures_snapshot = copy.deepcopy(natures_payload)
            elif last_natures_snapshot:
                natures_payload = copy.deepcopy(last_natures_snapshot)
                row_payload["natures"] = natures_payload

            for nature in natures_payload or []:
                element_name = (nature.get("element_name") or {}).get("interpreted")
                element_obj = (
                    Element.objects.filter(name=element_name).first()
                    if element_name
                    else None
                )
                self.specimen_initial.append(
                    {
                        "row_id": row_id,
                        "element": element_obj.pk if element_obj else None,
                        "side": (nature.get("side") or {}).get("interpreted"),
                        "condition": (nature.get("condition") or {}).get("interpreted"),
                        "verbatim_element": (
                            nature.get("verbatim_element") or {}
                        ).get("interpreted"),
                        "portion": (nature.get("portion") or {}).get("interpreted"),
                        "fragments": (
                            nature.get("fragments") or {}
                        ).get("interpreted"),
                    }
                )

        references_payload = list(self.accession_payload.get("references") or [])
        for index, reference_payload in enumerate(references_payload):
            ref_id = reference_payload.get("_ref_id") or f"ref-{index}"
            self.reference_payload_map[ref_id] = reference_payload
            self.reference_initial.append(
                {
                    "ref_id": ref_id,
                    "order": index,
                    "first_author": (
                        reference_payload.get("reference_first_author") or {}
                    ).get("interpreted"),
                    "title": (reference_payload.get("reference_title") or {}).get(
                        "interpreted"
                    ),
                    "year": (reference_payload.get("reference_year") or {}).get(
                        "interpreted"
                    ),
                    "page": (reference_payload.get("page") or {}).get("interpreted"),
                }
            )

        field_slips_payload = list(self.accession_payload.get("field_slips") or [])
        for index, field_slip_payload in enumerate(field_slips_payload):
            slip_id = field_slip_payload.get("_field_slip_id") or f"field-slip-{index}"
            self.fieldslip_payload_map[slip_id] = field_slip_payload
            horizon_payload = field_slip_payload.get("verbatim_horizon") or {}
            self.fieldslip_initial.append(
                {
                    "slip_id": slip_id,
                    "order": index,
                    "field_number": (
                        field_slip_payload.get("field_number") or {}
                    ).get("interpreted"),
                    "verbatim_locality": (
                        field_slip_payload.get("verbatim_locality") or {}
                    ).get("interpreted"),
                    "verbatim_taxon": (
                        field_slip_payload.get("verbatim_taxon") or {}
                    ).get("interpreted"),
                    "verbatim_element": (
                        field_slip_payload.get("verbatim_element") or {}
                    ).get("interpreted"),
                    "horizon_formation": (
                        horizon_payload.get("formation") or {}
                    ).get("interpreted"),
                    "horizon_member": (
                        horizon_payload.get("member") or {}
                    ).get("interpreted"),
                    "horizon_bed": (
                        horizon_payload.get("bed_or_horizon") or {}
                    ).get("interpreted"),
                    "horizon_chronostratigraphy": (
                        horizon_payload.get("chronostratigraphy") or {}
                    ).get("interpreted"),
                    "aerial_photo": (
                        field_slip_payload.get("aerial_photo") or {}
                    ).get("interpreted"),
                    "verbatim_latitude": (
                        field_slip_payload.get("verbatim_latitude") or {}
                    ).get("interpreted"),
                    "verbatim_longitude": (
                        field_slip_payload.get("verbatim_longitude") or {}
                    ).get("interpreted"),
                    "verbatim_elevation": (
                        field_slip_payload.get("verbatim_elevation") or {}
                    ).get("interpreted"),
                }
            )

        self.storage_suggestions = list(
            dict.fromkeys(value for value in self.storage_suggestions if value)
        )

        collection_abbr = (
            self.accession_payload.get("collection_abbreviation") or {}
        ).get("interpreted")
        collection_obj = (
            Collection.objects.filter(abbreviation=collection_abbr).first()
            if collection_abbr
            else None
        )
        prefix_abbr = (
            self.accession_payload.get("specimen_prefix_abbreviation") or {}
        ).get("interpreted")
        prefix_obj = (
            Locality.objects.filter(abbreviation=prefix_abbr).first()
            if prefix_abbr
            else None
        )
        specimen_no_value = (
            self.accession_payload.get("specimen_no") or {}
        ).get("interpreted")
        try:
            specimen_no_initial = int(specimen_no_value)
        except (TypeError, ValueError):
            specimen_no_initial = specimen_no_value
        type_status_initial = (
            self.accession_payload.get("type_status") or {}
        ).get("interpreted")
        comment_initial = (
            self.accession_payload.get("comment") or {}
        ).get("interpreted")
        accession_instance = getattr(media, "accession", None) or Accession()
        accessioned_by_user = (
            getattr(getattr(media, "accession", None), "accessioned_by", None)
            or request.user
        )

        self.acc_initial = {
            "collection": collection_obj,
            "specimen_prefix": prefix_obj,
            "specimen_no": specimen_no_initial,
            "type_status": type_status_initial,
            "comment": comment_initial,
            "accessioned_by": accessioned_by_user,
        }
        self.accession_instance = accession_instance

        self.accession_form: AccessionForm | None = None
        self.row_formset = None
        self.ident_formset = None
        self.specimen_formset = None
        self.reference_formset = None
        self.fieldslip_formset = None
        self.row_contexts: list[dict] = []
        self.last_diff_result: dict[str, object] | None = None

    def build_forms(self) -> None:
        if self.request.method == "POST":
            self.accession_form = AccessionForm(
                self.request.POST,
                prefix="accession",
                instance=self.accession_instance,
            )
            self.row_formset = AccessionRowFormSet(self.request.POST, prefix="row")
            self.ident_formset = IdentificationQCFormSet(
                self.request.POST, prefix="ident"
            )
            self.specimen_formset = SpecimenQCFormSet(
                self.request.POST, prefix="specimen"
            )
            self.reference_formset = ReferenceQCFormSet(
                self.request.POST, prefix="reference"
            )
            self.fieldslip_formset = FieldSlipQCFormSet(
                self.request.POST, prefix="fieldslip"
            )
        else:
            self.accession_form = AccessionForm(
                prefix="accession",
                instance=self.accession_instance,
                initial=self.acc_initial,
            )
            self.row_formset = AccessionRowFormSet(
                prefix="row", initial=self.row_initial
            )
            self.ident_formset = IdentificationQCFormSet(
                prefix="ident", initial=self.ident_initial
            )
            self.specimen_formset = SpecimenQCFormSet(
                prefix="specimen", initial=self.specimen_initial
            )
            self.reference_formset = ReferenceQCFormSet(
                prefix="reference", initial=self.reference_initial
            )
            self.fieldslip_formset = FieldSlipQCFormSet(
                prefix="fieldslip", initial=self.fieldslip_initial
            )

        comment_field = self.accession_form.fields.get("comment")
        if comment_field is not None:
            comment_field.widget.attrs.setdefault("rows", 2)

        for form in self.ident_formset:
            remarks_field = form.fields.get("identification_remarks")
            if remarks_field is not None:
                remarks_field.widget.attrs.setdefault("rows", 2)

        self.row_contexts = _build_row_contexts(
            self.row_formset, self.ident_formset, self.specimen_formset
        )

    def forms_valid(self) -> bool:
        return (
            self.accession_form.is_valid()
            and self.row_formset.is_valid()
            and self.ident_formset.is_valid()
            and self.specimen_formset.is_valid()
            and self.reference_formset.is_valid()
            and self.fieldslip_formset.is_valid()
        )

    def save(self) -> dict[str, object]:
        cleaned_rows = []
        for form in self.row_formset:
            cleaned = form.cleaned_data
            if not cleaned:
                continue
            row_id = cleaned.get("row_id") or form.initial.get("row_id")
            if not row_id:
                continue
            try:
                order_value = int(cleaned.get("order"))
            except (TypeError, ValueError):
                order_value = len(cleaned_rows)
            storage_value = cleaned.get("storage")
            if isinstance(storage_value, str):
                storage_value = storage_value.strip()
            elif storage_value is not None and hasattr(storage_value, "area"):
                storage_value = storage_value.area
            if storage_value == "":
                storage_value = None
            cleaned_rows.append(
                {
                    "row_id": row_id,
                    "order": order_value,
                    "specimen_suffix": cleaned.get("specimen_suffix") or "-",
                    "storage": storage_value,
                    "status": cleaned.get("status"),
                }
            )

        ident_clean_map: dict[str, dict] = {}
        for form in self.ident_formset:
            cleaned = form.cleaned_data
            if not cleaned:
                continue
            if cleaned.get('DELETE'):
                continue
            row_id = cleaned.get("row_id")
            if not row_id:
                continue
            ident_clean_map[row_id] = cleaned

        specimen_clean_map: dict[str, list[dict]] = {}
        for form in self.specimen_formset:
            cleaned = form.cleaned_data
            if not cleaned:
                continue
            if cleaned.get('DELETE'):
                continue
            row_id = cleaned.get("row_id")
            if not row_id:
                continue
            element_obj = cleaned.get("element")
            if not element_obj and not any(
                cleaned.get(field)
                for field in (
                    "side",
                    "condition",
                    "verbatim_element",
                    "portion",
                    "fragments",
                )
            ):
                continue
            specimen_clean_map.setdefault(row_id, []).append(cleaned)

        reference_entries: list[dict] = []
        for form in self.reference_formset:
            cleaned = form.cleaned_data
            if not cleaned:
                continue

            def _normalize(value):
                if isinstance(value, str):
                    value = value.strip()
                return value or None

            first_author = _normalize(cleaned.get("first_author"))
            title = _normalize(cleaned.get("title"))
            year = _normalize(cleaned.get("year"))
            page = _normalize(cleaned.get("page"))

            if not any((first_author, title, year, page)):
                continue

            ref_id = _normalize(cleaned.get("ref_id")) or _normalize(
                form.initial.get("ref_id")
            )
            if not ref_id:
                ref_id = f"ref-{len(reference_entries)}"
            try:
                order_value = int(cleaned.get("order"))
            except (TypeError, ValueError):
                order_value = len(reference_entries)
            reference_entries.append(
                {
                    "ref_id": ref_id,
                    "order": order_value,
                    "first_author": first_author,
                    "title": title,
                    "year": year,
                    "page": page,
                }
            )

        fieldslip_entries: list[dict] = []
        for form in self.fieldslip_formset:
            cleaned = form.cleaned_data
            if not cleaned:
                continue
            slip_id = (
                cleaned.get("slip_id")
                or form.initial.get("slip_id")
                or f"field-slip-{len(fieldslip_entries)}"
            )
            try:
                order_value = int(cleaned.get("order"))
            except (TypeError, ValueError):
                order_value = len(fieldslip_entries)
            fieldslip_entries.append(
                {
                    "slip_id": slip_id,
                    "order": order_value,
                    "field_number": cleaned.get("field_number"),
                    "verbatim_locality": cleaned.get("verbatim_locality"),
                    "verbatim_taxon": cleaned.get("verbatim_taxon"),
                    "verbatim_element": cleaned.get("verbatim_element"),
                    "horizon_formation": cleaned.get("horizon_formation"),
                    "horizon_member": cleaned.get("horizon_member"),
                    "horizon_bed": cleaned.get("horizon_bed"),
                    "horizon_chronostratigraphy": cleaned.get(
                        "horizon_chronostratigraphy"
                    ),
                    "aerial_photo": cleaned.get("aerial_photo"),
                    "verbatim_latitude": cleaned.get("verbatim_latitude"),
                    "verbatim_longitude": cleaned.get("verbatim_longitude"),
                    "verbatim_elevation": cleaned.get("verbatim_elevation"),
                }
            )

        sorted_rows = sorted(cleaned_rows, key=lambda item: item["order"])
        existing_new_order = [
            entry["row_id"]
            for entry in sorted_rows
            if entry["row_id"] in self.row_payload_map
        ]
        rows_rearranged = existing_new_order != self.original_row_ids[: len(existing_new_order)]

        sorted_references = sorted(reference_entries, key=lambda item: item["order"])
        sorted_fieldslips = sorted(fieldslip_entries, key=lambda item: item["order"])

        cleaned_accession = self.accession_form.cleaned_data
        collection_obj = cleaned_accession.get("collection")
        prefix_obj = cleaned_accession.get("specimen_prefix")
        specimen_no_cleaned = cleaned_accession.get("specimen_no")
        type_status_cleaned = cleaned_accession.get("type_status")
        comment_cleaned = cleaned_accession.get("comment")

        storage_cache: dict[str, Storage] = {}

        diff_result: dict[str, object] = {
            "field_diffs": [],
            "rows_reordered": rows_rearranged,
            "count_diffs": [],
            "warnings": [],
        }

        with transaction.atomic():
            _set_interpreted(
                self.accession_payload,
                "collection_abbreviation",
                collection_obj.abbreviation if collection_obj else None,
            )
            _set_interpreted(
                self.accession_payload,
                "specimen_prefix_abbreviation",
                prefix_obj.abbreviation if prefix_obj else None,
            )
            _set_interpreted(
                self.accession_payload,
                "specimen_no",
                specimen_no_cleaned,
            )
            _set_interpreted(
                self.accession_payload,
                "type_status",
                type_status_cleaned,
            )
            _set_interpreted(
                self.accession_payload,
                "comment",
                comment_cleaned,
            )

            updated_rows = []
            updated_identifications = []
            for entry in sorted_rows:
                row_id = entry["row_id"]
                original_row = copy.deepcopy(self.row_payload_map.get(row_id, {}))
                _set_interpreted(
                    original_row,
                    "specimen_suffix",
                    entry["specimen_suffix"],
                )
                storage_value = entry["storage"]
                storage_name = None
                if isinstance(storage_value, str) and storage_value:
                    cache_key = storage_value.lower()
                    storage_obj = storage_cache.get(cache_key)
                    if storage_obj is None:
                        storage_obj = Storage.objects.filter(
                            area__iexact=storage_value
                        ).first()
                        if storage_obj is None:
                            storage_obj = Storage.objects.create(area=storage_value)
                        storage_cache[cache_key] = storage_obj
                    storage_name = storage_obj.area
                elif isinstance(storage_value, Storage):
                    storage_name = storage_value.area
                _set_interpreted(original_row, "storage_area", storage_name)

                original_natures = original_row.get("natures") or []
                new_natures = []
                specimens = specimen_clean_map.get(row_id, [])
                for index, specimen_data in enumerate(specimens):
                    original_nature = (
                        copy.deepcopy(original_natures[index])
                        if index < len(original_natures)
                        else {}
                    )
                    element_obj = specimen_data.get("element")
                    element_name = element_obj.name if element_obj else None
                    _set_interpreted(original_nature, "element_name", element_name)
                    _set_interpreted(
                        original_nature,
                        "side",
                        specimen_data.get("side"),
                    )
                    _set_interpreted(
                        original_nature,
                        "condition",
                        specimen_data.get("condition"),
                    )
                    _set_interpreted(
                        original_nature,
                        "verbatim_element",
                        specimen_data.get("verbatim_element"),
                    )
                    _set_interpreted(
                        original_nature,
                        "portion",
                        specimen_data.get("portion"),
                    )
                    _set_interpreted(
                        original_nature,
                        "fragments",
                        specimen_data.get("fragments"),
                    )
                    new_natures.append(original_nature)
                original_row["natures"] = new_natures
                updated_rows.append(original_row)

                ident_cleaned = ident_clean_map.get(row_id, {})
                original_ident = copy.deepcopy(
                    self.ident_payload_map.get(row_id, {})
                )
                _set_interpreted(
                    original_ident, "taxon", ident_cleaned.get("taxon")
                )
                _set_interpreted(
                    original_ident,
                    "identification_qualifier",
                    ident_cleaned.get("identification_qualifier"),
                )
                _set_interpreted(
                    original_ident,
                    "verbatim_identification",
                    ident_cleaned.get("verbatim_identification"),
                )
                _set_interpreted(
                    original_ident,
                    "identification_remarks",
                    ident_cleaned.get("identification_remarks"),
                )
                identified_by_obj = ident_cleaned.get("identified_by")
                _set_interpreted(
                    original_ident,
                    "identified_by",
                    identified_by_obj.pk if identified_by_obj else None,
                )
                reference_obj = ident_cleaned.get("reference")
                _set_interpreted(
                    original_ident,
                    "reference",
                    reference_obj.pk if reference_obj else None,
                )
                _set_interpreted(
                    original_ident,
                    "date_identified",
                    ident_cleaned.get("date_identified"),
                )
                updated_identifications.append(original_ident)

            self.accession_payload["rows"] = updated_rows
            self.accession_payload["identifications"] = updated_identifications

            updated_references = []
            for entry in sorted_references:
                ref_id = entry["ref_id"]
                original_reference = copy.deepcopy(
                    self.reference_payload_map.get(ref_id, {})
                )
                _set_interpreted(
                    original_reference,
                    "reference_first_author",
                    entry.get("first_author"),
                )
                _set_interpreted(
                    original_reference,
                    "reference_title",
                    entry.get("title"),
                )
                _set_interpreted(
                    original_reference,
                    "reference_year",
                    entry.get("year"),
                )
                _set_interpreted(original_reference, "page", entry.get("page"))
                updated_references.append(original_reference)

            self.accession_payload["references"] = updated_references

            updated_field_slips = []
            for entry in sorted_fieldslips:
                slip_id = entry["slip_id"]
                original_field_slip = copy.deepcopy(
                    self.fieldslip_payload_map.get(slip_id, {})
                )
                _set_interpreted(
                    original_field_slip,
                    "field_number",
                    entry.get("field_number"),
                )
                _set_interpreted(
                    original_field_slip,
                    "verbatim_locality",
                    entry.get("verbatim_locality"),
                )
                _set_interpreted(
                    original_field_slip,
                    "verbatim_taxon",
                    entry.get("verbatim_taxon"),
                )
                _set_interpreted(
                    original_field_slip,
                    "verbatim_element",
                    entry.get("verbatim_element"),
                )
                horizon_payload = original_field_slip.get("verbatim_horizon") or {}
                horizon_payload = copy.deepcopy(horizon_payload)
                _set_interpreted(
                    horizon_payload,
                    "formation",
                    entry.get("horizon_formation"),
                )
                _set_interpreted(
                    horizon_payload,
                    "member",
                    entry.get("horizon_member"),
                )
                _set_interpreted(
                    horizon_payload,
                    "bed_or_horizon",
                    entry.get("horizon_bed"),
                )
                _set_interpreted(
                    horizon_payload,
                    "chronostratigraphy",
                    entry.get("horizon_chronostratigraphy"),
                )
                original_field_slip["verbatim_horizon"] = horizon_payload
                _set_interpreted(
                    original_field_slip,
                    "aerial_photo",
                    entry.get("aerial_photo"),
                )
                _set_interpreted(
                    original_field_slip,
                    "verbatim_latitude",
                    entry.get("verbatim_latitude"),
                )
                _set_interpreted(
                    original_field_slip,
                    "verbatim_longitude",
                    entry.get("verbatim_longitude"),
                )
                _set_interpreted(
                    original_field_slip,
                    "verbatim_elevation",
                    entry.get("verbatim_elevation"),
                )
                updated_field_slips.append(original_field_slip)

            self.accession_payload["field_slips"] = updated_field_slips
            self.data["accessions"][0] = self.accession_payload

            diff_result = diff_media_payload(
                self.original_data,
                self.data,
                rows_reordered=rows_rearranged,
            )

            self.media.ocr_data = self.data
            self.media.rows_rearranged = rows_rearranged
            self.media.save(update_fields=["ocr_data", "rows_rearranged"])

        field_diffs = diff_result.get("field_diffs", [])
        for path, old_val, new_val in field_diffs:
            if not path:
                continue
            MediaQCLog.objects.create(
                media=self.media,
                change_type=MediaQCLog.ChangeType.OCR_DATA,
                field_name=path,
                old_value={"value": old_val},
                new_value={"value": new_val},
                changed_by=self.request.user,
            )

        self.last_diff_result = diff_result
        return diff_result

@login_required
def MediaInternQCWizard(request, pk):
    media = get_object_or_404(Media, uuid=pk)

    if not is_intern(request.user):
        return HttpResponseForbidden("Intern access required.")

    manager = MediaQCFormManager(request, media)
    manager.build_forms()

    qc_comments = _get_qc_comments(media)
    latest_qc_comment = qc_comments[-1] if qc_comments else None

    if request.method == "POST":
        if manager.forms_valid():
            try:
                manager.save()
            except ValidationError as exc:
                for message in _collect_validation_messages(exc):
                    manager.accession_form.add_error(None, message)
                    messages.error(request, message)
            else:
                try:
                    media.transition_qc(
                        Media.QCStatus.PENDING_EXPERT,
                        user=request.user,
                    )
                except ValidationError as exc:
                    for message in _collect_validation_messages(exc):
                        manager.accession_form.add_error(None, message)
                        messages.error(request, message)
                else:
                    messages.success(
                        request, "Media forwarded for expert review."
                    )
                    return redirect("dashboard")

    qc_diff = manager.last_diff_result or diff_media_payload(
        manager.original_data,
        manager.data,
        rows_reordered=media.rows_rearranged,
    )
    qc_preview = build_preview_accession(
        manager.data,
        manager.accession_form,
        request_user=request.user,
    )

    form_media = _build_qc_form_media(manager)

    context = {
        "media": media,
        "accession_form": manager.accession_form,
        "row_formset": manager.row_formset,
        "ident_formset": manager.ident_formset,
        "specimen_formset": manager.specimen_formset,
        "reference_formset": manager.reference_formset,
        "fieldslip_formset": manager.fieldslip_formset,
        "row_contexts": manager.row_contexts,
        "storage_suggestions": manager.storage_suggestions,
        "storage_datalist_id": AccessionRowQCForm.storage_datalist_id,
        "qc_comments": qc_comments,
        "latest_qc_comment": latest_qc_comment,
        "qc_history_logs": _get_qc_history(media, limit=10),
        "qc_diff": qc_diff,
        "qc_preview": qc_preview,
        "qc_acknowledged_warnings": set(),
        "form_media": form_media,
    }

    return render(request, "cms/qc/intern_wizard.html", context)


def _parse_conflict_resolution(post_data, conflicts):
    resolution_map: dict[str, dict[str, object]] = {}
    missing: list[str] = []

    conflicts_by_html = {
        conflict.get("html_key"): conflict
        for conflict in conflicts
        if conflict.get("html_key") and conflict.get("key")
    }

    for html_key, conflict in conflicts_by_html.items():
        key = conflict["key"]
        action = post_data.get(f"resolution_action__{html_key}")
        if not action:
            missing.append(key)
            continue

        if action == "new_instance":
            resolution_map[key] = {"action": "new_instance"}
            continue

        if action != "update_existing":
            missing.append(key)
            continue

        entry: dict[str, object] = {"action": "update_existing"}

        target_value = post_data.get(f"target_accession__{html_key}")
        if target_value and str(target_value).isdigit():
            entry["accession_id"] = int(target_value)

        fields: dict[str, object] = {}
        proposed = conflict.get("proposed", {})
        for field_name in ("type_status", "comment"):
            if post_data.get(f"apply_field__{html_key}__{field_name}"):
                fields[field_name] = proposed.get(field_name)
        entry["fields"] = fields

        references: list[int] = []
        for ref in proposed.get("references", []):
            index = ref.get("index")
            if index is None:
                continue
            field_name = f"add_reference__{html_key}__{index}"
            if post_data.get(field_name):
                try:
                    references.append(int(index))
                except (TypeError, ValueError):
                    continue
        entry["references"] = references

        field_slips: list[int] = []
        for slip in proposed.get("field_slips", []):
            index = slip.get("index")
            if index is None:
                continue
            field_name = f"add_field_slip__{html_key}__{index}"
            if post_data.get(field_name):
                try:
                    field_slips.append(int(index))
                except (TypeError, ValueError):
                    continue
        entry["field_slips"] = field_slips

        rows: list[str] = []
        for row in proposed.get("rows", []):
            html_suffix = row.get("html_suffix")
            specimen_suffix = row.get("specimen_suffix")
            if not html_suffix or specimen_suffix in (None, ""):
                continue
            if post_data.get(f"replace_row__{html_key}__{html_suffix}"):
                rows.append(str(specimen_suffix))
        entry["rows"] = rows

        resolution_map[key] = entry

    return resolution_map, missing


def _annotate_conflict_selections(conflicts, resolution_map):
    for conflict in conflicts:
        key = conflict.get("key")
        selection = resolution_map.get(key, {})
        conflict["selected_action"] = selection.get("action")
        conflict["selected_accession_id"] = selection.get("accession_id")
        fields = selection.get("fields") or {}
        conflict["selected_fields"] = set(fields.keys())
        rows = selection.get("rows") or []
        conflict["selected_rows"] = {str(value) for value in rows}
        references = selection.get("references") or []
        conflict["selected_references"] = {
            int(value) for value in references if str(value).isdigit()
        }
        field_slips = selection.get("field_slips") or []
        conflict["selected_field_slips"] = {
            int(value) for value in field_slips if str(value).isdigit()
        }


def _build_qc_form_media(manager: "MediaQCFormManager") -> FormsMedia:
    combined = FormsMedia()
    for formish in (
        getattr(manager, "accession_form", None),
        getattr(manager, "row_formset", None),
        getattr(manager, "ident_formset", None),
        getattr(manager, "specimen_formset", None),
        getattr(manager, "reference_formset", None),
        getattr(manager, "fieldslip_formset", None),
    ):
        if not formish:
            continue
        media = getattr(formish, "media", None)
        if media:
            combined += media
    return combined


@login_required
def MediaExpertQCWizard(request, pk):
    media = get_object_or_404(Media, uuid=pk)

    user = request.user
    if not (
        user.is_superuser
        or user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
    ):
        return HttpResponseForbidden("Expert access required.")

    manager = MediaQCFormManager(request, media)
    manager.build_forms()

    qc_comment = ""
    action = "save"
    selected_resolution: dict[str, dict[str, object]] = {}
    conflict_details = describe_accession_conflicts(media)
    acknowledged_warnings: set[str] = set()
    diff_result: dict[str, object] | None = None
    warnings_map: dict[str, dict[str, object]] = {}

    if request.method == "POST":
        qc_comment = (request.POST.get("qc_comment") or "").strip()
        action = request.POST.get("action") or "save"
        acknowledged_warnings = {
            value for value in request.POST.getlist("acknowledge_warnings") if value
        }

        if manager.forms_valid():
            try:
                diff_result = manager.save()
            except ValidationError as exc:
                for message in _collect_validation_messages(exc):
                    manager.accession_form.add_error(None, message)
                    messages.error(request, message)
            else:
                conflict_details = describe_accession_conflicts(media)
                resolution_map: dict[str, dict[str, object]] = {}
                missing_resolutions: list[str] = []

                if action == "approve" and conflict_details:
                    resolution_map, missing_resolutions = _parse_conflict_resolution(
                        request.POST, conflict_details
                    )
                    selected_resolution = resolution_map

                if diff_result:
                    warnings_map = {
                        warning.get("code"): warning
                        for warning in diff_result.get("warnings", [])
                        if warning.get("code")
                    }
                else:
                    warnings_map = {}

                if action == "approve":
                    processed = (media.ocr_data or {}).get("_processed_accessions") or []
                    if media.accession_id or processed:
                        message = (
                            "This media already has linked accessions and cannot be "
                            "approved again."
                        )
                        manager.accession_form.add_error(None, message)
                        messages.error(request, message)
                    elif missing_resolutions:
                        for key in missing_resolutions:
                            message = (
                                f"Select how to handle the existing accession {key} before approving."
                            )
                            manager.accession_form.add_error(None, message)
                            messages.error(request, message)
                    else:
                        unresolved_warnings = [
                            warning
                            for code, warning in warnings_map.items()
                            if code not in acknowledged_warnings
                        ]
                        if unresolved_warnings:
                            for warning in unresolved_warnings:
                                message = warning.get("message") or (
                                    "Review and acknowledge outstanding QC warnings before approving."
                                )
                                manager.accession_form.add_error(None, message)
                                messages.error(request, message)
                        else:
                            try:
                                with transaction.atomic():
                                    media.transition_qc(
                                        Media.QCStatus.APPROVED,
                                        user=user,
                                        note=qc_comment or None,
                                        resolution=resolution_map or None,
                                    )
                            except ValidationError as exc:
                                for message in _collect_validation_messages(exc):
                                    manager.accession_form.add_error(None, message)
                                    messages.error(request, message)
                                conflict_details = describe_accession_conflicts(media)
                                selected_resolution = resolution_map
                            except Exception as exc:
                                message = f"Importer error: {exc}"
                                manager.accession_form.add_error(None, message)
                                messages.error(request, message)
                                conflict_details = describe_accession_conflicts(media)
                                selected_resolution = resolution_map
                            else:
                                media.refresh_from_db()
                                for code in acknowledged_warnings:
                                    warning = warnings_map.get(code)
                                    if not warning:
                                        continue
                                    MediaQCLog.objects.create(
                                        media=media,
                                        change_type=MediaQCLog.ChangeType.OCR_DATA,
                                        field_name="warning_acknowledged",
                                        old_value={"code": code},
                                        new_value={
                                            "acknowledged": True,
                                            "count": warning.get("count"),
                                        },
                                        description=(
                                            f"QC warning acknowledged: {warning.get('label')}"
                                        ),
                                        changed_by=user,
                                    )
                                _create_qc_comment(media, qc_comment, user)
                                messages.success(
                                    request,
                                    "Media approved and accessions created.",
                                )
                                return redirect("dashboard")
                elif action == "return_intern":
                    try:
                        media.transition_qc(
                            Media.QCStatus.PENDING_INTERN,
                            user=user,
                            note=qc_comment or None,
                        )
                    except ValidationError as exc:
                        for message in _collect_validation_messages(exc):
                            manager.accession_form.add_error(None, message)
                            messages.error(request, message)
                    else:
                        media.refresh_from_db()
                        _create_qc_comment(media, qc_comment, user)
                        messages.success(
                            request,
                            "Media returned to interns for additional edits.",
                        )
                        return redirect("dashboard")
                elif action == "request_rescan":
                    try:
                        media.transition_qc(
                            Media.QCStatus.REJECTED,
                            user=user,
                            note=qc_comment or None,
                        )
                    except ValidationError as exc:
                        for message in _collect_validation_messages(exc):
                            manager.accession_form.add_error(None, message)
                            messages.error(request, message)
                    else:
                        media.refresh_from_db()
                        _create_qc_comment(media, qc_comment, user)
                        messages.success(request, "Media flagged for rescan.")
                        return redirect("dashboard")
                else:
                    if qc_comment:
                        try:
                            media.transition_qc(
                                media.qc_status,
                                user=user,
                                note=qc_comment,
                            )
                        except ValidationError as exc:
                            for message in _collect_validation_messages(exc):
                                manager.accession_form.add_error(None, message)
                                messages.error(request, message)
                        else:
                            media.refresh_from_db()
                            _create_qc_comment(media, qc_comment, user)
                            messages.success(request, "Changes saved.")
                            return redirect("media_expert_qc", pk=media.uuid)
                    else:
                        messages.success(request, "Changes saved.")
                        return redirect("media_expert_qc", pk=media.uuid)

    _annotate_conflict_selections(conflict_details, selected_resolution)
    qc_comments = _get_qc_comments(media)

    qc_diff = diff_result or manager.last_diff_result or diff_media_payload(
        manager.original_data,
        manager.data,
        rows_reordered=media.rows_rearranged,
    )
    qc_preview = build_preview_accession(
        manager.data,
        manager.accession_form,
        request_user=request.user,
    )

    form_media = _build_qc_form_media(manager)

    context = {
        "media": media,
        "accession_form": manager.accession_form,
        "row_formset": manager.row_formset,
        "ident_formset": manager.ident_formset,
        "specimen_formset": manager.specimen_formset,
        "reference_formset": manager.reference_formset,
        "fieldslip_formset": manager.fieldslip_formset,
        "row_contexts": manager.row_contexts,
        "storage_suggestions": manager.storage_suggestions,
        "storage_datalist_id": AccessionRowQCForm.storage_datalist_id,
        "qc_comment": qc_comment,
        "qc_comments": qc_comments,
        "qc_history_logs": _get_qc_history(media, limit=10),
        "qc_conflicts": conflict_details,
        "qc_diff": qc_diff,
        "qc_preview": qc_preview,
        "qc_acknowledged_warnings": acknowledged_warnings,
        "form_media": form_media,
    }

    return render(request, "cms/qc/expert_wizard.html", context)


class LocalityListView(FilterView):
    model = Locality
    template_name = 'cms/locality_list.html'
    context_object_name = 'localities'
    paginate_by = 10
    filterset_class = LocalityFilter



class LocalityDetailView(DetailView):
    model = Locality
    template_name = 'cms/locality_detail.html'
    context_object_name = 'locality'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        accessions = self.object.accession_set.all()
        if not (
            user.is_authenticated and (
                user.is_superuser or
                user.groups.filter(name__in=["Collection Managers", "Curators"]).exists()
            )
        ):
            accessions = accessions.filter(is_published=True)

        accessions = prefetch_accession_related(accessions)

        paginator = Paginator(accessions, 10)
        page_number = self.request.GET.get('page')
        accessions = paginator.get_page(page_number)

        attach_accession_summaries(accessions)

        context['accessions'] = accessions
        context['page_obj'] = accessions
        context['is_paginated'] = accessions.paginator.num_pages > 1

        return context

    
    



class PlaceListView(FilterView):
    model = Place
    template_name = 'cms/place_list.html'
    context_object_name = 'places'
    paginate_by = 10
    filterset_class = PlaceFilter


class PlaceDetailView(DetailView):
    model = Place
    template_name = 'cms/place_detail.html'
    context_object_name = 'place'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['children'] = Place.objects.filter(
            related_place=self.object, relation_type=PlaceRelation.PART_OF
        )
        return context


@login_required
@user_passes_test(is_collection_manager)
def upload_media(request, accession_id):
    accession = get_object_or_404(Accession, id=accession_id)

    if request.method == 'POST':
        form = MediaUploadForm(request.POST, request.FILES) # Important: request.FILES for file handling
        if form.is_valid():
            media = form.save(commit=False)
            media.accession = accession  # Link media to the correct accession
            media.save()
            return redirect('accession_detail', pk=accession_id)  # Redirect to accession detail page

    else:
        form = MediaUploadForm()

    return render(request, 'cms/upload_media.html', {'form': form, 'accession': accession})


@staff_member_required
def upload_scan(request):
    """Upload one or more scan images to the ``uploads/incoming`` folder.

    The watcher script later validates filenames and moves each file to
    ``uploads/pending`` or ``uploads/rejected`` as appropriate.
    """
    incoming_dir = Path(settings.MEDIA_ROOT) / 'uploads' / 'incoming'
    os.makedirs(incoming_dir, exist_ok=True)

    form_kwargs = {"max_upload_bytes": settings.SCAN_UPLOAD_MAX_BYTES}

    if request.method == 'POST':
        form = ScanUploadForm(request.POST, request.FILES, **form_kwargs)
        if form.is_valid():
            files = form.cleaned_data['files']
            total_files = len(files)
            fs = FileSystemStorage(location=incoming_dir)
            for index, file in enumerate(files, start=1):
                saved_name = fs.save(file.name, file)
                saved_path = incoming_dir / saved_name
                if saved_name != file.name:
                    desired_path = incoming_dir / file.name
                    if desired_path.exists():
                        desired_path.unlink()
                    saved_path.rename(desired_path)
                    saved_name = file.name
                    saved_path = desired_path
                process_file(saved_path)
                messages.success(
                    request,
                    f'Uploaded {file.name} ({index} of {total_files})',
                )
            return redirect('admin-upload-scan')
    else:
        form = ScanUploadForm(**form_kwargs)

    context = {
        'form': form,
        'scan_upload_max_bytes': settings.SCAN_UPLOAD_MAX_BYTES,
        'scan_upload_batch_max_bytes': settings.SCAN_UPLOAD_BATCH_MAX_BYTES,
        'scan_upload_timeout_seconds': settings.SCAN_UPLOAD_TIMEOUT_SECONDS,
    }

    return render(request, 'admin/upload_scan.html', context)


def _count_pending_scans() -> int:
    pending_dir = Path(settings.MEDIA_ROOT) / "uploads" / "pending"
    if not pending_dir.exists():
        return 0
    return sum(1 for _ in pending_dir.glob("*"))


def _should_loop(request) -> bool:
    flag = request.GET.get("loop", "").lower()
    return flag in {"1", "true", "yes", "on"}


def _parse_ocr_limit(request) -> int | None:
    raw = request.GET.get("limit")
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _compute_expected_total(attempted: int, remaining: int, limit: int | None) -> int:
    if limit is None:
        return attempted + remaining
    return max(attempted, min(limit, attempted + remaining))


@staff_member_required
def do_ocr(request):
    """Process pending scans sequentially, looping if requested."""

    loop = _should_loop(request)
    limit_hint = _parse_ocr_limit(request)
    (
        successes,
        failures,
        total,
        errors,
        jammed,
        processed_filenames,
    ) = process_pending_scans(limit=1)
    latest_filename = processed_filenames[-1] if processed_filenames else None

    aggregated: dict[str, Any] | None = None
    if loop:
        stats = request.session.get("ocr_loop_stats", {
            "successes": 0,
            "failures": 0,
            "attempted": 0,
            "errors": [],
        })
        stats["successes"] += successes
        stats["failures"] += failures
        stats["attempted"] += total
        stats.setdefault("errors", [])
        stats["errors"].extend(errors)
        stats.setdefault("latest_filename", None)
        stats.setdefault("expected_total", None)
        if latest_filename:
            stats["latest_filename"] = latest_filename
        if jammed:
            stats["jammed"] = jammed
        aggregated = stats
        request.session["ocr_loop_stats"] = stats
        request.session.modified = True

    remaining = _count_pending_scans()
    errors_list = list(aggregated["errors"]) if aggregated else list(errors)
    attempted_total = aggregated["attempted"] if aggregated else total
    expected_total = _compute_expected_total(attempted_total, remaining, limit_hint)
    if aggregated is not None:
        aggregated["expected_total"] = expected_total
        if aggregated.get("latest_filename") is None and latest_filename:
            aggregated["latest_filename"] = latest_filename

    # Sanitize error messages for external exposure: extract only the scan filename portion.
    def _sanitize_ocr_errors(error_list):
        sanitized = []
        for msg in error_list:
            # Expected format: "{filename}: {exception}"
            parts = msg.split(':', 1)
            filename = parts[0].strip() if parts else "Unknown"
            sanitized.append(filename)
        return sanitized

    sanitized_errors = _sanitize_ocr_errors(errors_list)
    detail = {
        "successes": aggregated["successes"] if aggregated else successes,
        "failures": aggregated["failures"] if aggregated else failures,
        "attempted": attempted_total,
        "errors": sanitized_errors,
        "jammed": aggregated.get("jammed") if aggregated else jammed,
        "remaining": remaining,
        "loop": loop,
        "expected_total": aggregated.get("expected_total") if aggregated else expected_total,
        "latest_filename": aggregated.get("latest_filename") if aggregated else latest_filename,
        "current_index": attempted_total,
    }

    if request.headers.get("HX-Request") or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(detail)

    if loop and remaining > 0 and not detail["jammed"]:
        query_params = {"loop": "1"}
        if limit_hint is not None:
            query_params["limit"] = str(limit_hint)
        next_url = f"{reverse('admin-do-ocr')}?{urlencode(query_params)}"
        expected_display = detail["expected_total"] or detail["attempted"]
        latest_segment = (
            f" (Latest: {detail['latest_filename']})"
            if detail["latest_filename"]
            else ""
        )
        body = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>Continuing OCR…</title><meta http-equiv=\"refresh\" content=\"0; url={next_url}\"></head>"
            "<body><p>Continuing OCR… scan "
            f"{detail['current_index']} of {expected_display}{latest_segment}.</p></body></html>"
        )
        response = HttpResponse(body)
        response["Refresh"] = f"0;url={next_url}"
        return response

    if loop and "ocr_loop_stats" in request.session:
        del request.session["ocr_loop_stats"]
        request.session.modified = True

    if detail["attempted"] == 0:
        messages.info(request, "No pending scans to process.")
        # Show only affected scan file names, not raw error messages
    else:
        expected_display = detail["expected_total"] or detail["attempted"]
        latest_segment = (
            f" Latest scan: {detail['latest_filename']}."
            if detail["latest_filename"]
            else ""
        )
        messages.info(
            request,
            f"Processed {detail['successes']} of {expected_display} scans this run.{latest_segment}",
        )

    if detail["failures"]:
        error_text = "; ".join(detail["errors"])
        messages.error(request, f"OCR failed for {detail['failures']} scans: {error_text}")
    if detail["jammed"]:
        messages.error(
            request,
            (
                "OCR halted because scan "
                f"{detail['jammed']} timed out after three attempts. Please investigate before retrying."
            ),
        )

    return redirect('admin:index')

@login_required
@user_passes_test(is_collection_manager)
def accession_create(request):
    if request.method == 'POST':
        form = AccessionForm(request.POST, request.FILES)
        if form.is_valid():
            accession = form.save(commit=False)

            # Safe place to modify the object before saving
            # e.g., accession.created_by = request.user

            accession.save()  # Now the PK is assigned
            form.save_m2m()   # In case future fields need this

            return redirect('accession_list')
    else:
        form = AccessionForm()

    return render(request, 'cms/accession_form.html', {'form': form})

@login_required
@user_passes_test(is_collection_manager)
def accession_edit(request, pk):
    accession = get_object_or_404(Accession, pk=pk)

    if request.method == 'POST':
        form = AccessionForm(request.POST, request.FILES, instance=accession)
        if form.is_valid():
            form.save()
            return redirect('accession_detail', pk=accession.pk)
    else:
        form = AccessionForm(instance=accession)

    return render(request, 'cms/accession_form.html', {'form': form})

@login_required
@user_passes_test(is_collection_manager)
def add_accession_row(request, accession_id):
    accession = get_object_or_404(Accession, id=accession_id)
    
    if request.method == 'POST':
        form = AddAccessionRowForm(request.POST, request.FILES, accession=accession)
        if form.is_valid():
            accession_row = form.save(commit=False)
            accession_row.accession = accession  # Link accession_row to the correct accession
            accession_row.save()
            return redirect('accession_detail', pk=accession_id)  # Redirect to accession detail page
    else:
        form = AddAccessionRowForm(accession=accession)
    return render(request, 'cms/add_accession_row.html', {'form': form, 'accession': accession})

@login_required
@user_passes_test(is_collection_manager)
def add_comment_to_accession(request, accession_id):
    accession = get_object_or_404(Accession, id=accession_id)

    if request.method == 'POST':
        form = AccessionCommentForm(request.POST)
        if form.is_valid():
            accession_comment = form.save(commit=False)
            accession_comment.specimen_no = accession  # Link comment to the correct accession (specimen no)
            accession_comment.status = 'N'
            accession_comment.save()
            return redirect('accession_detail', pk=accession_id)  # Redirect to accession detail page

    else:
        form = AccessionCommentForm()

    return render(request, 'cms/add_accession_comment.html', {'form': form, 'accession': accession})

@login_required
@user_passes_test(is_collection_manager)
def add_reference_to_accession(request, accession_id):
    accession = get_object_or_404(Accession, id=accession_id)

    if request.method == 'POST':
        form = AccessionReferenceForm(request.POST)
        if form.is_valid():
            accession_reference = form.save(commit=False)
            accession_reference.accession = accession  # Link reference to the correct accession
            accession_reference.save()
            return redirect('accession_detail', pk=accession_id)  # Redirect to accession detail page

    else:
        form = AccessionReferenceForm()

    return render(request, 'cms/add_accession_reference.html', {'form': form, 'accession': accession})

@login_required
@user_passes_test(is_collection_manager)
def add_identification_to_accession_row(request, accession_row_id):
    accession_row = get_object_or_404(AccessionRow, id=accession_row_id)
    taxonomy = []

    if request.method == 'POST':
        form = AccessionRowIdentificationForm(request.POST)
        if form.is_valid():
            accession_row_identification = form.save(commit=False)
            accession_row_identification.accession_row = accession_row  # Link specimen to the correct accession_row
            accession_row_identification.save()
            return redirect('accessionrow_detail', pk=accession_row_id)  # Redirect to accession row detail page
        else:
            print("Form errors:", form.errors)  # Debugging output
    else:
        form = AccessionRowIdentificationForm()

    return render(
        request,
        'cms/add_accession_row_identification.html',
        {
            'form': form,
            'accession_row': accession_row,
        }
    )

@login_required
@user_passes_test(is_collection_manager)
def add_specimen_to_accession_row(request, accession_row_id):
    accession_row = get_object_or_404(AccessionRow, id=accession_row_id)

    if request.method == 'POST':
        form = AccessionRowSpecimenForm(request.POST)
        if form.is_valid():
            accession_row_specimen = form.save(commit=False)
            accession_row_specimen.accession_row = accession_row  # Link specimen to the correct accession_row
            accession_row_specimen.save()
            return redirect('accessionrow_detail', pk=accession_row_id)  # Redirect to accession row detail page
        else:
            print("Form errors:", form.errors)  # Debugging output
    else:
        form = AccessionRowSpecimenForm()

    return render(request, 'cms/add_accession_row_specimen.html', {'form': form, 'accession_row': accession_row})

@login_required
@user_passes_test(is_collection_manager)
def add_geology_to_accession(request, accession_id):
    accession = get_object_or_404(Accession, id=accession_id)

    if request.method == 'POST':
        form = AccessionGeologyForm(request.POST)
        if form.is_valid():
            accession_geology = form.save(commit=False)
            accession_geology.accession = accession
            accession_geology.save()
            return redirect('accession_detail', pk=accession_id)
        else:
            print("Form errors:", form.errors)  # Debugging output
    else:
        form = AccessionGeologyForm()

    return render(request, 'cms/add_accession_geology.html', {'form': form, 'accession': accession})

class PreparationListView(LoginRequiredMixin, PreparationAccessMixin, FilterView):
    """ List all preparations. """
    model = Preparation
    template_name = "cms/preparation_list.html"
    context_object_name = "preparations"
    paginate_by = 10
    ordering = ["-created_on"]
    filterset_class = PreparationFilter

    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser or 
            user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        )
    
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.annotate(
            accession_label=Concat(
                'accession_row__accession__specimen_prefix__abbreviation',
                Value(' '),
                'accession_row__accession__specimen_no',
                'accession_row__specimen_suffix',
                output_field=CharField()
            )
        )

class PreparationDetailView(LoginRequiredMixin, DetailView):
    """ Show details of a single preparation. """
    model = Preparation
    template_name = "cms/preparation_detail.html"
    context_object_name = "preparation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        preparation = self.object
        context["can_edit"] = (
            user.is_superuser
            or (
                user.groups.filter(name="Curators").exists()
                and user == preparation.curator
            )
            or (
                user.groups.filter(name="Preparators").exists()
                and user == preparation.preparator
            )
        )
        context["history_entries"] = build_history_entries(preparation)
        return context

class PreparationCreateView(LoginRequiredMixin, CreateView):
    """ Create a new preparation record. """
    model = Preparation
    form_class = PreparationForm
    template_name = "cms/preparation_form.html"

    def form_valid(self, form):
        """ Auto-assign the current user as the preparator if not set. """
        if not form.instance.preparator:
            form.instance.preparator = self.request.user
        return super().form_valid(form)

    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser or 
            user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        )

class PreparationUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """ Update an existing preparation. """
    model = Preparation
    form_class = PreparationForm
    template_name = "cms/preparation_form.html"

    def test_func(self):
        preparation = self.get_object()
        user = self.request.user

        # Admins can always edit
        if user.is_superuser:
            return True

        # Curators can edit only if they are assigned as the curator
        if user.groups.filter(name="Curators").exists() and user == preparation.curator:
            return True

        # Preparators can edit their own preparations
        if user.groups.filter(name="Preparators").exists() and user == preparation.preparator:
            return True

        return False

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        user = self.request.user

        # Restrict status choices for preparators
        if user.groups.filter(name="Preparators").exists() and user == self.get_object().preparator:
            status_field = form.fields.get("status")
            if status_field:
                status_field.choices = [
                    choice for choice in status_field.choices
                    if choice[0] not in [PreparationStatus.APPROVED, PreparationStatus.DECLINED]
                ]
                status_field.error_messages[
                    "invalid_choice"
                ] = "You cannot set status to Approved or Declined."

        # Restrict status choices for curators
        if user.groups.filter(name="Curators").exists() and user == self.get_object().curator:
            status_field = form.fields.get("status")
            if status_field:
                status_field.choices = [
                    (PreparationStatus.APPROVED, PreparationStatus.APPROVED.label),
                    (PreparationStatus.DECLINED, PreparationStatus.DECLINED.label),
                ]
                status_field.error_messages[
                    "invalid_choice"
                ] = "You can only set status to Approved or Declined."
            curator_field = form.fields.get("curator")
            if curator_field:
                curator_field.initial = user
                curator_field.disabled = True

        return form

    def form_valid(self, form):
        user = self.request.user

        if user.groups.filter(name="Preparators").exists() and user == self.get_object().preparator:
            if form.cleaned_data.get("status") in [PreparationStatus.APPROVED, PreparationStatus.DECLINED]:
                form.add_error("status", "You cannot set status to Approved or Declined.")
                return self.form_invalid(form)

        if user.groups.filter(name="Curators").exists() and user == self.get_object().curator:
            status = form.cleaned_data.get("status")
            if status not in [PreparationStatus.APPROVED, PreparationStatus.DECLINED]:
                form.add_error("status", "You can only set status to Approved or Declined.")
                return self.form_invalid(form)
            form.instance.curator = user
            form.instance.approval_status = status.lower()

        return super().form_valid(form)

class PreparationDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """ Delete a preparation record. """
    model = Preparation
    success_url = reverse_lazy("preparation_list")
    template_name = "cms/preparation_confirm_delete.html"

    def test_func(self):
        preparation = self.get_object()
        user = self.request.user

        # Allow admins always
        if user.is_superuser:
            return True

        # Allow curators if they are not the preparator
        return user != preparation.preparator and user.groups.filter(name="Curators").exists()


class PreparationApproveView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """ Allows a curator to approve or decline a preparation. """
    model = Preparation
    form_class = PreparationApprovalForm
    template_name = "cms/preparation_approve.html"

    def test_func(self):
        preparation = self.get_object()
        user = self.request.user

        # Allow admins always
        if user.is_superuser:
            return True

        # Allow curators if they are not the preparator
        return user != preparation.preparator and user.groups.filter(name="Curators").exists()

    def form_valid(self, form):
        """ Auto-set approval date when curator approves or declines. """
        preparation = form.save(commit=False)
        preparation.curator = self.request.user
        preparation.approval_date = now()
        preparation.save()
        return redirect("preparation_detail", pk=preparation.pk)

class PreparationMediaUploadView(View):
    def get(self, request, pk):
        preparation = get_object_or_404(Preparation, pk=pk)

        # Permission check
        if not request.user.is_authenticated or (
            not request.user.is_superuser and
            not request.user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        ):
            return redirect("preparation_detail", pk=pk)

        form = PreparationMediaUploadForm()
        return render(request, "cms/preparation_media_upload.html", {
            "form": form,
            "preparation": preparation,
        })

    def post(self, request, pk):
        preparation = get_object_or_404(Preparation, pk=pk)

        if not request.user.is_authenticated or (
            not request.user.is_superuser and
            not request.user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        ):
            return redirect("preparation_detail", pk=pk)

        form = PreparationMediaUploadForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist("media_files")
            context = form.cleaned_data["context"]
            notes = form.cleaned_data["notes"]

            for file in files:
                media = Media.objects.create(
                    media_location=file,
#                    created_by=request.user
                )
                PreparationMedia.objects.create(
                    preparation=preparation,
                    media=media,
                    context=context,
                    notes=notes
                )
            return redirect("preparation_detail", pk=pk)

        return render(request, "cms/preparation_media_upload.html", {
            "form": form,
            "preparation": preparation,
        })


@login_required
def inventory_start(request):
    """Start an inventory session or display expected specimens."""
    if request.method == "POST":
        shelf_ids = request.POST.getlist("shelf_ids")
        if shelf_ids:
            request.session["inventory_shelf_ids"] = shelf_ids
            messages.success(request, "Inventory session started.")
            return redirect("inventory_start")

    shelf_ids = request.session.get("inventory_shelf_ids")
    if shelf_ids:
        selected_shelf_ids = [int(s) for s in shelf_ids]
        active_prep_qs = Preparation.objects.filter(
            status__in=[PreparationStatus.PENDING, PreparationStatus.IN_PROGRESS]
        ).select_related("original_storage", "temporary_storage")

        specimens = (
            AccessionRow.objects
            .filter(
                Q(storage_id__in=selected_shelf_ids) |
                Q(
                    preparations__original_storage_id__in=selected_shelf_ids,
                    preparations__status__in=[PreparationStatus.PENDING, PreparationStatus.IN_PROGRESS],
                )
            )
            .select_related("accession", "storage")
            .prefetch_related(Prefetch("preparations", queryset=active_prep_qs, to_attr="active_preparations"))
            .order_by(
                "storage__area",
                "accession__collection__abbreviation",
                "accession__specimen_prefix__abbreviation",
                "accession__specimen_no",
                "accession__instance_number",
                "specimen_suffix",
            )
            .distinct()
        )

        specimens = list(specimens)
        for spec in specimens:
            if getattr(spec, "active_preparations", []):
                prep = spec.active_preparations[0]
                spec.display_shelf = prep.original_storage or spec.storage
                spec.current_location = prep.temporary_storage or spec.storage
            else:
                spec.display_shelf = spec.storage
                spec.current_location = spec.storage

        shelves = Storage.objects.all()
        context = {
            "specimens": specimens,
            "status_choices": InventoryStatus.choices,
            "shelves": shelves,
            "selected_shelf_ids": selected_shelf_ids,
        }
        return render(request, "inventory/session.html", context)

    shelves = Storage.objects.all()
    return render(request, "inventory/start.html", {"shelves": shelves})


@require_POST
@login_required
def inventory_update(request):
    specimen_id = request.POST.get("specimen_id")
    status = request.POST.get("status")
    if not specimen_id:
        return JsonResponse({"success": False}, status=400)
    specimen = get_object_or_404(AccessionRow, id=specimen_id)
    if status in dict(InventoryStatus.choices):
        specimen.status = status
    else:
        specimen.status = None
    specimen.save(update_fields=["status"])
    return JsonResponse({"success": True})


@require_POST
@login_required
def inventory_reset(request):
    shelf_ids = request.POST.getlist("shelf_ids")
    if not shelf_ids:
        return JsonResponse({"success": False}, status=400)
    AccessionRow.objects.filter(
        Q(storage_id__in=shelf_ids) |
        Q(
            preparations__original_storage_id__in=shelf_ids,
            preparations__status__in=[PreparationStatus.PENDING, PreparationStatus.IN_PROGRESS],
        )
    ).update(status=None)
    return JsonResponse({"success": True})


@require_POST
@login_required
def inventory_clear(request):
    request.session.pop("inventory_shelf_ids", None)
    return JsonResponse({"success": True})


@require_POST
@login_required
def inventory_log_unexpected(request):
    identifier = request.POST.get("identifier")
    if not identifier:
        return JsonResponse({"success": False}, status=400)
    UnexpectedSpecimen.objects.create(identifier=identifier)
    return JsonResponse({"success": True})


class CollectionManagerAccessMixin(UserPassesTestMixin):
    def test_func(self):
        return is_collection_manager(self.request.user) or self.request.user.is_superuser


class DrawerRegisterAccessMixin(CollectionManagerAccessMixin):
    pass


class StorageListView(LoginRequiredMixin, CollectionManagerAccessMixin, FilterView):
    model = Storage
    template_name = "cms/storage_list.html"
    context_object_name = "storages"
    paginate_by = 10
    filterset_class = StorageFilter

    def get_queryset(self):
        return (
            Storage.objects.select_related("parent_area")
            .prefetch_related("storage_set")
            .annotate(specimen_count=Count("accessionrow", distinct=True))
            .order_by("area")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = (
            is_collection_manager(self.request.user) or self.request.user.is_superuser
        )
        return context


class StorageDetailView(LoginRequiredMixin, CollectionManagerAccessMixin, DetailView):
    model = Storage
    template_name = "cms/storage_detail.html"
    context_object_name = "storage"

    def get_queryset(self):
        accession_rows = AccessionRow.objects.select_related(
            "accession__collection",
            "accession__specimen_prefix",
        ).order_by(
            "accession__collection__abbreviation",
            "accession__specimen_no",
            "specimen_suffix",
        )
        child_storages = Storage.objects.select_related("parent_area").order_by("area")
        return (
            Storage.objects.select_related("parent_area")
            .prefetch_related(
                Prefetch("accessionrow_set", queryset=accession_rows, to_attr="prefetched_rows"),
                Prefetch("storage_set", queryset=child_storages, to_attr="child_storages"),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = (
            is_collection_manager(self.request.user) or self.request.user.is_superuser
        )
        specimens = getattr(self.object, "prefetched_rows", [])
        paginator = Paginator(specimens, 10)
        page_number = self.request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        context["specimen_page_obj"] = page_obj
        context["specimens"] = page_obj.object_list
        context["specimen_count"] = paginator.count
        context["children"] = getattr(self.object, "child_storages", [])
        context["history_entries"] = build_history_entries(self.object)
        return context


class StorageCreateView(LoginRequiredMixin, CollectionManagerAccessMixin, CreateView):
    model = Storage
    form_class = StorageForm
    template_name = "cms/storage_form.html"
    success_url = reverse_lazy("storage_list")


class StorageUpdateView(LoginRequiredMixin, CollectionManagerAccessMixin, UpdateView):
    model = Storage
    form_class = StorageForm
    template_name = "cms/storage_form.html"
    success_url = reverse_lazy("storage_list")


class DrawerRegisterListView(LoginRequiredMixin, DrawerRegisterAccessMixin, FilterView):
    model = DrawerRegister
    template_name = "cms/drawerregister_list.html"
    context_object_name = "drawers"
    paginate_by = 10
    filterset_class = DrawerRegisterFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = (
            is_collection_manager(self.request.user) or self.request.user.is_superuser
        )
        return context


class DrawerRegisterReorderView(LoginRequiredMixin, DrawerRegisterAccessMixin, View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        order = data.get("order", [])
        # Assign larger priority values to items appearing earlier in the
        # provided order so they are shown first when ordered descending.
        for priority, pk in enumerate(reversed(order), start=1):
            DrawerRegister.objects.filter(pk=pk).update(priority=priority)
        return JsonResponse({"status": "ok"})


class DrawerRegisterDetailView(LoginRequiredMixin, DrawerRegisterAccessMixin, DetailView):
    model = DrawerRegister
    template_name = "cms/drawerregister_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = (
            is_collection_manager(self.request.user) or self.request.user.is_superuser
        )
        context["history_entries"] = build_history_entries(self.object)
        return context


class DrawerRegisterCreateView(LoginRequiredMixin, DrawerRegisterAccessMixin, CreateView):
    model = DrawerRegister
    form_class = DrawerRegisterForm
    template_name = "cms/drawerregister_form.html"
    success_url = reverse_lazy("drawerregister_list")


class DrawerRegisterUpdateView(LoginRequiredMixin, DrawerRegisterAccessMixin, UpdateView):
    model = DrawerRegister
    form_class = DrawerRegisterForm
    template_name = "cms/drawerregister_form.html"
    success_url = reverse_lazy("drawerregister_list")


@login_required
def start_scan(request, pk):
    drawer = get_object_or_404(DrawerRegister, pk=pk)
    scanning_utils.auto_complete_scans(
        Scanning.objects.filter(user=request.user, end_time__isnull=True)
    )
    Scanning.objects.create(
        drawer=drawer, user=request.user, start_time=scanning_utils.nairobi_now()
    )
    return redirect("dashboard")


@login_required
def stop_scan(request, pk):
    drawer = get_object_or_404(DrawerRegister, pk=pk)
    scan = (
        Scanning.objects.filter(drawer=drawer, user=request.user, end_time__isnull=True)
        .order_by("-start_time")
        .first()
    )
    if scan:
        auto_end = scanning_utils.calculate_scan_auto_end(scan.start_time)
        scan.end_time = min(scanning_utils.nairobi_now(), auto_end)
        scan.save()
    return redirect("dashboard")
    
