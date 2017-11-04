import json

from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from commarketing.models import Banner, CATEGORIES, SmartCategory, SLIDE
from ikwen_kakocase.kako.tests_views import wipe_test_data


class MarketingViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['kc_members.yaml', 'kc_setup_data.yaml', 'kc_operators_configs.yaml',
                'kc_profiles.yaml', 'categories.yaml', 'products.yaml', 'smart_objects.yaml']

    def setUp(self):
        self.client = Client()
        # call_command('loaddata', 'kc_setup_data.yaml', database=UMBRELLA)
        # call_command('loaddata', 'kc_operators_configs.yaml', database=UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()
        # wipe_test_data(UMBRELLA)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       IS_RETAILER=True, IS_PROVIDER=False)
    def test_BannerList(self):
        """
        Page must return HTTP 200 status
        """
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('marketing:banner_list'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       IS_RETAILER=True, IS_PROVIDER=False)
    def test_SmartCategoryList(self):
        """
        Page must return HTTP 200 status
        """
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('marketing:smart_category_list'))
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       IS_RETAILER=True, IS_PROVIDER=False)
    def test_ChangeSmartObject_with_new_banner(self):
        """
        Must create a new banner in the database. BannerList must return HTTP 200 after the operation
        """
        self.client.login(username='member3', password='admin')
        self.client.post(reverse('marketing:change_smart_object', args=('banner', )),
                         {'smart_object_id': '',
                          'title': 'Store Opening',
                          'content_type': 'Categories',
                          'display': 'Slide',
                          'is_active': 'yes'}
                         )
        slide = Banner.objects.get(slug='store-opening', display=SLIDE)  # Slug must be correctly set
        self.assertEqual(slide.title, 'Store opening')
        self.assertEqual(slide.content_type, CATEGORIES)
        response = self.client.get(reverse('marketing:banner_list'))
        self.assertEqual(response.status_code, 200)
        slides = response.context['slide_list']
        popups = response.context['popup_list']
        fw_sections = response.context['fw_section_list']
        fs_popups = response.context['fs_popup_list']
        self.assertEqual(slides.count(), 3)
        self.assertEqual(popups.count(), 0)
        self.assertEqual(fw_sections.count(), 0)
        self.assertEqual(fs_popups.count(), 0)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       IS_RETAILER=True, IS_PROVIDER=False)
    def test_ChangeSmartObject_with_existing_banner(self):
        """
        Changing an existing banner updates information with new one
        """
        self.client.login(username='member3', password='admin')
        response = self.client.post(reverse('marketing:change_smart_object', args=('banner', )),
                                    {'smart_object_id': '56a9b37b3301e0706b549221',
                                     'title': 'New trendy jeans',
                                     'content_type': 'Categories',
                                     'display': 'Slide',
                                     'is_active': 'yes'}
                                    )
        self.assertEqual(response.status_code, 302)
        banner = Banner.objects.get(pk='56a9b37b3301e0706b549221')
        self.assertEqual(banner.title, 'New trendy jeans')
        self.assertEqual(banner.slug, 'new-trendy-jeans')  # Slug must be correctly set
    #
    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_ChangeSmartObject_with_new_smart_category(self):
        """
        Must create a new SmartCategory in the database. SmartObjectList must return HTTP 200 after the operation
        """
        self.client.login(username='member3', password='admin')
        self.client.post(reverse('marketing:change_smart_object', args=('smartcategory', )),
                         {'smart_object_id': '',
                          'title': 'Best Sellers',
                          'content_type': 'Categories',
                          'order_of_appearance': 3,
                          'description': '',
                          'is_active': 'yes'}
                         )
        smart_category = SmartCategory.objects.get(slug='best-sellers')  # Slug must be correctly set
        self.assertEqual(smart_category.title, 'Best sellers')
        response = self.client.get(reverse('marketing:smart_category_list'))
        self.assertEqual(response.status_code, 200)
        smart_categories = response.context['smart_category_list']
        self.assertEqual(smart_categories.count(), 3)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       IS_RETAILER=True, IS_PROVIDER=False)
    def test_ChangeSmartObject_with_existing_smart_category(self):
        """
        Changing an existing SmartCategory updates information with new one
        """
        self.client.login(username='member3', password='admin')
        response = self.client.post(reverse('marketing:change_smart_object', args=('smartcategory', )),
                                    {'smart_object_id': '56a9b37b3301e0706b549223',
                                     'title': 'New men arrivals',
                                     'content_type': 'Categories',
                                     'order_of_appearance': 3,
                                     'is_active': 'yes'})
        smart_category = SmartCategory.objects.get(pk='56a9b37b3301e0706b549223')
        self.assertEqual(smart_category.title, 'New men arrivals')
        self.assertEqual(smart_category.slug, 'new-men-arrivals')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_set_smart_object_content(self):
        """
        set_stock causes the stock to lower or raise by the number of units, all passed as GET parameters
        """
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('marketing:set_smart_object_content', args=('add', )),
                                   {'smart_object_id': '56a9b37b3301e0706b549223',
                                    'selection': '569228a9b37b3301e0706b51,569228a9b37b3301e0706b52,569228a9b37b3301e0706b53'})
        self.assertEqual(response.status_code, 302)
        smart_category = SmartCategory.objects.get(pk='56a9b37b3301e0706b549223')
        self.assertListEqual(smart_category.items_fk_list, [u'569228a9b37b3301e0706b51', u'569228a9b37b3301e0706b52', u'569228a9b37b3301e0706b53'])
        response = self.client.get(reverse('marketing:set_smart_object_content', args=('remove', )),
                                   {'smart_object_id': '56a9b37b3301e0706b549223',
                                    'selection': '569228a9b37b3301e0706b51,569228a9b37b3301e0706b53'})
        self.assertEqual(response.status_code, 200)
        smart_category = SmartCategory.objects.get(pk='56a9b37b3301e0706b549223')
        self.assertListEqual(smart_category.items_fk_list, [u'569228a9b37b3301e0706b52'])

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_delete_smart_object(self):
        """
        set_stock causes the stock to lower or raise by the number of units, all passed as GET parameters
        """
        self.client.login(username='member3', password='admin')
        response = self.client.get(reverse('marketing:delete_smart_object'),
                                   {'selection': '56a9b37b3301e0706b549223,56a9b37b3301e0706b549224'})
        response = json.loads(response.content)
        self.assertIsNotNone(response['message'])
