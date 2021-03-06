# -*- coding: utf-8 -*-
import json
import logging
import random
import string
from datetime import datetime, timedelta
from threading import Thread

import requests
from currencies.models import Currency
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, render
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template
from django.utils.translation import gettext as _, activate
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import SUDO, Member, COMMUNITY
from ikwen.billing.models import PaymentMean, BankAccount, MoMoTransaction
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen.core.models import Country, ConsoleEvent, ConsoleEventType, Service
from ikwen.core.utils import get_service_instance, add_event, as_matrix, add_database
from ikwen.core.views import HybridListView
from ikwen.core.templatetags.url_utils import strip_base_alias
from ikwen.flatpages.models import FlatPage
from ikwen.rewarding.models import Reward
from ikwen.rewarding.utils import reward_member
from ikwen.revival.models import ProfileTag, MemberProfile

from ikwen_kakocase.commarketing.models import SmartCategory, CATEGORIES, PRODUCTS, Banner, SLIDE, TILES, POPUP, \
    FULL_WIDTH_SECTION, \
    FULL_SCREEN_POPUP
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kako.utils import mark_duplicates
from ikwen_kakocase.kakocase.models import OperatorProfile, ProductCategory, SOLD_OUT_EVENT, \
    INSUFFICIENT_STOCK_EVENT, LOW_STOCK_EVENT, CATEGORIES_PREVIEWS_PER_ROW, DeliveryOption
from ikwen_kakocase.sales.models import PromoCode
from ikwen_kakocase.sales.views import apply_promotion_discount
from ikwen_kakocase.shopping.models import AnonymousBuyer, Customer, Review, DeliveryAddress
from ikwen_kakocase.shopping.utils import parse_order_info, send_order_confirmation_email, \
    after_order_confirmation, send_order_confirmation_sms
from ikwen_kakocase.trade.models import Order, BrokenProduct, LateDelivery, Deal
from ikwen_kakocase.trade.utils import generate_tx_code
from permission_backend_nonrel.models import UserPermissionList

logger = logging.getLogger('ikwen')

_OPTIMUM = 'optimum'
COZY = "Cozy"
COMPACT = "Compact"
COMFORTABLE = "Comfortable"


class TemplateSelector(object):

    def get_template_names(self):
        config = get_service_instance().config
        try:
            if config.theme.template.slug == _OPTIMUM:
                return [self.optimum_template_name]
        except:
            pass
        return [self.template_name]


def add_member_auto_profiletag(request, **kwargs):
    """
    Adds an auto profile to member based on the category
    of product he is visiting.
    """
    if request.user.is_authenticated():
        tag_slug = None
        if kwargs.get('category_slug'):
            tag_slug = kwargs.get('category_slug')
            name = ProductCategory.objects.get(slug=tag_slug).name
        elif kwargs.get('smart_category_slug'):
            tag_slug = kwargs.get('smart_category_slug')
            try:
                name = SmartCategory.objects.get(slug=tag_slug).title
            except:
                name = Banner.objects.get(slug=tag_slug).title
        if tag_slug:
            try:
                tag, update = ProfileTag.objects.get_or_create(name=name, slug='__' + tag_slug, is_auto=True)
                member_profile, update = MemberProfile.objects.get_or_create(member=request.user)
                if tag.id not in member_profile.tag_fk_list:
                    member_profile.tag_fk_list.append(tag.id)
                    member_profile.save()
            except:
                pass


class Home(TemplateSelector, TemplateView):
    template_name = 'shopping/home.html'
    optimum_template_name = 'shopping/optimum/home.html'

    def _get_row_len(self):
        config = get_service_instance().config
        if config.theme and config.theme.display == COMFORTABLE:
            return 2
        elif config.theme and config.theme.display == COZY:
            return 3
        else:
            return getattr(settings, 'PRODUCTS_PREVIEWS_PER_ROW', 4)

    def get_context_data(self, **kwargs):
        context = super(Home, self).get_context_data(**kwargs)

        preview_sections_count = getattr(settings, 'PREVIEW_SECTIONS_COUNT', 7)
        preview_smart_categories = list(SmartCategory.objects
                                        .filter(items_count__gt=0, is_active=True, show_on_home=True)
                                        .order_by('order_of_appearance', 'title', '-updated_on')[:preview_sections_count])
        additional = preview_sections_count - len(preview_smart_categories)
        preview_categories = list(ProductCategory.objects
                                  .filter(items_count__gt=0, is_active=True, show_on_home=True)
                                  .order_by('order_of_appearance', 'name', '-updated_on')[:additional])
        to_be_removed = []
        for item in preview_categories:
            products = item.get_visible_items()
            products_list = apply_promotion_discount(list(products))
            item.as_matrix = as_matrix(products_list, self._get_row_len())
            if not item.as_matrix:
                to_be_removed.append(item)
        for item in to_be_removed:
            preview_categories.remove(item)
        to_be_removed = []
        for item in preview_smart_categories:
            if item.content_type == CATEGORIES:
                item.as_matrix = as_matrix(item.get_category_queryset(), CATEGORIES_PREVIEWS_PER_ROW)
            else:
                products = item.get_product_queryset()
                products_list = []
                if products:
                    products_list = apply_promotion_discount(list(products))
                item.as_matrix = as_matrix(products_list, self._get_row_len())
            if not item.as_matrix:
                to_be_removed.append(item)
        for item in to_be_removed:
            preview_smart_categories.remove(item)

        context['preview_categories'] = preview_categories
        context['preview_smart_categories'] = preview_smart_categories
        context['slideshow'] = Banner.objects.filter(display=SLIDE, is_active=True).order_by('order_of_appearance', '-id')
        context['home_tiles'] = Banner.objects.filter(display=TILES, is_active=True).order_by('order_of_appearance')
        context['popups'] = Banner.objects.filter(display=POPUP, is_active=True)
        fw_section_qs = Banner.objects.filter(display=FULL_WIDTH_SECTION, is_active=True).order_by('-id')
        context['fw_section'] = fw_section_qs[0] if fw_section_qs.count() > 0 else None
        fw_popup_qs = Banner.objects.filter(display=FULL_SCREEN_POPUP, is_active=True).order_by('-id')
        context['fs_popups'] = fw_popup_qs[0] if fw_popup_qs.count() > 0 else None
        return context

    def get(self, request, *args, **kwargs):
        service = get_service_instance()
        cookie_name = "%s_first_time" % service.project_name_slug

        if request.user.is_anonymous() and not request.COOKIES.get(cookie_name):
            return HttpResponseRedirect(reverse('first_time'))

        return super(Home, self).get(request, *args, **kwargs)


class SmartObjectDetail(TemplateSelector, TemplateView):
    template_name = 'shopping/product_list.html'
    optimum_template_name = 'shopping/optimum/product_list.html'

    def get(self, request, *args, **kwargs):
        context = super(SmartObjectDetail, self).get_context_data(**kwargs)
        slug = kwargs['slug']
        try:
            smart_object = Banner.objects.filter(slug=slug).order_by('-updated_on')[0]
        except:
            smart_object = SmartCategory.objects.filter(slug=slug).order_by('-updated_on')[0]
        context['smart_object'] = smart_object
        return render(request, self.get_template_names, context)


class ProductList(TemplateSelector, HybridListView):
    template_name = 'shopping/product_list.html'
    optimum_template_name = 'shopping/optimum/product_list.html'

    search_field = 'tags'
    ordering = ('id', )
    queryset = Product.objects.select_related('provider').exclude(Q(retail_price__isnull=True) & Q(retail_price=0))\
        .filter(visible=True, is_duplicate=False)

    context_object_name = 'product_list'

    def _get_row_len(self):
        config = get_service_instance().config
        if config.theme and config.theme.display == COMPACT:
            return 3
        return 2

    def get(self, request, *args, **kwargs):
        # Add this category to Member Profile
        add_member_auto_profiletag(request, **kwargs)
        q = request.GET.get('q')
        if q:
            try:
                order = list(Order.objects.filter(aotc=q.lower()))[-1]
                cart_url = reverse('shopping:cart', args=(order.id, ))
                return HttpResponseRedirect(cart_url)
            except IndexError:
                pass
        return super(ProductList, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProductList, self).get_context_data(**kwargs)
        all_smart_categories_level2 = SmartCategory.objects.filter(content_type=CATEGORIES, appear_in_menu=False,
                                                                   is_active=True,
                                                                   items_count__gt=0).order_by('order_of_appearance')
        smart_categories_level1 = list(SmartCategory.objects.filter(
            content_type=PRODUCTS, appear_in_menu=False, is_active=True,
            items_count__gt=0).order_by('order_of_appearance'))
        brands = list(set([p.brand for p in Product.objects.filter(visible=True, is_duplicate=False)
                           if p.brand]))

        smart_categories_level2 = []
        for sc in all_smart_categories_level2:
            show_this = False
            for category in sc.get_category_queryset():
                if category.items_count > 0:
                    show_this = True
                    break
            if show_this:
                smart_categories_level2.append(sc)
        exclude_list_pks = []
        for smart_category in smart_categories_level2:
            exclude_list_pks.extend(list(set([c.pk for c in smart_category.get_category_queryset()])))
        categories = list(ProductCategory.objects.filter(appear_in_menu=False, items_count__gt=0)\
            .exclude(pk__in=exclude_list_pks).order_by('name'))
        top_products = Product.objects.exclude(Q(retail_price__isnull=True) & Q(retail_price=0))\
            .filter(visible=True, is_duplicate=False).order_by('-total_units_sold')
        top_products = apply_promotion_discount(list(top_products))

        page_size = 9 if self.request.user_agent.is_mobile else 15
        q = self.request.GET.get('q')
        category_slug = self.kwargs.get('category_slug')
        smart_category_slug = self.kwargs.get('smart_category_slug')
        banner_slug = self.kwargs.get('banner_slug')
        base_queryset = self.get_queryset()
        if q:
            product_queryset = base_queryset.filter(tags__icontains=q).order_by('name')
            page_title = q
            context['content_type'] = PRODUCTS
        elif category_slug:
            category = get_object_or_404(ProductCategory, slug=category_slug)
            product_queryset = base_queryset.filter(category=category).order_by('order_of_appearance', '-updated_on')
            page_title = category.name
            context['category'] = category
            context['obj_group'] = category
            context['object_id'] = category.id
            context['content_type'] = PRODUCTS
        else:
            if banner_slug:
                smart_object = get_object_or_404(Banner, slug=banner_slug)
            else:
                smart_object = get_object_or_404(SmartCategory, slug=smart_category_slug)
            context['smart_object'] = smart_object
            context['obj_group'] = smart_object
            if smart_object.content_type == CATEGORIES:
                context['category_list_as_matrix'] = as_matrix(list(smart_object.get_category_queryset()), 2)
                product_queryset = None
            else:
                base_queryset = smart_object.get_product_queryset()
                product_queryset = base_queryset

            context['object_id'] = smart_object.id
            context['content_type'] = smart_object.content_type
            page_title = smart_object.title

        context['filter_smart_categories_level2'] = smart_categories_level2
        context['filter_smart_categories_level1'] = smart_categories_level1
        context['category_list'] = categories
        context['show_categories_filter'] = len(smart_categories_level2) + len(smart_categories_level1) + len(categories)
        context['page_title'] = page_title
        context['brands'] = sorted(brands)
        context['top_products'] = top_products[:5]

        if product_queryset:
            product_queryset_lst = apply_promotion_discount(list(product_queryset))
            paginator = Paginator(product_queryset_lst, page_size)
            products_page = paginator.page(1)
            context['products_page'] = products_page
            context['product_list_as_matrix'] = as_matrix(products_page.object_list, self._get_row_len())
            try:
                sorted_by_price = list(base_queryset.order_by('retail_price'))
                context['min_price'] = sorted_by_price[0].retail_price
                context['max_price'] = sorted_by_price[-1].retail_price
            except:
                pass
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'html_results':
            context['content_type'] = PRODUCTS
            product_queryset = self.get_queryset()
            if self.kwargs.get('category_slug'):
                slug = self.kwargs.get('category_slug')
                category = ProductCategory.objects.get(slug=slug)
                product_queryset = product_queryset.filter(category=category)
            elif self.kwargs.get('smart_category_slug'):
                slug = self.kwargs.get('smart_category_slug')
                try:
                    smart_object = Banner.objects.get(slug=slug)
                except Banner.DoesNotExist:
                    smart_object = SmartCategory.objects.get(slug=slug)
                product_queryset = smart_object.get_product_queryset()
            try:
                min_price = int(self.request.GET.get('min_price'))
                max_price = int(self.request.GET.get('max_price'))
                product_queryset = product_queryset.filter(Q(retail_price__gte=min_price) & Q(retail_price__lte=max_price))
            except:
                pass

            page_size = 9 if self.request.user_agent.is_mobile else 15
            order_by = str(self.request.GET['order_by'])
            product_queryset = self.get_search_results(product_queryset, max_chars=4)
            product_queryset = product_queryset.order_by(order_by)

            product_queryset = apply_promotion_discount(list(product_queryset))
            paginator = Paginator(product_queryset, page_size)
            page = self.request.GET.get('page')
            try:
                products_page = paginator.page(page)
                context['product_list_as_matrix'] = as_matrix(products_page.object_list, self._get_row_len())
            except PageNotAnInteger:
                products_page = paginator.page(1)
                context['product_list_as_matrix'] = as_matrix(products_page.object_list, self._get_row_len())
            except EmptyPage:
                products_page = paginator.page(paginator.num_pages)
                context['product_list_as_matrix'] = as_matrix(products_page.object_list, self._get_row_len())
            context['products_page'] = products_page
            return render(self.request, 'shopping/snippets/product_list_results.html', context)
        else:
            return super(ProductList, self).render_to_response(context, **response_kwargs)


class ProductDetail(TemplateSelector, TemplateView):
    template_name = 'shopping/product_detail.html'
    optimum_template_name = 'shopping/optimum/product_detail.html'

    def get_context_data(self, **kwargs):
        context = super(ProductDetail, self).get_context_data(**kwargs)
        add_member_auto_profiletag(self.request, **kwargs)
        category_slug = kwargs['category_slug']
        product_slug = kwargs['product_slug']
        category = ProductCategory.objects.get(slug=category_slug)
        try:
            current_product = Product.objects.select_related('provider').filter(category=category, slug=product_slug)[0]
        except IndexError:
            raise Http404('No product matches the given query.')
        product = apply_promotion_discount([current_product])[0]
        category = product.category
        context['product'] = product
        product_uri = reverse('shopping:product_detail', args=(category.slug, product.slug))
        product_uri = product_uri.replace(getattr(settings, 'WSGI_SCRIPT_ALIAS', ''), '')
        context['product_uri'] = product_uri
        base_queryset = Product.objects.select_related('provider')\
            .exclude(pk=product.id).filter(visible=True, is_duplicate=False)
        suggestions = base_queryset.filter(category=category, brand=product.brand).order_by('-updated_on')[:6]
        if suggestions.count() < 6:
            additional = 6 - suggestions.count()
            exclude_list = [p.pk for p in suggestions]
            suggestions = list(suggestions)
            suggestions.extend(list(base_queryset.exclude(pk__in=exclude_list).filter(category=product.category)
                                    .order_by('-updated_on')[:additional]))
        suggestions = apply_promotion_discount(list(suggestions))
        context['suggestion_list'] = suggestions
        context['review_count'] = Review.objects.filter(product=product).count()
        context['review_list'] = Review.objects.filter(product=product).order_by('-id')[:50]
        service = get_service_instance()
        banks = []
        for p in OperatorProfile.objects.filter(business_type=OperatorProfile.BANK):
            try:
                banks.append(p.service)
            except:
                continue
        deal_list = []
        for bank in banks:
            try:
                bank_db = bank.database
                add_database(bank_db)
                deal = Deal.objects.using(bank_db)\
                    .filter(product_slug=product.slug, merchant=service, bank=bank).order_by('term_cost')[0]
                deal_list.append(deal)
            except:
                continue
        context['deal_list'] = deal_list
        member = self.request.user
        from daraja.models import Dara
        if member.is_authenticated():
            try:
                Review.objects.get(member=member, product=product)
            except Review.DoesNotExist:
                context['can_review'] = True
            try:
                Dara.objects.get(member=member)
                context['is_dara'] = True
            except Dara.DoesNotExist:
                pass
        return context


class Cart(TemplateSelector, TemplateView):
    template_name = 'shopping/cart.html'
    optimum_template_name = 'shopping/optimum/cart.html'

    def get_context_data(self, **kwargs):
        context = super(Cart, self).get_context_data(**kwargs)
        try:
            max_delivery_packing_cost = DeliveryOption.objects.filter(is_active=True).order_by('-packing_cost')[0].packing_cost
        except IndexError:
            max_delivery_packing_cost = 0
        context['max_delivery_packing_cost'] = max_delivery_packing_cost
        order_id = kwargs.get('order_id')
        if order_id:
            order = get_object_or_404(Order, pk=order_id)
            if order.status != Order.PENDING_FOR_PAYMENT:
                if not order.currency:
                    order.currency = Currency.active.base()
                diff = datetime.now() - order.created_on
                if diff.total_seconds() >= 3600:
                    order.is_more_than_one_hour_old = True
                context['order'] = order

            self.request.session.modified = True
            try:
                del self.request.session['promo_code']
            except:
                pass
        return context


class Checkout(TemplateSelector, TemplateView):
    template_name = 'shopping/checkout.html'
    optimum_template_name = 'shopping/optimum/checkout.html'

    def get(self, request, *args, **kwargs):
        action = self.request.GET.get('action')
        if action == 'delete':
            return self.delete_address(request)
        return super(Checkout, self).get(request, *args, **kwargs)

    def delete_address(self, request, item_arg=None):
        member = request.user
        item = request.GET.get('item')
        if not item:
            item = item_arg
        if member.customer:
            customer = member.customer
            customer.delivery_addresses.pop(int(item))
            customer.save()
            # messages.success(self.request, 'Address deleted')
            return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
        return HttpResponseRedirect(reverse('shopping:orders_history'))

    def get_context_data(self, **kwargs):
        context = super(Checkout, self).get_context_data(**kwargs)
        context['countries'] = Country.objects.all()
        delivery_option_id = self.request.GET.get('delivery_option_id')
        delivery_option = get_object_or_404(DeliveryOption, pk=delivery_option_id)
        member = self.request.user
        previous_addresses = []
        if member.is_authenticated():
            try:
                previous_addresses = member.customer.delivery_addresses
            except Customer.DoesNotExist:
                pass
        else:
            anonymous_buyer_id = self.request.GET.get('anonymous_buyer_id')
            if anonymous_buyer_id:
                try:
                    anonymous_buyer = AnonymousBuyer.objects.get(pk=anonymous_buyer_id)
                    previous_addresses = anonymous_buyer.delivery_addresses
                except AnonymousBuyer.DoesNotExist:
                    pass
        address_choices = []
        if delivery_option.type == DeliveryOption.PICK_UP_IN_STORE:
            context['delivery_option'] = delivery_option
            context['pick_up_in_store'] = True
            for i in range(len(previous_addresses)):
                obj = previous_addresses[i]
                if not obj.country:
                    obj.index = i
                    address_choices.append(obj)
        else:
            for i in range(len(previous_addresses)):
                obj = previous_addresses[i]
                if obj.country:
                    obj.index = i
                    address_choices.append(obj)
        context['previous_addresses'] = list(reversed(address_choices))
        return context


def load_checkout_summary(request, *args, **kwargs):
    items_count = request.GET['items_count']
    items_cost = float(request.GET['items_cost'])
    packing_cost = float(request.GET['packing_cost'])
    delivery_option_id = request.GET.get('delivery_option_id')
    items_gross_cost = items_cost
    delivery_option = None
    promo_code = None
    if request.session.get('promo_code'):
        promo_id = request.session.get('promo_code')['id']
        try:
            now = datetime.now()
            promo_code = PromoCode.objects.get(pk=promo_id, start_on__lte=now, end_on__gt=now, is_active=True)
        except PromoCode.DoesNotExist:
            pass
        else:
            items_cost = items_gross_cost * (100 - promo_code.rate) / 100

    total_cost = items_cost
    if request.GET.get('buy_packing'):
        total_cost += packing_cost
    if delivery_option_id:
        delivery_option = DeliveryOption.objects.get(pk=delivery_option_id)
        total_cost += delivery_option.cost

    available_options = list(DeliveryOption.objects\
                             .filter(checkout_min__lte=items_gross_cost, is_active=True).order_by('cost'))
    delivery_options = set()
    for i in available_options:
        for j in available_options:
            if i.description == j.description:
                if i.cost < j.cost:
                    delivery_options.add(i)
                else:
                    delivery_options.add(j)
    delivery_options = list(delivery_options)
    delivery_options.sort(lambda x, y: 1 if x.cost > y.cost else -1)

    main_payment_mean = PaymentMean.objects.get(is_main=True)
    payment_mean_list = PaymentMean.objects.filter(is_main=False, is_active=True)
    context = {'items_cost': items_cost, 'items_count': items_count, 'items_gross_cost': items_gross_cost, 'delivery_option': delivery_option,
               'total_cost': total_cost, 'config': get_service_instance().config, 'delivery_options': delivery_options,
               'main_payment_mean': main_payment_mean, 'payment_mean_list': payment_mean_list, 'promo_code': promo_code}
    return render(request, 'shopping/snippets/checkout_summary.html', context)


class Contact(TemplateSelector, TemplateView):
    template_name = 'shopping/contact.html'


class FlatPageView(TemplateSelector, TemplateView):
    template_name = 'flatpages/flatpage_view.html'
    optimum_template_name = 'flatpages/optimum/flatpage_view.html'

    def get(self, request, *args, **kwargs):
        url = kwargs['url']
        flatpage = get_object_or_404(FlatPage, url=url)
        context = self.get_context_data(**kwargs)
        context['page'] = flatpage
        template_names = flatpage.template_name if flatpage.template_name else self.get_template_names()
        return render(request, template_names, context)


@cache_page(60 * 10)
def get_order_from_aotc(request, aotc, *args, **kwargs):
    try:
        order = Order.objects.get(aotc=aotc)
    except Order.DoesNotExist:
        response = {'error': _("No order found with this AOTC")}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    return HttpResponse(
        json.dumps(order.to_dict()),
        'content-type: text/json'
    )


@login_required
def notify_issue(request, order_id, issue_type, *args, **kwargs):
    details = request.GET.get('details', '')
    retailer_called = request.GET.get('retailer_called', False)
    order = get_object_or_404(Order, pk=order_id)
    if issue_type == 'LateDelivery':
        LateDelivery.objects.create(order=order, details=details, retailer_called=retailer_called)
    else:
        BrokenProduct.objects.create(order=order, details=details)
    return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')


def check_stock_single(request, *args, **kwargs):
    """
    Checks stock of a single product
    """
    product_id = request.GET['product_id']
    qty = int(request.GET['qty'])
    product = Product.objects.get(pk=product_id)
    service = product.provider
    member = service.member
    if product.stock <= qty:
        try:
            cet = ConsoleEventType.objects.using('umbrella').get(codename=LOW_STOCK_EVENT)
            yesterday = datetime.now() - timedelta(days=1)
            ConsoleEvent.objects.using('umbrella').get(event_type=cet, member=member,
                                                       object_id=product.id, created_on__gte=yesterday)
        except ConsoleEvent.DoesNotExist:
            add_event(service, LOW_STOCK_EVENT, member=member, object_id=product.id)
    if product.stock < qty:
        product.stock = product.stock if product.stock >= product.min_order else 0
        return HttpResponse(json.dumps({'insufficient': True, 'available': product.stock}), 'content-type: text/json')
    return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')


def check_stock(request, *args, **kwargs):
    """
    Checks stock of product in order and returns the list of product
    which stock were insufficient stock. Products in that list
    are grabbed from the provider's database and thus carry the
    current available stock.
    """
    order = parse_order_info(request)
    insufficient = []
    for entry in order.entries:
        service = entry.product.provider
        db = service.database
        product_original = entry.product.get_from(db)
        member = service.member
        if product_original.stock < entry.count:
            insufficient.append(product_original)
            try:
                cet = ConsoleEventType.objects.using('umbrella').get(codename=INSUFFICIENT_STOCK_EVENT)
                yesterday = datetime.now() - timedelta(days=1)
                ConsoleEvent.objects.using('umbrella').get(event_type=cet, member=member,
                                                           object_id=product_original.id, created_on__gte=yesterday)
            except ConsoleEvent.DoesNotExist:
                add_event(service, INSUFFICIENT_STOCK_EVENT, member=member, object_id=product_original.id)
    if len(insufficient) > 0:
        response = [product.to_dict() for product in insufficient]
        return HttpResponseRedirect(json.dumps(response), 'content-type: text/json')


def set_momo_order_checkout(request, payment_mean, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_BEFORE_CHECKOUT"
    """
    service = get_service_instance()
    config = service.config
    if getattr(settings, 'DEBUG', False):
        order = parse_order_info(request)
    else:
        try:
            order = parse_order_info(request)
        except:
            return HttpResponseRedirect(reverse('shopping:checkout'))
    order.retailer = service
    order.payment_mean = payment_mean
    order.save()  # Save first to generate the Order id
    order = Order.objects.get(pk=order.id)  # Grab the newly created object to avoid create another one in subsequent save()

    member = request.user
    if member.is_authenticated():
        order.member = member
    else:
        order.aotc = generate_tx_code(order.id, order.anonymous_buyer.auto_inc)

    order.rcc = generate_tx_code(order.id, config.rel_id)
    order.save()
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])

    if getattr(settings, 'UNIT_TESTING', False) and payment_mean.slug != 'mtn-momo':
        request.session['object_id'] = order.id
        request.session['signature'] = signature

    amount = order.total_cost
    model_name = 'trade.Order'
    mean = request.GET.get('mean', MTN_MOMO)
    cancel_url = reverse('shopping:cart')

    from daraja.models import Dara, DARA_CASH
    if mean == DARA_CASH:
        try:
            if getattr(settings, 'DEBUG', False):
                _umbrella_db = 'ikwen_umbrella'
            elif getattr(settings, 'UNIT_TESTING', False):
                _umbrella_db = 'test_ikwen_umbrella'
            else:
                _umbrella_db = 'ikwen_umbrella_prod'
            add_database(_umbrella_db)
            dara = Dara.objects.using(_umbrella_db).get(member=request.user)
            if dara.bonus_cash < order.total_cost:
                messages.error(request, "Insufficient balance. You have only <strong>XAF %s</strong> "
                                        "in your DaraCash account." % intcomma(dara.bonus_cash))
                return HttpResponseRedirect(cancel_url)
        except Dara.DoesNotExist:
            messages.error(request, "Only Dara can use this mean of payment.")
            return HttpResponseRedirect(cancel_url)

    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=service.id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A', model=model_name,
                object_id=order.id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)

    notification_url = reverse('shopping:confirm_checkout', args=(tx.id, signature))
    return_url = reverse('shopping:cart', args=(order.id, ))
    if mean == DARA_CASH:
        try:
            tx.status = MoMoTransaction.SUCCESS
            tx.message = 'OK'
            tx.processor_tx_id = tx.id
            tx.phone = request.user.phone
            tx.is_running = False
            tx.save()
            dara.lower_bonus_cash(order.total_cost)
            confirm_checkout(request, signature=signature)
            return HttpResponseRedirect(return_url)
        except:
            messages.error(request, "Unknown Server Error.")
            return HttpResponseRedirect(cancel_url)

    if getattr(settings, 'UNIT_TESTING', False):
        return HttpResponse(json.dumps({'notification_url': notification_url}), content_type='text/json')
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'http://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    payer_id = request.user.username if request.user.is_authenticated() else '<Anonymous>'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', service.project_name_slug),
        'amount': order.total_cost,
        'merchant_name': config.company_name,
        'notification_url': service.url + strip_base_alias(notification_url),
        'return_url': service.url + strip_base_alias(return_url),
        'cancel_url': service.url + strip_base_alias(cancel_url),
        'payer_id': payer_id
    }
    try:
        r = requests.get(endpoint, params, verify=False)
        resp = r.json()
        token = resp.get('token')
        if token:
            next_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
        else:
            logger.error("%s - Init payment flow failed with URL %s and message %s" % (service.project_name, r.url, resp['errors']))
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL." % service.project_name, exc_info=True)
        next_url = cancel_url
    return HttpResponseRedirect(next_url)


def confirm_checkout(request, *args, **kwargs):
    order_id = request.POST.get('order_id', request.session.get('object_id'))
    tx = None
    if order_id:
        signature = request.session['signature']
    else:
        status = request.GET['status']
        message = request.GET['message']
        operator_tx_id = request.GET['operator_tx_id']
        phone = request.GET['phone']
        tx_id = kwargs['tx_id']
        try:
            tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
            if not getattr(settings, 'DEBUG', False):
                tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
                expiry = tx.created_on + timedelta(seconds=tx_timeout)
                if datetime.now() > expiry:
                    return HttpResponse("Transaction %s timed out." % tx_id)

            tx.status = status
            tx.message = 'OK' if status == MoMoTransaction.SUCCESS else message
            tx.processor_tx_id = operator_tx_id
            tx.phone = phone
            tx.is_running = False
            tx.save()
        except:
            raise Http404("Transaction %s not found" % tx_id)
        if status != MoMoTransaction.SUCCESS:
            return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))
        order_id = tx.object_id
        signature = tx.task_id

    callback_signature = kwargs.get('signature')
    no_check_signature = request.GET.get('ncs')
    if getattr(settings, 'DEBUG', False):
        if not no_check_signature:
            if callback_signature != signature:
                return HttpResponse('Invalid transaction signature')
    else:
        if callback_signature != signature:
            return HttpResponse('Invalid transaction signature')

    order = get_object_or_404(Order, pk=order_id)

    bank_id = request.POST.get('bank_id')
    if bank_id:
        account_number = request.POST['account_number']
        deal_id = request.POST.get('deal_id')
        return submit_order_for_bank_approval(request, order, bank_id, account_number, deal_id)

    order.status = Order.PENDING
    order.save()

    after_order_confirmation(order, momo_tx=tx)
    member = order.member
    if member:
        buyer_name = member.full_name
    else:
        buyer_name = order.delivery_address.name
    buyer_email = order.delivery_address.email
    buyer_phone = order.delivery_address.phone

    reward_pack_list = []
    if member:
        activate(member.language)
        try:
            reward_pack_list, coupon_count = reward_member(order.retailer, member, Reward.PAYMENT,
                                                           amount=order.items_cost, model_name='trade.Order')
        except:
            logger.error('%s - Failed to reward member %s for '
                         'order %s of %dF' % (order.retailer.project_name, member.username, order.id, order.items_cost))
    subject = _("Order successful")
    send_order_confirmation_email(request, subject, buyer_name, buyer_email, order, reward_pack_list=reward_pack_list)
    if getattr(settings, 'UNIT_TESTING', False):
        send_order_confirmation_sms(buyer_name, buyer_phone, order)
    else:
        Thread(target=send_order_confirmation_sms, args=(buyer_name, buyer_phone, order)).start()

    return HttpResponse("Notification received")


def review_product(request, product_id, *args, **kwargs):
    """
    This view is used to comment and rate a product
    """
    rating = request.GET['rating']
    comment = request.GET.get('comment')
    member = request.user
    product = Product.objects.get(pk=product_id)
    product.total_rating += float(rating)
    product.rating_count += 1
    product.save()
    if member.is_authenticated():
        Review.objects.create(product=product, member=member, rating=rating, comment=comment)
    else:
        name = request.GET['name']
        email = request.GET['email']
        Review.objects.create(product=product, name=name, email=email, rating=rating, comment=comment)
    return HttpResponse(json.dumps({"success": True}))


def render_order_event(event, request):
    try:
        order = Order.objects.get(pk=event.object_id)
        if not order.currency:
            order.currency = Currency.active.base()
    except Order.DoesNotExist:
        return ''
    currency_symbol = get_service_instance().config.currency_symbol
    html_template = get_template('shopping/events/order_notice.html')
    entries_count = len(order.entries)
    more_entries = entries_count - 3  # Number to show on the "View more" button
    from ikwen.conf import settings as ikwen_settings
    c = Context({'event': event, 'service': event.service, 'order': order, 'currency_symbol': currency_symbol,
                 'entries_count': entries_count,'more_entries': more_entries,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
    return html_template.render(c)


class ChooseDeal(TemplateSelector, TemplateView):
    template_name = 'shopping/choose_deal.html'

    def get_context_data(self, **kwargs):
        context = super(ChooseDeal, self).get_context_data(**kwargs)
        order = get_object_or_404(Order, pk=self.request.session['object_id'])
        product = order.entries[0].product
        bank_list = []
        for operator in OperatorProfile.objects.filter(business_type=OperatorProfile.BANK):
            try:
                bank_db = operator.service.database
                add_database(bank_db)
                bank_original = Service.objects.using(bank_db).get(pk=operator.service.id)
                if len(order.entries) == 1:
                    # Deals are possible for one single product at a time, therefore there must be only 1 entry
                    bank_original.deal_list = Deal.objects.using(bank_db).filter(product_slug=product.slug)
                bank_list.append(bank_original)
            except Service.DoesNotExist:
                continue
        context['order'] = order
        context['bank_list'] = bank_list
        context['bank_accounts'] = BankAccount.objects.using(UMBRELLA).filter(member=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        payment_mean = get_object_or_404(PaymentMean, slug='cashflex')
        if getattr(settings, 'DEBUG', False):
            set_momo_order_checkout(request, payment_mean, **kwargs)
        else:
            try:
                set_momo_order_checkout(request, payment_mean, **kwargs)
            except:
                msg = _('Error setting up Deals selection page')
                messages.error(request, msg)
                logger.error(msg, exc_info=True)
                return HttpResponseRedirect(reverse('shopping:cancel'))
        return HttpResponseRedirect(reverse('shopping:choose_deal'))


def load_bank_deals(request, *args, **kwargs):
    """
    Loads deals of a bank towards a product on the merchant's website.
    """
    product_id = request.GET['product_id']
    deal_list = []
    for deal in Deal.objects.filter(product=product_id):
        try:
            deal_list.append(deal.to_dict())
        except:
           continue

    response = {'deal_list': deal_list}
    callback = request.GET['callback']
    jsonp = callback + '(' + json.dumps(response) + ')'
    return HttpResponse(jsonp, content_type='application/json')


@login_required
def submit_order_for_bank_approval(request, order, bank_id, account_number, deal_id=None):
    merchant = get_service_instance()
    bank = Service.objects.get(pk=bank_id)
    payment_mean = PaymentMean.objects.get(slug=bank.project_name_slug)
    order.payment_mean = payment_mean
    entry = order.entries[0]
    product = entry.product
    product.stock -= entry.count
    if product.stock == 0:
        sudo_group = Group.objects.get(name=SUDO)
        add_event(merchant, SOLD_OUT_EVENT, group_id=sudo_group.id, object_id=product.id)
        mark_duplicates(product)
    product.save()
    bank_db = bank.database
    add_database(bank_db)
    try:
        member = Member.objects.using(bank_db).get(pk=order.member.id)
    except Member.DoesNotExist:
        member = order.member
        member.save(using=bank_db)
        group = Group.objects.using(bank_db).get(name=COMMUNITY)
        obj_list, created = UserPermissionList.objects.using(bank_db).get_or_create(user=member)
        obj_list.group_fk_list.append(group.id)
        obj_list.save(using=bank_db)
    account_number_slug = slugify(account_number)
    try:
        BankAccount.objects.using(UMBRELLA).get(slug=account_number_slug)
    except BankAccount.DoesNotExist:
        m = Member.objects.using(UMBRELLA).get(pk=member.id)
        b = Service.objects.using(UMBRELLA).get(pk=bank_id)
        BankAccount.objects.using(UMBRELLA).create(member=m, bank=b, number=account_number, slug=account_number_slug)
    if deal_id:
        if len(order.entries) > 1:
            messages.error(request, _("Terms payment is available only for one single product at a time."))
            return HttpResponseRedirect(reverse('shopping:cart'))
        deal = Deal.objects.using(bank_db).get(pk=deal_id)
    else:
        deal = Deal(bank=bank)
    order.deal = deal
    order.account_number = account_number
    order.status = Order.PENDING_FOR_APPROVAL
    order.save()
    order.save(using=bank_db)
    try:
        del(request.session['object_id'])
    except:
        pass
    subject = _("Order submit for approval")
    send_order_confirmation_email(request, subject, member.full_name, member.email, order)
    bank_profile_original = OperatorProfile.objects.using(bank_db).get(service=bank)
    if bank_profile_original.return_url:
        nvp_dict = {'member': member.full_name, 'email': member.email, 'phone': member.phone,
                    'order_rcc': order.rcc.upper(), 'account_number': account_number,
                    'deal': str(deal), 'merchant': merchant.project_name}
        Thread(target=lambda url, data: requests.post(url, data=data),
               args=(bank_profile_original.return_url, nvp_dict)).start()

    next_url = reverse('shopping:cart', args=(order.id, ))
    return HttpResponseRedirect(next_url)

    # api_url = bank.url + reverse('trade:collect_order_for_approval',
    #                              args=(order.member.id, deal_id, entry.count, bank.api_key))
    # requests.get(api_url, {'deal_id': deal_id, 'count': entry.count, 'api_key': bank.api_key})


class Cancel(TemplateSelector, TemplateView):
    template_name = 'shopping/cancel.html'
    optimum_template_name = 'shopping/optimum/cancel.html'

    def get(self, request, *args, **kwargs):
        try:
            Order.objects.filter(pk=request.session['object_id']).delete()
            del(request.session['object_id'])
        except:
            pass
        return super(Cancel, self).get(request, *args, **kwargs)


@csrf_exempt
def test_return_url(request, *args, **kwargs):
    """
    This view serves only testing purposes. It acts as the RETURN_URL
    that is applicable to providers and delivery companies Profile
    """
    base_dir = getattr(settings, 'BASE_DIR')
    f = open(base_dir + '/routed_data.txt', 'a+')
    for key, value in request.POST.items():
        f.write('%s: %s\n' % (key, value))
    f.close()
    return HttpResponse('OK')


def load_countries(*args, **kwargs):
    countries = Country.objects.using(UMBRELLA).all()
    for country in countries:
        country.save(using='default')
    return HttpResponse(
    json.dumps({'Success': True}),
    'content-type: text/json'
    )


class CouponList(TemplateView):
    template_name = 'shopping/coupon_list.html'


class OrderHistory(TemplateView):
    template_name = 'shopping/optimum/order_history.html'

    def post(self, request, *args, **kwargs):
        member = request.user
        delivery_address = DeliveryAddress.objects.create()
        country_iso2 = request.POST.get('country_iso2')
        if country_iso2:
            try:
                country = Country.objects.get(iso2=country_iso2)
                delivery_address.country = country
            except:
                pass
        city = request.POST.get('city')
        if city:
            delivery_address.city = city
        address_details = request.POST.get('details')
        if address_details:
            delivery_address.details = address_details
        postal_code = request.POST.get('postal_code')
        if postal_code:
            delivery_address.postal_code = postal_code
        phone = request.POST.get('phone')
        if phone:
            delivery_address.phone = phone
        email = request.POST.get('email')
        if email:
            delivery_address.email = email
        if member.customer:
            customer = member.customer
            delivery_address.save()
            customer.delivery_addresses.append(delivery_address)
            customer.save()
            item = request.POST.get('item')
            self.delete_address(request, item)

        return HttpResponseRedirect(reverse('shopping:orders_history'))

    def get(self, request, *args, **kwargs):
        action = self.request.GET.get('action')
        if action == 'delete':
            return self.delete_address(request)
        return super(OrderHistory, self).get(request, *args, **kwargs)

    def delete_address(self, request, item_arg=None):
        member = request.user
        item = request.GET.get('item')
        if not item:
            item = item_arg
        if member.customer:
            customer = member.customer
            customer.delivery_addresses.pop(int(item))
            customer.save()
            # messages.success(self.request, 'Address deleted')
            return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
        return HttpResponseRedirect(reverse('shopping:orders_history'))

    def get_context_data(self, **kwargs):
        context = super(OrderHistory, self).get_context_data(**kwargs)
        context['countries'] = Country.objects.all()
        member = self.request.user
        customer = None
        if member.customer:
            customer = member.customer
        context['customer'] = customer
        try:
            order_history_list = Order.objects\
                .filter(member=member, status__in=[Order.SHIPPED, Order.PENDING, Order.DELIVERED]).order_by('-id')[:20]
            context['order_history_list'] = order_history_list
        except:
            pass
        context['member'] = member
        return context


class DisplayDeviceDimension(TemplateView):
    template_name = 'shopping/device_dimension.html'


class SingleProduct(TemplateView):
    template_name = 'shopping/optimum/single_product.html'

    def get_context_data(self, **kwargs):
        context = super(SingleProduct, self).get_context_data(**kwargs)
        context['template_cache_duration'] = 400
        service = get_service_instance()
        db = service.database
        add_database(db)
        # try:
        #     current_product = Product.objects.select_related('provider').filter(category=category)[0]
        # except IndexError:
        #     raise Http404('No product matches the given query.')
        current_product = Product.objects.using(db).filter(visible=True)[0]
        product = apply_promotion_discount([current_product])[0]
        category = product.category
        context['product'] = product
        context['category'] = category
        return context