import json
from datetime import timedelta, time
from time import sleep

from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest
from ikwen_kakocase.sales.models import Promotion, PromoCode
from ikwen_kakocase.sales.views import apply_promotion_discount

from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kako.tests_views import wipe_test_data
from ikwen_kakocase.trade.models import Order


class SalesViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    This, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['categories.yaml', 'kc_products.yaml', 'kc_promotions.yaml', 'kc_promo_codes.yaml',
                'kc_setup_data.yaml', 'order', 'delivery_option.yaml', 'kc_operators_configs.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', 'umbrella')

    def tearDown(self):
        wipe_test_data()
        wipe_test_data('umbrella')

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101')
    def test_ProductDetail_with_active_promotion(self):
        """
        ProductDetail view must load the correct product in the page
        """

        response = self.client.get(reverse('shopping:product_detail', args=('food', 'coca-cola')))
        self.assertEqual(response.status_code, 200)
        product = response.context['product']
        self.assertEqual(product.name, 'Coca-Cola')
        self.assertEqual(product.on_sale, True)
        self.assertEqual(product.previous_price, 450)
        self.assertEqual(product.retail_price, 405)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_apply_promotion_discount_full(self):
        """
            here we test the complete operation of the promotion management function;
            here for a given promotion, the test will determine if in the end, the promotion will normally apply
            where it is necessary and with the expected values

        """
        # promoted_category = ProductCategory.objects.get(pk='569228a9b37b3301e0706b52')
        # product_in_category = Product.objects.filter(category=promoted_category)
        all_site_product = Product.objects.all()
        specific_promoted_item, item_in_promoted_category, item_in_site = {}, {}, {}
        promotions = Promotion.objects.all()
        for promotion in promotions:
            promotion.is_active = True
            promotion.save()

        final_product_list = apply_promotion_discount(list(all_site_product))
        for product in final_product_list:
            if product.id == '55d1fa8feb60008099bd4152':
                specific_promoted_item = product
            if product.id == '55d1fa8feb60008099bd4153':
                item_in_promoted_category = product
            if product.id == '55d1fa8feb60008099bd4151':
                item_in_site = product

        self.assertEqual(specific_promoted_item.name, 'Coca-Cola')
        self.assertEqual(specific_promoted_item.on_sale, True)
        self.assertEqual(specific_promoted_item.previous_price, 450)
        self.assertEqual(specific_promoted_item.retail_price, 405)

        self.assertEqual(item_in_promoted_category.name, 'Castel')
        self.assertEqual(item_in_promoted_category.on_sale, True)
        self.assertEqual(item_in_promoted_category.previous_price, 700)
        self.assertEqual(item_in_promoted_category.retail_price, 665)

        self.assertEqual(item_in_site.name, 'Samsung Galaxy S7')
        self.assertEqual(item_in_site.on_sale, True)
        self.assertEqual(item_in_site.previous_price, 480000)
        self.assertEqual(item_in_site.retail_price, 384000)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_apply_promotion_discount_on_category_only(self):
        """
            here we test the complete operation of the promotion management function;
            here for a given promotion, the test will determine if at the end, the promotion will normally be apply
            on the category "Food" products only

        """
        all_site_product = Product.objects.all()
        specific_promoted_item, item_in_promoted_category, item_in_site = {}, {}, {}
        promotions = Promotion.objects.all()
        for promotion in promotions:
            promotion.is_active = False
            if promotion.category:
                promotion.is_active = True
            promotion.save()

        final_product_list = apply_promotion_discount(list(all_site_product))
        for product in final_product_list:
            if product.id == '55d1fa8feb60008099bd4152':
                specific_promoted_item = product
            if product.id == '55d1fa8feb60008099bd4153':
                item_in_promoted_category = product
            if product.id == '55d1fa8feb60008099bd4151':
                item_in_site = product

        self.assertEqual(specific_promoted_item.name, 'Coca-Cola')
        self.assertEqual(specific_promoted_item.on_sale, False)
        self.assertEqual(specific_promoted_item.retail_price, 450)

        self.assertEqual(item_in_promoted_category.name, 'Castel')
        self.assertEqual(item_in_promoted_category.on_sale, True)
        self.assertEqual(item_in_promoted_category.previous_price, 700)
        self.assertEqual(item_in_promoted_category.retail_price, 665)

        self.assertEqual(item_in_site.name, 'Samsung Galaxy S7')
        self.assertEqual(item_in_site.on_sale, False)
        self.assertEqual(item_in_site.retail_price, 480000)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103')
    def test_load_checkout_summary_with_promocode(self):
        response = self.client.get(reverse('sales:find_promo_code'), data={'code': 'partner15'})

        response = self.client.get(reverse('shopping:load_checkout_summary'),
                                    data={'items_count':2, 'items_cost':482700, 'delivery_option_id': '55d1feb9b37b301e070604d3'})


        self.assertEqual(response.context['items_cost'],410295)
        self.assertEqual(response.context['items_gross_cost'],482700)


    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b103',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/shopping/',
                       UNIT_TESTING=True)  # TESTING=True causes OperatorProfile.get_rel() to return the same object
    def test_confirm_checkout_with_authenticated_user(self):
        coupon = PromoCode.objects.get(pk='56b37b3379b531e011456651')

        self.client.session['promo_code'] = coupon.to_dict()
        self.client.session['promo_code_id'] = '56b37b3379b531e011456651'
        self.client.session['promo_rate'] = coupon.rate

        self.client.login(username='member4', password='admin')
        response = self.client.post(reverse('shopping:paypal_set_checkout'),
                                    {'name': 'Simo Messina', 'phone': '655003321', 'email': 'member4@ikwen.com',
                                     'country_iso2': 'CM', 'city': 'Yaounde', 'address': 'Odza',
                                     'entries': '55d1fa8feb60008099bd4151:1,55d1fa8feb60008099bd4153:6',
                                     'delivery_option_id': '55d1feb9b37b301e070604d3',
                                     'success_url': reverse('shopping:checkout')})
        json_resp = json.loads(response.content)
        response = self.client.post(reverse('shopping:paypal_do_checkout'),
                                    data={'order_id': json_resp['order_id']})

        order = Order.objects.all()[0]
        self.assertIsNone(order.aotc)
        self.assertIsNotNone(order.member)
