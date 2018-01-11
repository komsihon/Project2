import json
from datetime import datetime, timedelta

from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest, timezone
from django.utils.timezone import get_current_timezone
from ikwen_kakocase.kako.models import Product

from ikwen.accesscontrol.models import Member

from ikwen.core.models import OperatorWallet, Service

from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import get_service_instance, add_database_to_settings
from ikwen_kakocase.kako.tests_views import wipe_test_data
from ikwen_kakocase.kakocase.models import ProductCategory, OperatorProfile, TIME_LEFT_TO_COMMIT_TO_SELF_DELIVERY
from ikwen_kakocase.trade.models import Order, Package, Deal


class TradeViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_setup_data.yaml', 'kc_operators_configs.yaml', 'kc_members.yaml',
                'kc_profiles.yaml', 'categories.yaml', 'products.yaml', 'orders.yaml', 'after_sales.yaml']

    def setUp(self):
        self.client = Client()
        add_database_to_settings('test_kc_tecnomobile')
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_foka')
        add_database_to_settings('test_kc_ems')
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data('test_kc_sabc')
        wipe_test_data('test_kc_foka')
        wipe_test_data('test_kc_ems')
        wipe_test_data(UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)

        for fixture in ['kc_setup_data.yaml', 'kc_operators_configs.yaml']:
            call_command('loaddata', fixture, database=UMBRELLA)
            call_command('loaddata', fixture, database='test_kc_tecnomobile')
            call_command('loaddata', fixture, database='test_kc_sabc')
            call_command('loaddata', fixture, database='test_kc_foka')
            call_command('loaddata', fixture, database='test_kc_ems')

    def tearDown(self):
        add_database_to_settings('test_kc_tecnomobile')
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_foka')
        add_database_to_settings('test_kc_ems')
        add_database_to_settings('test_kc_afic')
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data('test_kc_sabc')
        wipe_test_data('test_kc_foka')
        wipe_test_data('test_kc_ems')
        wipe_test_data('test_kc_afic')
        wipe_test_data(UMBRELLA)
        OperatorWallet.objects.using(WALLETS_DB_ALIAS).all().update(balance=0)
        cache.clear()

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_PROVIDER=True)
    def test_OrderListView(self):
        """
        Page must return HTTP 200 status. Access is limited to authorized collaborators only
        """
        response = self.client.get(reverse('trade:order_list'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:order_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['orders_page'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_OrderListView_html_results_format(self):
        """
        Requesting orders list with GET parameter format=html_results&q=searchTerm should.
        Result must return as a list of objects rendered with the template
        """
        Order.objects.all().update(status=Order.SHIPPED)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:order_list'), {'status': Order.SHIPPED, 'format': 'html_results'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['orders_page'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_OrderListView_with_rcc_search(self):
        """
        Requesting orders list with an RCC as the text query re
        """
        Order.objects.all().update(status=Order.SHIPPED)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:order_list'), {'q': 'RCC1', 'format': 'html_results'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['orders_page'].object_list[0].rcc, 'rcc1')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_get_order_details(self):
        """
        Return the RCC of the order within a JSON object
        """
        response = self.client.get(reverse('trade:get_order_details'), {'order_id': '55d1feb60008099bd4151fa1'})
        self.assertEqual(response.status_code, 302)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:get_order_details'), {'order_id': '55d1feb60008099bd4151fa1'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       USE_TZ=False)
    def test_RetailerDashboard(self):
        """
        Make sure the page is reachable
        """
        for retailer in OperatorProfile.objects.filter(business_type=OperatorProfile.RETAILER):
            retailer.counters_reset_on = timezone.now()
            retailer.save()
        for provider in OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER):
            provider.counters_reset_on = timezone.now()
            provider.save()
        for category in ProductCategory.objects.all():
            category.counters_reset_on = timezone.now()
            category.save()
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:retailer_dashboard'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       USE_TZ=False)
    def test_ProviderDashboard(self):
        """
        Make sure the page is reachable
        """
        for retailer in OperatorProfile.objects.filter(business_type=OperatorProfile.RETAILER):
            retailer.counters_reset_on = timezone.now()
            retailer.save()
        for provider in OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER):
            provider.counters_reset_on = timezone.now()
            provider.save()
        for category in ProductCategory.objects.all():
            category.counters_reset_on = timezone.now()
            category.save()
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('trade:provider_dashboard'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_PackageListView(self):
        """
        Page must return HTTP 200 status. Access is limited to authorized collaborators only
        """
        response = self.client.get(reverse('trade:package_list'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:package_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['orders_page'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_get_package_details(self):
        """
        get_package_details returns a JSON encoded Package object
        """
        self.client.login(username='member3', password='admin')
        # package = Package.objects.get(pk='57d1feb900080151fa399bd1')
        # package
        response = self.client.get(reverse('trade:get_package_details'), {'package_id': '57d1feb900080151fa399bd1'})
        response = json.loads(response.content)
        self.assertEqual(response['id'], '57d1feb900080151fa399bd1')
        response = self.client.get(reverse('trade:get_package_details'), {'ppc': 'PPC1'})
        response = json.loads(response.content)
        self.assertEqual(response['id'], '57d1feb900080151fa399bd1')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_get_package_from_order_rcc(self):
        """
        Return JSON object {'error': 'Order expected to be delivered in another city'} when
        requiring RCC of an Order to be delivered in a City other than the one of the Retailer
        """
        Package.objects.get(pk='57d1feb900080151fa399bd2').delete()
        response = self.client.get(reverse('trade:get_package_from_rcc'), {'rcc': 'rcc3'})
        self.assertEqual(response.status_code, 302)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('trade:get_package_from_rcc'), {'rcc': 'rcc3'})
        response = json.loads(response.content)
        self.assertEqual(response['id'], '57d1feb900080151fa399bd1')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_RETAILER=False,
                       IS_PROVIDER=True, IS_DELIVERY_MAN=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/trade/',
                       TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_shipping_with_authenticated_member(self):
        yesterday = timezone.now() - timedelta(days=1)
        for db in ('default', 'test_kc_ems', UMBRELLA):
            for profile in OperatorProfile.objects.using(db).all():
                profile.counters_reset_on = yesterday
                profile.payment_delay = OperatorProfile.UPON_CONFIRMATION
                profile.save()

        self.client.login(username='member3', password='admin')
        order = Order.objects.get(pk='55d1feb60008099bd4151fa3')
        order.split_into_packages()  # Simulates order confirmation

        response = self.client.get(reverse('trade:confirm_shipping'), {'order_id': '55d1feb60008099bd4151fa3'})
        json_response = json.loads(response.content)
        self.assertTrue(json_response['success'])

        order = Order.objects.get(pk='55d1feb60008099bd4151fa3')
        order_ems = Order.objects.using('test_kc_ems').get(pk='55d1feb60008099bd4151fa3')
        self.assertEqual(order.status, Order.SHIPPED)

        # Check counters
        cache.clear()
        retailer_profile = OperatorProfile.objects.using('test_kc_foka').get(pk='56922874b37b33706b51f003')
        self.assertEqual(retailer_profile.earnings_history, [4150, 1900, 36608, 3040, 9175, 49529.2])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_RETAILER=False,
                       IS_PROVIDER=True, IS_DELIVERY_MAN=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/trade/',
                       TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_shipping_with_retailer_as_delivery_man(self):
        """
        Earnings of retailers are set upon confirmation of an Order by the delivery person
        """
        yesterday = timezone.now() - timedelta(days=1)
        for db in ('default', 'test_kc_ems', UMBRELLA):
            for profile in OperatorProfile.objects.using(db).all():
                profile.counters_reset_on = yesterday
                profile.payment_delay = OperatorProfile.UPON_CONFIRMATION
                profile.save()

        self.client.login(username='member3', password='admin')
        order = Order.objects.get(pk='55d1feb60008099bd4151fa3')
        order.split_into_packages()  # Simulates order confirmation
        order.delivery_option.company = get_service_instance()  # Simulates retailer taking responsibility to deliver
        order.save(using='default')

        response = self.client.get(reverse('trade:confirm_shipping'), {'order_id': '55d1feb60008099bd4151fa3'})
        json_response = json.loads(response.content)
        self.assertTrue(json_response['success'])

        order = Order.objects.get(pk='55d1feb60008099bd4151fa3')
        self.assertEqual(order.status, Order.SHIPPED)

        # Check counters
        cache.clear()
        retailer_profile = get_service_instance(using='test_kc_foka').config
        self.assertEqual(retailer_profile.earnings_history, [4150, 1900, 36608, 3040, 9175, 52469.2])
        wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b103', provider='paypal')
        self.assertEqual(wallet.balance, 52469.2)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', IS_DELIVERY_COMPANY=True, TESTING=True)
    def test_list_partner_companies(self):

        response = self.client.get(reverse('trade:list_partner_companies'), {'query': 'CAM'})
        self.assertEqual(response.status_code, 200)
        json_response = json.loads(response.content)
        self.assertEqual(json_response['suggestions'][0]['value'], 'Campost')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102', IS_PROVIDER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/cashflex/')
    def test_PartnerList_add_partner_with_provider_adding_partner_bank(self):
        partner_id = '56eb6d04b37b3379b531b107'
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('trade:partner_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('trade:partner_list'),
                                   {'action': 'add_partner', 'partner_id': partner_id}, follow=True)
        final = response.redirect_chain[-1]
        location = final[0].strip('/').split('/')[-1]
        self.assertEqual(location, 'partners')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', IS_BANK=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/cashflex/')
    def test_PartnerList_add_partner_with_bank_adding_partner_merchant(self):
        partner_id = '56eb6d04b37b3379b531b101'
        username = 'arch'
        self.client.login(username='member7', password='admin')
        OperatorProfile.objects.filter(service=partner_id).delete()
        Service.objects.filter(pk=partner_id).delete()
        Member.objects.filter(username=username).delete()
        response = self.client.get(reverse('trade:partner_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('trade:partner_list'),
                                   {'action': 'add_partner', 'partner_id': partner_id}, follow=True)
        final = response.redirect_chain[-1]
        location = final[0].strip('/').split('/')[-1]
        self.assertEqual(location, 'partners')
        # Partner must be found in the local database
        OperatorProfile.objects.get(service=partner_id)
        Service.objects.get(pk=partner_id)
        Member.objects.get(username=username)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', IS_BANK=True)
    def test_DealList_with_set_product_deal_list(self):
        product_id = '55d1fa8feb60008099bd4151'
        product = Product.objects.get(pk=product_id)
        data = {
            'frequency0': 'Day', 'terms_count0': 20, 'first_term0': 10000,
            'term_cost0': 1500, 'about0': 'Perfect for small businesses', 'is_active0': 'on',
            'frequency1': 'Month', 'terms_count1': 5, 'first_term1': 15000,
            'term_cost1': 5000, 'about1': 'Perfect for employees', 'is_active1': 'on',
        }
        self.client.login(username='member7', password='admin')
        self.client.post(reverse('trade:deal_list', args=(product_id, )), data)
        self.assertEqual(Deal.objects.filter(product_slug=product.slug).count(), 2)
        self.assertEqual(Deal.objects.using('test_kc_tecnomobile').filter(product_slug=product.slug).count(), 2)
        deal1 = Deal.objects.get(product_slug=product.slug, frequency='Day')
        self.assertEqual(deal1.bank.id, '56eb6d04b37b3379b531b107')
        self.assertEqual(deal1.terms_count, 20)
        self.assertEqual(deal1.first_term, 10000)
        self.assertEqual(deal1.term_cost, 1500)
        self.assertEqual(deal1.about, 'Perfect for small businesses')
