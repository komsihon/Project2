import json
from datetime import timedelta, time
from time import sleep

from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest, timezone
from ikwen.accesscontrol.models import Member

from ikwen.partnership.models import PartnerProfile

from ikwen.core.models import Service, OperatorWallet

from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import get_service_instance, add_database_to_settings
from ikwen_kakocase.kako.models import Product, ProductCategory
from ikwen_kakocase.kako.tests_views import wipe_test_data
from ikwen_kakocase.kakocase.models import OperatorProfile
from ikwen_kakocase.shopping.models import Review, AnonymousBuyer
from ikwen_kakocase.trade.models import Order, Package


class ShoppingViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_setup_data.yaml', 'kc_operators_configs.yaml', 'kc_basic_configs.yaml', 'kc_members.yaml',
                'kc_profiles.yaml', 'categories.yaml', 'products.yaml', 'kc_promotions', 'kc_promocode']

    def setUp(self):
        self.client = Client()
        add_database_to_settings('test_kc_tecnomobile')
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_ems')
        add_database_to_settings('test_kc_partner_jumbo')
        add_database_to_settings('test_kc_afic')
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data('test_kc_sabc')
        wipe_test_data('test_kc_ems')
        wipe_test_data('test_kc_partner_jumbo')
        wipe_test_data('test_kc_afic')
        wipe_test_data(UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', fixture, database='test_kc_tecnomobile')
            call_command('loaddata', fixture, database='test_kc_sabc')
            call_command('loaddata', fixture, database='test_kc_ems')
            call_command('loaddata', fixture, database='test_kc_afic')
            call_command('loaddata', fixture, database=UMBRELLA)

    def tearDown(self):
        add_database_to_settings('test_kc_tecnomobile')
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_ems')
        add_database_to_settings('test_kc_afic')
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data('test_kc_sabc')
        wipe_test_data('test_kc_ems')
        wipe_test_data('test_kc_partner_jumbo')
        wipe_test_data('test_kc_afic')
        wipe_test_data(UMBRELLA)
        OperatorWallet.objects.using(WALLETS_DB_ALIAS).all().update(balance=0)
        cache.clear()

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_IKWEN=False)
    def test_Home(self):
        """
        Page must return HTTP 200 status, products with largest items_sold must come first.
        """
        response = self.client.get(reverse('shopping:home'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductListView(self):
        """
        Page must return HTTP 200 status.
        """
        response = self.client.get(reverse('shopping:product_list', args=('food', )))
        self.assertEqual(response.status_code, 200)
        products_page = response.context['products_page']
        self.assertEqual(products_page.paginator.count, 3)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductListView_with_empty_product_list(self):
        """
        Page must return HTTP 200 status, products with largest items_sold must come first.
        """
        Product.objects.all().delete()
        response = self.client.get(reverse('shopping:product_list', args=('food', )))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductListView_as_html_results(self):
        """
        Requesting products list with GET parameter format=html_results&q=searchTerm should.
        Result must return as a rendered product_list
        """
        response = self.client.get(reverse('shopping:product_list', args=('food', )),
                                   {'format': 'html_results', 'order_by': 'name', 'q': 'col', 'page': 1})
        self.assertEqual(response.status_code, 200)
        products_page = response.context['products_page']
        self.assertEqual(products_page.paginator.count, 1)
        self.assertEqual(products_page.object_list[0].name, 'Coca-Cola')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductDetail(self):
        """
        ProductDetail view must load the correct product in the page
        """
        response = self.client.get(reverse('shopping:product_detail', args=('food', 'coca-cola')))
        self.assertEqual(response.status_code, 200)
        product = response.context['product']
        self.assertEqual(product.name, 'Coca-Cola')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_Cart(self):
        """
        Cart view must return HTTP 200
        """
        response = self.client.get(reverse('shopping:cart'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_Cart_with_checkout_confirmation(self):
        """
        Cart view must return HTTP 200. Order older than 1 hour render
        differently. Make sure it still renders correctly.
        """
        call_command('loaddata', 'orders.yaml')
        response = self.client.get(reverse('shopping:cart', args=('55d1feb60008099bd4151fa2', )))
        self.assertEqual(response.status_code, 200)
        old_issue_date = timezone.now() - timedelta(hours=2)
        Order.objects.all().update(created_on=old_issue_date)
        response = self.client.get(reverse('shopping:cart', args=('55d1feb60008099bd4151fa2', )))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_Checkout(self):
        """
        Checkout view must return HTTP 200
        """
        response = self.client.get(reverse('shopping:checkout'), {'delivery_option_id': '55d1feb9b37b301e070604d3',
                                                                  'pay_with': 'paypal'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_RETAILER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_anonymous_user(self):
        """
        Saves order, splits it into packages, updates counters and sets order AOTC
        """
        yesterday = timezone.now() - timedelta(days=1)
        for db in ('default', 'test_kc_tecnomobile', 'test_kc_sabc'):
            for profile in OperatorProfile.objects.using(db).all():
                profile.counters_reset_on = yesterday
                profile.save()
            for category in ProductCategory.objects.using(db).all():
                category.counters_reset_on = yesterday
                category.save()
            for product in Product.objects.using(db).all():
                product.counters_reset_on = yesterday
                product.save()

        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'details': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3'})
        json_resp = json.loads(response.content)
        self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        self.assertIsNone(order.member)
        self.assertIsNotNone(order.aotc)
        buyer = AnonymousBuyer.objects.get(phone='655003321')
        self.assertEqual(len(buyer.delivery_addresses), 1)
        pack1 = Package.objects.using('test_kc_tecnomobile').all()[0]
        pack2 = Package.objects.using('test_kc_sabc').all()[0]
        self.assertEqual(Package.objects.using('test_kc_tecnomobile').all().count(), 1)
        self.assertEqual(Package.objects.using('test_kc_sabc').all().count(), 1)
        self.assertEqual(Package.objects.using('test_kc_ems').all().count(), 2)
        self.assertEqual(pack1.entries[0].product.id, '55d1fa8feb60008099bd4151')
        self.assertEqual(pack2.entries[0].product.id, '55d1fa8feb60008099bd4153')

        ab = AnonymousBuyer.objects
        self.assertEqual(ab.using('default').exclude(pk='57b336eb6d04b379b531a001').count(), 1)
        self.assertEqual(ab.using('test_kc_tecnomobile').exclude(pk='57b336eb6d04b379b531a001').count(), 1)
        self.assertEqual(ab.using('test_kc_sabc').exclude(pk='57b336eb6d04b379b531a001').count(), 1)
        self.assertEqual(ab.using('test_kc_ems').exclude(pk='57b336eb6d04b379b531a001').count(), 1)

        # Assuming IKWEN collects 2% on revenue of provider and one of retailer
        self.assertEqual(pack1.provider_revenue, 430000)
        self.assertEqual(pack1.provider_earnings, 421400)
        self.assertEqual(pack1.retailer_earnings, 49000)
        self.assertEqual(pack2.provider_revenue, 2760)
        self.assertEqual(pack2.provider_earnings, 2704.8)
        self.assertEqual(pack2.retailer_earnings, 529.2)
        self.assertEqual(order.retailer_earnings, 49529.2)
        self.assertEqual(order.delivery_earnings, 2940)
        self.assertEqual(order.ikwen_order_earnings, 9666)
        self.assertEqual(order.ikwen_delivery_earnings, 60)

        # Check counters
        cache.clear()
        retailer_profile = get_service_instance().config
        self.assertEqual(retailer_profile.items_traded_history, [18, 9, 57, 23, 46, 7.0])
        self.assertEqual(retailer_profile.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(retailer_profile.earnings_history, [4150, 1900, 36608, 3040, 9175, 49529.2])
        self.assertEqual(retailer_profile.turnover_history, [33800, 22700, 204150, 40890, 70235, 483300.0])

        tecno_profile = OperatorProfile.objects.get(pk='56922874b37b33706b51f001')
        self.assertEqual(tecno_profile.items_traded_history, [18, 9, 57, 23, 46, 1.0])
        self.assertEqual(tecno_profile.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(tecno_profile.earnings_history, [33800, 22700, 204150, 40890, 70235, 49000.0])

        sabc_profile = OperatorProfile.objects.get(pk='56922874b37b33706b51f002')
        self.assertEqual(sabc_profile.items_traded_history, [18, 9, 57, 23, 46, 6.0])
        self.assertEqual(sabc_profile.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(sabc_profile.earnings_history, [33800, 22700, 204150, 40890, 70235, 529.2])

        tecno_profile_original = OperatorProfile.objects.using('test_kc_tecnomobile').get(pk='56922874b37b33706b51f001')
        self.assertEqual(tecno_profile_original.items_traded_history, [18, 9, 57, 23, 46, 1.0])
        self.assertEqual(tecno_profile_original.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(tecno_profile_original.earnings_history, [33800, 22700, 204150, 40890, 70235, 421400.0])

        tecno_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b101', provider='paypal')
        self.assertEqual(tecno_wallet.balance, 421400)

        retailer_profile_mirror1 = retailer_profile.get_from('test_kc_tecnomobile')
        self.assertEqual(retailer_profile_mirror1.items_traded_history, [18, 9, 57, 23, 46, 1.0])
        self.assertEqual(retailer_profile_mirror1.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(retailer_profile_mirror1.earnings_history, [4150, 1900, 36608, 3040, 9175, 421400.0])

        sabc_profile_original = OperatorProfile.objects.using('test_kc_sabc').get(pk='56922874b37b33706b51f002')
        self.assertEqual(sabc_profile_original.items_traded_history, [18, 9, 57, 23, 46, 6.0])
        self.assertEqual(sabc_profile_original.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(sabc_profile_original.earnings_history, [33800, 22700, 204150, 40890, 70235, 2704.8])

        sabc_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b102', provider='paypal')
        self.assertEqual(sabc_wallet.balance, 2704.8)

        ems_profile_original = OperatorProfile.objects.using('test_kc_ems').get(pk='56922874b37b33706b51f005')
        self.assertEqual(ems_profile_original.items_traded_history, [18, 9, 57, 23, 46, 7])
        self.assertEqual(ems_profile_original.orders_count_history, [11, 4, 41, 15, 27, 1])
        self.assertEqual(ems_profile_original.earnings_history, [33800, 22700, 204150, 40890, 70235, 2940])

        retailer_profile_mirror2 = retailer_profile.get_from('test_kc_sabc')
        self.assertEqual(retailer_profile_mirror2.items_traded_history, [18, 9, 57, 23, 46, 6.0])
        self.assertEqual(retailer_profile_mirror2.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(retailer_profile_mirror2.earnings_history, [4150, 1900, 36608, 3040, 9175, 2704.8])

        category1 = ProductCategory.objects.get(pk='569228a9b37b3301e0706b51')
        self.assertListEqual(category1.items_traded_history, [18, 9, 57, 23, 46, 1])
        self.assertListEqual(category1.orders_count_history, [11, 4, 41, 15, 27, 1])
        self.assertListEqual(category1.earnings_history, [4150, 1900, 36608, 3040, 9175, 49000])

        category2 = ProductCategory.objects.get(pk='569228a9b37b3301e0706b52')
        self.assertListEqual(category2.items_traded_history, [30, 16, 52, 78, 31, 6])
        self.assertListEqual(category2.orders_count_history, [11, 4, 27, 41, 15, 1])
        self.assertListEqual(category2.earnings_history, [4150, 3040, 9175, 1900, 36608, 529.2])

        category1_mirror = ProductCategory.objects.using('test_kc_tecnomobile').get(pk='569228a9b37b3301e0706b51')
        self.assertListEqual(category1_mirror.items_traded_history, [18, 9, 57, 23, 46, 1])
        self.assertListEqual(category1_mirror.orders_count_history, [11, 4, 41, 15, 27, 1])
        self.assertListEqual(category1_mirror.earnings_history, [4150, 1900, 36608, 3040, 9175, 421400])

        category2_mirror = ProductCategory.objects.using('test_kc_sabc').get(pk='569228a9b37b3301e0706b52')
        self.assertListEqual(category2_mirror.items_traded_history, [30, 16, 52, 78, 31, 6])
        self.assertListEqual(category2_mirror.orders_count_history, [11, 4, 27, 41, 15, 1])
        self.assertListEqual(category2_mirror.earnings_history, [4150, 3040, 9175, 1900, 36608, 2704.8])

        product1_original = Product.objects.using('test_kc_tecnomobile').get(pk='55d1fa8feb60008099bd4151')
        self.assertEqual(product1_original.stock, 44)

        product1 = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        self.assertListEqual(product1.units_sold_history, [30, 14, 48, 45, 1])
        self.assertEqual(product1.total_units_sold, 138)
        self.assertEqual(product1.stock, 44)

        product2 = Product.objects.get(pk='55d1fa8feb60008099bd4153')
        self.assertListEqual(product2.units_sold_history, [74, 51, 35, 89, 6])
        self.assertEqual(product2.total_units_sold, 255)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_RETAILER=True,
                       IS_PROVIDER=False, IS_DELIVERY_MAN=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_platform_having_partner_retailer(self):
        """
        The partner Operator must be paid as well during the checkout confirmation operation
        """
        call_command('loaddata', 'kc_members.yaml', database='test_kc_partner_jumbo')
        call_command('loaddata', 'kc_setup_data.yaml', database='test_kc_partner_jumbo')
        call_command('loaddata', 'kc_partners.yaml')
        call_command('loaddata', 'kc_partners.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_partners.yaml', database='test_kc_partner_jumbo')
        call_command('loaddata', 'kc_partner_app_retail_config.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_partner_app_retail_config.yaml', database='test_kc_partner_jumbo')
        partner = Service.objects.get(pk='56eb6d04b9b531b10537b331')
        service = get_service_instance()
        service.retailer = partner
        service.save()

        logicom_service = Service.objects.get(pk='56eb6d04b37b3379b531b105')
        logicom_service.retailer = Service.objects.get(pk='56eb6d04b9b531b10537b331')
        logicom_service.save()

        yesterday = timezone.now() - timedelta(days=1)
        for db in ('default', UMBRELLA, 'test_kc_tecnomobile', 'test_kc_sabc'):
            for profile in OperatorProfile.objects.using(db).all():
                profile.counters_reset_on = yesterday
                profile.ikwen_share_fixed = 100   # ikwen collects 100F per transaction
                profile.save(using=db)

        cache.clear()
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'details': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3'})
        json_resp = json.loads(response.content)
        self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        pack1 = Package.objects.using('test_kc_tecnomobile').all()[0]
        pack2 = Package.objects.using('test_kc_sabc').all()[0]

        # Assuming IKWEN collects 2% on revenue of provider and one of retailer
        self.assertEqual(pack1.provider_revenue, 430000)
        self.assertEqual(pack1.provider_earnings, 421300)
        self.assertEqual(pack1.retailer_earnings, 49000)
        self.assertEqual(pack2.provider_revenue, 2760)
        self.assertEqual(pack2.provider_earnings, 2604.8)
        self.assertEqual(pack2.retailer_earnings, 529.2)
        self.assertEqual(order.retailer_earnings, 49429.2)
        self.assertEqual(order.delivery_earnings, 2840)
        self.assertEqual(round(order.ikwen_order_earnings, 1), 3986.4)
        self.assertEqual(order.ikwen_delivery_earnings, 64)
        self.assertEqual(order.eshop_partner_earnings, 5979.6)
        self.assertEqual(order.logicom_partner_earnings, 96)

        # Check counters for ikwen and partner
        cache.clear()
        service_umbrella = get_service_instance(UMBRELLA)
        self.assertEqual(service_umbrella.turnover_history, [483300])
        self.assertEqual(round(service_umbrella.earnings_history[0], 1), 3986.4)
        self.assertEqual(service_umbrella.transaction_count_history, [1])
        self.assertEqual(round(service_umbrella.transaction_earnings_history[0], 1), 3986.4)

        app_umbrella = service_umbrella.app
        self.assertEqual(app_umbrella.turnover_history, [483300])
        self.assertEqual(round(app_umbrella.earnings_history[0], 1), 3986.4)
        self.assertEqual(app_umbrella.transaction_count_history, [1])
        self.assertEqual(round(app_umbrella.transaction_earnings_history[0], 1), 3986.4)

        logicom_service_umbrella = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b105')
        self.assertEqual(logicom_service_umbrella.turnover_history, [3000])
        self.assertEqual(logicom_service_umbrella.earnings_history, [64])
        self.assertEqual(logicom_service_umbrella.transaction_count_history, [1])
        self.assertEqual(logicom_service_umbrella.transaction_earnings_history, [64])

        logicom_app_umbrella = logicom_service_umbrella.app
        self.assertEqual(logicom_app_umbrella.turnover_history, [3000])
        self.assertEqual(logicom_app_umbrella.earnings_history, [64])
        self.assertEqual(logicom_app_umbrella.transaction_count_history, [1])
        self.assertEqual(logicom_app_umbrella.transaction_earnings_history, [64])

        service_mirror_partner = Service.objects.using('test_kc_partner_jumbo').get(pk=service_umbrella.id)
        self.assertEqual(service_mirror_partner.turnover_history, [483300])
        self.assertEqual(service_mirror_partner.earnings_history, [5979.6])
        self.assertEqual(service_mirror_partner.transaction_count_history, [1])
        self.assertEqual(service_mirror_partner.transaction_earnings_history, [5979.6])

        app_mirror_partner = service_mirror_partner.app
        self.assertEqual(app_mirror_partner.turnover_history, [483300])
        self.assertEqual(app_mirror_partner.earnings_history, [5979.6])
        self.assertEqual(app_mirror_partner.transaction_count_history, [1])
        self.assertEqual(app_mirror_partner.transaction_earnings_history, [5979.6])

        partner_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b9b531b10537b331')
        partner_profile_original = PartnerProfile.objects.using('test_kc_partner_jumbo').get(pk='56922a3bb37b33da18d02fb1')
        partner_profile_umbrella = PartnerProfile.objects.using(UMBRELLA).get(pk='56922a3bb37b33da18d02fb1')
        self.assertEqual(partner_wallet.balance, 6075.6)


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_authenticated_user(self):
        """
        Saves order and leaves AOTC None
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        json_resp = json.loads(response.content)
        response = self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        self.assertIsNone(order.aotc)
        self.assertIsNotNone(order.member)


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_PROVIDER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_provider_being_delivery_company(self):
        """
        When order is delivered by the provider, he collects the delivery fees directly
        """
        OperatorProfile.objects.using('umbrella').filter(pk='56922874b37b33706b51f001').update(ikwen_share_fixed=300, ikwen_share_rate=0)
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1',
                                    'delivery_option_id': '55d1feb9b37b301e070604d4',
                                    'success_url': reverse('shopping:checkout')})
        json_resp = json.loads(response.content)
        self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        pack = Package.objects.using('test_kc_tecnomobile').all()[0]

        self.assertEqual(pack.provider_earnings, 479700)
        self.assertEqual(order.delivery_earnings, 3000)
        self.assertEqual(order.ikwen_delivery_earnings, 0)

        # Check counters for ikwen and partner
        cache.clear()
        profile = get_service_instance('test_kc_tecnomobile').config
        self.assertEqual(profile.turnover_history[-1], 483000)
        self.assertEqual(profile.earnings_history[-1], 482700)
        self.assertEqual(profile.orders_count_history[-1], 1)
        self.assertEqual(profile.items_traded_history[-1], 1)

        service_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b101', provider='paypal')
        self.assertEqual(service_wallet.balance, 482700)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_authenticated_user_using_previous_address(self):
        """
        Saves order and uses the previous address with given index as delivery address for this order
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                   {'phone': '', 'email': '', 'country_iso2': '', 'city': '', 'address': '',
                                    'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                    'previous_address_index': '0', 'delivery_option_id': '55d1feb9b37b301e070604d3'})
        json_resp = json.loads(response.content)
        response = self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        self.assertIsNone(order.aotc)
        self.assertEqual(order.delivery_address.city, 'Yaounde')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', DEBUG=True, UNIT_TESTING=True)
    def test_confirm_checkout_with_momo_payment(self):
        """
        Checking out with Mobile Money should work well too
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        response = self.client.get(reverse('billing:init_momo_transaction'), data={'phone': '677003321'})
        json_resp = json.loads(response.content)
        tx_id = json_resp['tx_id']
        sleep(1)  # Wait for the transaction to complete before querying status
        response = self.client.get(reverse('billing:check_momo_transaction_status'), data={'tx_id': tx_id})
        json_resp = json.loads(response.content)
        order = Order.objects.all()[0]
        self.assertTrue(json_resp['success'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', IS_PROVIDER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', DEBUG=True, UNIT_TESTING=True)
    def test_confirm_checkout_with_paid_packaging(self):
        """
        Packaging cost must be included in order cost if Product has packaging cost
        and buyer decided to purchase with packaging along
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4154:10', 'buy_packaging': 'yes',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        response = self.client.get(reverse('billing:init_momo_transaction'), data={'phone': '677003321'})
        json_resp = json.loads(response.content)
        tx_id = json_resp['tx_id']
        sleep(1)  # Wait for the transaction to complete before querying status
        response = self.client.get(reverse('billing:check_momo_transaction_status'), data={'tx_id': tx_id})
        json_resp = json.loads(response.content)
        order = Order.objects.all()[0]
        self.assertEqual(order.packaging_cost, 1000)
        self.assertEqual(order.total_cost, 14000)

        service_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b102', provider='mtn-momo')
        self.assertEqual(service_wallet.balance, 10780)
        self.assertTrue(json_resp['success'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', IS_PROVIDER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', DEBUG=True, UNIT_TESTING=True)
    def test_confirm_checkout_with_unpaid_packaging(self):
        """
        Packaging cost must be ignored if Product has packaging cost
        and buyer decided to refuse to buy packaging
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4154:10', 'buy_packaging': '',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        response = self.client.get(reverse('billing:init_momo_transaction'), data={'phone': '677003321'})
        json_resp = json.loads(response.content)
        tx_id = json_resp['tx_id']
        sleep(1)  # Wait for the transaction to complete before querying status
        response = self.client.get(reverse('billing:check_momo_transaction_status'), data={'tx_id': tx_id})
        json_resp = json.loads(response.content)
        order = Order.objects.all()[0]
        self.assertEqual(order.packaging_cost, 0)
        self.assertEqual(order.total_cost, 13000)

        service_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b102', provider='mtn-momo')
        self.assertEqual(service_wallet.balance, 9800)
        self.assertTrue(json_resp['success'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', DEBUG=True, UNIT_TESTING=True)
    def test_confirm_checkout_with_cashflex_and_cash_payment(self):
        """
        CasFlex payment submits order for approval by the target bank.
        Cash Payment indicates that the user did not choose any terms payment.
        Multiple products are supported for cash payment
        """
        bank_id = '56eb6d04b37b3379b531b107'
        bank = Service.objects.get(pk=bank_id)
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:choose_deal'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')}, follow=True)
        self.assertTrue(response.status_code, 200)
        self.client.post(reverse('shopping:confirm_checkout'), data={'bank_id': bank_id, 'account_number': '000111'})

        order = Order.objects.filter(status=Order.PENDING_FOR_APPROVAL)[0]  # Order was saved as PendingForApproval
        self.assertEqual(order.deal.bank, bank)
        copy = Order.objects.using('test_kc_afic').filter(status=Order.PENDING_FOR_APPROVAL)[0]
        member = Member.objects.using('test_kc_afic').get(username='member4')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', DEBUG=True, UNIT_TESTING=True)
    def test_confirm_checkout_with_cashflex_and_terms_payment(self):
        """
        CasFlex payment submits order for approval by the target bank.
        Terms payment indicates that user choose a deal offered by the bank.
        Terms payment is avaible for one single item at a time in an order
        """
        # call_command('loaddata', 'kc_setup_data.yaml', database='test_kc_afic')
        call_command('loaddata', 'kc_deals.yaml', database='test_kc_afic')
        bank_id = '56eb6d04b37b3379b531b107'
        deal_id = '59a456d04b379b531a0016d1'
        bank = Service.objects.get(pk=bank_id)
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:choose_deal'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')}, follow=True)
        self.assertTrue(response.status_code, 200)
        self.client.post(reverse('shopping:confirm_checkout'), data={'bank_id': bank_id, 'deal_id': deal_id,
                                                                     'account_number': '000111'})

        order = Order.objects.filter(status=Order.PENDING_FOR_APPROVAL)[0]  # Order was saved as PendingForApproval
        self.assertEqual(order.deal.id, deal_id)
        copy = Order.objects.using('test_kc_afic').filter(status=Order.PENDING_FOR_APPROVAL)[0]
        member = Member.objects.using('test_kc_afic').get(username='member4')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_review_product_with_anonymous_user(self):
        """
        Reviewing a product when anonymous creates a Review object
        and sets the member as the current one. e-mail and name are required
        """
        response = self.client.get(reverse('shopping:review_product', args=('55d1fa8feb60008099bd4151', )),
                                   {'rating': 3, 'comment': 'Good product', 'name': 'Simo', 'email': 'simo@ikwen.com'})
        json_resp = json.loads(response.content)
        self.assertTrue(json_resp['success'])
        p1 = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        self.assertEqual(p1.rating_count, 1)
        self.assertEqual(p1.total_rating, 3)
        review = Review.objects.get(product=p1)
        self.assertIsNone(review.member)
        self.assertEqual(review.name, 'Simo')
        self.assertEqual(review.email, 'simo@ikwen.com')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_review_product_with_authenticated_user(self):
        """
        Reviewing a product when authenticated creates a Review object
        and sets the member as the current one. No e-mail or name is needed
        """
        self.client.login(username='member4', password='admin')
        response = self.client.get(reverse('shopping:review_product', args=('55d1fa8feb60008099bd4151', )),
                                   {'rating': 3, 'comment': 'Good product'})
        json_resp = json.loads(response.content)
        self.assertTrue(json_resp['success'])
        p1 = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        self.assertEqual(p1.rating_count, 1)
        self.assertEqual(p1.total_rating, 3)
        review = Review.objects.get(product=p1)
        self.assertEqual(review.member.username, 'member4')