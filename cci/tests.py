import json

from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest
from ikwen.core.utils import add_database_to_settings
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.models import Service

from ikwen_kakocase.kako.tests_views import wipe_test_data, copy_service_and_config_to_default_db


class CCITestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['cci_member.yaml', 'cci_setup_data.yaml', 'cci_collected.yaml', 'cci_rewarding.yaml']

    def setUp(self):
        self.client = Client()
        call_command('loaddata', 'cci_setup_data.yaml', database='umbrella')
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()
        # wipe_test_data(UMBRELLA)

# Slug must be correctly set

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_cci_pages(self):
        """
        Must create a new SmartCategory in the database. SmartObjectList must return HTTP 200 after the operation
        """
        # copy_service_and_config_to_default_db()
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('cci:home'))
        self.assertEqual(response.status_code, 200)
        customer_id = '56eb6d04b37b3379b531e011'
        response = self.client.get(reverse('cci:get_user_coupon'),
                                   {'customer_id': customer_id})
        coupons = response.context['coupons']
        self.assertEqual(len(coupons), 0)
        response = self.client.get(reverse('cci:save_cci'),
                                   {'customer_id': customer_id, 'amount': 5000,'coupon_id': '593928184fc0c279dc0f73b2'})
        save_with_coupon = json.loads(response.content)
        self.assertEqual(save_with_coupon.success, True)