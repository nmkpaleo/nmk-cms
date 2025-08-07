import csv
from datetime import timedelta
from dal import autocomplete
from django import forms
from django.db import transaction
from django.db.models import Value, CharField
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_filters.views import FilterView
from .filters import AccessionFilter, PreparationFilter, ReferenceFilter, FieldSlipFilter, LocalityFilter


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
                    SpecimenCompositeForm, ReferenceForm, LocalityForm)

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
    PreparationStatus,
)

from cms.resources import FieldSlipResource
from cms.utils import generate_accessions_from_series
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

    if user.groups.filter(name="Preparators").exists():
        my_preparations = Preparation.objects.filter(
            preparator=user
        ).exclude(status=PreparationStatus.COMPLETED)

        priority_threshold = now().date() - timedelta(days=7)
        priority_tasks = my_preparations.filter(started_on__lte=priority_threshold)

        context = {
            "role": "Preparator",
            "my_preparations": my_preparations,
            "priority_tasks": priority_tasks,
        }
        return render(request, "cms/dashboard.html", context)

    if user.groups.filter(name="Curators").exists():
        completed_preparations = Preparation.objects.filter(
            status=PreparationStatus.COMPLETED,
            curator=user,
        )

        context = {
            "role": "Curator",
            "completed_preparations": completed_preparations,
        }
        return render(request, "cms/dashboard.html", context)

    # Placeholder for other roles
    return render(request, "cms/dashboard.html", {"role": "Unknown"})

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
from django.db.models import Q

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

        accessions = self.object.accession_set.all()
        paginator = Paginator(accessions, 5)  
        page_number = self.request.GET.get('page')
        accessions = paginator.get_page(page_number)


        context['accessions'] = accessions     # so your base template's pagination still works
       
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

    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser or 
            user.groups.filter(name__in=["Curators", "Collection Managers"]).exists()
        )

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

        # Restrict status choices for curators
        if user.groups.filter(name="Curators").exists() and user == self.get_object().curator:
            status_field = form.fields.get("status")
            if status_field:
                status_field.choices = [
                    (PreparationStatus.APPROVED, PreparationStatus.APPROVED.label),
                    (PreparationStatus.DECLINED, PreparationStatus.DECLINED.label),
                ]
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
    
