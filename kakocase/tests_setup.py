import json

from django.conf import settings
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

# Override BILLING_SUBSCRIPTION_MODEL before ikwen.billing.models is loaded
setattr(settings, 'BILLING_SUBSCRIPTION_MODEL', 'core.Service')
setattr(settings, 'BILLING_INVOICE_ITEM_MODEL', 'billing.IkwenInvoiceItem')


from ikwen.theming.models import Theme
from ikwen_kakocase.kako.tests_views import wipe_test_data

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.core.models import Service, Application
from ikwen.billing.models import CloudBillingPlan, InvoicingConfig, InvoiceEntry, IkwenInvoiceItem
from ikwen_kakocase.kakocase.models import OperatorProfile


class KakocaseSetupTestCase(unittest.TestCase):
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
        wipe_test_data('levignon')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103', LOCAL_DEV=True,
                       BILLING_SUBSCRIPTION_MODEL='core.Service',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/cloud_setup/')
    def test_setup(self):
        call_command('loaddata', 'kc_partners.yaml')
        call_command('loaddata', 'kc_partner_app_retail_config.yaml')
        call_command('loaddata', 'kc_partners.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_partner_app_retail_config.yaml', database=UMBRELLA)
        call_command('loaddata', 'themes.yaml', database=UMBRELLA)
        app = Application.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531a001')
        theme = Theme.objects.using(UMBRELLA).get(pk='588fc0c224123d63bb4fc4e1')
        billing_cycle = 'Quarterly'
        billing_plan = CloudBillingPlan.objects.using(UMBRELLA).get(pk='55e7b9b531a003371b6d0cb1')
        member = Member.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531e014')
        project_name = 'Le Vignon'
        domain = 'levignon.cm'
        business_type = OperatorProfile.PROVIDER
        setup_cost = 45000
        monthly_cost = 13500
        partner = Service.objects.using(UMBRELLA).get(pk='56eb6d04b9b531b10537b331')
        item1 = IkwenInvoiceItem(label='Domain name')
        item2 = IkwenInvoiceItem(label='Website cloud_setup', price=billing_plan.setup_cost, amount=setup_cost)
        item3 = IkwenInvoiceItem(label='Shooting of 50 products', amount=50000)
        item4 = IkwenInvoiceItem(label='Publication of 100 products', amount=25000)
        entries = [
            InvoiceEntry(item=item1, short_description=domain),
            InvoiceEntry(item=item2, total=setup_cost),
            InvoiceEntry(item=item3, total=50000),
            InvoiceEntry(item=item4, total=25000)
        ]
        from ikwen_kakocase.kakocase.cloud_setup import deploy
        deploy(app, member, business_type, project_name, billing_plan, theme,
               monthly_cost, entries, billing_cycle, domain, partner_retailer=partner)
        service_partner = Service.objects.get(domain='levignon.cm')
        service_umbrella = Service.objects.using(UMBRELLA).get(domain='levignon.cm')
        service_original = Service.objects.using('levignon').get(domain='levignon.cm')
        self.assertIsNotNone(service_umbrella.config)
        self.assertIsNotNone(service_partner.config)
        self.assertIsNotNone(service_original.config)
        self.assertIsNotNone(InvoicingConfig.objects.using('levignon').all()[0])
