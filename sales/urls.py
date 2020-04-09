
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required

from ikwen_kakocase.sales.views import PromotionList, PromoCodeList, ChangePromotion, ChangePromoCode, find_promo_code\
    , delete_promo_object, toggle_object_attribute, save_customer_email, EmailList

urlpatterns = patterns(
    '',
    url(r'^promotions/$', permission_required('commarketing.ik_manage_marketing')(PromotionList.as_view()), name='promotion_list'),
    url(r'^promocodes/$', permission_required('commarketing.ik_manage_marketing')(PromoCodeList.as_view()), name='promocode_list'),
    url(r'^changePromotion/$', permission_required('commarketing.ik_manage_marketing') (ChangePromotion.as_view()), name='change_promotion'),
    url(r'^changePromotion/(?P<promotion_id>[-\w]+)/$', permission_required('commarketing.ik_manage_marketing') (ChangePromotion.as_view()), name='change_promotion'),
    url(r'^changePromoCode/$', permission_required('commarketing.ik_manage_marketing')(ChangePromoCode.as_view()), name='change_promocode'),
    url(r'^changePromoCode/(?P<object_id>[-\w]+)/$', permission_required('commarketing.ik_manage_marketing')(ChangePromoCode.as_view()), name='change_promocode'),
    url(r'^find_promo_code$', find_promo_code, name='find_promo_code'),
    url(r'^delete_promo_object$', permission_required('commarketing.ik_manage_marketing')(delete_promo_object), name='delete_promo_object'),
    url(r'^toggle_object_attribute$', toggle_object_attribute, name='toggle_object_attribute'),
    url(r'^save_email$', save_customer_email, name='save_email'),
    url(r'^emails/$', EmailList.as_view(), name='email_list'),
)