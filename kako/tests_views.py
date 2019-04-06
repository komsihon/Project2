import json

from django.conf import settings
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest
from ikwen_kakocase.commarketing.models import SmartCategory

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.core.models import Service, ConsoleEvent
from ikwen.core.utils import get_service_instance, add_database_to_settings
from ikwen.revival.models import ProfileTag, ObjectProfile, Revival
from ikwen_kakocase.kako.models import Product, RecurringPaymentService
from ikwen_kakocase.kakocase.models import ProductCategory, OperatorProfile


def wipe_test_data(db='default'):
    """
    This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
    each test. So the flush is performed manually with this custom tearDown()
    """
    import ikwen_kakocase.kako.models
    import ikwen_kakocase.trade.models
    import ikwen_kakocase.shopping.models
    import ikwen_kakocase.kakocase.models
    import ikwen_kakocase.commarketing.models
    import ikwen.core.models
    import ikwen.revival.models
    if db != 'default':
        add_database_to_settings(db)
    for name in ('Customer', 'AnonymousBuyer', ):
        model = getattr(ikwen_kakocase.shopping.models, name)
        model.objects.using(db).all().delete()
    for name in ('OperatorProfile', 'ProductCategory', 'BusinessCategory', 'DeliveryOption', 'City'):
        model = getattr(ikwen_kakocase.kakocase.models, name)
        model.objects.using(db).all().delete()
    for name in ('Product', 'RecurringPaymentService', 'Photo'):
        model = getattr(ikwen_kakocase.kako.models, name)
        model.objects.using(db).all().delete()
    for name in ('Order', 'Package'):
        model = getattr(ikwen_kakocase.trade.models, name)
        model.objects.using(db).all().delete()
    for name in ('Banner', 'SmartCategory'):
        model = getattr(ikwen_kakocase.commarketing.models, name)
        model.objects.using(db).all().delete()
    for name in ('Application', 'Service', 'Config', 'ConsoleEventType', 'ConsoleEvent', 'Country', ):
        model = getattr(ikwen.core.models, name)
        model.objects.using(db).all().delete()
    for name in ('PartnerProfile', 'ApplicationRetailConfig'):
        model = getattr(ikwen.partnership.models, name)
        model.objects.using(db).all().delete()
    for name in ('ObjectProfile', 'MemberProfile', 'Revival', 'ProfileTag', 'Target'):
        model = getattr(ikwen.revival.models, name)
        model.objects.using(db).all().delete()
    for name in ('Product', 'Payment', 'Invoice', 'Subscription', 'InvoicingConfig',
                 'PaymentMean', 'MoMoTransaction', 'SupportBundle', 'SupportCode'):
        model = getattr(ikwen.billing.models, name)
        model.objects.using(db).all().delete()


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
    fixtures = ['kc_members.yaml', 'kc_profiles.yaml', 'categories.yaml', 'orders.yaml']

    def setUp(self):
        self.client = Client()
        call_command('loaddata', 'kc_setup_data.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_operators_configs.yaml', database=UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')
        wipe_test_data(UMBRELLA)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProviderListView(self):
        """
        Page must return HTTP 200 status
        Providers with 'Auto' last_stock_update_method must come first
        """
        copy_service_and_config_to_default_db()
        response = self.client.get(reverse('kako:provider_list'))
        self.assertEqual(response.status_code, 200)
        providers = response.context['providers']
        self.assertEqual(providers.count(), 2)
        self.assertEqual(providers[0].service.project_name, 'sabc')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProviderListView_json_format(self):
        """
        Requesting providers list with GET parameter format=json&q=searchTerm should
        perform a search and return a list providers in JSON format.
        """
        copy_service_and_config_to_default_db()
        response = self.client.get(reverse('kako:provider_list'), {'format': 'json', 'q': 'mobil', 'start': 0, 'length': 24})
        self.assertEqual(response.status_code, 200)
        # print response.content
        providers = json.loads(response.content)
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0]['company_name'], 'Tecno Mobile Telecom')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProviderListView_query_by_category_json_format(self):
        """
        Requesting providers list with GET parameter format=json&category_slug=categorySlug&q=searchTerm should
        perform a search and return a list providers in JSON format.
        """
        copy_service_and_config_to_default_db()
        response = self.client.get(reverse('kako:provider_list'),
                                   {'format': 'json', 'category_slug': 'beverage', 'q': 'bra', 'start': 0, 'length': 24})
        self.assertEqual(response.status_code, 200)
        providers = json.loads(response.content)
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0]['company_name'], 'Les Brasseries du Cameroun')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProviderProductListView(self):
        """
        Page must return HTTP 200 status, products with largest items_sold must come first.
        """
        copy_service_and_config_to_default_db()
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b102')
        add_database_to_settings(service.database)
        Product.objects.using(service.database).all().delete()
        call_command('loaddata', 'kc_setup_data.yaml', database=service.database)
        call_command('loaddata', 'products.yaml', database=service.database)
        provider = Service.objects.using(service.database).get(pk='56eb6d04b37b3379b531b102')
        Product.objects.using(service.database).exclude(provider=provider).delete()
        response = self.client.get(reverse('kako:provider_product_list', args=('56922874b37b33706b51f002', )))
        self.assertEqual(response.status_code, 200)
        products = response.context['products']
        self.assertEqual(products.count(), 3)
        self.assertEqual(products[0].name, 'Breaded fish')
        from pymongo import Connection
        cnx = Connection()
        cnx.drop_database(service.database)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProviderProductListView_json_format(self):
        """
        Requesting products list with GET parameter format=json&q=searchTerm should.
        Result must return as a list of JSON objects
        """
        copy_service_and_config_to_default_db()
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b102')
        add_database_to_settings(service.database)
        Product.objects.using(service.database).all().delete()
        call_command('loaddata', 'products.yaml', database=service.database)
        response = self.client.get(reverse('kako:provider_product_list', args=('56922874b37b33706b51f002', )),
                                   {'format': 'json', 'q': 'col', 'start': 0, 'length': 24})
        self.assertEqual(response.status_code, 200)
        products = json.loads(response.content)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], 'Coca-Cola')
        from pymongo import Connection
        cnx = Connection()
        cnx.drop_database(service.database)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProviderProductListView_query_by_category_json_format(self):
        """
        Requesting products list with GET parameter format=json&category_slug=slug&q=searchTerm should.
        Result must return as a list of JSON objects
        """
        copy_service_and_config_to_default_db()
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b102')
        add_database_to_settings(service.database)
        Product.objects.using(service.database).all().delete()
        call_command('loaddata', 'kc_setup_data.yaml', database=service.database)
        call_command('loaddata', 'products.yaml', database=service.database)
        provider = Service.objects.using(service.database).get(pk='56eb6d04b37b3379b531b102')
        Product.objects.using(service.database).exclude(provider=provider).delete()
        response = self.client.get(reverse('kako:provider_product_list', args=('56922874b37b33706b51f002', )),
                                   {'format': 'json', 'category_slug': 'food', 'q': 'col', 'start': 0, 'length': 24})
        self.assertEqual(response.status_code, 200)
        products = json.loads(response.content)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], 'Coca-Cola')
        from pymongo import Connection
        cnx = Connection()
        cnx.drop_database(service.database)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductList(self):
        """
        Page must return HTTP 200 status, products with largest items_sold must come first.
        """
        call_command('loaddata', 'kc_setup_data.yaml')
        call_command('loaddata', 'kc_operators_configs.yaml')
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:product_list'))
        self.assertEqual(response.status_code, 200)
        products = response.context['product_list']
        self.assertEqual(products.count(), 4)
        self.assertEqual(products[0].name, 'Samsung Galaxy S7')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductList_json_format(self):
        """
        Requesting products list with GET parameter format=json&q=searchTerm should.
        Result must return as a list of JSON objects
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:product_list'),
                                   {'format': 'json', 'q': 'col', 'start': 0, 'length': 24})
        self.assertEqual(response.status_code, 200)
        products = json.loads(response.content)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['name'], 'Coca-Cola')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ProductList_filter_by_category_json_format(self):
        """
        Requesting products list with GET parameter format=json&q=searchTerm should.
        Result must return as a list of JSON objects
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:product_list'),
                                   {'format': 'json', 'category_slug': 'food', 'start': 0, 'length': 24})
        self.assertEqual(response.status_code, 200)
        products = json.loads(response.content)
        self.assertEqual(len(products), 3)
        self.assertEqual(products[0]['name'], 'Coca-Cola')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_do_import_products(self):
        """
        Importing products merely copies a list of products from the provider database to the retailer database.
        Retailer profile and Member object are copied to the provider's database and vice versa.
        Every imported product must have the field is_retailed=True.
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        copy_service_and_config_to_default_db()
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b102')
        add_database_to_settings(service.database)
        Product.objects.using(service.database).all().delete()
        call_command('loaddata', 'kc_profiles.yaml', database=service.database)
        call_command('loaddata', 'products.yaml', database=service.database)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:do_import_products'),
                                   {'provider_slug': 'les-brasseries-du-cameroun',
                                    'provider_id': '56922874b37b33706b51f002',
                                    'product_ids': '55d1fa8feb60008099bd4152,55d1fa8feb60008099bd4153'})
        self.assertEqual(response.status_code, 200)
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        self.assertEqual(Product.objects.using('default').all().count(), 2)
        Member.objects.using(service.database).get(username='member3')  # Member must be in Provider's database
        OperatorProfile.objects.using(service.database).get(pk='56922874b37b33706b51f003')  # Retailer must be in Provider's database
        Service.objects.using(service.database).get(pk='56eb6d04b37b3379b531b103')  # Service must be in Provider's database
        for product in Product.objects.using(service.database).filter(pk__in=['55d1fa8feb60008099bd4152', '55d1fa8feb60008099bd4153']):
            self.assertTrue(product.is_retailed)
        from pymongo import Connection
        cnx = Connection()
        cnx.drop_database(service.database)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_do_import_products_with_unauthorized_member(self):
        """
        Unauthorized member cannot import product
        """
        copy_service_and_config_to_default_db()
        response = self.client.get(reverse('kako:do_import_products'))
        self.assertEqual(response.status_code, 302)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_update_product_retail_price_with_modification_allowed(self):
        """
        Updating retail price works only when modification is allowed
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:update_product_retail_price'),
                                   {'product_id': '55d1fa8feb60008099bd4152', 'price': '500'})
        self.assertEqual(response.status_code, 200)
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        self.assertEqual(Product.objects.get(pk='55d1fa8feb60008099bd4152').retail_price, 500)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_update_product_retail_price_with_new_price_bigger_than_max_price(self):
        """
        Retail price is set to max_price if new price is bigger than the max_price set by provider.
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:update_product_retail_price'),
                                   {'product_id': '55d1fa8feb60008099bd4152', 'price': '600'})
        self.assertEqual(response.status_code, 200)
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        self.assertEqual(Product.objects.get(pk='55d1fa8feb60008099bd4152').retail_price, 500)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_update_product_retail_price_with_modification_not_allowed(self):
        """
        Updating retail price works only when modification is allowed
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'products.yaml')
        product = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        product.retail_price_is_modifiable = False
        product.save()
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:update_product_retail_price'),
                                   {'product_id': '55d1fa8feb60008099bd4152', 'price': '500'})
        self.assertEqual(response.status_code, 200)
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        self.assertEqual(product.retail_price, 450)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       CACHES=None)
    def test_update_product_stock_with_modification_not_allowed(self):
        """
        Stock is set to the new value and OperatorProfile stock_updated_on and
        last_stock_update_method are respectively set to now and Manual
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'products.yaml')
        response = self.client.get(reverse('kako:update_product_stock'),
                                   {'product_id': '55d1fa8feb60008099bd4152', 'stock': '54'})
        self.assertEqual(response.status_code, 302)
        self.client.login(username='member3', password='admin')  # Login now
        response = self.client.get(reverse('kako:update_product_stock'),
                                   {'product_id': '55d1fa8feb60008099bd4152', 'stock': '54'})
        self.assertEqual(response.status_code, 200)
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        product = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        self.assertEqual(product.stock, 54)
        sabc_profile_umbrella = OperatorProfile.objects.using(UMBRELLA).get(pk='56922874b37b33706b51f003')
        self.assertEqual(sabc_profile_umbrella.last_stock_update_method, OperatorProfile.MANUAL_UPDATE)


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_AddProductView(self):
        """
        AddProductView must return HTTP 200 with or without a product, and return HTTP 302 if user unauthorized
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_setup_data.yaml')
        call_command('loaddata', 'kc_operators_configs.yaml')
        call_command('loaddata', 'products.yaml')
        copy_service_and_config_to_default_db()
        response = self.client.get(reverse('kako:change_product'))
        self.assertEqual(response.status_code, 302)
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:change_product'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('kako:change_product'), {'product_id': '55d1fa8feb60008099bd4152'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ChangeProduct_with_new_product(self):
        """
        submit_product view updates product information if it previously exists.
        Only retail_price can be set if user is a Retailer
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        category_id = '569228a9b37b3301e0706b51'
        self.client.login(username='member3', password='admin')
        response = self.client.post(reverse('kako:change_product'),
                                    {'name': 'New Black Chocolate', 'brand': 'Mambo',
                                     'category': category_id,
                                     'wholesale_price': '0',
                                     'retail_price': '600',
                                     'min_order': '1',
                                     'packing_price': '0',
                                     'summary': 'Some summary',
                                     'description': 'Some description'})
        product = Product.objects.get(slug='new-black-chocolate')  # Slug must be correctly set
        self.assertEqual(product.name, 'New Black Chocolate')
        self.assertEqual(product.category, ProductCategory.objects.get(pk='569228a9b37b3301e0706b51'))
        self.assertEqual(product.wholesale_price, 0)  # wholesale_price remains unchanged
        self.assertIsNone(product.max_price)  # max_price is None
        self.assertEqual(product.retail_price, 600)  # retail_price cannot be bigger than max_price
        self.assertEqual(product.description, 'Some description')
        category = ProductCategory.objects.get(pk=category_id)
        tag = ProfileTag.objects.get(name=category.name, slug='__' + category.slug, is_auto=True)
        Revival.objects.using(UMBRELLA).get(service=get_service_instance(), model_name='kako.product',
                                            object_id=product.id, profile_tag_id=tag.id)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       IS_RETAILER=True, IS_PROVIDER=False)
    def test_submit_product_with_existing_product(self):
        """
        submit_product view updates product information if it previously exists.
        Only retail_price can be set if user is a Retailer
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_setup_data.yaml')
        call_command('loaddata', 'kc_operators_configs.yaml')
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        product = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        product.provider = get_service_instance()  # Make provider of this product the current retailer
        product.save()
        p_dict = product.__dict__
        p_dict['category'] = '569228a9b37b3301e0706b51'
        p_dict['name'] = 'Black Chocolate'
        p_dict['brand'] = 'Mambo'
        p_dict['summary'] = 'Some summary'
        p_dict['description'] = 'Some description'
        p_dict['retail_price'] = 500
        response = self.client.post(reverse('kako:change_product', args=('55d1fa8feb60008099bd4152', )), p_dict)
        product = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        self.assertEqual(product.name, 'Black Chocolate')
        self.assertEqual(product.slug, 'black-chocolate')  # Slug must be correctly set
        self.assertEqual(product.category, ProductCategory.objects.get(pk='569228a9b37b3301e0706b51'))
        self.assertEqual(product.retail_price, 500)
        self.assertEqual(product.summary, 'Some summary')
        self.assertEqual(product.description, 'Some description')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       IS_PROVIDER=True)
    def test_submit_product_with_existing_product_being_retailed(self):
        """
        submit_product view redirects to the add_view page without actually updating product information
        if a provider attemps to update information of a product being retailed.
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        copy_service_and_config_to_default_db()
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b102')
        add_database_to_settings(service.database)
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member2', password='admin')
        product = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        product.is_retailed = True
        product.save()
        p_dict = product.__dict__
        p_dict['category'] = p_dict['category_id']
        p_dict['retail_price'] = 500
        response = self.client.post(reverse('kako:change_product', args=('55d1fa8feb60008099bd4152', )), p_dict)
        self.assertIsNotNone(response.context['error'])
        product = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        self.assertEqual(product.retail_price, 450)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_submit_product_with_new_service(self):
        """
        submit_product view can only update retail_price of services
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        response = self.client.post(reverse('kako:change_product'),
                                   {'product_type': 'service',
                                    'name': 'Auto Insurance', 'brand': '',
                                    'category': '569228a9b37b3301e0706b54',
                                    'duration': '91',
                                    'duration_text': '3 mois',
                                    'wholesale_price': '0',
                                    'retail_price': '6000',
                                    'summary': 'Some summary',
                                    'description': 'Some description'})
        service = RecurringPaymentService.objects.get(slug='auto-insurance')  # Slug must be correctly set
        self.assertEqual(service.name, 'Auto Insurance')
        self.assertEqual(service.category, ProductCategory.objects.get(pk='569228a9b37b3301e0706b54'))
        self.assertEqual(service.wholesale_price, 0)  # wholesale_price remains unchanged
        self.assertIsNone(service.max_price)  # max_price is None
        self.assertEqual(service.retail_price, 6000)  # retail_price cannot be bigger than max_price
        self.assertEqual(service.summary, 'Some summary')
        self.assertEqual(service.description, 'Some description')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_submit_product_with_existing_service(self):
        """
        submit_product view update information of a previously existing RecurringPaymentService
        """
        copy_service_and_config_to_default_db()
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'products.yaml')
        self.client.login(username='member3', password='admin')
        service = RecurringPaymentService.objects.get(pk='55d1fa8feb60008099bd4154')
        service.provider = get_service_instance()  # Make provider of this service the current retailer
        service.save()
        response = self.client.post(reverse('kako:change_product'),
                                   {'product_id': '55d1fa8feb60008099bd4154',
                                    'category': '569228a9b37b3301e0706b54',
                                    'name': 'Loss insurance',
                                    'product_type': 'service',
                                    'duration': service.duration,
                                    'duration_text': service.duration_text,
                                    'retail_price': '6000',
                                    'summary': 'Some summary',
                                    'description': 'Some description'})
        service = RecurringPaymentService.objects.get(pk='55d1fa8feb60008099bd4154')
        self.assertEqual(service.name, 'Loss insurance')
        self.assertEqual(service.slug, 'loss-insurance')  # Slug must be correctly set
        self.assertEqual(service.category, ProductCategory.objects.get(pk='569228a9b37b3301e0706b54'))
        self.assertEqual(service.retail_price, 6000)  # retail_price cannot be bigger than max_price
        self.assertEqual(service.summary, 'Some summary')
        self.assertEqual(service.description, 'Some description')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       IS_PROVIDER=True)
    def test_delete_product_with_product_being_in_a_smart_category(self):
        """
        Deleting a product decrements the items_count
        of Category or SmartCategory it belongs to 
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_setup_data.yaml')
        call_command('loaddata', 'kc_operators_configs.yaml')
        call_command('loaddata', 'categories.yaml')
        call_command('loaddata', 'products.yaml')
        call_command('loaddata', 'smart_objects.yaml')
        obj = SmartCategory.objects.get(pk='56a9b37b3301e0706b549224')
        obj.items_count = 1
        obj.items_fk_list.append('55d1fa8feb60008099bd4152')
        obj.save()
        self.client.login(username='member2', password='admin')
        self.client.get(reverse('kako:put_product_in_trash'), {'selection': '55d1fa8feb60008099bd4152'})
        category = ProductCategory.objects.get(pk='569228a9b37b3301e0706b52')
        smart_category = SmartCategory.objects.get(pk='56a9b37b3301e0706b549224')
        self.assertEqual(category.items_count, 2)
        self.assertEqual(smart_category.items_count, 0)
        self.assertListEqual(smart_category.items_fk_list, [])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_delete_category_with_category_being_in_a_smart_category(self):
        """
        Deleting a product decrements the items_count
        of Category or SmartCategory it belongs to 
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_setup_data.yaml')
        call_command('loaddata', 'kc_operators_configs.yaml')
        call_command('loaddata', 'categories.yaml')
        call_command('loaddata', 'smart_objects.yaml')
        obj = SmartCategory.objects.get(pk='56a9b37b3301e0706b549223')
        obj.items_count = 1
        obj.items_fk_list.append('569228a9b37b3301e0706b52')
        obj.save()
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('kako:delete_category'),
                                   {'selection': '569228a9b37b3301e0706b52'})
        smart_category = SmartCategory.objects.get(pk='56a9b37b3301e0706b549223')
        self.assertEqual(smart_category.items_count, 0)
        self.assertListEqual(smart_category.items_fk_list, [])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_do_import_products_from_spreadsheet_with_unauthorized_member(self):
        """
        Unauthorized member cannot import product
        """
        copy_service_and_config_to_default_db()
        response = self.client.get(reverse('kako:do_import_products_from_spreadsheet'))
        self.assertEqual(response.status_code, 302)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       MEDIA_ROOT='')
    def test_do_import_products_from_spreadsheet(self):
        """
        Importing products merely pulls a list of products from an Excel file into the database
        """
        media_root = getattr(settings, 'BASE_DIR') + '/'
        setattr(settings, 'MEDIA_ROOT', media_root)
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'products.yaml')
        copy_service_and_config_to_default_db()
        Product.objects.all().delete()
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('kako:do_import_products_from_spreadsheet'), {'upload_id': '56eb6d779b33b531e09104b1'})
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        self.assertEqual(Product.objects.all().count(), 2)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102')
    def test_set_stock(self):
        """
        set_stock sets stock to the number of units, all passed as url parameter
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        call_command('loaddata', 'kc_setup_data.yaml')
        call_command('loaddata', 'kc_operators_configs.yaml')
        call_command('loaddata', 'products.yaml')
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b103')
        add_database_to_settings(service.database)
        Product.objects.using(service.database).all().delete()
        call_command('loaddata', 'products.yaml', database=service.database)
        response = self.client.get(reverse('kako:set_stock', args=('api-signature2', '55d1fa8feb60008099bd4152', 12)))
        response = json.loads(response.content)
        self.assertTrue(response['success'])
        self.assertDictEqual(response['details'], {'kcid': '55d1fa8feb60008099bd4152', 'stock': 12})
        product = Product.objects.using(service.database).get(pk='55d1fa8feb60008099bd4152')
        self.assertEqual(product.stock, 12)
        config = get_service_instance(UMBRELLA).config
        self.assertEqual(config.last_stock_update_method, OperatorProfile.AUTO_UPDATE)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b102',
                       IS_PROVIDER=True, IS_RETAILER=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/kako/')
    def test_put_product_in_trash(self):
        """
        set_stock causes the stock to lower or raise by the number of units, all passed as GET parameters
        """
        call_command('loaddata', 'kc_members.yaml', database=UMBRELLA)
        copy_service_and_config_to_default_db()
        service = Service.objects.using(UMBRELLA).get(pk='56eb6d04b37b3379b531b103')
        add_database_to_settings(service.database)
        call_command('loaddata', 'kc_setup_data.yaml', database='default')
        call_command('loaddata', 'products.yaml', database='default')
        call_command('loaddata', 'kc_operators_configs.yaml', database='default')
        call_command('loaddata', 'categories.yaml', database=service.database)
        call_command('loaddata', 'products.yaml', database=service.database)
        Product.objects.using('default').all().update(is_retailed=True)
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('kako:put_product_in_trash') + '?selection=55d1fa8feb60008099bd4152')
        response = json.loads(response.content)
        self.assertIsNotNone(response['message'])
        product = Product.objects.using(service.database).filter(pk='55d1fa8feb60008099bd4152')
        self.assertEqual(product.count(), 0)
        member3 = Member.objects.using(UMBRELLA).get(username='member3')
        self.assertEqual(member3.personal_notices, 1)
        self.assertEqual(ConsoleEvent.objects.using(UMBRELLA).filter(member=member3).count(), 1)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', IS_BANK=True, LOCAL_DEV=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/kako/')
    def test_load_product_from_url_with_unregistered_partner(self):
        """
        Products from unregistered partner cannot be loaded.
        """
        for alias in ('default', 'test_kc_tecnomobile'):
            call_command('loaddata', 'kc_setup_data.yaml', database=alias)
            call_command('loaddata', 'kc_operators_configs.yaml', database=alias)
        call_command('loaddata', 'categories.yaml', database='test_kc_tecnomobile')
        call_command('loaddata', 'products.yaml', database='test_kc_tecnomobile')
        Service.objects.filter(project_name='tecnomobile').delete()
        OperatorProfile.objects.filter(company_name='Tecno Mobile Telecom').delete()

        url = 'http://tecnomobile.ikwen.com/phones-and-tablets/samsung-galaxy-s7'
        self.client.login(username='member7', password='admin')
        response = self.client.get(reverse('kako:load_product_from_url'), {'url': url})
        response = json.loads(response.content)
        self.assertEqual(response['error'], 'You must add Tecno Mobile Telecom as a Partner Merchant to import his products.')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', IS_BANK=True, LOCAL_DEV=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/kako/')
    def test_load_product_from_url_with_registered_partner(self):
        """
        Retrieves product an merchant based on URL of product
        """
        for alias in ('default', 'test_kc_tecnomobile'):
            call_command('loaddata', 'kc_setup_data.yaml', database=alias)
            call_command('loaddata', 'kc_operators_configs.yaml', database=alias)
        call_command('loaddata', 'categories.yaml', database='test_kc_tecnomobile')
        call_command('loaddata', 'products.yaml', database='test_kc_tecnomobile')
        url = 'http://tecnomobile.ikwen.com/phones-and-tablets/samsung-galaxy-s7'
        self.client.login(username='member7', password='admin')
        response = self.client.get(reverse('kako:load_product_from_url'), {'url': url})
        response = json.loads(response.content)
        self.assertEqual(response['product']['slug'], 'samsung-galaxy-s7')  # Product has been correctly retrieved

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', IS_BANK=True, LOCAL_DEV=False,
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/kako/')
    def test_save_product_from_url_with_registered_partner(self):
        """
        Retrieves product an merchant based on URL of product
        """
        for alias in ('umbrella', 'test_kc_tecnomobile'):
            call_command('loaddata', 'kc_members.yaml', database=alias)
        for alias in ('default', 'test_kc_tecnomobile'):
            call_command('loaddata', 'kc_setup_data.yaml', database=alias)
            call_command('loaddata', 'kc_operators_configs.yaml', database=alias)
        call_command('loaddata', 'categories.yaml', database='test_kc_tecnomobile')
        call_command('loaddata', 'products.yaml', database='test_kc_tecnomobile')
        Product.objects.all().delete()

        url = 'http://tecnomobile.ikwen.com/phones-and-tablets/samsung-galaxy-s7'
        self.client.login(username='member7', password='admin')
        response = self.client.get(reverse('kako:save_product_from_url'), {'url': url})
        self.assertEqual(response.status_code, 302)
        Product.objects.get(slug='samsung-galaxy-s7')  # Product has been correctly saved locally
