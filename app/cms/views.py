from django.shortcuts import render, redirect
from django.views.generic import DetailView, ListView
from .models import FieldSlip
from .forms import FieldSlipForm

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
