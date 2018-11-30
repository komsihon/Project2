# -*- coding: utf-8 -*-
from datetime import timedelta
from urlparse import urlparse

from django.conf import settings
from django.template.defaultfilters import slugify
from django.utils.translation import gettext as _

from ikwen.core.models import Service
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.conf import settings as ikwen_settings
from ikwen.core.utils import add_database, get_mail_content
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
    slug = slugify(name)
    try:
        category = ProductCategory.objects.get(slug=slug)
    except ProductCategory.DoesNotExist:
        category = ProductCategory.objects.create(name=name, slug=slug, earnings_history=[0],
                                                  orders_count_history=[0], items_traded_history=[0], turnover_history=[0])
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


def render_products_added(target, product, revival):
    service = revival.service
    db = service.database
    if target.member.date_joined > product.created_on or target.revival_count >= 1:
        # Do not revive customers who joined after product creation
        return None, None
    limit = product.created_on + timedelta(days=3)
    product_list = Product.objects.using(db).filter(created_on__range=(product.created_on, limit))
    subject = _("You're going to love these new products! Check them out" % product.name)
    template_name = 'kako/mails/products_added.html'
    media_url = ikwen_settings.CLUSTER_MEDIA_URL + service.project_name_slug
    extra_context = {
        'member_name': target.member.first_name,
        'product_list': product_list,
        'media_url': media_url
    }
    html_content = get_mail_content(subject, template_name=template_name, service=service, extra_context=extra_context)
    return subject, html_content


def render_product_on_sale(target, product, revival):
    service = revival.service
    if target.member.date_joined > product.created_on or target.revival_count >= 1:
        # Do not revive customers who joined after product creation
        return None, None
    subject = _("Wow ! Seize this opportunity on %s" % product.name)
    template_name = 'kako/mails/product_on_sale.html'
    media_url = ikwen_settings.CLUSTER_MEDIA_URL + service.project_name_slug
    extra_context = {
        'member_name': target.member.first_name,
        'product': product.project_name,
        'media_url': media_url
    }
    html_content = get_mail_content(subject, template_name=template_name, service=service, extra_context=extra_context)
    return subject, html_content
