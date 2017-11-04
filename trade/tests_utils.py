from django.core.management import call_command
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import add_database_to_settings
from ikwen_kakocase.kako.tests_views import wipe_test_data
from ikwen_kakocase.trade.models import Order, Package


class TradeUtilsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_setup_data.yaml', 'kc_operators_configs.yaml', 'kc_members.yaml',
                'kc_profiles.yaml', 'categories.yaml', 'products.yaml']

    def setUp(self):
        self.client = Client()
        add_database_to_settings('test_kc_tecnomobile')
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_ems')
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data('test_kc_sabc')
        wipe_test_data('test_kc_ems')
        wipe_test_data(UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', fixture, database='test_kc_tecnomobile')
            call_command('loaddata', fixture, database='test_kc_sabc')
            call_command('loaddata', fixture, database='test_kc_ems')
            call_command('loaddata', fixture, database=UMBRELLA)
        call_command('loaddata', 'orders.yaml')

    def tearDown(self):
        add_database_to_settings('test_kc_tecnomobile')
        add_database_to_settings('test_kc_sabc')
        add_database_to_settings('test_kc_ems')
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data('test_kc_sabc')
        wipe_test_data('test_kc_ems')
        wipe_test_data(UMBRELLA)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       TESTING=True)
    def test_Order_split_into_packages(self):
        """
        Creates Packages and save them to each provider's database
        """
        order = Order.objects.get(pk='55d1feb60008099bd4151fa3')
        packages_info = order.split_into_packages()
        pack1 = Package.objects.using('test_kc_tecnomobile').all()[0]
        pack2 = Package.objects.using('test_kc_sabc').all()[0]
        self.assertEqual(Package.objects.using('test_kc_tecnomobile').all().count(), 1)
        self.assertEqual(Package.objects.using('test_kc_sabc').all().count(), 1)
        self.assertEqual(Package.objects.using('test_kc_ems').all().count(), 2)
        self.assertEqual(packages_info['test_kc_tecnomobile']['package'], pack1)
        self.assertEqual(packages_info['test_kc_sabc']['package'], pack2)
        # Assuming IKWEN collects 2% on revenue of provider and one of retailer
        self.assertEqual(pack1.provider_revenue, 430000)
        self.assertEqual(pack1.provider_earnings, 421400)
        self.assertEqual(pack1.retailer_earnings, 49000)
        self.assertEqual(pack2.provider_revenue, 2760)
        self.assertEqual(pack2.provider_earnings, 2704.8)
        self.assertEqual(pack2.retailer_earnings, 529.2)
        self.assertEqual(order.retailer_earnings, 49529.2)
        self.assertEqual(order.delivery_earnings, 2940)
