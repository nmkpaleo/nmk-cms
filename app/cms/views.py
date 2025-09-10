import csv
import json
import os
from datetime import timedelta
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
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse_lazy, reverse
from django.utils.timezone import now
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView

from cms.forms import (AccessionBatchForm, AccessionCommentForm,
                    AccessionForm, AccessionFieldSlipForm, AccessionGeologyForm,
                    AccessionNumberSelectForm,
                    AccessionRowIdentificationForm, AccessionMediaUploadForm,
                    AccessionRowSpecimenForm,
                    AccessionReferenceForm, AddAccessionRowForm, FieldSlipForm,
                    MediaUploadForm, NatureOfSpecimenForm, PreparationForm,
                    PreparationApprovalForm, PreparationMediaUploadForm,
                    SpecimenCompositeForm, ReferenceForm, LocalityForm,
                    PlaceForm, DrawerRegisterForm, ScanUploadForm)

from cms.models import (
    Accession,
    AccessionNumberSeries,
    AccessionFieldSlip,
    AccessionReference,
    AccessionRow,
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
)

from cms.resources import FieldSlipResource
from .utils import build_history_entries
from cms.utils import generate_accessions_from_series
from cms.upload_processing import process_file
from cms.ocr_processing import process_pending_scans
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
    
class PreparationAccessMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser or
            user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        )

# Helper function to check if user is in the "Collection Managers" group
def is_collection_manager(user):
    return user.groups.filter(name="Collection Managers").exists()


def can_manage_places(user):
    return user.is_superuser or user.groups.filter(name="Collection Managers").exists()

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

        context.update({"is_intern": True, "my_drawers": my_drawers})

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
        accession_rows = AccessionRow.objects.filter(accession=self.object)
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

        if user.is_authenticated and (
            user.is_superuser or
            user.groups.filter(name__in=["Collection Managers", "Curators"]).exists()
        ):
            return qs  # Show all

        return qs.filter(is_published=True)  # Public users only see published accessions

class AccessionRowDetailView(DetailView):
    model = AccessionRow
    template_name = 'cms/accession_row_detail.html'
    context_object_name = 'accessionrow'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['natureofspecimens'] = NatureOfSpecimen.objects.filter(accession_row=self.object)
        context['identifications'] = Identification.objects.filter(accession_row=self.object)
        return context

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

class ReferenceListView(FilterView):
    model = Reference
    template_name = 'cms/reference_list.html'
    context_object_name = 'references'
    paginate_by = 10



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

        paginator = Paginator(accessions, 5)
        page_number = self.request.GET.get('page')
        accessions = paginator.get_page(page_number)

        context['accessions'] = accessions

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
    successes, failures, errors = process_pending_scans()
    if successes:
        messages.success(request, f"OCR succeeded for {successes} scans")
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
    paginate_by = 2
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


class DrawerRegisterAccessMixin(UserPassesTestMixin):
    def test_func(self):
        return is_collection_manager(self.request.user) or self.request.user.is_superuser


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
    
