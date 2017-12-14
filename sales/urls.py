
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required

from ikwen_kakocase.sales.views import PromotionList, PromoCodeList, ChangePromotion, ChangePromoCode, find_promo_code\
    , delete_promo_object, toggle_object_attribute, save_customer_email, EmailList

urlpatterns = patterns(
    '',
    url(r'^promotions/$', PromotionList.as_view(), name='promotion_list'),
    url(r'^promocodes/$', PromoCodeList.as_view(), name='promo_code_list'),
    url(r'^change_promotion/$', ChangePromotion.as_view(), name='change_promotion'),
    url(r'^change_promotion/(?P<promotion_id>[-\w]+)/$', ChangePromotion.as_view(), name='change_promotion'),
    url(r'^change_promo_code/$', ChangePromoCode.as_view(), name='change_promo_code'),
    url(r'^change_promo_code/(?P<promo_code_id>[-\w]+)/$', ChangePromoCode.as_view(), name='change_promo_code'),
    url(r'^find_promo_code$', find_promo_code, name='find_promo_code'),
    url(r'^delete_promo_object$', delete_promo_object, name='delete_promo_object'),
    url(r'^toggle_object_attribute$', toggle_object_attribute, name='toggle_object_attribute'),
    url(r'^save_email$', save_customer_email, name='save_email'),
    url(r'^emails/$', EmailList.as_view(), name='email_list'),
)