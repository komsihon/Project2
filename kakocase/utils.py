# -*- coding: utf-8 -*-
from django.utils.translation import gettext as _
from ikwen.core.models import Application

from ikwen.core.models import ConsoleEventType


def get_cash_out_requested_message(member):
    """
    Returns a tuple (mail subject, mail body, sms text) to send to
    member upon generation of an invoice
    @param invoice: Invoice object
    """
    subject = _("Cash-out requested by %s" % member.full_name)
    message = _("Dear %(member_name)s,<br><br>"
                "This is a notice that an invoice has been generated on %(date_issued)s.<br><br>"
                "<strong style='font-size: 1.2em'>Invoice #%(invoice_number)s</strong><br>"
                "Amount: %(amount).2f %(currency)s<br>"
                "Due Date:  %(due_date)s<br><br>"
                "<strong>Invoice items:</strong><br>"
                "<span style='color: #111'>%(invoice_description)s</span><br><br>"
                "Thank you for your business with "
                "%(company_name)s." % {'member_name': member.first_name,
                                       'company_name': config.company_name,
                                       'invoice_number': invoice.number,
                                       'amount': invoice.amount,
                                       'currency': invoicing_config.currency,
                                       'date_issued': invoice.date_issued.strftime('%B %d, %Y'),
                                       'due_date': invoice.due_date.strftime('%B %d, %Y'),
                                       'invoice_description': invoice.subscription.details})
    return subject, message


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
