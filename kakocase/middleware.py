# -*- coding: utf-8 -*-
"""
This module groups utility middlewares that Tsunami uses.
"""

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect

from ikwen.core.utils import get_service_instance
from ikwen.core.urls import SIGN_IN, DO_SIGN_IN, LOGOUT


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
        next_url = reverse('welcome')
        member = request.user

        if rm.namespace == 'ikwen':
            if rm.url_name in [SIGN_IN, DO_SIGN_IN, LOGOUT]:
                return
        if rm.url_name != 'welcome':
            if not service.config.is_ecommerce_active:
                if not member.is_superuser:
                    return HttpResponseRedirect(next_url)
