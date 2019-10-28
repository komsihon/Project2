# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db import models
from django.utils.translation import gettext_lazy as _
from djangotoolbox.fields import EmbeddedModelField, ListField
from ikwen_kakocase.sales.models import PromoCode

from ikwen.partnership.models import ApplicationRetailConfig

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.billing.models import AbstractSubscription, PaymentMean
from ikwen.core.models import Model, Service
from ikwen.core.utils import to_dict, add_database_to_settings, get_service_instance
from ikwen.rewarding.models import Coupon
from ikwen_kakocase.kakocase.models import OperatorProfile
from ikwen_kakocase.shopping.models import AnonymousBuyer
from ikwen_kakocase.trade.utils import generate_tx_code


class Order(Model):
    """
    An order placed by a customer
    """
    PENDING_FOR_PAYMENT = 'PendingForPayment'
    PENDING_FOR_APPROVAL = 'PendingForApproval'
    REJECTED = 'Rejected'
    PENDING = 'Pending'
    SHIPPED = 'Shipped'
    DELIVERED = 'Delivered'
    retailer = models.ForeignKey(Service)
    member = models.ForeignKey(Member, blank=True, null=True, db_index=True)
    anonymous_buyer = models.ForeignKey(AnonymousBuyer, blank=True, null=True, db_index=True)
    entries = ListField(EmbeddedModelField('OrderEntry'))
    items_count = models.IntegerField()
    items_cost = models.IntegerField()
    packing_cost = models.IntegerField(default=0)
    delivery_option = EmbeddedModelField('kakocase.DeliveryOption')
    delivery_company = models.ForeignKey(Service, related_name='+')
    pick_up_in_store = models.BooleanField(default=False)
    total_cost = models.IntegerField(default=0)
    currency = EmbeddedModelField('currencies.Currency', blank=True, null=True)  # Currency used when placing this Order
    payment_mean = models.ForeignKey(PaymentMean, null=True)
    deal = EmbeddedModelField('Deal', blank=True, null=True, db_index=True)
    account_number = models.CharField(max_length=60, blank=True, null=True, db_index=True)
    delivery_address = EmbeddedModelField('shopping.DeliveryAddress')
    delivery_expected_on = models.DateTimeField()
    confirmed_on = models.DateTimeField(blank=True, null=True, db_index=True)
    # Tags are set upon saving of object and are made of names of products contained in the order
    tags = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=15, default=PENDING_FOR_PAYMENT)
    device = models.CharField(max_length=15, blank=True)  # Type of device on which order was issued (PC, Phone, Tablet)

    # Retailer Collection Code: that is code retailer gives
    # to the provider to collect his package.
    rcc = models.CharField(max_length=30, unique=True, db_index=True)

    # Anonymous Order Tracking Code: Code generated for an anonymous
    # buyer to follow his order online.
    aotc = models.CharField(max_length=30, blank=True, null=True, db_index=True)
    confirmed_by = models.ForeignKey(Member, blank=True, null=True, related_name='deliveries', db_index=True)

    # EARNINGS
    retailer_earnings = models.FloatField(default=0)  # Amount retailer is supposed to earn if everything goes well
    referrer_earnings = models.FloatField(default=0)  # Amount referrer is supposed to earn if everything goes well
    delivery_earnings = models.FloatField(default=0)  # Amount delivery company is supposed to earn at the end

    ikwen_order_earnings = models.FloatField(default=0)  # Amount ikwen is supposed to earn from retailer
    ikwen_delivery_earnings = models.FloatField(default=0)  # Amount ikwen is supposed to earn from delivery company
    eshop_partner_earnings = models.FloatField(default=0)  # Amount partner is supposed to earn at the end
    logicom_partner_earnings = models.FloatField(default=0)  # Amount partner for logistics company is supposed to earn
    coupon = models.ForeignKey(PromoCode, blank=True, null=True)  # Coupon used by buyer
    cr_coupon_id = models.CharField(max_length=30, blank=True, null=True)  # ID of CR Coupon  used by buyer if any

    def __unicode__(self):
        return self.rcc

    class Meta:
        permissions = (
            ("ik_view_dashboard", _("View report dashboard")),
            ("ik_manage_order", _("Manage orders")),
        )

    def get_products_as_string(self):
        return ', '.join(['%d %s' % (entry.count, entry.product.name) for entry in self.entries])

    def get_providers(self):
        """

        """
        return list(set([entry.product.provider for entry in self.entries]))

    def get_buyer(self):
        if self.member:
            return self.member
        return self.anonymous_buyer

    def _get_cr_coupon(self):
        if self.cr_coupon_id:
            try:
                return Coupon.objects.using(UMBRELLA).get(pk=self.cr_coupon_id)
            except Coupon.DoesNotExist:
                pass
    cr_coupon = property(_get_cr_coupon)

    def get_nvp_api_dict(self):
        address = self.delivery_address
        option = self.delivery_option
        country = address.country

        nvp_dict = {'id': self.id, 'rcc': self.rcc, 'buyer_name': address.name,
                    'expected_on': self.delivery_expected_on,
                    'country_name': country.name, 'country_iso2': country.iso2, 'country_iso3': country.iso3,
                    'city': address.city, 'address': address.details, 'email': address.email, 'phone': address.phone,
                    'delivery_option_id': option.id, 'delivery_option_name': option.name,
                    'delivery_option_cost': option.cost, 'max_delay': option.max_delay,
                    'items_cost': self.items_cost, 'items_count': self.items_count, 'total_cost': self.total_cost}
        i = 1
        for entry in self.entries:
            product = entry.product
            nvp_dict['item_name%d' % i] = product.name
            nvp_dict['item_qty%d' % i] = entry.count
            nvp_dict['item_amt%d' % i] = product.retail_price
            i += 1
        return nvp_dict

    def split_into_packages(self, referrer=None):
        service = get_service_instance()
        logicom = self.delivery_company
        delivery_man_db = logicom.database
        add_database_to_settings(delivery_man_db)
        delivery_man_profile_umbrella = OperatorProfile.objects.using(UMBRELLA).get(service=logicom)
        total_provider_charges = 0
        total_referrer_earnings = 0
        if logicom != service:
            delivery_charges = self.delivery_option.cost * delivery_man_profile_umbrella.ikwen_share_rate / 100
            delivery_charges += delivery_man_profile_umbrella.ikwen_share_fixed
        else:
            delivery_charges = 0
        self.delivery_earnings = self.delivery_option.cost - delivery_charges
        service = get_service_instance()
        config = service.config
        packages_info = {}
        for entry in self.entries:
            provider = entry.product.provider
            provider_db = provider.database
            retail_cost = entry.count * (entry.product.retail_price + entry.product.packing_price)
            provider_revenue = entry.count * (entry.product.retail_price + entry.product.packing_price)
            if referrer:
                referrer_earnings = provider_revenue * referrer.share_rate / 100
            else:
                referrer_earnings = 0

            total_referrer_earnings += referrer_earnings
            if packages_info.get(provider_db):
                package = packages_info[provider_db]['package']
                provider_profile = packages_info[provider_db]['provider_profile']
                provider_charges = provider_revenue * provider_profile.ikwen_share_rate / 100
                total_provider_charges += provider_charges
                provider_earnings = provider_revenue - provider_charges - referrer_earnings
                package.entries.append(entry)
                package.items_count += entry.count
                package.provider_revenue += provider_revenue
                package.retail_cost += retail_cost
                package.provider_earnings += provider_earnings
                package.referrer_earnings += referrer_earnings
            else:
                provider_profile_umbrella = OperatorProfile.objects.using(UMBRELLA).get(service=provider)
                provider_charges = provider_revenue * provider_profile_umbrella.ikwen_share_rate / 100
                provider_charges += provider_profile_umbrella.ikwen_share_fixed
                total_provider_charges += provider_charges
                provider_earnings = provider_revenue - provider_charges - referrer_earnings
                ppc = generate_tx_code(self.id, provider.config.rel_id)
                packages_info[provider_db] = {
                    'package': Package(order=self, provider=provider, ppc=ppc, items_count=entry.count,
                                       retail_cost=retail_cost, provider_revenue=provider_revenue, entries=[entry],
                                       provider_earnings=provider_earnings, referrer_earnings=referrer_earnings,
                                       delivery_expected_on=self.delivery_expected_on,
                                       delivery_company=self.delivery_company),
                    'provider_profile': provider_profile_umbrella
                }
        if self.member:
            customer = self.member.customer
            self.member.save(using=delivery_man_db)
            customer.save(using=delivery_man_db)
        else:
            self.anonymous_buyer.save(using=delivery_man_db)

        self.referrer_earnings = total_referrer_earnings
        total_provider_charges += delivery_charges
        if getattr(settings, 'IS_RETAILER', False):
            total_provider_charges += config.ikwen_share_fixed
        eshop_partner = service.retailer
        eshop_partner_earnings = 0
        if eshop_partner:
            eshop_retail_config = ApplicationRetailConfig.objects.using(UMBRELLA).get(partner=eshop_partner, app=service.app)
            eshop_partner_earnings = total_provider_charges * (100 - eshop_retail_config.ikwen_tx_share_rate) / 100

        if service != logicom:
            logicom_partner = self.delivery_company.retailer
            logicom_partner_earnings = 0
            if logicom_partner:
                logicom_retail_config = ApplicationRetailConfig.objects.using(UMBRELLA).get(partner=logicom_partner, app=service.app)
                logicom_partner_earnings = delivery_charges * (100 - logicom_retail_config.ikwen_tx_share_rate) / 100
            self.logicom_partner_earnings = logicom_partner_earnings
            self.ikwen_delivery_earnings = delivery_charges - logicom_partner_earnings

        self.eshop_partner_earnings = eshop_partner_earnings
        self.ikwen_order_earnings = total_provider_charges - eshop_partner_earnings
        self.save(using=delivery_man_db)  # Copy to DeliveryMan DB to rebuild FK
        self.save(using='default')  # Causes retailer_earnings to be updated

        for db in packages_info.keys():
            add_database_to_settings(db)
            if self.member:
                self.member.save(using=db)
            else:
                self.anonymous_buyer.save(using=db)
            self.save(using=db)  # Save Order in mirror databases to rebuild FK relationships
            packages_info[db]['package'].save(using=delivery_man_db)
            packages_info[db]['package'].save(using=db)
        return packages_info

    def to_dict(self):
        var = to_dict(self)
        var['created_on'] = naturaltime(self.created_on)
        var['delivery_expected_on'] = naturaltime(self.delivery_expected_on)
        var['confirmed_on'] = naturaltime(self.confirmed_on)
        del(var['entries'])
        del(var['rcc'])  # MAKE SURE WE HIDE THE RCC until required explicitly
        return var


class OrderEntry(models.Model):
    # product is declared as EmbeddedField because we want to keep
    # information on the product exactly like they were on the
    # day of order. This way we are keeping the price on that day,
    # reference number, etc. Declaring it as ForeignKey would have
    # been problematic if product was changed or deleted since it
    # could lead to inconsistency or errors in related query data fetch
    product = EmbeddedModelField('kako.Product')
    count = models.IntegerField()

    def get_total(self):
        """
        Gets the total cost for this entry only. Mainly aimed at usage in django templates
        """
        return self.product.retail_price * self.count


class Package(Model):
    """
    Items within an :class:`Order` that must be provided by a single :class:`people.models.Provider`

    :attr:order
    :attr:entries List of :class:`OrderEntry` contained in this package
    :attr:ppc Provider Packaging Code. Code the :class:`people.models.Provider` to identify and prepare packages
    :attr:items_count Number of items contained in this package
    :attr:total_cost Cost that will be earned by this :class:`people.models.Provider`, not the cost of the Order
    :attr:status PENDING if the Package has been collected by :class:`people.models.Provider`, SHIPPED otherwise
    """
    order = models.ForeignKey(Order, db_index=True)
    provider = models.ForeignKey(Service, blank=True, null=True, db_index=True)
    entries = ListField(EmbeddedModelField('OrderEntry'))
    ppc = models.CharField(max_length=30, unique=True, db_index=True)
    items_count = models.IntegerField(default=0)
    provider_revenue = models.FloatField(default=0)
    retail_cost = models.FloatField(default=0)
    confirmed_on = models.DateTimeField(blank=True, null=True, db_index=True)
    confirmed_by = models.ForeignKey(Member, blank=True, null=True, db_index=True,
                                     related_name='packages_prepared')
    status = models.CharField(max_length=15, default=Order.PENDING)
    provider_earnings = models.FloatField(default=0)
    retailer_earnings = models.FloatField(default=0)
    referrer_earnings = models.FloatField(default=0)
    delivery_expected_on = models.DateTimeField(blank=True, null=True)
    delivery_company = models.ForeignKey(Service, related_name='+')

    class Meta:
        permissions = (
            ("ik_manage_package", _("Manage packages")),
        )

    def get_nvp_api_dict(self):
        order = self.order
        address = order.delivery_address
        option = order.delivery_option
        country = address.country
        nvp_dict = {'id': order.id, 'rcc': order.rcc, 'buyer_name': address.name,
                    'provider_ikwen_name': self.provider.project_name_slug, 'expected_on': order.delivery_expected_on,
                    'country_name': country.name, 'country_iso2': country.iso2, 'country_iso3': country.iso3,
                    'city': address.city, 'address': address.details, 'email': address.email, 'phone': address.phone,
                    'delivery_option_id': option.id, 'delivery_option_name': option.name,
                    'delivery_option_cost': option.cost, 'max_delay': option.max_delay}
        i = 1
        for entry in self.entries:
            product = entry.product
            nvp_dict['item_name%d' % i] = product.name
            nvp_dict['item_qty%d' % i] = entry.count
            i += 1
        return nvp_dict

    def to_dict(self):
        var = to_dict(self)
        var['created_on'] = self.created_on.strftime('%Y-%m-%d %H:%M:%S')
        var['confirmed_on'] = self.confirmed_on.strftime('%Y-%m-%d %H:%M:%S') if self.confirmed_on else None
        var['delivery_expected_on'] = self.delivery_expected_on.strftime('%Y-%m-%d %H:%M:%S') if self.delivery_expected_on else None
        return var


class Subscription(AbstractSubscription):
    """
    A subscription to a :class:`kako.models.RecurringPaymentService` sold to
    end user by a  :class:`people.models.Retailer`. Those subscriptions are handled
    by ikwen billing apps that will issue invoices and reminders.
    It will further collect payments. Upon payment, the share between provider
    and retailer will be applied just like it would be with a :class:`kako.models.Product`
    """
    service = EmbeddedModelField('kako.RecurringPaymentService')


class Deal(Model):
    """
    A mean of acquisition of a Product offered by a financial institution
    """
    DAY = 'Day'
    WEEK = 'Week'
    MONTH = 'Month'
    FREQUENCY_CHOICES = (
        (DAY, _('Day')),
        (WEEK, _('Week')),
        (MONTH, _('Month'))
    )
    # product_slug is used rather than a foreign key to Product because
    # using ForeignKey forces us to define a Deal for each duplicate of
    # the Product. Using product_slug instead directly points to all the
    # duplicates of the same product since they have the same slug
    product_slug = models.CharField(max_length=150, blank=True, null=True)
    merchant = models.ForeignKey(Service)
    bank = models.ForeignKey(Service, related_name='+')
    frequency = models.CharField(max_length=30, choices=FREQUENCY_CHOICES, blank=True, null=True,
                                 help_text="Day, Week or Month")
    terms_count = models.IntegerField(default=2, blank=True, null=True)
    first_term = models.FloatField(blank=True, null=True)
    term_cost = models.FloatField(blank=True, null=True)
    about = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __unicode__(self):
        if self.product_slug:
            return "%d/%s - %ss" % (self.term_cost, _(self.frequency), _(self.frequency))
        return "Cash"


class Issue(Model):
    order = models.ForeignKey(Order)
    details = models.TextField(blank=True)
    solved = models.BooleanField(default=False)
    solution = models.TextField(blank=True)

    class Meta:
        abstract = True
        permissions = (
            ("manage_issue", _("Manage issues")),
        )

    def to_dict(self):
        var = to_dict(self)
        var['created_on'] = naturaltime(self.created_on)
        return var


class LateDelivery(Issue):
    retailer_called = models.BooleanField()


class BrokenProduct(Issue):
    pass
