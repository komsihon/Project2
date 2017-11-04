from urlparse import urlparse

from django.conf import settings
from django.template.defaultfilters import slugify
from ikwen.core.models import Service

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import get_service_instance, add_database
from ikwen_kakocase.kako.admin import ProductResource
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kakocase.models import ProductCategory


def import_products(filename):
    """
    Import products contained in an xls or xlsx spreadsheet file.
    :param filename: xls or xlsx file path
    :return: True if error occured, False otherwise
    """
    import tablib
    product_resource = ProductResource()
    dataset = tablib.Dataset()  # We need a dataset object
    if filename[-3:] == 'xls':
        dataset.xls = open(filename).read()
    else:
        dataset.xlsx = open(filename).read()
    result = product_resource.import_data(dataset, dry_run=False)
    return result.has_errors()


def create_category(name):
    """
    Adds a new :class:`ikwen_kakocase.models.ProductCategory` in the actual
    :class:`ikwen_kakocase.models.OperatorProfile` database.
    We start by searching the category with the given name in UMBRELLA database.
    If not found there, it is created and appended in the list of product_categories
    for the actual Operator business_category so that subsequently created platforms
    of the same business_category are cloud_setup with those categories from the beginning.
    """
    name = name.capitalize()
    slug = slugify(name)
    try:
        ProductCategory.objects.using(UMBRELLA).get(slug=slug)
    except ProductCategory.DoesNotExist:
        category = ProductCategory.objects.using(UMBRELLA)\
            .create(name=name, slug=slug, earnings_history=[0],
                    orders_count_history=[0], items_traded_history=[0], turnover_history=[0])
        business_category = get_service_instance(UMBRELLA).config.business_category
        if business_category:
            business_category.product_categories.append(category)
            business_category.save()
        category.save(using='default')
    else:
        try:
            category = ProductCategory.objects.using('default').get(slug=slug)
        except ProductCategory.DoesNotExist:
            category = ProductCategory.objects.using(UMBRELLA).get(slug=slug)
            category.items_count = 0
            category.save(using='default')
    return category


def mark_duplicates(product):
    queryset = Product.objects.filter(category=product.category, slug=product.slug,
                                      brand=product.brand).order_by('-stock', '-updated_on')
    if queryset.count() >= 1:
        queryset.update(is_duplicate=True)
        original = queryset[0]
        original.is_duplicate = False
        original.save()


def get_product_from_url(url):
    tokens = urlparse(url.strip())
    domain = tokens.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    path = tokens.path.strip('/').split('/')
    slug = path[-1]
    if getattr(settings, 'LOCAL_DEV', False):
        pslug = path[0]
        merchant = Service.objects.using(UMBRELLA).get(project_name_slug=pslug)
    else:
        merchant = Service.objects.using(UMBRELLA).get(domain=domain)
    merchant_db = merchant.database
    add_database(merchant_db)
    product = Product.objects.using(merchant_db).get(slug=slug, is_duplicate=False)
    return product, merchant
