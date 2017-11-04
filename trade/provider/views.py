import json
import logging
from datetime import datetime, timedelta
from threading import Thread

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.core.mail import EmailMessage
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import F
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from ikwen_kakocase.kako.models import Product

from ikwen.core.constants import CONFIRMED, PENDING
from ikwen_kakocase.shopping.utils import after_order_confirmation

from ikwen.core.utils import add_event, increment_history_field, get_service_instance,\
    add_database_to_settings, get_mail_content, set_counters, rank_watch_objects

from ikwen.core.models import Service
from ikwen.accesscontrol.backends import UMBRELLA

from ikwen.core.views import HybridListView
from ikwen_kakocase.kakocase.models import OperatorProfile, DeliveryOption, ORDER_SHIPPED_EVENT, ORDER_PACKAGED_EVENT
from ikwen_kakocase.trade.models import Package, Order
from ikwen_kakocase.trade.views import KakocaseDashboardBase

logger = logging.getLogger('ikwen')


class PackageList(HybridListView):
    template_name = 'trade/provider/package_list.html'
    model = Package
    ordering = ('delivery_expected_on', )
    context_object_name = 'package_list'

    def get_context_data(self, **kwargs):
        context = super(PackageList, self).get_context_data(**kwargs)
        queryset = self.get_queryset().filter(status=Order.PENDING)
        if getattr(settings, 'IS_PROVIDER', False):
            service = get_service_instance()
            queryset = queryset.exclude(delivery_company=service)
            context['partners'] = OperatorProfile.objects.filter(business_type=OperatorProfile.LOGISTICS)
        else:
            context['partners'] = OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER)

        page_size = 15 if self.request.user_agent.is_mobile else 25
        paginator = Paginator(queryset, page_size)
        orders_page = paginator.page(1)
        context['orders_page'] = orders_page
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'html_results':
            package_queryset = self.get_queryset()
            q = self.request.GET.get('q')
            status = self.request.GET.get('status')
            partner_id = self.request.GET.get('partner_id')
            context['filter_results'] = self.request.GET.get('filter_results')
            try:
                days_left = int(self.request.GET.get('days_left'))
            except ValueError:
                days_left = None
            by_ppc = False
            if q:
                try:
                    Package.objects.get(ppc=q.lower())
                    package_queryset = Package.objects.filter(ppc=q.lower())
                    by_ppc = True
                except Package.DoesNotExist:
                    package_queryset = self.get_search_results(package_queryset)
            if not by_ppc:
                if status and status.lower() != 'all':
                    package_queryset = package_queryset.filter(status=status)
                    context['status'] = status
                if partner_id:
                    partner = Service.objects.get(pk=partner_id)
                    if getattr(settings, 'IS_PROVIDER', False):
                        package_queryset = package_queryset.filter(delivery_company=partner)
                    else:
                        package_queryset = package_queryset.filter(provider=partner)
                    context['partner'] = partner
                if days_left is not None:
                    deadline = datetime.now() + timedelta(days=days_left)
                    start = deadline.replace(hour=0, minute=0, second=0)
                    end = deadline.replace(hour=23, minute=59, second=59)
                    package_queryset = package_queryset.filter(delivery_expected_on__gte=start)
                    package_queryset = package_queryset.filter(delivery_expected_on__lte=end)
                    context['days_left'] = days_left
                if getattr(settings, 'IS_PROVIDER', False):
                    service = get_service_instance()
                    package_queryset = package_queryset.exclude(delivery_company=service)

            page_size = 15 if self.request.user_agent.is_mobile else 25
            paginator = Paginator(package_queryset, page_size)
            page = self.request.GET.get('page')
            try:
                orders_page = paginator.page(page)
            except PageNotAnInteger:
                orders_page = paginator.page(1)
            except EmptyPage:
                orders_page = paginator.page(paginator.num_pages)
            context['q'] = q
            context['orders_page'] = orders_page
            return render(self.request, 'trade/snippets/package_list_results.html', context)
        else:
            return super(PackageList, self).render_to_response(context, **response_kwargs)


@permission_required('trade.ik_manage_package')
def get_package_details(request, *args, **kwargs):
    ppc = request.GET.get('ppc')
    package_id = request.GET.get('package_id')
    if ppc:
        package = get_object_or_404(Package, ppc=ppc)
    else:
        package = get_object_or_404(Package, pk=package_id)
    return HttpResponse(
        json.dumps(package.to_dict()),
        'content-type: text/json'
    )


@permission_required('trade.ik_manage_order')
def get_package_from_rcc(request, *args, **kwargs):
    rcc = request.GET['rcc']
    try:
        order = Order.objects.get(rcc=rcc)
    except Order.DoesNotExist:
        response = {'error': _("No order found with this RCC")}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    package = get_object_or_404(Package, order=order)
    return HttpResponse(
        json.dumps(package.to_dict()),
        'content-type: text/json'
    )


@permission_required('trade.ik_manage_order')
def confirm_shipping(request, *args, **kwargs):
    order_id = request.GET.get('order_id')
    package_id = request.GET.get('package_id')
    try:
        if package_id:
            package = Package.objects.get(pk=package_id)
            package.status = Order.SHIPPED
            package.confirmed_on = datetime.now()
            package.confirmed_by = request.user
            package.save()
            order = package.order
        else:
            order = Order.objects.get(pk=order_id)
        order.status = Order.SHIPPED
        order.confirmed_on = datetime.now()
        order.confirmed_by = request.user
        order.save()
    except Order.DoesNotExist:
        response = {'error': _("No Order found with this ID: %s" % order_id)}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    except Package.DoesNotExist:
        response = {'error': _("No Package found with this ID: %s" % package_id)}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    except:
        response = {'error': _("Unknow error occured")}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    else:
        response = {'success': True}

    delivery_company = order.delivery_option.company
    # Set provider balance for those with payment_delay=UPON_CONFIRMATION.
    # Those with payment_delay=STRAIGHT had their balance set in confirm_checkout()
    for package in order.package_set.all():
        provider_service_umbrella = Service.objects.using(UMBRELLA).get(pk=package.provider.id)
        if delivery_company.id != provider_service_umbrella.id:
            provider_profile_umbrella = provider_service_umbrella.config
            if provider_profile_umbrella.payment_delay == OperatorProfile.UPON_CONFIRMATION:
                provider_db = provider_service_umbrella.database
                add_database_to_settings(provider_db)
                provider_original = Service.objects.using(provider_db).get(pk=package.provider.id)
                provider_original.raise_balance(package.provider_earnings, order.payment_mean.slug)

    if getattr(settings, 'IS_PROVIDER', False):
        service = get_service_instance()
        retailer_service = order.retailer
        retailer_earnings = order.retailer_earnings
        if delivery_company == retailer_service:
            retailer_earnings += order.delivery_earnings

        retailer_profile = retailer_service.config
        retailer_db = retailer_service.database
        add_database_to_settings(retailer_db)
        retailer_profile_original = OperatorProfile.objects.using(retailer_db).get(pk=retailer_profile.id)

        set_counters(retailer_profile_original)
        increment_history_field(retailer_profile_original, 'earnings_history', retailer_earnings)
        retailer_profile.report_counters_to_umbrella()
        retailer_profile_original.raise_balance(retailer_earnings, order.payment_mean.slug)

        if order.delivery_option.type == DeliveryOption.HOME_DELIVERY:
            if order.member:
                add_event(service, ORDER_SHIPPED_EVENT, member=order.member, object_id=order.id)
            subject = _("Your order was shipped")
        else:
            if order.member:
                add_event(service, ORDER_PACKAGED_EVENT, member=order.member, object_id=order.id)
            subject = _("Your order is packaged and ready")

        if order.aotc:
            buyer_name = order.anonymous_buyer.name
            email = order.anonymous_buyer.email
        else:
            member = order.member
            buyer_name = member.full_name
            email = member.email

        html_content = get_mail_content(subject, '', template_name='shopping/mails/order_notice.html',
                                        extra_context={'rcc': order.rcc.upper(), 'buyer_name': buyer_name, 'order': order})
        sender = '%s <no-reply@%s>' % (service.project_name, service.domain)
        msg = EmailMessage(subject, html_content, sender, [email])
        msg.content_subtype = "html"
        Thread(target=lambda m: m.send(), args=(msg, )).start()

    return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('trade.ik_manage_package')
def confirm_processing(request, *args, **kwargs):
    """
    This function targets only Logistics Companies and mark a Package as shipped
    """
    package_id = request.GET['package_id']
    try:
        package = Package.objects.get(pk=package_id)
        package.status = Order.SHIPPED
        package.confirmed_on = datetime.now()
        package.confirmed_by = request.user
        package.save()

        order = package.order
        order.status = Order.SHIPPED
        order.confirmed_on = datetime.now()
        order.confirmed_by = request.user
        order.save()
    except Package.DoesNotExist:
        response = {'error': _("No Package found with this ID")}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    except:
        response = {'error': _("Unknow error occured")}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    else:
        response = {'success': True}

    config = get_service_instance().config
    set_counters(config)
    increment_history_field(config, 'orders_count_history')
    increment_history_field(config, 'items_traded_history', order.items_count)
    increment_history_field(config, 'earnings_history', order.delivery_earnings)
    increment_history_field(config, 'turnover_history', order.delivery_option.cost)
    config.report_counters_to_umbrella()

    return HttpResponse(json.dumps(response), 'content-type: text/json')


def notify_order_process(request, order_id, status, bank_id, *args, **kwargs):
    merchant = get_service_instance()
    if getattr(settings, 'DEBUG', False):
        order = Order.objects.get(pk=order_id, status=Order.PENDING_FOR_APPROVAL)
        if status == CONFIRMED:  # If Bank confirmed then make Order visible here by setting it to PENDING
            order.status = PENDING
            after_order_confirmation(order, update_stock=False)
        else:
            for entry in order.entries:
                Product.objects.filter(pk=entry.product.id).update(stock=F('stock') + entry.count)
            order.status = status
            order.save()
        return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
    else:
        try:
            bank = Service.objects.using(UMBRELLA).get(pk=bank_id)
        except Service.DoesNotExist:
            logger.error("Approval notification failed on % for order_id %s, "
                         "from bank with ID %s" % (merchant.project_name, order_id, bank_id), exc_info=True)
            return HttpResponseForbidden("Invalid security headers.")
        try:
            order = Order.objects.get(pk=order_id, status=Order.PENDING_FOR_APPROVAL)
            if order.deal.bank != bank:
                logger.error("%s: Referer bank with ID %s does not "
                             "match the one on order_id %s" % (merchant.project_name, order_id, bank_id), exc_info=True)
                return HttpResponseForbidden("Invalid security headers.")
            if status == CONFIRMED:  # If Bank confirmed then make Order visible here by setting it to PENDING
                order.status = PENDING
                after_order_confirmation(order, update_stock=False)
                logger.debug("Order %s on %s from %s successfully confirmed "
                             "by Bank %s" % (order.id, merchant.project_name, order.member.username, bank.project_name))
            else:
                for entry in order.entries:
                    try:
                        Product.objects.filter(pk=entry.product.id).update(stock=F('stock') + entry.count)
                    except:
                        logger.warning("Could not reset stock of %s after bank revocation "
                                       "of order %s on %s" % entry.product.name, order_id, merchant.project_name)
                order.status = status
                order.save()
            response = {"success": True}
        except Order.DoesNotExist:
            response = {"error": "Order not found."}
        except:
            response = {"error": "Error while running after_order_confirmation"}
            logger.error("After confirmation of Order %s from %s on %s failed" % (order.id, order.member.username, merchant.project_name_slug), exc_info=True)
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class ProviderDashboard(KakocaseDashboardBase):
    template_name = 'trade/provider/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(ProviderDashboard, self).get_context_data(**kwargs)
        retailers = list(OperatorProfile.objects.filter(business_type=OperatorProfile.RETAILER))
        for retailer in retailers:
            set_counters(retailer)
        retailers_report = {
            'today': rank_watch_objects(retailers, 'earnings_history'),
            'yesterday': rank_watch_objects(retailers, 'earnings_history', 1),
            'last_week': rank_watch_objects(retailers, 'earnings_history', 7),
            'last_28_days': rank_watch_objects(retailers, 'earnings_history', 28)
        }
        context['retailers_report'] = retailers_report
        return context
