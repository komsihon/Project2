
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required, login_required

from ikwen_kakocase.kakocase.views import list_available_companies, DeliveryOptionList, DeployCloud,\
    add_delivery_company_to_local_database, Go, SuccessfulDeployment


urlpatterns = patterns(
    '',
    url(r'^go$', login_required(Go.as_view()), name='go'),
    url(r'^successfull_deployment/(?P<service_id>[-\w]+)/$', login_required(SuccessfulDeployment.as_view()), name='successful_deployment'),
    url(r'^deployCloud/$', DeployCloud.as_view(), name='deploy_cloud'),
    url(r'^deliveryOptions/$', permission_required('accesscontrol.sudo')(DeliveryOptionList.as_view()), name='delivery_options'),
    url(r'^list_available_companies/$', list_available_companies, name='list_available_companies'),
    url(r'^add_delivery_company_to_local_database/$', add_delivery_company_to_local_database, name='add_delivery_company_to_local_database'),
)
