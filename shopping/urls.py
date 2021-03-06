
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required

from ikwen_kakocase.shopping.paypal.views import SetExpressCheckout, GetExpressCheckoutDetails, DoExpressCheckout, PayPalCancel
from ikwen_kakocase.shopping.views import ProductList, ProductDetail, confirm_checkout, Cart, \
    check_stock, check_stock_single, Home, Contact, load_checkout_summary, Checkout, review_product, test_return_url, \
    ChooseDeal, Cancel, load_countries, CouponList, OrderHistory, DisplayDeviceDimension

urlpatterns = patterns(
    '',
    url(r'^$', Home.as_view(), name='home'),
    url(r'^contact/$', Contact.as_view(), name='contact'),
    url(r'^cart/$', Cart.as_view(), name='cart'),
    url(r'^cart/(?P<order_id>[-\w]+)/$', Cart.as_view(), name='cart'),
    url(r'^checkout/$', Checkout.as_view(), name='checkout'),
    url(r'^check_stock$', check_stock, name='check_stock'),
    url(r'^check_stock_single$', check_stock_single, name='check_stock_single'),
    url(r'^load_checkout_summary$', load_checkout_summary, name='load_checkout_summary'),

    url(r'^paypal/setCheckout/', SetExpressCheckout.as_view(), name='paypal_set_checkout'),
    url(r'^paypal/getDetails/$', GetExpressCheckoutDetails.as_view(), name='paypal_get_details'),
    url(r'^paypal/doCheckout/$', DoExpressCheckout.as_view(), name='paypal_do_checkout'),
    url(r'^paypal/cancel/$', PayPalCancel.as_view(), name='paypal_cancel'),

    url(r'^test_return_url$', test_return_url, name='test_return_url'),
    url(r'^chooseDeal/$', login_required(ChooseDeal.as_view()), name='choose_deal'),
    url(r'^confirm_checkout$', confirm_checkout, name='confirm_checkout'),
    url(r'^confirm_checkout/(?P<tx_id>[-\w]+)/(?P<signature>[-\w]+)$', confirm_checkout, name='confirm_checkout'),
    url(r'^cancel$', Cancel.as_view(), name='cancel'),

    url(r'^coupons$', login_required(CouponList.as_view()), name='coupon_list'),

    url(r'^ordersHistory$', login_required(OrderHistory.as_view()), name='orders_history'),
    url(r'^deviceDimensions/$', DisplayDeviceDimension.as_view(), name='display_device_dimension'),


    url(r'^review_product/(?P<product_id>[-\w]+)/$', review_product, name='review_product'),
    url(r'^content/(?P<banner_slug>[-\w]+)/$', ProductList.as_view(), name='banner_product_list'),
    url(r'^products/(?P<smart_category_slug>[-\w]+)/$', ProductList.as_view(), name='smart_object_detail'),
    url(r'^search/$', ProductList.as_view(), name='search'),
    url(r'^load_countries$', load_countries, name='load_countries'),
    url(r'^(?P<category_slug>[-\w]+)/$', ProductList.as_view(), name='product_list'),
    url(r'^(?P<category_slug>[-\w]+)/(?P<product_slug>[-\w]+)$', ProductDetail.as_view(), name='product_detail'),


)
