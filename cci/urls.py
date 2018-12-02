
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required, login_required

from ikwen_kakocase.cci.views import CCI, get_member_cumulated_coupon, save_cloud_cashin_payment, CCIList


urlpatterns = patterns(
    '',
    url(r'^$', login_required(CCI.as_view()), name='home'),
    url(r'^CCIList$', login_required(CCIList.as_view()), name='CCIList'),
    url(r'^get_user_coupon', get_member_cumulated_coupon, name='get_user_coupon'),
    url(r'^save_cci', save_cloud_cashin_payment, name='save_cci'),
)