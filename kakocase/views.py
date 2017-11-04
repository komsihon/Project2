import json

from django.conf import settings
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.http.response import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.http import urlquote
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from ikwen.partnership.models import ApplicationRetailConfig

from ikwen.theming.models import Theme, Template

from ikwen.accesscontrol.models import Member

from ikwen.billing.models import IkwenInvoiceItem, InvoiceEntry, CloudBillingPlan

from ikwen.core.models import Service, Application

from ikwen.core.views import BaseView
from django.utils.translation import gettext as _

from ikwen_kakocase.kakocase.models import OperatorProfile, DeliveryOption

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import get_service_instance
from ikwen_kakocase.kakocase.cloud_setup import DeploymentForm, deploy


class DeliveryOptionList(BaseView):
    template_name = 'core/iframe_admin.html'

    def get_context_data(self, **kwargs):
        context = super(DeliveryOptionList, self).get_context_data(**kwargs)
        iframe_url = reverse('admin:kakocase_deliveryoption_changelist')
        context['model_name'] = _('Delivery Option')
        context['iframe_url'] = iframe_url
        return context


def list_available_companies(request, *args, **kwargs):
    """
    Used for company auto-complete in delivery option admin upon
    creation of an Option and also when adding a Bank.
    """
    q = request.GET['query'].lower()
    if len(q) < 2:
        return

    companies = []
    business_type = request.GET.get('business_type', OperatorProfile.LOGISTICS)
    queryset = OperatorProfile.objects.using(UMBRELLA).filter(business_type=business_type)
    word = slugify(q)[:4]
    if word:
        companies = list(queryset.filter(company_name__icontains=word)[:10])

    suggestions = [{'value': c.company_name, 'data': c.service.pk} for c in companies]
    if business_type == OperatorProfile.LOGISTICS:
        service = get_service_instance()
        # Add current Provider among potential delivery companies as he can deliver himself
        yourself = {'value': _('Yourself'), 'data': service.pk}
        suggestions.insert(0, yourself)
    response = {'suggestions': suggestions}
    return HttpResponse(json.dumps(response), content_type='application/json')


def add_delivery_company_to_local_database(request, *args, **kwargs):
    company_id = request.GET['company_id']
    company = Service.objects.using(UMBRELLA).get(pk=company_id)
    try:
        Service.objects.get(pk=company_id)
    except Service.DoesNotExist:
        config = company.config
        company.save(using='default')
        config.save(using='default')
    return HttpResponse(json.dumps({'success': True}), content_type='application/json')


def set_session_data(request, *args, **kwargs):
    manage_packages = False
    manage_drivy = False
    if getattr(settings, 'IS_DELIVERY_COMPANY', False):
        manage_packages = True
    if getattr(settings, 'IS_PROVIDER', False):
        service = get_service_instance()
        if DeliveryOption.objects.exclude(company=service).count() > 0:
            manage_packages = True
        try:
            DeliveryOption.objects.get(type=DeliveryOption.PICK_UP_IN_STORE, is_active=True)
            manage_drivy = True
        except DeliveryOption.DoesNotExist:
            pass
    request.session['manage_packages'] = manage_packages
    request.session['manage_drivy'] = manage_drivy


class DeployCloud(BaseView):
    template_name = 'kakocase/cloud_setup/deploy.html'

    def get_context_data(self, **kwargs):
        context = super(DeployCloud, self).get_context_data(**kwargs)
        context['billing_cycles'] = Service.BILLING_CYCLES_CHOICES
        app_slug = kwargs['app_slug']
        app = Application.objects.using(UMBRELLA).get(slug=app_slug)
        context['app'] = app
        template_list = list(Template.objects.using(UMBRELLA).filter(app=app))
        context['theme_list'] = Theme.objects.using(UMBRELLA).filter(template__in=template_list)
        context['can_choose_themes'] = True
        if getattr(settings, 'IS_IKWEN', False):
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner__isnull=True)
            if billing_plan_list.count() == 0:
                setup_months_count = 3
                context['ikwen_setup_cost'] = app.base_monthly_cost * setup_months_count
                context['ikwen_monthly_cost'] = app.base_monthly_cost
                context['setup_months_count'] = setup_months_count
        else:
            service = get_service_instance()
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner=service)
            if billing_plan_list.count() == 0:
                retail_config = ApplicationRetailConfig.objects.using(UMBRELLA).get(app=app, partner=service)
                setup_months_count = 3
                context['ikwen_setup_cost'] = retail_config.ikwen_monthly_cost * setup_months_count
                context['ikwen_monthly_cost'] = retail_config.ikwen_monthly_cost
                context['setup_months_count'] = setup_months_count
        if billing_plan_list.count() > 0:
            context['billing_plan_list'] = billing_plan_list
            context['setup_months_count'] = billing_plan_list[0].setup_months_count
        return context

    def get(self, request, *args, **kwargs):
        member = request.user
        uri = request.META['REQUEST_URI']
        next_url = reverse('ikwen:sign_in') + '?next=' + urlquote(uri)
        if member.is_anonymous():
            return HttpResponseRedirect(next_url)
        if not getattr(settings, 'IS_IKWEN', False):
            if not member.has_perm('accesscontrol.sudo'):
                return HttpResponseForbidden("You are not allowed here. Please login as an administrator.")
        return super(DeployCloud, self).get(request, *args, **kwargs)

    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        form = DeploymentForm(request.POST)
        if form.is_valid():
            app_id = form.cleaned_data.get('app_id')
            project_name = form.cleaned_data.get('project_name')
            business_type = form.cleaned_data.get('business_type')
            billing_cycle = form.cleaned_data.get('billing_cycle')
            billing_plan_id = form.cleaned_data.get('billing_plan_id')
            domain = form.cleaned_data.get('domain')
            theme_id = form.cleaned_data.get('theme_id')
            partner_id = form.cleaned_data.get('partner_id')
            app = Application.objects.using(UMBRELLA).get(pk=app_id)
            theme = Theme.objects.using(UMBRELLA).get(pk=theme_id)
            billing_plan = CloudBillingPlan.objects.using(UMBRELLA).get(pk=billing_plan_id)

            is_ikwen = getattr(settings, 'IS_IKWEN', False)
            if not is_ikwen or (is_ikwen and request.user.is_staff):
                customer_id = form.cleaned_data.get('customer_id')
                customer = Member.objects.using(UMBRELLA).get(pk=customer_id)
                setup_cost = form.cleaned_data.get('setup_cost')
                monthly_cost = form.cleaned_data.get('monthly_cost')
                if setup_cost < billing_plan.setup_cost:
                    return HttpResponseForbidden("Attempt to set a Setup cost lower than allowed.")
                if monthly_cost < billing_plan.monthly_cost:
                    return HttpResponseForbidden("Attempt to set a monthly cost lower than allowed.")
            else:
                # User self-deploying his website
                customer = Member.objects.using(UMBRELLA).get(pk=request.user.id)
                setup_cost = billing_plan.setup_cost
                monthly_cost = billing_plan.monthly_cost

            partner = Service.objects.using(UMBRELLA).get(pk=partner_id) if partner_id else None
            invoice_entries = []
            domain_name = IkwenInvoiceItem(label='Domain name')
            domain_name_entry = InvoiceEntry(item=domain_name, short_description=domain)
            invoice_entries.append(domain_name_entry)
            website_setup = IkwenInvoiceItem(label='Website setup', price=billing_plan.setup_cost, amount=setup_cost)
            short_description = "%d products" % billing_plan.max_objects
            website_setup_entry = InvoiceEntry(item=website_setup, short_description=short_description, total=setup_cost)
            invoice_entries.append(website_setup_entry)
            i = 0
            while True:
                try:
                    label = request.POST['item%d' % i]
                    amount = float(request.POST['amount%d' % i])
                    if not (label and amount):
                        break
                    item = IkwenInvoiceItem(label=label, amount=amount)
                    entry = InvoiceEntry(item=item, total=amount)
                    invoice_entries.append(entry)
                    i += 1
                except:
                    break
            if getattr(settings, 'DEBUG', False):
                service = deploy(app, customer, business_type, project_name, billing_plan, theme,
                                 monthly_cost, invoice_entries, billing_cycle, domain, partner_retailer=partner)
            else:
                try:
                    service = deploy(app, customer, business_type, project_name, billing_plan, theme,
                                     monthly_cost, invoice_entries, billing_cycle, domain, partner_retailer=partner)
                except Exception as e:
                    context = self.get_context_data(**kwargs)
                    context['error'] = e.message
                    return render(request, 'kakocase/cloud_setup/deploy.html', context)
            if is_ikwen:
                if request.user.is_staff:
                    next_url = reverse('partnership:change_service', args=(service.id, ))
                else:
                    next_url = reverse('ikwen:console')
            else:
                next_url = reverse('change_service', args=(service.id, ))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['form'] = form
            return render(request, 'kakocase/cloud_setup/deploy.html', context)


class SortableListMixin(object):

    def get(self, request, *args, **kwargs):
        sorted_keys = request.GET.get('sorted')
        if sorted_keys:
            for token in sorted_keys.split(','):
                category_id, order_of_appearance = token.split(':')
                try:
                    self.model.objects.filter(pk=category_id).update(order_of_appearance=order_of_appearance)
                except:
                    continue
            return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
        return super(SortableListMixin, self).get(request, *args, **kwargs)


def run_sudo_cmd(request, *args, **kwargs):
    import subprocess
    # subprocess.call(['sudo', 'ln', '-sf', 'home/komsihon/PycharmProjects/KakocaseDelivery/apache.conf',
    #                  '/etc/apache2/sites-enabled/test.conf'])
    subprocess.call(['sudo', 'touch', '/home/komsihon/PycharmProjects/sudo_file.txt'])
    return HttpResponse('Finished')
