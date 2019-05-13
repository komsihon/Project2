# -*- coding: utf-8 -*-
import logging
from datetime import timedelta, datetime
from threading import Thread

import requests
from currencies.context_processors import currencies
from currencies.models import Currency
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.utils.translation import gettext as _

from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.accesscontrol.models import SUDO
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.models import Country, Service
from ikwen.core.utils import set_counters, get_service_instance, increment_history_field, get_mail_content, \
    add_database, add_event, send_sms, XEmailMessage

from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kako.utils import mark_duplicates
from ikwen_kakocase.sales.models import PromoCode
from ikwen_kakocase.sales.views import apply_promotion_discount
from ikwen_kakocase.kakocase.models import OperatorProfile, ProductCategory, SOLD_OUT_EVENT, NEW_ORDER_EVENT

from currencies.conf import SESSION_KEY as CURRENCY_SESSION_KEY
from echo.models import Balance
from echo.utils import count_pages, notify_for_empty_messaging_credit, notify_for_low_messaging_credit, LOW_SMS_LIMIT

logger = logging.getLogger('ikwen.crons')


def parse_order_info(request):
    from ikwen_kakocase.kako.models import Product
    from ikwen_kakocase.shopping.models import Customer, AnonymousBuyer, DeliveryAddress
    from ikwen_kakocase.trade.models import OrderEntry, Order
    from ikwen_kakocase.kakocase.models import DeliveryOption

    entries = request.POST['entries'].split(',')
    delivery_option_id = request.POST['delivery_option_id']
    buy_packing = request.POST.get('buy_packing', False)
    try:
        currency = Currency.objects.get(code=request.session[CURRENCY_SESSION_KEY])
    except KeyError:
        currency = Currency.active.base()
    except Currency.DoesNotExist:
        currency = Currency.objects.all()[0]

    delivery_option = DeliveryOption.objects.get(pk=delivery_option_id)
    seconds = delivery_option.max_delay * 3600
    deadline = timezone.now() + timedelta(seconds=seconds)
    pick_up_in_store = True if delivery_option.type == DeliveryOption.PICK_UP_IN_STORE else False
    order = Order(items_cost=0, items_count=0, total_cost=0, device=request.user_agent.device.family,
                  delivery_option=delivery_option, delivery_expected_on=deadline,
                  delivery_company=delivery_option.company, pick_up_in_store=pick_up_in_store,
                  currency=currency)

    previous_address_index = request.POST.get('previous_address_index')
    if not previous_address_index:
        try:
            country = Country.objects.get(iso2=request.POST.get('country_iso2'))
        except Country.DoesNotExist:
            country = None
        city = request.POST.get('city')
        name = request.POST.get('name')
        email = request.POST['email']
        phone = request.POST['phone']
        postal_code = request.POST.get('postal_code', 'N/A')
        if pick_up_in_store:
            details = delivery_option.name
        else:
            details = request.POST.get('details', '<empty>')
        address = DeliveryAddress(name=name, country=country, city=city,
                                  details=details, postal_code=postal_code, email=email, phone=phone)

    if request.user.is_authenticated():
        try:
            customer = Customer.objects.get(member=request.user)
        except Customer.DoesNotExist:
            customer = Customer.objects.create(member=request.user)
            customer.delivery_addresses.append(address)
        else:
            if not previous_address_index:
                for obj in customer.delivery_addresses:
                    if obj.country == country and obj.city == city and \
                       obj.details == details and obj.phone == phone and obj.email == email:
                        break
                else:
                    customer.delivery_addresses.append(address)
            else:
                address = customer.delivery_addresses[int(previous_address_index)]
        customer.save()
        order.tags = request.user.full_name
    else:
        anonymous_buyer_id = request.POST.get('anonymous_buyer_id')
        name = request.POST.get('name')
        order.tags = name
        if anonymous_buyer_id:
            try:
                anonymous_buyer = AnonymousBuyer.objects.get(pk=anonymous_buyer_id)
            except AnonymousBuyer.DoesNotExist:
                anonymous_buyer = AnonymousBuyer.objects.create(email=email, name=name, phone=phone)
        else:
            anonymous_buyer = AnonymousBuyer.objects.create(email=email, name=name, phone=phone)
        if not previous_address_index:
            try:
                last_address = anonymous_buyer.delivery_addresses[-1]
                if last_address.country != country or last_address.city != city or \
                   last_address.details != details or last_address.phone != phone or last_address.email != email:
                    anonymous_buyer.delivery_addresses.append(address)
            except IndexError:
                anonymous_buyer.delivery_addresses.append(address)
            anonymous_buyer.name = name
            anonymous_buyer.save()
        else:
            address = anonymous_buyer.delivery_addresses[int(previous_address_index)]
        order.anonymous_buyer = anonymous_buyer

    coupon = None
    if request.session.get('promo_code'):
        promo_id = request.session['promo_code_id']
        try:
            now = datetime.now()
            coupon = PromoCode.objects.get(pk=promo_id, start_on__lte=now, end_on__gt=now, is_active=True)
        except PromoCode.DoesNotExist:
            pass

    for entry in entries:
        tokens = entry.split(':')
        product = Product.objects.get(pk=tokens[0])
        product = apply_promotion_discount([product])[0]
        product.units_sold_history = []  # Wipe these unnecessary data for this case
        count = int(tokens[1])

        if not buy_packing:
            product.packing_price = 0  # Cancel packing price if refused to buy packing

        if coupon:
            rate = coupon.rate
            product.retail_price = product.retail_price * (100 - rate) / 100
            # product.packing_price = product.packing_price * (100 - rate) / 100

        order_entry = OrderEntry(product=product,  count=count)
        order.entries.append(order_entry)
        order.items_count += count
        order.items_cost += product.retail_price * count
        order.packing_cost += product.packing_price * count
        order.tags += ' ' + product.name

    order.coupon = coupon
    order.packing_cost += delivery_option.packing_cost
    order.total_cost = order.items_cost + order.packing_cost + delivery_option.cost
    order.delivery_address = address
    return order


def send_order_confirmation_email(request, subject, buyer_name, buyer_email, order, message=None, reward_pack_list=None):
    service = get_service_instance()
    coupon_count = 0
    if reward_pack_list:
        template_name = 'shopping/mails/order_notice_with_reward.html'
        for pack in reward_pack_list:
            coupon_count += pack.count
    else:
        template_name = 'shopping/mails/order_notice.html'

    with transaction.atomic(using=WALLETS_DB_ALIAS):
        balance, update = Balance.objects.using(WALLETS_DB_ALIAS).get_or_create(service_id=service.id)
        if 0 < balance.mail_count < LOW_SMS_LIMIT:
            try:
                notify_for_low_messaging_credit(service, balance)
            except:
                logger.error("Failed to notify %s for low messaging credit." % service, exc_info=True)
        if balance.mail_count == 0 and not getattr(settings, 'UNIT_TESTING', False):
            try:
                notify_for_empty_messaging_credit(service, balance)
            except:
                logger.error("Failed to notify %s for empty messaging credit." % service, exc_info=True)
            return
        crcy = currencies(request)['CURRENCY']
        html_content = get_mail_content(subject, template_name=template_name,
                                        extra_context={'buyer_name': buyer_name, 'order': order, 'message': message,
                                                       'IS_BANK': getattr(settings, 'IS_BANK', False),
                                                       'coupon_count': coupon_count, 'crcy': crcy})
        sender = '%s <no-reply@%s>' % (service.project_name, service.domain)
        msg = XEmailMessage(subject, html_content, sender, [buyer_email])
        bcc = [email.strip() for email in service.config.notification_email.split(',') if email.strip()]
        bcc.append(service.member.email)
        msg.bcc = list(set(bcc))
        msg.content_subtype = "html"
        if not getattr(settings, 'UNIT_TESTING', False):
            balance.mail_count -= len(msg.bcc) + 1
        balance.save()
        Thread(target=lambda m: m.send(), args=(msg, )).start()


def send_order_confirmation_sms(buyer_name, buyer_phone, order):
    service = get_service_instance()
    config = service.config
    script_url = getattr(settings, 'SMS_API_SCRIPT_URL', config.sms_api_script_url)
    if not script_url:
        return
    details_max_length = 90
    details = order.get_products_as_string()
    if len(details) > details_max_length:
        tokens = details.split(',')
        while len(details) > details_max_length:
            tokens = tokens[:-1]
            details = ','.join(tokens)
        details += ' ...'
    client_text = _("Order successful:\n"
                    "%(details)s\n"
                    "Your RCC is %(rcc)s\n"
                    "Thank you." % {'details': details, 'rcc': order.rcc.upper()})
    iao_text = "Order from %(buyer_name)s:\n" \
               "%(details)s\n" \
               "RCC: %(rcc)s" % {'buyer_name': buyer_name[:20], 'details': details, 'rcc': order.rcc.upper()}

    iao_phones = [phone.strip() for phone in config.notification_phone.split(',') if phone.strip()]
    client_page_count = count_pages(client_text)
    iao_page_count = count_pages(iao_text)
    needed_credit = client_page_count + iao_page_count * len(iao_phones)
    balance, update = Balance.objects.using(WALLETS_DB_ALIAS).get_or_create(service_id=service.id)
    if needed_credit < balance.mail_count < LOW_SMS_LIMIT:
        try:
            notify_for_low_messaging_credit(service, balance)
        except:
            logger.error("Failed to notify %s for low messaging credit." % service, exc_info=True)
    if balance.sms_count < needed_credit:
        try:
            notify_for_empty_messaging_credit(service, balance)
        except:
            logger.error("Failed to notify %s for empty messaging credit." % service, exc_info=True)
        return
    buyer_phone = buyer_phone.strip()
    buyer_phone = slugify(buyer_phone).replace('-', '')
    if buyer_phone and len(buyer_phone) == 9:
        buyer_phone = '237' + buyer_phone  # This works only for Cameroon
    try:
        with transaction.atomic(using=WALLETS_DB_ALIAS):
            balance.sms_count -= client_page_count
            balance.save()
            send_sms(buyer_phone, client_text, script_url=script_url, fail_silently=False)
    except:
        pass

    for phone in iao_phones:
        phone = slugify(phone).replace('-', '')
        if len(phone) == 9:
            phone = '237' + phone
        try:
            with transaction.atomic(using=WALLETS_DB_ALIAS):
                balance.sms_count -= iao_page_count
                balance.save()
                send_sms(phone, iao_text, script_url=script_url, fail_silently=False)
        except:
            pass


def set_ikwen_earnings_and_stats(order):
    service = get_service_instance()
    service_umbrella = Service.objects.using(UMBRELLA).get(pk=service.id)
    app_umbrella = service_umbrella.app

    delcom = order.delivery_company
    service_delcom_umbrella = Service.objects.using(UMBRELLA).get(pk=delcom.id)
    app_delcom_umbrella = service_delcom_umbrella.app

    # IKWEN STATS
    set_counters(service_umbrella)
    increment_history_field(service_umbrella, 'turnover_history', order.items_cost)
    increment_history_field(service_umbrella, 'earnings_history', order.ikwen_order_earnings)
    increment_history_field(service_umbrella, 'transaction_count_history')
    increment_history_field(service_umbrella, 'transaction_earnings_history', order.ikwen_order_earnings)

    set_counters(app_umbrella)
    increment_history_field(app_umbrella, 'turnover_history', order.items_cost)
    increment_history_field(app_umbrella, 'earnings_history', order.ikwen_order_earnings)
    increment_history_field(app_umbrella, 'transaction_count_history')
    increment_history_field(app_umbrella, 'transaction_earnings_history', order.ikwen_order_earnings)

    set_counters(service_delcom_umbrella)
    increment_history_field(service_delcom_umbrella, 'turnover_history', order.delivery_option.cost)
    increment_history_field(service_delcom_umbrella, 'earnings_history', order.ikwen_delivery_earnings)
    increment_history_field(service_delcom_umbrella, 'transaction_count_history')
    increment_history_field(service_delcom_umbrella, 'transaction_earnings_history', order.ikwen_delivery_earnings)

    set_counters(app_delcom_umbrella)
    increment_history_field(app_delcom_umbrella, 'turnover_history', order.delivery_option.cost)
    increment_history_field(app_delcom_umbrella, 'earnings_history', order.ikwen_delivery_earnings)
    increment_history_field(app_delcom_umbrella, 'transaction_count_history')
    increment_history_field(app_delcom_umbrella, 'transaction_earnings_history', order.ikwen_delivery_earnings)

    partner = service.retailer
    if partner:
        service_partner = get_service_instance(partner.database)
        app_partner = service_partner.app
        partner_umbrella = Service.objects.using(UMBRELLA).get(pk=partner.id)
        partner_app_umbrella = partner_umbrella.app

        set_counters(service_partner)
        increment_history_field(service_partner, 'turnover_history', order.items_cost)
        increment_history_field(service_partner, 'earnings_history', order.eshop_partner_earnings)
        increment_history_field(service_partner, 'transaction_count_history')
        increment_history_field(service_partner, 'transaction_earnings_history', order.eshop_partner_earnings)

        set_counters(app_partner)
        increment_history_field(app_partner, 'turnover_history', order.items_cost)
        increment_history_field(app_partner, 'earnings_history', order.eshop_partner_earnings)
        increment_history_field(app_partner, 'transaction_count_history')
        increment_history_field(app_partner, 'transaction_earnings_history', order.eshop_partner_earnings)

        partner.raise_balance(order.eshop_partner_earnings)

        set_counters(partner_umbrella)
        increment_history_field(partner_umbrella, 'turnover_history', order.items_cost)
        increment_history_field(partner_umbrella, 'earnings_history', order.ikwen_order_earnings)
        increment_history_field(partner_umbrella, 'transaction_count_history')
        increment_history_field(partner_umbrella, 'transaction_earnings_history', order.ikwen_order_earnings)

        set_counters(partner_app_umbrella)
        increment_history_field(partner_app_umbrella, 'turnover_history', order.items_cost)
        increment_history_field(partner_app_umbrella, 'earnings_history', order.ikwen_order_earnings)
        increment_history_field(partner_app_umbrella, 'transaction_count_history')
        increment_history_field(partner_app_umbrella, 'transaction_earnings_history', order.ikwen_order_earnings)

    delcom_partner = delcom.retailer  # Partner who actually created Delivery partner website
    if delcom_partner:
        service_delcom_partner = Service.objects.using(delcom_partner.database).get(pk=delcom.id)
        app_delcom_partner = service_delcom_partner.app
        delcom_partner_umbrella = Service.objects.using(UMBRELLA).get(pk=delcom_partner.id)
        delcom_partner_app_umbrella = delcom_partner_umbrella.app

        set_counters(service_delcom_partner)
        increment_history_field(service_delcom_partner, 'turnover_history', order.delivery_option.cost)
        increment_history_field(service_delcom_partner, 'earnings_history', order.logicom_partner_earnings)
        increment_history_field(service_delcom_partner, 'transaction_count_history')
        increment_history_field(service_delcom_partner, 'transaction_earnings_history', order.logicom_partner_earnings)

        set_counters(app_delcom_partner)
        increment_history_field(app_delcom_partner, 'turnover_history', order.delivery_option.cost)
        increment_history_field(app_delcom_partner, 'earnings_history', order.logicom_partner_earnings)
        increment_history_field(app_delcom_partner, 'transaction_count_history')
        increment_history_field(app_delcom_partner, 'transaction_earnings_history', order.logicom_partner_earnings)

        delcom_partner.raise_balance(order.logicom_partner_earnings)

        set_counters(delcom_partner_umbrella)
        increment_history_field(delcom_partner_umbrella, 'turnover_history', order.delivery_option.cost)
        increment_history_field(delcom_partner_umbrella, 'earnings_history', order.ikwen_delivery_earnings)
        increment_history_field(delcom_partner_umbrella, 'transaction_count_history')
        increment_history_field(delcom_partner_umbrella, 'transaction_earnings_history', order.ikwen_delivery_earnings)

        set_counters(delcom_partner_app_umbrella)
        increment_history_field(delcom_partner_app_umbrella, 'turnover_history', order.delivery_option.cost)
        increment_history_field(delcom_partner_app_umbrella, 'earnings_history', order.ikwen_delivery_earnings)
        increment_history_field(delcom_partner_app_umbrella, 'transaction_count_history')
        increment_history_field(delcom_partner_app_umbrella, 'transaction_earnings_history', order.ikwen_delivery_earnings)


def set_logicom_earnings_and_stats(order):
    delcom = order.delivery_company
    delcom_original = Service.objects.using(delcom.database).get(pk=delcom.id)
    delcom_profile_original = delcom_original.config
    provider = order.get_providers()[0]
    provider_profile_mirror = Service.objects.using(delcom.database).get(pk=provider.id).config
    
    set_counters(delcom_profile_original)
    increment_history_field(delcom_profile_original, 'items_traded_history', order.items_count)
    increment_history_field(delcom_profile_original, 'turnover_history', order.delivery_option.cost)
    increment_history_field(delcom_profile_original, 'orders_count_history')
    increment_history_field(delcom_profile_original, 'earnings_history', order.delivery_earnings)
    delcom_profile_original.report_counters_to_umbrella()

    delcom_original.raise_balance(order.delivery_earnings)

    set_counters(provider_profile_mirror)
    increment_history_field(provider_profile_mirror, 'items_traded_history', order.items_count)
    increment_history_field(provider_profile_mirror, 'turnover_history', order.delivery_option.cost)
    increment_history_field(provider_profile_mirror, 'orders_count_history')
    increment_history_field(provider_profile_mirror, 'earnings_history', order.delivery_earnings)


def after_order_confirmation(order, update_stock=True):
    member = order.member
    service = get_service_instance()
    retailer_profile = service.config
    retailer_profile_umbrella = get_service_instance(UMBRELLA).config
    delcom = order.delivery_option.company
    delcom_db = delcom.database
    add_database(delcom_db)
    delcom_profile_original = OperatorProfile.objects.using(delcom_db).get(pk=delcom.config.id)
    sudo_group = Group.objects.get(name=SUDO)

    packages_info = order.split_into_packages()
    set_ikwen_earnings_and_stats(order)

    if delcom != service:
        set_logicom_earnings_and_stats(order)

    if getattr(settings, 'IS_RETAILER', False):
        set_counters(retailer_profile)
        increment_history_field(retailer_profile, 'items_traded_history', order.items_count)
        increment_history_field(retailer_profile, 'orders_count_history')
        increment_history_field(retailer_profile, 'turnover_history', order.items_cost)
        increment_history_field(retailer_profile, 'earnings_history', order.retailer_earnings)
        retailer_profile.report_counters_to_umbrella()

    if member:
        customer = member.customer
        set_counters(customer)
        customer.last_payment_on = datetime.now()
        increment_history_field(customer, 'orders_count_history')
        increment_history_field(customer, 'items_purchased_history', order.items_count)
        increment_history_field(customer, 'turnover_history', order.items_cost)
        increment_history_field(customer, 'earnings_history', order.retailer_earnings)

    for provider_db in packages_info.keys():
        package = packages_info[provider_db]['package']
        provider_earnings = package.provider_earnings
        provider_revenue = package.provider_revenue
        if package.provider == delcom:
            provider_earnings += order.delivery_earnings
            provider_revenue += order.delivery_earnings
        provider_profile_umbrella = packages_info[provider_db]['provider_profile']
        provider_profile_original = provider_profile_umbrella.get_from(provider_db)
        provider_original = provider_profile_original.service
        provider_profile = provider_profile_umbrella.get_from('default')
        retailer_profile_mirror = OperatorProfile.objects.using(provider_db).get(pk=retailer_profile.id)

        if getattr(settings, 'IS_RETAILER', False):
            set_counters(provider_profile)
            increment_history_field(provider_profile, 'orders_count_history')
            increment_history_field(provider_profile, 'earnings_history', package.retailer_earnings)
            increment_history_field(provider_profile, 'items_traded_history', package.items_count)
            increment_history_field(provider_profile, 'turnover_history', package.retail_cost)

            set_counters(retailer_profile_mirror)
            increment_history_field(retailer_profile_mirror, 'orders_count_history')
            increment_history_field(retailer_profile_mirror, 'earnings_history', provider_earnings)
            increment_history_field(retailer_profile_mirror, 'items_traded_history', package.items_count)
            increment_history_field(retailer_profile_mirror, 'turnover_history', provider_revenue)

        set_counters(provider_profile_original)
        increment_history_field(provider_profile_original, 'orders_count_history')
        increment_history_field(provider_profile_original, 'earnings_history', provider_earnings)
        increment_history_field(provider_profile_original, 'items_traded_history', package.items_count)
        increment_history_field(provider_profile_original, 'turnover_history', provider_revenue)
        provider_profile_original.report_counters_to_umbrella()

        if delcom == service:
            provider_original.raise_balance(provider_earnings, provider=order.payment_mean.slug)
        else:
            if delcom_profile_original.return_url:
                nvp_dict = package.get_nvp_api_dict()
                Thread(target=lambda url, data: requests.post(url, data=data),
                       args=(delcom_profile_original.return_url, nvp_dict)).start()
            if provider_profile_original.payment_delay == OperatorProfile.STRAIGHT:
                if package.provider_earnings > 0:
                    provider_original.raise_balance(provider_earnings, provider=order.payment_mean.slug)
        if provider_profile_original.return_url:
            nvp_dict = package.get_nvp_api_dict()
            Thread(target=lambda url, data: requests.post(url, data=data),
                   args=(provider_profile_original.return_url, nvp_dict)).start()

    delivery_fees_accounted = False
    for entry in order.entries:
        product = entry.product
        provider_service = product.provider
        provider_db = provider_service.database
        provider_profile_umbrella = OperatorProfile.objects.using(UMBRELLA).get(service=provider_service)
        product_original = Product.objects.using(provider_db).get(pk=product.id)
        category = product.category
        category_original = ProductCategory.objects.using(provider_db).get(pk=category.id)

        turnover = entry.count * product.retail_price
        set_counters(category)
        if service == provider_service:
            provider_turnover = turnover
            provider_earnings = provider_turnover * (100 - provider_profile_umbrella.ikwen_share_rate) / 100
            if service == delcom and not delivery_fees_accounted:
                turnover += order.delivery_earnings
                provider_earnings += order.delivery_earnings
                delivery_fees_accounted = True
            increment_history_field(category, 'earnings_history', provider_earnings)
            increment_history_field(category, 'turnover_history', turnover)
        else:
            provider_turnover = entry.count * product.wholesale_price
            provider_earnings = provider_turnover * (100 - provider_profile_umbrella.ikwen_share_rate) / 100
            profit = turnover - provider_turnover
            retailer_earnings = profit * (100 - retailer_profile_umbrella.ikwen_share_rate) / 100
            increment_history_field(category, 'earnings_history', retailer_earnings)
            increment_history_field(category, 'turnover_history', provider_turnover)

            set_counters(category_original)
            increment_history_field(category_original, 'orders_count_history')
            increment_history_field(category_original, 'earnings_history', provider_earnings)
            increment_history_field(category_original, 'items_traded_history', entry.count)
            increment_history_field(category_original, 'turnover_history', provider_turnover)

        increment_history_field(category, 'orders_count_history')
        increment_history_field(category, 'items_traded_history', entry.count)
        category.report_counters_to_umbrella()

        if update_stock:
            product_original.stock -= entry.count
            if product_original.stock == 0:
                add_event(service, SOLD_OUT_EVENT, group_id=sudo_group.id, object_id=product_original.id)
                mark_duplicates(product)
        product_original.save()
        product_original.save(using='default')  # Causes the stock to be updated in the local database
        set_counters(product)
        increment_history_field(product, 'units_sold_history', entry.count)

        set_counters(product_original)
        increment_history_field(product_original, 'units_sold_history', entry.count)
    add_event(service, NEW_ORDER_EVENT, group_id=sudo_group.id, object_id=order.id)
