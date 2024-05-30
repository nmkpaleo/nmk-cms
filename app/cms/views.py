from django.shortcuts import render, redirect
from django.views.generic import DetailView
from .models import FieldSlip
from .forms import FieldSlipForm

def fieldslip_create(request):
    if request.method == 'POST':
        form = FieldSlipForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('fieldslip-list')
    else:
        form = FieldSlipForm()
    return render(request, 'fieldslip_form.html', {'form': form})

class FieldSlipDetailView(DetailView):
    model = FieldSlip
    template_name = 'fieldslip_detail.html'
    context_object_name = 'fieldslip'
