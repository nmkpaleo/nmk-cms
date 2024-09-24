from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.views.generic import DetailView, ListView
from .models import FieldSlip, Accession
from .forms import FieldSlipForm
from .forms import FieldSlipForm
import csv
from django.http import HttpResponse
from .resources import FieldSlipResource

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
            return redirect('fieldslip-list')  # Redirect after successful import

    return render(request, 'cms/fieldslip_import.html')  # Render the import form




def index(request):
    """View function for home page of site."""
    return render(request, 'index.html')

def base_generic(request):
    return render(request, 'base_generic.html')

def fieldslip_create(request):
    if request.method == 'POST':
        form = FieldSlipForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('fieldslip-list')  #  to redirect to the list view
    else:
        form = FieldSlipForm()
    return render(request, 'cms/fieldslip_form.html', {'form': form})

def fieldslip_edit(request, pk):
    fieldslip = get_object_or_404(FieldSlip, pk=pk)
    if request.method == 'POST':
        form = FieldSlipForm(request.POST, request.FILES, instance=fieldslip)
        if form.is_valid():
            form.save()
            return redirect('fieldslip-detail', pk=fieldslip.pk)  # Redirect to the detail view
    else:
        form = FieldSlipForm(instance=fieldslip)
    return render(request, 'cms/fieldslip_form.html', {'form': form})

class FieldSlipDetailView(DetailView):
    model = FieldSlip
    template_name = 'cms/fieldslip_detail.html'
    context_object_name = 'fieldslip'

class FieldSlipListView(ListView):
    model = FieldSlip
    template_name = 'cms/fieldslip_list.html'
    context_object_name = 'fieldslips'

class AccessionDetailView(DetailView):
    model = Accession
    template_name = 'cms/accession_detail.html'
    context_object_name = 'accession'

class AccessionListView(ListView):
    model = Accession
    template_name = 'cms/accession_list.html'
    context_object_name = 'accessions'
