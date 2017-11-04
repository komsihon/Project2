from django.conf import settings
from ikwen.core.context_processors import project_settings as ikwen_settings

from ikwen_kakocase.kakocase.models import DeliveryOption
from ikwen_kakocase.trade.models import Order


def project_settings(request):
    """
    Adds utility project url and ikwen base url context variable to the context.
    """
    kakocase_settings = ikwen_settings(request)['settings']
    kakocase_settings.update({
        'IS_PROVIDER': getattr(settings, 'IS_PROVIDER', False),
        'IS_RETAILER': getattr(settings, 'IS_RETAILER', False),
        'IS_DELIVERY_COMPANY': getattr(settings, 'IS_DELIVERY_COMPANY', False),
        'IS_BANK': getattr(settings, 'IS_BANK', False),
        'CHECKOUT_MIN': getattr(settings, 'CHECKOUT_MIN'),
        'TEMPLATE_WITH_HOME_TILES': getattr(settings, 'TEMPLATE_WITH_HOME_TILES', False),
    })
    return {
        'settings': kakocase_settings
    }


def constants(request):
    """
    Adds utility project constants to the context.
    """
    return {
        'constants': {
            'PICK_UP_IN_STORE': DeliveryOption.PICK_UP_IN_STORE,
            'HOME_DELIVERY': DeliveryOption.HOME_DELIVERY,
            'PENDING': Order.PENDING,
            'SHIPPED': Order.SHIPPED
        }
    }
