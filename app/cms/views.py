import copy
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
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
from django.forms import formset_factory, modelformset_factory
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

from cms.resources import FieldSlipResource
from .utils import build_history_entries
from cms.utils import generate_accessions_from_series
from cms.upload_processing import process_file
from cms.ocr_processing import process_pending_scans, describe_accession_conflicts
from formtools.wizard.views import SessionWizardView

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

    expert_qc_status_lists: list[dict] = []
    intern_qc_status_lists: list[dict] = []
    if user.is_superuser or user.groups.filter(
        name__in=["Curators", "Collection Managers"]
    ).exists():
        entries = (
            Media.objects.filter(qc_status=Media.QCStatus.PENDING_EXPERT)
            .select_related("accession", "accession_row")
            .order_by("-modified_on")[:10]
        )
        expert_qc_status_lists.append(
            {
                "status": Media.QCStatus.PENDING_EXPERT.value,
                "label": Media.QCStatus.PENDING_EXPERT.label,
                "entries": entries,
            }
        )
        context.update(
            {
                "is_expert": True,
                "expert_qc_status_lists": expert_qc_status_lists,
            }
        )

    if user.groups.filter(name="Interns").exists():
        active_scan_id_subquery = Scanning.objects.filter(
            drawer=OuterRef("pk"), user=user, end_time__isnull=True
        ).values("id")[:1]
        active_scan_start_subquery = Scanning.objects.filter(
            drawer=OuterRef("pk"), user=user, end_time__isnull=True
        ).values("start_time")[:1]
        my_drawers = (
            DrawerRegister.objects.filter(
                scanning_status=DrawerRegister.ScanningStatus.IN_PROGRESS,
                scanning_users=user,
            )
            .annotate(active_scan_id=Subquery(active_scan_id_subquery))
            .annotate(active_scan_start=Subquery(active_scan_start_subquery))
        )

        for status_choice in (
            Media.QCStatus.PENDING_INTERN,
            Media.QCStatus.REJECTED,
        ):
            entries = (
                Media.objects.filter(qc_status=status_choice)
                .select_related("accession", "accession_row")
                .order_by("-modified_on")[:10]
            )
            intern_qc_status_lists.append(
                {
                    "status": status_choice.value,
                    "label": status_choice.label,
                    "entries": entries,
                }
            )

        context.update(
            {
                "is_intern": True,
                "my_drawers": my_drawers,
                "intern_qc_status_lists": intern_qc_status_lists,
            }
        )

    context.setdefault("expert_qc_status_lists", expert_qc_status_lists)
    context.setdefault("intern_qc_status_lists", intern_qc_status_lists)

    if not context:
        context["no_role"] = True

    return render(request, "cms/dashboard.html", context)

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
        delete_field = self.fields.get('DELETE')
        if delete_field is not None:
            delete_field.widget = forms.HiddenInput()


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
        delete_field = self.fields.get('DELETE')
        if delete_field is not None:
            delete_field.widget = forms.HiddenInput()


AccessionRowFormSet = formset_factory(AccessionRowQCForm, extra=0, can_delete=False)
IdentificationQCFormSet = formset_factory(
    AccessionRowIdentificationQCForm, extra=0, can_delete=True
)
SpecimenQCFormSet = formset_factory(AccessionRowSpecimenQCForm, extra=0, can_delete=True)


class AccessionReferenceQCForm(forms.Form):
    ref_id = forms.CharField(widget=forms.HiddenInput())
    order = forms.IntegerField(widget=forms.HiddenInput())
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


def _interpreted_value(value):
    if isinstance(value, dict):
        if 'interpreted' in value:
            return value.get('interpreted')
        return None
    return value


def _ident_payload_has_meaningful_data(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in (
        'taxon',
        'identification_qualifier',
        'verbatim_identification',
        'identification_remarks',
        'identified_by',
        'reference',
        'date_identified',
    ):
        interpreted = _interpreted_value(entry.get(key))
        if interpreted not in (None, ''):
            return True
    return False


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


def _iter_field_diffs(old, new, path=""):
    if isinstance(new, dict) and not isinstance(old, dict):
        old = {}
    if isinstance(new, list) and not isinstance(old, list):
        old = []
    if isinstance(old, dict) and isinstance(new, dict):
        keys = set(old.keys()) | set(new.keys())
        for key in keys:
            if key == 'interpreted':
                old_val = old.get('interpreted')
                new_val = new.get('interpreted')
                if old_val != new_val:
                    yield path, old_val, new_val
            else:
                sub_path = f"{path}.{key}" if path else key
                yield from _iter_field_diffs(old.get(key), new.get(key), sub_path)
    elif isinstance(old, list) and isinstance(new, list):
        length = max(len(old), len(new))
        for index in range(length):
            old_value = old[index] if index < len(old) else None
            new_value = new[index] if index < len(new) else None
            sub_path = f"{path}[{index}]" if path else f"[{index}]"
            yield from _iter_field_diffs(old_value, new_value, sub_path)
    else:
        if old != new:
            yield path, old, new


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


class MediaQCFormManager:
    """Prepare and persist media QC forms shared by intern and expert wizards."""

    def __init__(self, request, media: Media):
        self.request = request
        self.media = media
        self.original_data = copy.deepcopy(media.ocr_data or {})
        self.data = copy.deepcopy(media.ocr_data or {})
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
            ref_id = (
                cleaned.get("ref_id")
                or form.initial.get("ref_id")
                or f"ref-{len(reference_entries)}"
            )
            try:
                order_value = int(cleaned.get("order"))
            except (TypeError, ValueError):
                order_value = len(reference_entries)
            reference_entries.append(
                {
                    "ref_id": ref_id,
                    "order": order_value,
                    "first_author": cleaned.get("first_author"),
                    "title": cleaned.get("title"),
                    "year": cleaned.get("year"),
                    "page": cleaned.get("page"),
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

            diffs = list(_iter_field_diffs(self.original_data, self.data))

            self.media.ocr_data = self.data
            self.media.rows_rearranged = rows_rearranged
            self.media.save(update_fields=["ocr_data", "rows_rearranged"])

        for path, old_val, new_val in diffs:
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

        return {"rows_rearranged": rows_rearranged, "diffs": diffs}

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

    if request.method == "POST":
        qc_comment = (request.POST.get("qc_comment") or "").strip()
        action = request.POST.get("action") or "save"

        if manager.forms_valid():
            try:
                manager.save()
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
        "qc_conflicts": conflict_details,
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

    if request.method == 'POST':
        form = ScanUploadForm(request.POST, request.FILES)
        files = request.FILES.getlist('files')
        if files:
            fs = FileSystemStorage(location=incoming_dir)
            for file in files:
                saved_name = fs.save(file.name, file)
                process_file(incoming_dir / saved_name)
                messages.success(request, f'Uploaded {file.name}')
            return redirect('admin-upload-scan')
        else:
            form.add_error('files', 'No file was submitted. Check the encoding type on the form.')
    else:
        form = ScanUploadForm()

    return render(request, 'admin/upload_scan.html', {'form': form})


@staff_member_required
def do_ocr(request):
    """Process pending scans with OCR."""
    successes, failures, total, errors = process_pending_scans()
    messages.info(request, f"{successes}/{total} scans OCR'd")
    if failures:
        detail = "; ".join(errors)
        messages.error(request, f"OCR failed for {failures} scans: {detail}")
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
    Scanning.objects.create(
        drawer=drawer, user=request.user, start_time=now()
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
        scan.end_time = now()
        scan.save()
    return redirect("dashboard")
    
