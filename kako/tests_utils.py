from django.core.management import call_command
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.revival.models import ProfileTag

from ikwen_kakocase.commarketing.models import Banner, PRODUCTS, SLIDE
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kako.tests_views import wipe_test_data
from ikwen_kakocase.kako.utils import create_category, mark_duplicates, get_product_from_url
from ikwen_kakocase.kakocase.models import ProductCategory, OperatorProfile


class KakoUtilsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_members.yaml', 'kc_profiles.yaml', 'kc_setup_data.yaml', 'kc_operators_configs.yaml',
                'categories.yaml', 'products.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()
        wipe_test_data('test_kc_tecnomobile')


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_create_category(self):
        """
        Creating a category creates it in local database.
        """
        create_category(name='New category')
        category = ProductCategory.objects.get(slug='new-category')
        self.assertEqual(category.name, 'New category')  # Upon creation, name is capitalized


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_Product_get_size_list(self):
        """
        Product.get_size_list returns a list of all sizes of Products with same slug, category and brand.
        """
        brand = 'Same Brand'
        c = ProductCategory.objects.all()[0]
        slug = 'same-slug'
        Product.objects.filter(pk='55d1fa8feb60008099bd4151').update(category=c, slug=slug, brand=brand, size="S")
        Product.objects.filter(pk='55d1fa8feb60008099bd4152').update(category=c, slug=slug, brand=brand, size="M")
        Product.objects.filter(pk='55d1fa8feb60008099bd4153').update(category=c, slug=slug, brand=brand, size="L")
        p1 = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        self.assertEqual(p1.get_size_list_label(), 'S / M / L')


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_mark_duplicates(self):
        """
        Product.get_size_list returns a list of all sizes of Products with same slug, category and brand.
        """
        brand = 'Same Brand'
        c = ProductCategory.objects.all()[0]
        slug = 'same-slug'
        Product.objects.filter(pk='55d1fa8feb60008099bd4151').update(category=c, slug=slug, brand=brand, size="S", stock=10)
        Product.objects.filter(pk='55d1fa8feb60008099bd4152').update(category=c, slug=slug, brand=brand, size="M", stock=5)
        Product.objects.filter(pk='55d1fa8feb60008099bd4153').update(category=c, slug=slug, brand=brand, size="L", stock=7)
        p1 = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        mark_duplicates(p1)
        p2 = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        p3 = Product.objects.get(pk='55d1fa8feb60008099bd4153')
        self.assertTrue(p2.is_duplicate)
        self.assertTrue(p3.is_duplicate)
        self.assertFalse(p1.is_duplicate)
        p1.delete()
        p2 = Product.objects.get(pk='55d1fa8feb60008099bd4152')
        self.assertTrue(p2.is_duplicate)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_Product_delete(self):
        """
        Product.get_size_list returns a list of all sizes of Products with same slug, category and brand.
        """
        Banner.objects.create(title='Banner', content_type=PRODUCTS, display=SLIDE,
                              items_fk_list=['55d1fa8feb60008099bd4151', '55d1fa8feb60008099bd4152'])
        p1 = Product.objects.get(pk='55d1fa8feb60008099bd4151')
        p1.delete()
        banner = Banner.objects.get(title='Banner')
        self.assertListEqual(banner.items_fk_list, ['55d1fa8feb60008099bd4152'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', LOCAL_DEV=False)
    def test_get_product_from_url(self):
        """
        Retrieves product an merchant based on URL of product
        """
        call_command('loaddata', 'kc_setup_data.yaml', database='umbrella')
        call_command('loaddata', 'categories.yaml', database='test_kc_tecnomobile')
        call_command('loaddata', 'products.yaml', database='test_kc_tecnomobile')
        url = 'http://tecnomobile.ikwen.com/phones-and-tablets/samsung-galaxy-s7'
        product, merchant = get_product_from_url(url)
        self.assertEqual(product.slug, 'samsung-galaxy-s7')
        self.assertEqual(merchant.id, '56eb6d04b37b3379b531b101')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b107', LOCAL_DEV=False)
    def test_post_delete_category(self):
        """
        Retrieves product an merchant based on URL of product
        """
        category = ProductCategory.objects.get(pk='569228a9b37b3301e0706b51')  # 'phone-and-tablets'
        slug = category.slug
        ProfileTag.objects.create(name=category.name, slug='__' + category.slug, is_auto=True)
        category.delete()
        self.assertRaises(ProfileTag.DoesNotExist, ProfileTag.objects.get, **{'slug': '__' + slug})
