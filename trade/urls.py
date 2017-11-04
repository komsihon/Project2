
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required

from ikwen_kakocase.trade.provider.views import get_package_details, PackageList, ProviderDashboard, \
    get_package_from_rcc, confirm_shipping, confirm_processing, notify_order_process
from ikwen_kakocase.trade.views import OrderList, require_order_rcc, get_order_details, LateDeliveryList, \
    BrokenProductList, RetailerDashboard, list_partner_companies, approve_or_reject, \
    PartnerList, DealList

urlpatterns = patterns(
    '',
    url(r'^orders/$', permission_required('trade.ik_manage_order')(OrderList.as_view()), name='order_list'),
    url(r'^orders/(?P<drivy>[-\w]+)/$', permission_required('trade.ik_manage_drivy')(OrderList.as_view()), name='order_list'),
    url(r'^retail/lateDeliveries/$', permission_required('trade.ik_manage_order')(LateDeliveryList.as_view()), name='late_delivery_list'),
    url(r'^retail/brokenProducts/$', permission_required('trade.ik_manage_order')(BrokenProductList.as_view()), name='broken_product_list'),
    url(r'^retail/require_order_rcc$', require_order_rcc, name='require_order_rcc'),
    url(r'^retail/get_order_details$', get_order_details, name='get_order_details'),
    url(r'^retail/dashboard/$', permission_required('trade.ik_view_dashboard')(RetailerDashboard.as_view()), name='retailer_dashboard'),

    url(r'^wholesale/packages/$', permission_required('trade.ik_manage_package')(PackageList.as_view()), name='package_list'),
    url(r'^wholesale/get_package_details$', get_package_details, name='get_package_details'),
    url(r'^wholesale/get_package_from_rcc$', get_package_from_rcc, name='get_package_from_rcc'),
    url(r'^wholesale/confirm_shipping$', confirm_shipping, name='confirm_shipping'),
    url(r'^wholesale/confirm_processing$', confirm_processing, name='confirm_processing'),
    url(r'^wholesale/dashboard/$', permission_required('trade.ik_view_dashboard')(ProviderDashboard.as_view()), name='provider_dashboard'),
    url(r'^partners/$', permission_required('accesscontrol.sudo')(PartnerList.as_view()), name='partner_list'),

    url(r'^approve_or_reject$', approve_or_reject, name='approve_or_reject'),
    url(r'^notify_order_process/(?P<order_id>[-\w]+)/(?P<status>[-\w]+)/(?P<bank_id>[-\w]+)/$', notify_order_process, name='notify_order_process'),
    url(r'^bank/deals/(?P<product_id>[-\w]+)/$', permission_required('trade.ik_manage_product')(DealList.as_view()), name='deal_list'),

    url(r'^list_partner_companies/$', list_partner_companies, name='list_partner_companies'),
)
