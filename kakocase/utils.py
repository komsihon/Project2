# -*- coding: utf-8 -*-
from threading import Thread

from django.utils.translation import gettext as _, activate

from ikwen.core.utils import *
from ikwen.core.models import Application, Service, ConsoleEventType
from ikwen.accesscontrol.backends import UMBRELLA

from ikwen_kakocase.shopping.models import Customer
from ikwen_kakocase.trade.models import Order
from daraja.models import DARAJA, REFEREE_JOINED_EVENT, Dara


def set_customer_dara(service, referrer, member):
    """
    Binds referrer to member referred.
    :param service: Referred Service
    :param referrer: Member who referred (The Dara)
    :param member: Referred Member
    :return:
    """
    try:
        db = service.database
        add_database(db)
        app = Application.objects.using(db).get(slug=DARAJA)
        dara_service = Service.objects.using(db).get(app=app, member=referrer)
        customer, change = Customer.objects.using(db).get_or_create(member=member)
        if customer.referrer:
            return

        customer.referrer = dara_service
        customer.save()

        dara_db = dara_service.database
        add_database(dara_db)
        member.save(using=dara_db)
        customer.save(using=dara_db)

        try:
            dara_umbrella = Dara.objects.using(UMBRELLA).get(member=referrer)
            if dara_umbrella.level == 2:
                if dara_umbrella.xp in [2, 3, 4]:
                    dara_umbrella.xp += 1
                    dara_umbrella.save()
        except:
            pass

        service_mirror = Service.objects.using(dara_db).get(pk=service.id)
        set_counters(service_mirror)
        increment_history_field(service_mirror, 'community_history')

        add_event(service, REFEREE_JOINED_EVENT, member)

        diff = datetime.now() - member.date_joined

        activate(referrer.language)
        sender = "%s via ikwen <no-reply@ikwen.com>" % member.full_name
        if diff.days > 1:
            subject = _("I'm back on %s !" % service.project_name)
        else:
            subject = _("I just joined %s !" % service.project_name)
        html_content = get_mail_content(subject, template_name='daraja/mails/referee_joined.html',
                                        extra_context={'referred_service_name': service.project_name, 'referee': member,
                                                       'referred_service_url': service.url})
        msg = XEmailMessage(subject, html_content, sender, [referrer.email])
        msg.content_subtype = "html"
        Thread(target=lambda m: m.send(), args=(msg, )).start()
    except:
        logger.error("%s - Error while setting Customer Dara", exc_info=True)


def create_console_event_types():
    app = Application.objects.get(slug='kakocase')
    CASH_OUT_REQUEST_EVENT = 'CashOutRequestEvent'
    PROVIDER_ADDED_PRODUCTS_EVENT = 'ProviderAddedProductsEvent'
    PROVIDER_REMOVED_PRODUCT_EVENT = 'ProviderRemovedProductEvent'
    PROVIDER_PUSHED_PRODUCT_EVENT = 'ProviderPushedProductEvent'
    NEW_ORDER_EVENT = 'NewOrderEvent'
    ORDER_SHIPPED_EVENT = 'OrderShippedEvent'
    ORDER_PACKAGED_EVENT = 'OrderPackagedEvent'  # Case of Pick up in store
    INSUFFICIENT_STOCK_EVENT = 'InsufficientStockEvent'
    LOW_STOCK_EVENT = 'LowStockEvent'
    SOLD_OUT_EVENT = 'SoldOutEvent'
    ConsoleEventType.objects.create(app=app, codename=CASH_OUT_REQUEST_EVENT, title="Member requested Cash-out",
                                    target=ConsoleEventType.BUSINESS, renderer="kakocase.views.render_cash_out_request_event")
    ConsoleEventType.objects.create(app=app, codename=ORDER_PACKAGED_EVENT, title="Your order is packaged and ready",
                                    target=ConsoleEventType.BUSINESS, renderer="shopping.views.render_order_event")
    ConsoleEventType.objects.create(app=app, codename=ORDER_SHIPPED_EVENT, title="Your order was shipped",
                                    target=ConsoleEventType.BUSINESS, renderer="shopping.views.render_order_event")


class LastOrderFilter(object):
    title = _('Last order')
    parameter_name = 'last_order'
    is_date_filter = True

    def lookups(self):
        choices = [
            ('__period__today', _("Today")),
            ('__period__yesterday', _("Yesterday")),
            ('__period__last_7_days', _("Last 7 days")),
            ('__period__last_30_days', _("Last 30 days")),
            ('__period__never', _("Never since 60 days")),
        ]
        return choices

    def queryset(self, request, queryset):
        value = request.GET.get(self.parameter_name)
        if not value:
            return queryset

        now = datetime.now()
        start_date, end_date = None, now
        value = value.replace('__period__', '')
        if value == 'never':
            start_date = now - timedelta(days=60)
            order_qs = Order.objects.select_related('member')\
                .filter(status__in=[Order.PENDING, Order.SHIPPED, Order.DELIVERED],
                        created_on__range=(start_date, end_date))
            member_id_list = [order.member.id for order in order_qs]
            return queryset.exclude(user_id__in=member_id_list)
        if value == 'today':
            start_date = datetime(now.year, now.month, now.day, 0, 0, 0)
        elif value == 'yesterday':
            yst = now - timedelta(days=1)
            start_date = datetime(yst.year, yst.month, yst.day, 0, 0, 0)
            end_date = datetime(yst.year, yst.month, yst.day, 23, 59, 59)
        elif value == 'last_7_days':
            b = now - timedelta(days=7)
            start_date = datetime(b.year, b.month, b.day, 0, 0, 0)
        elif value == 'last_30_days':
            b = now - timedelta(days=30)
            start_date = datetime(b.year, b.month, b.day, 0, 0, 0)
        else:
            start_date, end_date = value.split(',')
            start_date += ' 00:00:00'
            end_date += ' 23:59:59'
        order_qs = Order.objects.select_related('member')\
            .filter(status__in=[Order.PENDING, Order.SHIPPED, Order.DELIVERED],
                    created_on__range=(start_date, end_date))
        member_id_list = [order.member.id for order in order_qs]
        queryset = queryset.filter(user_id__in=member_id_list)
        return queryset
