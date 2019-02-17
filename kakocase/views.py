import json

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db.models.loading import get_model
from django.http import HttpResponse
from django.http.response import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.http import urlquote
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import TemplateView

from ikwen.partnership.models import ApplicationRetailConfig

from ikwen.theming.models import Theme, Template

from ikwen.accesscontrol.models import Member

from ikwen.billing.models import IkwenInvoiceItem, InvoiceEntry, CloudBillingPlan, Invoice

from ikwen.core.models import Service, Application

from django.utils.translation import gettext as _

from ikwen_kakocase.kakocase.models import OperatorProfile, DeliveryOption, BusinessCategory, TsunamiBundle

from ikwen.accesscontrol.utils import VerifiedEmailTemplateView
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import get_service_instance
from ikwen_kakocase.kakocase.cloud_setup import DeploymentForm, deploy


class AdminHome(TemplateView):
    template_name = 'kakocase/admin_home.html'


class DeliveryOptionList(TemplateView):
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
        if DeliveryOption.objects.filter(type=DeliveryOption.PICK_UP_IN_STORE, is_active=True).count() > 0:
            manage_drivy = True
    request.session['manage_packages'] = manage_packages
    request.session['manage_drivy'] = manage_drivy


class DeployCloud(VerifiedEmailTemplateView):
    template_name = 'kakocase/cloud_setup/deploy.html'

    def get_context_data(self, **kwargs):
        context = super(DeployCloud, self).get_context_data(**kwargs)
        context['billing_cycles'] = Service.BILLING_CYCLES_CHOICES
        app = Application.objects.using(UMBRELLA).get(slug='kakocase')
        context['app'] = app
        template_list = list(Template.objects.using(UMBRELLA).filter(app=app))
        context['theme_list'] = Theme.objects.using(UMBRELLA).filter(template__in=template_list)
        context['can_choose_themes'] = True
        if getattr(settings, 'IS_IKWEN', False):
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner__isnull=True, is_active=True)
            if billing_plan_list.count() == 0:
                setup_months_count = 3
                context['ikwen_setup_cost'] = app.base_monthly_cost * setup_months_count
                context['ikwen_monthly_cost'] = app.base_monthly_cost
                context['setup_months_count'] = setup_months_count
        else:
            service = get_service_instance()
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner=service, is_active=True)
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
            business_category_id = form.cleaned_data.get('business_category_id')
            domain = form.cleaned_data.get('domain')
            theme_id = form.cleaned_data.get('theme_id')
            partner_id = form.cleaned_data.get('partner_id')
            app = Application.objects.using(UMBRELLA).get(pk=app_id)
            theme = Theme.objects.using(UMBRELLA).get(pk=theme_id)
            billing_plan = CloudBillingPlan.objects.using(UMBRELLA).get(pk=billing_plan_id)
            if business_category_id:
                business_category = BusinessCategory.objects.using(UMBRELLA).get(pk=business_category_id)
            else:
                business_category = None

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
            if theme.cost > 0:
                theme_item = IkwenInvoiceItem(label='Website theme', price=theme.cost, amount=theme.cost)
                theme_entry = InvoiceEntry(item=theme_item, short_description=theme.name, total=theme.cost)
                invoice_entries.append(theme_entry)
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
                service = deploy(app, customer, business_type, project_name, billing_plan, theme, monthly_cost,
                                 invoice_entries, billing_cycle, domain, business_category, None,
                                 partner_retailer=partner)
            else:
                try:
                    service = deploy(app, customer, business_type, project_name, billing_plan, theme, monthly_cost,
                                     invoice_entries, billing_cycle, domain, business_category, None,
                                     partner_retailer=partner)
                except Exception as e:
                    context = self.get_context_data(**kwargs)
                    context['error'] = e.message
                    return render(request, 'kakocase/cloud_setup/deploy.html', context)
            if is_ikwen:
                if request.user.is_staff:
                    next_url = reverse('partnership:change_service', args=(service.id,))
                else:
                    next_url = reverse('ikwen:console')
            else:
                next_url = reverse('change_service', args=(service.id,))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['form'] = form
            return render(request, 'kakocase/cloud_setup/deploy.html', context)


class SortableListMixin(object):

    def get(self, request, *args, **kwargs):
        sorted_keys = request.GET.get('sorted')
        model_name = request.GET.get('model_name')
        if model_name:
            tokens = model_name.split('.')
            model = get_model(tokens[0], tokens[1])
        else:
            model = self.model
        if sorted_keys:
            for token in sorted_keys.split(','):
                category_id, order_of_appearance = token.split(':')
                try:
                    model.objects.filter(pk=category_id).update(order_of_appearance=order_of_appearance)
                except:
                    continue
            return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
        return super(SortableListMixin, self).get(request, *args, **kwargs)


class MerchantList(TemplateView):
    template_name = 'kakocase/merchant_list.html'

    def get_context_data(self, **kwargs):
        context = super(MerchantList, self).get_context_data(**kwargs)
        app = Application.objects.get(slug='kakocase')
        # merchant_list = Service.objects.using('umbrella').all()
        merchant_list = Service.objects.filter(app=app, monthly_cost=25000)
        context['merchant_list'] = merchant_list
        context['merchant_list_string'] = ' - '.join([m.project_name for m in merchant_list[:20]])
        return context


class SuccessfulDeployment(TemplateView):
    template_name = 'kakocase/tsunami/successful_deployment.html'

    def get_context_data(self, **kwargs):
        context = super(SuccessfulDeployment, self).get_context_data(**kwargs)
        service_id = kwargs.pop('service_id')
        service = get_object_or_404(Service, pk=service_id)
        context['invoice'] = Invoice.objects.filter(subscription=service)[0]
        context['new_service'] = service
        return context


class Go(VerifiedEmailTemplateView):
    template_name = 'kakocase/tsunami/go.html'

    def get_context_data(self, **kwargs):
        context = super(Go, self).get_context_data(**kwargs)
        context['billing_cycles'] = Service.BILLING_CYCLES_CHOICES
        app = Application.objects.using(UMBRELLA).get(slug='kakocase')
        context['app'] = app
        template_list = list(Template.objects.using(UMBRELLA).filter(app=app))
        context['theme'] = list(Theme.objects.using(UMBRELLA).filter(template__in=template_list))[-1]
        context['can_choose_themes'] = True
        billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner__isnull=True, is_active=True)
        setup_months_count = 3
        context['ikwen_setup_cost'] = app.base_monthly_cost * setup_months_count
        context['ikwen_monthly_cost'] = app.base_monthly_cost
        context['setup_months_count'] = setup_months_count
        context['billing_plan'] = billing_plan_list[0]
        context['business_category_list'] = BusinessCategory.objects.using(UMBRELLA).all()
        return context

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
            business_category_id = form.cleaned_data.get('business_category_id')
            bundle_id = form.cleaned_data.get('bundle_id')
            domain = form.cleaned_data.get('domain')
            theme_id = form.cleaned_data.get('theme_id')
            partner_id = form.cleaned_data.get('partner_id')
            app = Application.objects.using(UMBRELLA).get(pk=app_id)
            theme = Theme.objects.using(UMBRELLA).get(pk=theme_id)
            billing_plan = CloudBillingPlan.objects.using(UMBRELLA).get(pk=billing_plan_id)
            business_category = BusinessCategory.objects.using(UMBRELLA).get(pk=business_category_id)
            bundle = TsunamiBundle.objects.using(UMBRELLA).get(pk=bundle_id) if bundle_id else None

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
            if theme.cost > 0:
                theme_item = IkwenInvoiceItem(label='Website theme', price=theme.cost, amount=theme.cost)
                theme_entry = InvoiceEntry(item=theme_item, short_description=theme.name, total=theme.cost)
                invoice_entries.append(theme_entry)
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
                service = deploy(app, customer, business_type, project_name, billing_plan, theme, monthly_cost,
                                 invoice_entries, billing_cycle, domain, business_category, bundle,
                                 partner_retailer=partner)
            else:
                try:
                    service = deploy(app, customer, business_type, project_name, billing_plan, theme, monthly_cost,
                                     invoice_entries, billing_cycle, domain, business_category, bundle,
                                     partner_retailer=partner)
                except Exception as e:
                    context = self.get_context_data(**kwargs)
                    context['error'] = e.message
                    return render(request, 'kakocase/tsunami/go.html', context)
            next_url = reverse('kakocase:successful_deployment', args=(service.id, ))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['form'] = form
            return render(request, 'kakocase/tsunami/go.html', context)


class Welcome(TemplateView):
    template_name = 'kakocase/welcome.html'

    def get_context_data(self, **kwargs):
        context = super(Welcome, self).get_context_data(**kwargs)
        service = get_service_instance()
        config = OperatorProfile.objects.using(UMBRELLA).get(service=service)
        context['business_category'] = config.business_category.slug
        return context
