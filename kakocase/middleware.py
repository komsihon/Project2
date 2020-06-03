# -*- coding: utf-8 -*-
"""
This module groups utility middlewares that Tsunami uses.
"""

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect

from ikwen.core.utils import get_service_instance
from ikwen.core.urls import SIGN_IN, DO_SIGN_IN, LOGOUT, LOAD_EVENT
from ikwen_kakocase.shopping.utils import referee_registration_callback


class LandingPageMiddleware(object):
    """
    This middleware checks that the BusinessCategory implemented by this platform, the status of eCommerce activation
    and the privilege level of current user.

    Then it attributes the corresponding landing page template.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(settings, 'IS_IKWEN', False):
            return
        rm = request.resolver_match
        service = get_service_instance()
        next_url = reverse('guard_page')
        member = request.user

        if rm.namespace == 'ikwen':
            if rm.url_name in [SIGN_IN, DO_SIGN_IN, LOGOUT, LOAD_EVENT]:
                return
        if rm.url_name != 'guard_page':
            if not service.config.is_ecommerce_active:
                if not member.is_superuser:
                    return HttpResponseRedirect(next_url)


class BindDaraMiddleware(object):
    """
    Bind Dara to a user already logged in
    """
    def process_request(self, request):
        if request.user.is_authenticated():
            referee_registration_callback(request)
