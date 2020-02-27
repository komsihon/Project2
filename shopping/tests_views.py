import json
from datetime import timedelta

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
from ikwen_kakocase.shopping.models import Review, Customer
from ikwen_kakocase.trade.models import Order, Package

from daraja.models import Dara, BonusWallet


class ShoppingViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_setup_data.yaml', 'kc_operators_configs.yaml', 'kc_basic_configs.yaml', 'kc_members.yaml',
                'kc_profiles.yaml', 'categories.yaml', 'products.yaml', 'kc_promotions', 'kc_promocode',
                'drj_setup_data.yaml']

    def setUp(self):
        self.client = Client()
        add_database_to_settings('test_kc_referrer')
        add_database_to_settings('test_kc_ems')
        add_database_to_settings('test_kc_partner_jumbo')
        add_database_to_settings('test_kc_afic')
        wipe_test_data()
        wipe_test_data('test_kc_referrer')
        wipe_test_data('test_kc_ems')
        wipe_test_data('test_kc_partner_jumbo')
        wipe_test_data('test_kc_afic')
        wipe_test_data(UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', fixture, database='test_kc_referrer')
            call_command('loaddata', fixture, database='test_kc_ems')
            call_command('loaddata', fixture, database='test_kc_afic')
            call_command('loaddata', fixture, database=UMBRELLA)

    def tearDown(self):
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_ems')
        add_database_to_settings('test_kc_afic')
        wipe_test_data()
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
        self.client.login(username='member4', password='admin')
        response = self.client.get(reverse('shopping:checkout'), {'delivery_option_id': '55d1feb9b37b301e070604d3',
                                                                  'pay_with': 'paypal'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_RETAILER=False,
                       IS_PROVIDER=True, IS_DELIVERY_MAN=False,
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
        for db in ('default', UMBRELLA):
            for profile in OperatorProfile.objects.using(db).all():
                profile.counters_reset_on = yesterday
                profile.ikwen_share_fixed = 100   # ikwen collects 100F per transaction
                profile.save(using=db)

        cache.clear()
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'details': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3'})
        json_resp = json.loads(response.content)
        self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        pack1 = Package.objects.all()[0]

        # Assuming IKWEN collects 5% on revenue of provider and one of retailer
        self.assertEqual(pack1.provider_revenue, 540000)
        self.assertEqual(pack1.provider_earnings, 512900)
        self.assertEqual(order.delivery_earnings, 2750)
        self.assertEqual(round(order.ikwen_order_earnings, 1), 10940)
        self.assertEqual(order.ikwen_delivery_earnings, 100)
        self.assertEqual(order.eshop_partner_earnings, 16410)
        self.assertEqual(order.logicom_partner_earnings, 150)

        # Check counters for ikwen and partner
        cache.clear()
        service_umbrella = get_service_instance(UMBRELLA)
        self.assertEqual(service_umbrella.turnover_history, [540000])
        self.assertEqual(round(service_umbrella.earnings_history[0], 1), 10940)
        self.assertEqual(service_umbrella.transaction_count_history, [1])
        self.assertEqual(round(service_umbrella.transaction_earnings_history[0], 1), 10940)

        app_umbrella = service_umbrella.app
        self.assertEqual(app_umbrella.turnover_history, [540000])
        self.assertEqual(round(app_umbrella.earnings_history[0], 1), 10940)
        self.assertEqual(app_umbrella.transaction_count_history, [1])
        self.assertEqual(round(app_umbrella.transaction_earnings_history[0], 1), 10940)

        logicom_service_umbrella = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b105')
        self.assertEqual(logicom_service_umbrella.turnover_history, [3000])
        self.assertEqual(logicom_service_umbrella.earnings_history, [100])
        self.assertEqual(logicom_service_umbrella.transaction_count_history, [1])
        self.assertEqual(logicom_service_umbrella.transaction_earnings_history, [100])

        logicom_app_umbrella = logicom_service_umbrella.app
        self.assertEqual(logicom_app_umbrella.turnover_history, [3000])
        self.assertEqual(logicom_app_umbrella.earnings_history, [100])
        self.assertEqual(logicom_app_umbrella.transaction_count_history, [1])
        self.assertEqual(logicom_app_umbrella.transaction_earnings_history, [100])

        service_mirror_partner = Service.objects.using('test_kc_partner_jumbo').get(pk=service_umbrella.id)
        self.assertEqual(service_mirror_partner.turnover_history, [540000])
        self.assertEqual(service_mirror_partner.earnings_history, [16410])
        self.assertEqual(service_mirror_partner.transaction_count_history, [1])
        self.assertEqual(service_mirror_partner.transaction_earnings_history, [16410])

        app_mirror_partner = service_mirror_partner.app
        self.assertEqual(app_mirror_partner.turnover_history, [540000])
        self.assertEqual(app_mirror_partner.earnings_history, [16410])
        self.assertEqual(app_mirror_partner.transaction_count_history, [1])
        self.assertEqual(app_mirror_partner.transaction_earnings_history, [16410])

        partner_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b9b531b10537b331')
        partner_profile_original = PartnerProfile.objects.using('test_kc_partner_jumbo').get(pk='56922a3bb37b33da18d02fb1')
        partner_profile_umbrella = PartnerProfile.objects.using(UMBRELLA).get(pk='56922a3bb37b33da18d02fb1')
        self.assertEqual(partner_wallet.balance, 16560)

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
                                    'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
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
        pack = Package.objects.all()[0]

        self.assertEqual(pack.provider_earnings, 479700)
        self.assertEqual(order.delivery_earnings, 3000)
        self.assertEqual(order.ikwen_delivery_earnings, 0)

        # Check counters for ikwen and partner
        cache.clear()
        profile = get_service_instance().config
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
                                    'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                    'previous_address_index': '0', 'delivery_option_id': '55d1feb9b37b301e070604d3'})
        json_resp = json.loads(response.content)
        response = self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        self.assertIsNone(order.aotc)
        self.assertEqual(order.delivery_address.city, 'Yaounde')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', UNIT_TESTING=True)
    def test_confirm_checkout_with_momo_payment(self):
        """
        Checking out with Mobile Money should work well too
        """
        member = Member.objects.get(username='member4')
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        json_resp = json.loads(response.content)
        notification_url = json_resp['notification_url']
        response = self.client.get(notification_url, data={'status': 'Success', 'phone': '655003321',
                                                           'message': 'OK', 'operator_tx_id': 'OP_TX_1'})
        self.assertEqual(response.status_code, 200)
        order = Order.objects.filter(member=member)[0]
        self.assertEqual(order.status, Order.PENDING)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_PROVIDER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', UNIT_TESTING=True)
    def test_confirm_checkout_with_paid_packaging(self):
        """
        Packaging cost must be included in order cost if Product has packaging cost
        and buyer decided to purchase with packaging along
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4154:10', 'buy_packing': 'yes',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        json_resp = json.loads(response.content)
        notification_url = json_resp['notification_url']
        response = self.client.get(notification_url, data={'status': 'Success', 'phone': '677003321',
                                                           'message': 'OK', 'operator_tx_id': 'OP_TX_1'})
        self.assertEqual(response.status_code, 200)
        order = Order.objects.all()[0]
        self.assertEqual(order.packing_cost, 1000)
        self.assertEqual(order.total_cost, 14000)

        service_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b101', provider='mtn-momo')
        self.assertEqual(service_wallet.balance, 10450)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_PROVIDER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/', UNIT_TESTING=True)
    def test_confirm_checkout_with_unpaid_packaging(self):
        """
        Packaging cost must be ignored if Product has packaging cost
        and buyer decided to refuse to buy packaging
        """
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout'),
                                   {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                    'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                    'entries': '55d1fa8feb60008099bd4154:10', 'buy_packing': '',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')})
        json_resp = json.loads(response.content)
        notification_url = json_resp['notification_url']
        response = self.client.get(notification_url, data={'status': 'Success', 'phone': '655003321',
                                                           'message': 'OK', 'operator_tx_id': 'OP_TX_1'})
        self.assertEqual(response.status_code, 200)
        order = Order.objects.all()[0]
        self.assertEqual(order.packing_cost, 0)
        self.assertEqual(order.total_cost, 13000)

        service_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b101', provider='mtn-momo')
        self.assertEqual(service_wallet.balance, 9500)

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
                                    'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                    'delivery_option_id': '55d1feb9b37b301e070604d3',
                                    'success_url': reverse('shopping:checkout')}, follow=True)
        self.assertTrue(response.status_code, 200)
        self.client.post(reverse('shopping:confirm_checkout') + '?ncs=yes', data={'bank_id': bank_id, 'account_number': '000111'})

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
        Terms payment is available for one single item at a time in an order
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
        self.client.post(reverse('shopping:confirm_checkout') + '?ncs=yes', data={'bank_id': bank_id, 'deal_id': deal_id,
                                                                                  'account_number': '000111'})

        order = Order.objects.filter(status=Order.PENDING_FOR_APPROVAL)[0]  # Order was saved as PendingForApproval
        self.assertEqual(order.deal.id, deal_id)
        copy = Order.objects.using('test_kc_afic').filter(status=Order.PENDING_FOR_APPROVAL)[0]
        member = Member.objects.using('test_kc_afic').get(username='member4')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_RETAILER=False,
                       IS_PROVIDER=True, IS_DELIVERY_MAN=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_register_with_visitor_coming_from_dara_referral_link(self):
        """
        Registration using a Dara referral link ads the Dara
        as referrer of the newly registered Member
        """
        dara_share_link = reverse('shopping:product_detail', args=('food', 'coca-cola')) + '?referrer=56eb6d04b37b3379b531eda1'
        self.client.get(dara_share_link)
        origin = reverse('ikwen:register')
        self.client.post(origin, {'username': 'Test.User1@domain.com', 'password': 'secret', 'password2': 'secret',
                                  'phone': '655000001', 'first_name': 'Sah', 'last_name': 'Fogaing'}, follow=True)
        m = Member.objects.get(username='test.user1@domain.com')
        dara_service = Service.objects.get(pk='58aab5ca4fc0c21cb231e582')
        self.assertEqual(m.customer.referrer, dara_service)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_RETAILER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_buyer_having_referrer(self):
        """
        Saves order, splits it into packages, updates counters and sets order RCC.
        Since buyer has a referrer, his earnings must be correctly set
        """
        yesterday = timezone.now() - timedelta(days=1)
        for db in ('default', 'test_kc_referrer'):
            for service in Service.objects.using(db).all():
                service.counters_reset_on = yesterday
                service.save()
            for profile in OperatorProfile.objects.using(db).all():
                profile.counters_reset_on = yesterday
                profile.save()
            for dara in Dara.objects.using(db).all():
                dara.counters_reset_on = yesterday
                dara.save()
            for category in ProductCategory.objects.using(db).all():
                category.counters_reset_on = yesterday
                category.save()
            for product in Product.objects.using(db).all():
                product.counters_reset_on = yesterday
                product.save()

        referrer = Service.objects.get(pk='58aab5ca4fc0c21cb231e582')
        Customer.objects.filter(member='56eb6d04b37b3379b531e014').update(referrer=referrer)
        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                    {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                     'country_iso2': 'CM', 'city': 'Yaounde', 'details': 'Odza',
                                     'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                     'delivery_option_id': '55d1feb9b37b301e070604d3'})
        json_resp = json.loads(response.content)
        self.client.post(reverse('shopping:paypal_do_checkout'), data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        pack1 = Package.objects.all()[0]
        self.assertEqual(Package.objects.using('test_kc_ems').all().count(), 1)
        self.assertEqual(pack1.entries[0].product.id, '55d1fa8feb60008099bd4151')

        # Assuming IKWEN collects 5% on revenue of website and referrer gets 10%
        self.assertEqual(pack1.provider_revenue, 540000)
        self.assertEqual(pack1.provider_earnings, 459000)
        self.assertEqual(pack1.referrer_earnings, 54000)
        self.assertEqual(order.referrer_earnings, 54000)
        self.assertEqual(order.delivery_earnings, 2850)
        self.assertEqual(order.ikwen_order_earnings, 27150)
        self.assertEqual(order.ikwen_delivery_earnings, 150)

        # Check counters
        cache.clear()
        merchant = get_service_instance()
        merchant_profile = merchant.config
        self.assertEqual(merchant_profile.items_traded_history, [18, 9, 57, 23, 46, 7.0])
        self.assertEqual(merchant_profile.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(merchant_profile.earnings_history, [33800, 22700, 204150, 40890, 70235, 459000.0])
        self.assertEqual(merchant_profile.turnover_history, [33800, 22700, 204150, 40890, 70235, 540000.0])

        dara = Dara.objects.get(pk='58a9658b4fc0c25ddbeca241')
        self.assertEqual(dara.items_traded_history, [18, 9, 57, 23, 46, 7.0])
        self.assertEqual(dara.orders_count_history, [11, 4, 41, 15, 27, 1.0])
        self.assertEqual(dara.earnings_history, [33800, 22700, 204150, 40890, 70235, 459000.0])
        self.assertEqual(dara.turnover_history, [33800, 22700, 204150, 40890, 70235, 540000.0])

        dara_service_original = Service.objects.using('test_kc_referrer').get(pk='58aab5ca4fc0c21cb231e582')
        self.assertEqual(dara_service_original.transaction_count_history, [1.0])
        self.assertEqual(dara_service_original.earnings_history, [54000.0])

        tecno_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b101', provider='paypal')
        self.assertEqual(tecno_wallet.balance, 459000)

        merchant_mirror = Service.objects.using('test_kc_referrer').get(pk='56eb6d04b37b3379b531b101')
        self.assertEqual(merchant_mirror.transaction_count_history, [1.0])
        self.assertEqual(merchant_mirror.earnings_history, [54000.0])

        ems_profile_original = OperatorProfile.objects.using('test_kc_ems').get(pk='56922874b37b33706b51f005')
        self.assertEqual(ems_profile_original.items_traded_history, [18, 9, 57, 23, 46, 7])
        self.assertEqual(ems_profile_original.orders_count_history, [11, 4, 41, 15, 27, 1])
        self.assertEqual(ems_profile_original.earnings_history, [33800, 22700, 204150, 40890, 70235, 2850.0])

        category1 = ProductCategory.objects.get(pk='569228a9b37b3301e0706b51')
        self.assertListEqual(category1.items_traded_history, [18, 9, 57, 23, 46, 7])
        self.assertListEqual(category1.orders_count_history, [11, 4, 41, 15, 27, 1])
        self.assertListEqual(category1.earnings_history, [4150, 1900, 36608, 3040, 9175, 459000.0])

        product = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        self.assertListEqual(product.units_sold_history, [30, 14, 48, 45, 1])
        self.assertEqual(product.total_units_sold, 138)
        self.assertEqual(product.stock, 44)

        product = Product.objects.get(pk='5805d1fa008099bd4151feb6')
        self.assertListEqual(product.units_sold_history, [30, 14, 48, 84, 6])
        self.assertEqual(product.total_units_sold, 143)
        self.assertEqual(product.stock, 39)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_RETAILER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_dara_cash_and_insufficient_balance(self):
        """
        confirm_checkout fails if balance is insufficient
        """
        BonusWallet.objects.using('wallets').filter(dara_id='58a9658b4fc0c25ddbeca241').update(cash=0)
        self.client.login(username='armelsikati', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout') + '?mean=dara-cash',
                                    {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                     'country_iso2': 'CM', 'city': 'Yaounde', 'details': 'Odza',
                                     'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                     'delivery_option_id': '55d1feb9b37b301e070604d3'}, follow=True)
        final = response.redirect_chain[-1]
        self.assertEqual(final, '/cart/')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_RETAILER=True,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_dara_cash(self):
        """
        Saves order, splits it into packages, updates counters and sets order RCC.
        Since buyer has a referrer, his earnings must be correctly set
        """
        BonusWallet.objects.using('wallets').create(dara_id='58a9658b4fc0c25ddbeca241', cash=600000)
        referrer = Service.objects.get(pk='58aab5ca4fc0c21cb231e582')
        Customer.objects.filter(member='56eb6d04b37b3379b531eda1').update(referrer=referrer)
        self.client.login(username='armelsikati', password='admin')
        response = self.client.post(reverse('billing:momo_set_checkout') + '?mean=dara-cash',
                                    {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                     'country_iso2': 'CM', 'city': 'Yaounde', 'details': 'Odza',
                                     'entries': '55d1fa8feb60008099bd4151:1,5805d1fa008099bd4151feb6:6',
                                     'delivery_option_id': '55d1feb9b37b301e070604d3'})
        self.assertEqual(response.status_code, 302)

        tecno_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b101', provider='mtn-momo')
        self.assertEqual(tecno_wallet.balance, 513000)

        ems_wallet = OperatorWallet.objects.using(WALLETS_DB_ALIAS).get(nonrel_id='56eb6d04b37b3379b531b105',
                                                                        provider='mtn-momo')
        self.assertEqual(ems_wallet.balance, 2850)

        dara_bonus_wallet = BonusWallet.objects.using(WALLETS_DB_ALIAS).get(dara_id='58a9658b4fc0c25ddbeca241')
        self.assertEqual(dara_bonus_wallet.cash, 57000)

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
