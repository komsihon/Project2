import json
from datetime import datetime, timedelta

import logging
from threading import Thread

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import permission_required, login_required
from django.core.mail import EmailMessage
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import HttpResponse
from django.http.response import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import slugify
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from ikwen.core.constants import CONFIRMED
from ikwen_kakocase.trade.admin import OrderResource
from import_export.formats.base_formats import XLS

from ikwen.billing.models import PaymentMean

from ikwen.accesscontrol.backends import UMBRELLA

from ikwen.core.models import Service
from ikwen_kakocase.shopping.utils import send_order_confirmation_email

from ikwen.core.utils import calculate_watch_info, add_database, get_mail_content, slice_watch_objects

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance, rank_watch_objects, set_counters
from ikwen.core.views import HybridListView, DashboardBase
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kakocase.models import TIME_LEFT_TO_COMMIT_TO_SELF_DELIVERY, ProductCategory, OperatorProfile, DeliveryOption
from ikwen_kakocase.shopping.models import Customer
from ikwen_kakocase.trade.models import Order, LateDelivery, BrokenProduct, Package, Deal
logger = logging.getLogger('ikwen')


class OrderList(HybridListView):
    template_name = 'trade/order_list.html'
    model = Order
    if getattr(settings, 'IS_BANK', False):
        queryset = Order.objects.exclude(status=Order.PENDING_FOR_PAYMENT)
    else:
        queryset = Order.objects.exclude(Q(status=Order.PENDING_FOR_PAYMENT) & Q(status=Order.PENDING_FOR_APPROVAL))
    ordering = ('-id', )
    context_object_name = 'order_list'
    search_field = 'tags'

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'export':
            return self.export(request, *args, **kwargs)
        return super(OrderList, self).get(request, *args, **kwargs)

    def get_export_filename(self, file_format):
        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = "%s-%s.%s" % (self.model.__name__,
                                 date_str,
                                 file_format.get_extension())
        return filename

    def export(self, request, *args, **kwargs):
        status = request.GET.get('status')
        queryset = self.get_queryset()
        if status and status.lower() != 'all':
            queryset = queryset.filter(status=status)
        queryset = queryset.order_by(*self.ordering)
        file_format = XLS()
        data = OrderResource().export(queryset)
        export_data = file_format.export_data(data)
        content_type = file_format.get_content_type()
        # Django 1.7 uses the content_type kwarg instead of mimetype
        try:
            response = HttpResponse(export_data, content_type=content_type)
        except TypeError:
            response = HttpResponse(export_data, mimetype=content_type)
        response['Content-Disposition'] = 'attachment; filename=%s' % (
            self.get_export_filename(file_format),
        )
        return response

    def get_context_data(self, **kwargs):
        context = super(OrderList, self).get_context_data(**kwargs)
        if getattr(settings, 'IS_BANK', False):
            queryset = self.get_queryset().filter(status=Order.PENDING_FOR_APPROVAL)
        else:
            queryset = self.get_queryset().filter(status=Order.PENDING)
        is_drivy = True if kwargs.get('drivy') else False
        if getattr(settings, 'IS_PROVIDER', False):
            service = get_service_instance()
            queryset = queryset.filter(delivery_company=service)
            if is_drivy:
                queryset = queryset.filter(pick_up_in_store=True)
            else:
                queryset = queryset.exclude(pick_up_in_store=True)
        queryset = queryset.order_by(*self.ordering)
        page_size = 15 if self.request.user_agent.is_mobile else 25
        paginator = Paginator(queryset, page_size)
        orders_page = paginator.page(1)
        context['is_drivy'] = is_drivy
        context['orders_page'] = orders_page
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'html_results':
            order_queryset = self.get_queryset()
            q = self.request.GET.get('q')
            status = self.request.GET.get('status')
            by_rcc = False
            if q:
                try:
                    Order.objects.get(rcc=q.lower())
                    order_queryset = Order.objects.filter(rcc=q.lower())
                    by_rcc = True
                except Order.DoesNotExist:
                    order_queryset = self.get_search_results(order_queryset)
            if not by_rcc:
                is_drivy = context['is_drivy']
                if status and status.lower() != 'all':
                    order_queryset = order_queryset.filter(status=status)
                if getattr(settings, 'IS_PROVIDER', False):
                    service = get_service_instance()
                    order_queryset = order_queryset.filter(delivery_company=service)
                    if is_drivy:
                        order_queryset = order_queryset.filter(pick_up_in_store=True)
                    else:
                        order_queryset = order_queryset.exclude(pick_up_in_store=True)
            order_queryset = order_queryset.order_by(*self.ordering)
            page_size = 15 if self.request.user_agent.is_mobile else 25
            paginator = Paginator(order_queryset, page_size)
            page = self.request.GET.get('page')
            try:
                orders_page = paginator.page(page)
            except PageNotAnInteger:
                orders_page = paginator.page(1)
            except EmptyPage:
                orders_page = paginator.page(paginator.num_pages)
            context['q'] = q
            context['orders_page'] = orders_page
            return render(self.request, 'trade/snippets/order_list_results.html', context)
        else:
            return super(OrderList, self).render_to_response(context, **response_kwargs)


@permission_required('trade.ik_manage_order')
def require_order_rcc(request, *args, **kwargs):
    """
    This view is called when retailer explicitly requires
    the Order RCC to deliver the package himself
    """
    order_id = request.GET['order_id']
    service = get_service_instance()
    retailer = service.config
    if not retailer.is_certified:
        return HttpResponseForbidden(
            json.dumps({'error': 'Only CERTIFIED retailers may request to deliver themselves.'}),
            'content-type: text/json'
        )
    order = get_object_or_404(Order, pk=order_id, status=Order.PENDING)
    diff = datetime.now() - order.created_on
    if diff.total_seconds() > TIME_LEFT_TO_COMMIT_TO_SELF_DELIVERY:
        return HttpResponseForbidden(
            json.dumps({'error': 'Timeout'}),
            'content-type: text/json'
        )
    # if order.get_delivery_city() != retailer.city:
    #     return HttpResponseForbidden(
    #         json.dumps({'error': 'Order expected to be delivered in another city'}),
    #         'content-type: text/json'
    #     )
    delivery_company_db = order.delivery_option.company.database
    order.status = Order.PROCESSING
    order.delivery_option.company = service  # Replace delivery company by actual retailer
    order.save()
    # Delete Packages and Order from original delivery company database
    Package.objects.using(delivery_company_db).filter(order=order).delete()
    order.delete(using=delivery_company_db)

    return HttpResponse(
        json.dumps({'rcc': order.rcc}),
        'content-type: text/json'
    )


@login_required
def get_order_details(request, *args, **kwargs):
    package_id = request.GET.get('package_id')
    order_id = request.GET.get('order_id')
    if package_id:
        package = get_object_or_404(Package, pk=package_id)
        order = package.order
    else:
        package = None
        order = get_object_or_404(Order, pk=order_id)
    context = {
        'service': get_service_instance(),
        'package': package,
        'order': order
    }
    return render(request, 'trade/snippets/order_details.html', context)


def list_partner_companies(request, *args, **kwargs):
    """
    Used for company auto-complete in Package filter in PackageList view.
    """
    q = request.GET['query'].lower()
    if len(q) < 2:
        return
    companies = []
    if getattr(settings, 'IS_PROVIDER', False):
        business_type = request.GET.get('business_type', OperatorProfile.LOGISTICS)
        queryset = OperatorProfile.objects.filter(business_type=business_type)
    else:
        queryset = OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER)
    word = slugify(q)[:4]
    if word:
        companies = list(queryset.filter(company_name__icontains=word)[:10])

    suggestions = [{'value': c.company_name, 'data': c.service.pk} for c in companies]
    response = {'suggestions': suggestions}
    return HttpResponse(json.dumps(response), content_type='application/json')


class LateDeliveryList(HybridListView):
    template_name = 'trade/retailer/delay_complains.html'
    model = LateDelivery
    context_object_name = 'late_deliveries'

    def get_search_results(self, queryset):
        search_term = self.request.GET.get('q')
        if search_term and len(search_term) >= 2:
            for word in search_term.split(' '):
                word = slugify(word)[:4]
                if word:
                    members = list(Member.objects.filter(full_name__icontains=word))
                    orders = list(Order.objects.filter(member__in=members))
                    queryset = queryset.filter(order__in=orders)
                    if queryset.count() > 0:
                        break
        return queryset


class BrokenProductList(LateDeliveryList):
    template_name = 'trade/retailer/broken_product_list.html'
    model = BrokenProduct
    context_object_name = 'broken_products'


@permission_required('trade.ik_manage_order')
def set_issue_reply(request, issue_id, *args, **kwargs):
    try:
        issue = LateDelivery.objects.get(pk=issue_id)
    except LateDelivery.DoesNotExist:
        issue = get_object_or_404(BrokenProduct, pk=issue_id)
    issue.solution = request.GET['solution']
    issue.save()
    response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


class KakocaseDashboardBase(DashboardBase):

    def get_context_data(self, **kwargs):
        context = super(KakocaseDashboardBase, self).get_context_data(**kwargs)
        operator_profile = get_service_instance().config
        set_counters(operator_profile)
        earnings_today = calculate_watch_info(operator_profile.earnings_history)
        earnings_yesterday = calculate_watch_info(operator_profile.earnings_history, 1)
        earnings_last_week = calculate_watch_info(operator_profile.earnings_history, 7)
        earnings_last_28_days = calculate_watch_info(operator_profile.earnings_history, 28)

        orders_count_today = calculate_watch_info(operator_profile.orders_count_history)
        orders_count_yesterday = calculate_watch_info(operator_profile.orders_count_history, 1)
        orders_count_last_week = calculate_watch_info(operator_profile.orders_count_history, 7)
        orders_count_last_28_days = calculate_watch_info(operator_profile.orders_count_history, 28)

        # AEPO stands for Average Earning Per Order
        aepo_today = earnings_today['total'] / orders_count_today['total'] if orders_count_today['total'] else 0
        aepo_yesterday = earnings_yesterday['total'] / orders_count_yesterday['total']\
            if orders_count_yesterday and orders_count_yesterday['total'] else 0
        aepo_last_week = earnings_last_week['total'] / orders_count_last_week['total']\
            if orders_count_last_week and orders_count_last_week['total'] else 0
        aepo_last_28_days = earnings_last_28_days['total'] / orders_count_last_28_days['total']\
            if orders_count_last_28_days and orders_count_last_28_days['total'] else 0

        earnings_report = {
            'today': earnings_today,
            'yesterday': earnings_yesterday,
            'last_week': earnings_last_week,
            'last_28_days': earnings_last_28_days
        }
        orders_report = {
            'today': {
                'count': orders_count_today['total'] if orders_count_today else 0,
                'aepo': '%.2f' % aepo_today,  # AEPO: Avg Earning Per Order
            },
            'yesterday': {
                'count': orders_count_yesterday['total'] if orders_count_yesterday else 0,
                'aepo': '%.2f' % aepo_yesterday,  # AEPO: Avg Earning Per Order
            },
            'last_week': {
                'count': orders_count_last_week['total'] if orders_count_last_week else 0,
                'aepo': '%.2f' % aepo_last_week,  # AEPO: Avg Earning Per Order
            },
            'last_28_days': {
                'count': orders_count_last_28_days['total']if orders_count_last_28_days else 0,
                'aepo': '%.2f' % aepo_last_28_days,  # AEPO: Avg Earning Per Order
            }
        }
        categories = list(ProductCategory.objects.all())
        for category in categories:
            set_counters(category)
        categories_report = {
            'today': rank_watch_objects(categories, 'earnings_history'),
            'yesterday': rank_watch_objects(categories, 'earnings_history', 1),
            'last_week': rank_watch_objects(categories, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(categories, 'earnings_history', 28)
        }
        products = list(Product.objects.filter(visible=True, in_trash=False))
        for product in products:
            set_counters(product)
        products_report = {
            'today': rank_watch_objects(products, 'units_sold_history'),
            'yesterday': rank_watch_objects(products, 'units_sold_history', 1),
            'last_week': rank_watch_objects(products, 'units_sold_history', 7),
            'last_28_days': rank_watch_objects(products, 'units_sold_history', 28)
        }

        context['earnings_report'] = earnings_report
        context['orders_report'] = orders_report
        context['categories_report'] = categories_report
        context['products_report'] = products_report
        context['earnings_history'] = operator_profile.earnings_history[-30:]
        context['earnings_history_for_month_before_the_last_one'] = operator_profile.earnings_history[-60:-31]
        context['transaction_count_history'] = operator_profile.orders_count_history[-30:]
        return context


class RetailerDashboard(KakocaseDashboardBase):
    template_name = 'trade/retailer/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(RetailerDashboard, self).get_context_data(**kwargs)
        providers = list(OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER))
        for provider in providers:
            set_counters(provider)
        providers_report = {
            'today': rank_watch_objects(providers, 'earnings_history'),
            'yesterday': rank_watch_objects(providers, 'earnings_history', 1),
            'last_week': rank_watch_objects(providers, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(providers, 'earnings_history', 28)
        }

        customers_today = slice_watch_objects(Customer)
        customers_yesterday = slice_watch_objects(Customer, 1)
        customers_last_week = slice_watch_objects(Customer, 7)
        customers_last_28_days = slice_watch_objects(Customer, 28)
        customers_report = {
            'today': rank_watch_objects(customers_today, 'earnings_history'),
            'yesterday': rank_watch_objects(customers_yesterday, 'earnings_history', 1),
            'last_week': rank_watch_objects(customers_last_week, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(customers_last_28_days, 'earnings_history', 28)
        }
        context['providers_report'] = providers_report
        context['customers_report'] = customers_report
        return context


class LogicomDashboard(DashboardBase):
    template_name = 'trade/logicom/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(LogicomDashboard, self).get_context_data(**kwargs)
        operator_profile = get_service_instance().config
        set_counters(operator_profile)
        earnings_today = context['earnings_report']['today']
        earnings_yesterday = context['earnings_report']['yesterday']
        earnings_last_week = context['earnings_report']['last_week']
        earnings_last_28_days = context['earnings_report']['last_28_days']

        orders_count_today = calculate_watch_info(operator_profile.orders_count_history)
        orders_count_yesterday = calculate_watch_info(operator_profile.orders_count_history, 1)
        orders_count_last_week = calculate_watch_info(operator_profile.orders_count_history, 7)
        orders_count_last_28_days = calculate_watch_info(operator_profile.orders_count_history, 28)

        # AEPO stands for Average Earning Per Order
        aepo_today = earnings_today['total'] / orders_count_today['total'] if orders_count_today['total'] else 0
        aepo_yesterday = earnings_yesterday['total'] / orders_count_yesterday['total']\
            if orders_count_yesterday and orders_count_yesterday['total'] else 0
        aepo_last_week = earnings_last_week['total'] / orders_count_last_week['total']\
            if orders_count_last_week and orders_count_last_week['total'] else 0
        aepo_last_28_days = earnings_last_28_days['total'] / orders_count_last_28_days['total']\
            if orders_count_last_28_days and orders_count_last_28_days['total'] else 0

        orders_report = {
            'today': {
                'count': orders_count_today['total'] if orders_count_today else 0,
                'aepo': '%.2f' % aepo_today,  # AEPO: Avg Earning Per Order
            },
            'yesterday': {
                'count': orders_count_yesterday['total'] if orders_count_yesterday else 0,
                'aepo': '%.2f' % aepo_yesterday,  # AEPO: Avg Earning Per Order
            },
            'last_week': {
                'count': orders_count_last_week['total'] if orders_count_last_week else 0,
                'aepo': '%.2f' % aepo_last_week,  # AEPO: Avg Earning Per Order
            },
            'last_28_days': {
                'count': orders_count_last_28_days['total']if orders_count_last_28_days else 0,
                'aepo': '%.2f' % aepo_last_28_days,  # AEPO: Avg Earning Per Order
            }
        }
        providers = list(OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER))
        for provider in providers:
            set_counters(provider)
        providers_report = {
            'today': rank_watch_objects(providers, 'earnings_history'),
            'yesterday': rank_watch_objects(providers, 'earnings_history', 1),
            'last_week': rank_watch_objects(providers, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(providers, 'earnings_history', 28)
        }

        context['orders_report'] = orders_report
        context['providers_report'] = providers_report
        return context


class PartnerList(HybridListView):
    template_name = 'trade/partner_list.html'
    if getattr(settings, 'IS_BANK', False):
        queryset = OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER)
    else:
        queryset = OperatorProfile.objects.filter(business_type=OperatorProfile.BANK)
    context_object_name = 'partner_list'

    def add_partner(self, request):
        partner_id = request.GET['partner_id']
        partner = Service.objects.using(UMBRELLA).get(pk=partner_id)
        partner_config = OperatorProfile.objects.using(UMBRELLA).get(service=partner)
        partner_member = partner.member
        service = get_service_instance()
        member = Member.objects.get(pk=service.member.id)
        config = OperatorProfile.objects.get(service=service)
        if getattr(settings, 'IS_BANK', False):
            partner_member.save(using='default')
            partner.save(using='default')
            partner_config.save(using='default')
            partner_db = partner.database
            add_database(partner_db)
            member.save(using=partner_db)
            service.save(using=partner_db)
            config.save(using=partner_db)
            PaymentMean.objects.using(partner_db).filter(slug='cashflex').update(is_active=True)
            PaymentMean.objects.using(partner_db).create(name=service.project_name, slug=service.project_name_slug,
                                                         is_cashflex=True)
            subject = "Welcome"
        else:
            subject = "Request for integration"
        messages.success(request, _("%s successfully added." % partner_config.company_name))
        html_content = get_mail_content(subject, '', template_name='trade/mails/partnership_notice.html',
                                        extra_context={'settings': settings})
        sender = '%s <no-reply@%s>' % (service.project_name, service.domain)
        msg = EmailMessage(subject, html_content, sender, [partner_config.contact_email])
        msg.bcc = ['contact@ikwen.com']
        msg.content_subtype = "html"
        Thread(target=lambda m: m.send(), args=(msg, )).start()
        next_url = reverse('trade:partner_list')
        return HttpResponseRedirect(next_url)

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'add_partner':
            return self.add_partner(request)
        return super(PartnerList, self).get(request, *args, **kwargs)


class DealList(TemplateView):
    template_name = 'trade/bank/deal_list.html'

    def get_context_data(self, **kwargs):
        context = super(DealList, self).get_context_data(**kwargs)
        product_id = kwargs['product_id']
        product = get_object_or_404(Product, pk=product_id)
        context['product'] = product
        context['deal_list'] = Deal.objects.filter(product_slug=product.slug, merchant=product.provider)
        context['frequencies'] = Deal.FREQUENCY_CHOICES
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'delete':
            return self.delete_deal(request, *args, **kwargs)
        return super(DealList, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        product = context['product']
        merchant = product.provider
        bank = get_service_instance()
        merchant_db = merchant.database
        add_database(merchant_db)
        Deal.objects.filter(product_slug=product.slug, merchant=merchant).delete()
        Deal.objects.using(merchant_db).filter(product_slug=product.slug, merchant=merchant).delete()
        i = 0
        while True:
            try:
                is_active = True if request.POST.get('is_active%d' % i) else False
                deal = Deal.objects.create(product_slug=product.slug, merchant=merchant, bank=bank, frequency=request.POST['frequency%d' % i],
                                           terms_count=request.POST['terms_count%d' % i], first_term=request.POST['first_term%d' % i],
                                           term_cost=request.POST['term_cost%d' % i], about=request.POST['about%d' % i],
                                           is_active=is_active)
                deal.save(using=merchant_db)
                i += 1
            except MultiValueDictKeyError:
                break
        msg = _("Deals for %s successfully saved." % product.name)
        messages.success(request, msg)
        next_url = reverse('trade:deal_list', args=(product.id, ))
        return HttpResponseRedirect(next_url)

    def delete_deal(self, request, *args, **kwargs):
        deal_id = request.GET.get('deal_id')
        Deal.objects.filter(pk=deal_id).delete()
        response = {'deleted': [deal_id]}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('trade.ik_manage_order')
def approve_or_reject(request, *args, **kwargs):
    """
    This function targets only Banks and mark Order as accepted or rejected
    """
    if not getattr(settings, 'IS_BANK', False):
        return HttpResponseForbidden("Only Banks are allowed here.")
    order_id = request.GET['order_id']
    status = request.GET['status']
    message = request.GET.get('message')
    bank = get_service_instance()
    if getattr(settings, 'DEBUG', False):
        order = Order.objects.get(pk=order_id, status=Order.PENDING_FOR_APPROVAL)
        member = order.member
        merchant = Service.objects.using(UMBRELLA).get(pk=order.retailer.id)
        target = reverse('trade:notify_order_process', args=(order.id, status, bank.id))
        target = target.replace(getattr(settings, 'WSGI_SCRIPT_ALIAS', ''), '')
        url = merchant.url + target
        r = requests.get(url)
        resp = r.json()
        if resp.get('error'):
            logger.error(resp['error'])
            response = {'error': resp['error']}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        order.status = status
        order.confirmed_on = datetime.now()
        order.confirmed_by = request.user
        order.save()
        if status == CONFIRMED:
            # Order moved from status PENDING_FOR_APPROVAL to PENDING, meaning
            # that the financial institution accepted to repay the merchant
            logger.debug("Order '%s' approved by %s" % (order.id, request.user.username))
            response = {'success': True}
            subject = _("Your order on %s was approved" % merchant.project_name)
        else:
            response = {'success': True}
            subject = _("Your order on %s was rejected" % merchant.project_name)
        send_order_confirmation_email(subject, member.full_name, member.email, order, message)
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    else:
        try:
            order = Order.objects.get(pk=order_id)
            member = order.member
            merchant = Service.objects.using(UMBRELLA).get(pk=order.retailer.id)
            url = merchant.url + reverse('trade:notify_order_approval', args=(order.id, status, merchant.api_signature))
            try:
                r = requests.get(url)
                resp = r.json()
                if resp['error']:
                    logger.error(resp['error'])
                    response = {'error': resp['error']}
                    return HttpResponse(json.dumps(response), 'content-type: text/json')
                order.status = status
                order.confirmed_on = datetime.now()
                order.confirmed_by = request.user
                order.save()
                if status == CONFIRMED:
                    # Order moved from status PENDING_FOR_APPROVAL to PENDING, meaning
                    # that the financial institution accepted to repay the merchant
                    logger.debug("Order '%s' approved by %s" % (order.id, request.user.username))
                    response = {'success': True}
                    subject = _("Your order on %s was approved" % merchant.project_name)
                else:
                    response = {'success': True}
                    subject = _("Your order on %s was rejected" % merchant.project_name)
                send_order_confirmation_email(subject, member.full_name, member.email, order, message)
                return HttpResponse(json.dumps(response), 'content-type: text/json')
            except:
                msg = "Error while notifying merchant"
                logger.error(msg, exc_info=True)
                response = {'error': msg}
                return HttpResponse(json.dumps(response), 'content-type: text/json')
        except Order.DoesNotExist:
            response = {'error': _("No Order found with this ID")}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        except:
            response = {'error': _("Unknown error occurred")}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
