from django.conf import settings
from django.core.cache import cache
from ikwen.core.context_processors import project_settings as ikwen_settings
from ikwen_kakocase.commarketing.models import SmartCategory, CATEGORIES, PRODUCTS

from ikwen_kakocase.kakocase.models import DeliveryOption, ProductCategory
from ikwen_kakocase.trade.models import Order
from ikwen_kakocase.sales.models import CustomerEmail


def project_settings(request):
    """
    Adds utility project url and ikwen base url context variable to the context.
    """
    kakocase_settings = ikwen_settings(request)
    kakocase_settings['settings'].update({
        'IS_PROVIDER': getattr(settings, 'IS_PROVIDER', False),
        'IS_RETAILER': getattr(settings, 'IS_RETAILER', False),
        'IS_DELIVERY_COMPANY': getattr(settings, 'IS_DELIVERY_COMPANY', False),
        'IS_BANK': getattr(settings, 'IS_BANK', False),
        'CHECKOUT_MIN': getattr(settings, 'CHECKOUT_MIN'),
        'TEMPLATE_WITH_HOME_TILES': getattr(settings, 'TEMPLATE_WITH_HOME_TILES', False),
    })
    return kakocase_settings


def categories(request):
    smart_categories_level2 = cache.get('smart_categories_level2')  # SmartCategory containing a list of sample_categories
    if not smart_categories_level2:
        cache.delete('smart_categories_level1')
        cache.delete('menu_categories')
        smart_categories_level2 = list(SmartCategory.objects
                                       .filter(content_type=CATEGORIES, is_active=True, appear_in_menu=True)
                                       .order_by('order_of_appearance', '-updated_on'))
        if not getattr(settings, 'DEBUG', False):
            cache.set('smart_categories_level2', smart_categories_level2)
    smart_categories_level1 = cache.get('smart_categories_level1')  # SmartCategory containing a list of products
    if not smart_categories_level1:
        smart_categories_level1 = list(SmartCategory.objects
                                       .filter(content_type=PRODUCTS, is_active=True, appear_in_menu=True)
                                       .order_by('order_of_appearance', '-updated_on'))
        if not getattr(settings, 'DEBUG', False):
            cache.set('smart_categories_level1', smart_categories_level1)
    menu_categories = cache.get('menu_categories')  # Some sample_categories for the main menu
    if not menu_categories:
        menu_categories = list(ProductCategory.objects.filter(is_active=True, appear_in_menu=True)
                               .order_by('order_of_appearance', '-updated_on'))
        if not getattr(settings, 'DEBUG', False):
            cache.set('menu_categories', menu_categories)

    quick_access_categories = cache.get('quick_access_categories')
    if not quick_access_categories:
        quick_access_categories = list(ProductCategory.objects
                                       .filter(items_count__gt=0, is_active=True, appear_in_menu=False)
                                       .order_by('order_of_appearance', '-updated_on'))
        if len(quick_access_categories) >= 5:
            quick_access_categories = quick_access_categories[-5:]
        if not getattr(settings, 'DEBUG', False):
            cache.set('quick_access_categories', quick_access_categories)
    member = request.user
    if request.META['HTTP_HOST'] == 'go.ikwen.com':
        template_cache_duration = 0
    else:
        template_cache_duration = 0 if member.is_authenticated() and member.is_staff else 300
    return {
        'smart_categories_level2': smart_categories_level2,
        'smart_categories_level1': smart_categories_level1,
        'menu_categories': menu_categories,
        'quick_access_categories': quick_access_categories,
        'template_cache_duration': template_cache_duration
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


def newsletter_settings(request):
    """
    Adds utility project constants to the context.
    """
    member = request.user
    is_in_newsletter = False
    if member.is_authenticated():
        try:
            CustomerEmail.objects.get(email=member.email)
        except CustomerEmail.DoesNotExist:
            is_in_newsletter = False
        else:
            is_in_newsletter = True
    return {
        'is_in_newsletter': is_in_newsletter,
    }
