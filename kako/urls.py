
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required

from ikwen_kakocase.kako.provider.views import do_import_products_from_spreadsheet, product_batch_uploader, set_stock
from ikwen_kakocase.kako.views import ProviderList, ProviderProductList, do_import_products, \
    update_product_retail_price, \
    product_photo_uploader, ChangeProduct, ProductList, put_product_in_trash, \
    ProviderProductDetail, update_product_stock, delete_photo, CategoryList, ChangeCategory, delete_category, \
    toggle_category_attribute, load_product_from_url, save_product_from_url

urlpatterns = patterns(
    '',
    url(r'^providers/$', ProviderList.as_view(), name='provider_list'),
    url(r'^products/(?P<provider_id>[-\w]+)/$', ProviderProductList.as_view(), name='provider_product_list'),
    url(r'^detail/(?P<provider_id>[-\w]+)/(?P<product_id>[-\w]+)/$',
        permission_required('kako.ik_manage_product')(ProviderProductDetail.as_view()), name='provider_product_detail'),
    url(r'^do_import_products$', do_import_products, name='do_import_products'),
    url(r'^update_product_retail_price$', update_product_retail_price, name='update_product_retail_price'),
    url(r'^toggle_category_attribute$', toggle_category_attribute, name='toggle_category_attribute'),
    url(r'^update_product_stock$', update_product_stock, name='update_product_stock'),
    url(r'^product_photo_uploader$', product_photo_uploader, name='product_photo_uploader'),
    url(r'^delete_photo$', delete_photo, name='delete_photo'),
    url(r'^product/$', permission_required('kako.ik_manage_product')(ChangeProduct.as_view()), name='change_product'),
    url(r'^product/(?P<product_id>[-\w]+)/$', permission_required('kako.ik_manage_product')(ChangeProduct.as_view()),
        name='change_product'),
    url(r'^categories/$', permission_required('kako.ik_manage_product')(CategoryList.as_view()), name='category_list'),
    url(r'^category/$', permission_required('kako.ik_manage_product')(ChangeCategory.as_view()),
        name='change_category'),
    url(r'^category/(?P<category_id>[-\w]+)/$', permission_required('kako.ik_manage_product')(ChangeCategory.as_view()),
        name='change_category'),
    url(r'^delete_category$', delete_category, name='delete_category'),
    url(r'^products/$', permission_required('kako.ik_manage_product')(ProductList.as_view()), name='product_list'),

    url(r'^product_batch_uploader$', product_batch_uploader, name='product_batch_uploader'),
    url(r'^do_import_products_from_spreadsheet$', do_import_products_from_spreadsheet, name='do_import_products_from_spreadsheet'),
    url(r'^put_product_in_trash$', put_product_in_trash, name='put_product_in_trash'),
    url(r'^load_product_from_url$', load_product_from_url, name='load_product_from_url'),
    url(r'^save_product_from_url$', save_product_from_url, name='save_product_from_url'),

    url(r'^api/set_stock/(?P<api_signature>[-\w]+)/(?P<ref>[-\w]+)/(?P<units>\d+(.\d)*)/$', set_stock, name='set_stock')
)
