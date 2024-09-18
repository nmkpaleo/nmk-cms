from django.shortcuts import render, redirect
from django.views.generic import DetailView, ListView
from .models import FieldSlip, Accession
from .forms import FieldSlipForm
from .forms import FieldSlipForm


def index(request):
    """View function for home page of site."""
    return render(request, 'index.html')

def base_generic(request):
    return render(request, 'base_generic.html')

def fieldslip_create(request):
    if request.method == 'POST':
        form = FieldSlipForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('fieldslip-list')  #  to redirect to the list view
    else:
        form = FieldSlipForm()
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
