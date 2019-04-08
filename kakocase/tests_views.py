import json

from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest


from ikwen_kakocase.kako.tests_views import wipe_test_data

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.models import Service
from ikwen.core.utils import get_service_instance
from ikwen_kakocase.kakocase.models import OperatorProfile


def copy_service_and_config_to_default_db():
    service = get_service_instance(using=UMBRELLA)
    service.save(using='default')  # Copies Service to the default DB
    config = OperatorProfile.objects.using(UMBRELLA).get(service=service)
    config.save(using='default')
    return service, config


class KakoViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_members.yaml', 'kc_setup_data.yaml', 'kc_operators_configs.yaml', 'categories.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', fixture, database=UMBRELLA)

    def tearDown(self):
        wipe_test_data()
        wipe_test_data(UMBRELLA)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_IKWEN=False)
    def test_DeliveryOptionList(self):
        """
        Page must return HTTP 200 status
        """
        copy_service_and_config_to_default_db()
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kakocase:delivery_options'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_list_delivery_companies(self):
        response = self.client.get(reverse('kakocase:list_available_companies'),
                                   {'business_type': OperatorProfile.LOGISTICS, 'query': 'CAM'})
        self.assertEqual(response.status_code, 200)
        # print response.content
        resp = json.loads(response.content)
        suggestions = resp['suggestions']
        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[1]['value'], 'Campost')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', IS_IKWEN=False)
    def test_add_delivery_company_to_local_database(self):
        response = self.client.get(reverse('kakocase:add_delivery_company_to_local_database'),
                                   {'company_id': '56eb6d04b37b3379b531b105'})
        resp = json.loads(response.content)
        self.assertTrue(resp['success'])
        # Service and config must be found in the local database
        config = Service.objects.get(pk='56eb6d04b37b3379b531b105').config
