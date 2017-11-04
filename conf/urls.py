from django.conf import settings
from django.conf.urls import patterns, include, url

from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from ikwen.accesscontrol.views import SignIn
from ikwen_kakocase.shopping.views import Home, FlatPageView

from ikwen_kakocase.trade.provider.views import ProviderDashboard
from ikwen_kakocase.trade.views import RetailerDashboard, LogicomDashboard

admin.autodiscover()

if getattr(settings, 'IS_RETAILER', False):
    Dashboard = RetailerDashboard
elif getattr(settings, 'IS_PROVIDER', False):
    Dashboard = ProviderDashboard
else:
    Dashboard = LogicomDashboard

if getattr(settings, 'IS_DELIVERY_COMPANY', False) or getattr(settings, 'IS_BANK', False):
    LandingPage = SignIn
else:
    LandingPage = Home

urlpatterns = patterns(
    '',
    url(r'^laakam/', include(admin.site.urls)),
    url(r'^kakocase/', include('ikwen_kakocase.kakocase.urls', namespace='kakocase')),
    url(r'^kako/', include('ikwen_kakocase.kako.urls', namespace='kako')),
    url(r'^trade/', include('ikwen_kakocase.trade.urls', namespace='trade')),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^marketing/', include('ikwen_kakocase.commarketing.urls', namespace='marketing')),
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^currencies/', include('currencies.urls')),

    url(r'^ikwen/dashboard/$', permission_required('trade.ik_view_dashboard')(Dashboard.as_view()), name='dashboard'),
    url(r'^ikwen/theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^ikwen/cashout/', include('ikwen.cashout.urls', namespace='cashout')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),

    # url(r'^$', ProviderDashboard.as_view(), name='admin_home'),
    url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
    url(r'^$', LandingPage.as_view(), name='home'),
    url(r'^', include('ikwen_kakocase.shopping.urls', namespace='shopping')),
)
