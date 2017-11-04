import json
import os
from threading import Thread
from urlparse import urlparse

from ajaxuploader.views import AjaxFileUploader
from django.conf import settings
from django.contrib import messages
from django.contrib.admin import AdminSite, helpers
from django.contrib.auth.decorators import permission_required, login_required
from django.core import mail
from django.core.files.base import File
from django.core.mail import EmailMessage
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import F
from django.forms.models import modelform_factory
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from ikwen.accesscontrol.models import Member
from ikwen_kakocase.kakocase.templatetags.media_from_provider import from_provider

from ikwen.core.models import Service

from ikwen.accesscontrol.utils import get_members_having_permission

from ikwen_kakocase.commarketing.models import SmartCategory, Banner
from ikwen.accesscontrol.templatetags.auth_tokens import append_auth_tokens

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import add_database_to_settings, DefaultUploadBackend, get_service_instance, add_event, \
    get_mail_content, get_model_admin_instance, add_database
from ikwen.core.views import BaseView, HybridListView
from ikwen_kakocase.kako.admin import ProductAdmin, RecurringPaymentServiceAdmin
from ikwen_kakocase.kako.models import Product, RecurringPaymentService, Photo
from ikwen_kakocase.kako.utils import create_category, mark_duplicates, get_product_from_url
from ikwen_kakocase.kakocase.models import OperatorProfile, BusinessCategory, ProductCategory, PROVIDER_REMOVED_PRODUCT_EVENT, \
    PRODUCTS_LIMIT_ALMOST_REACHED_EVENT, PRODUCTS_LIMIT_REACHED_EVENT
from ikwen_kakocase.kakocase.admin import ProductCategoryAdmin


class ProviderList(HybridListView):
    template_name = 'kako/retailer/provider_list.html'
    queryset = OperatorProfile.objects.using(UMBRELLA).filter(business_type=OperatorProfile.PROVIDER, is_active=True)

    # 'Auto' comes before 'Manual' in lexicographical order so ordering by
    # 'last_stock_update_method' ASC insures that Providers with 'Auto' stock update
    # are shown prior to those with 'Manual' stock update
    ordering = ('-stock_updated_on', 'last_stock_update_method')
    context_object_name = 'providers'
    search_field = 'company_name'

    def get_context_data(self, **kwargs):
        context = super(ProviderList, self).get_context_data(**kwargs)
        context['business_categories'] = BusinessCategory.objects.using(UMBRELLA).all()
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'json':
            providers_qs = OperatorProfile.objects.using(UMBRELLA).filter(business_type=OperatorProfile.PROVIDER, is_active=True)
            if self.request.GET.get('category_slug'):
                category_slug = self.request.GET.get('category_slug')
                business_category = BusinessCategory.objects.using(UMBRELLA).get(slug=category_slug)
                providers_qs = providers_qs.filter(business_category=business_category)
            start = int(self.request.GET.get('start'))
            length = int(self.request.GET.get('length'))
            limit = start + length
            providers_qs = self.get_search_results(providers_qs)
            providers_qs = providers_qs.order_by(*self.ordering)[start:limit]
            response = [provider.to_dict() for provider in providers_qs]
            return HttpResponse(
                json.dumps(response),
                'content-type: text/json',
                **response_kwargs
            )
        else:
            return super(ProviderList, self).render_to_response(context, **response_kwargs)


class ProviderProductList(BaseView):
    template_name = 'kako/retailer/provider_product_list.html'

    def get_context_data(self, **kwargs):
        context = super(ProviderProductList, self).get_context_data(**kwargs)
        provider_id = kwargs['provider_id']
        service = OperatorProfile.objects.using(UMBRELLA).get(pk=provider_id).service
        add_database_to_settings(service.database)
        context['categories'] = ProductCategory.objects.using(service.database).filter(items_count__gt=0)
        context['provider_database'] = service.database
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        provider_database = context['provider_database']
        products = Product.objects.using(provider_database)\
                       .filter(visible=True, in_trash=False).order_by('-updated_on', '-total_units_sold')[:24]
        context['products'] = products
        return self.render_to_response(context)

    def render_to_response(self, context, **response_kwargs):
        provider_database = context['provider_database']
        if self.request.GET.get('format') == 'json':
            products_qs = Product.objects.using(provider_database).filter(visible=True, in_trash=False)
            if self.request.GET.get('category_slug'):
                category_slug = self.request.GET.get('category_slug')
                category = ProductCategory.objects.get(slug=category_slug)
                products_qs = products_qs.filter(category=category)
            start = int(self.request.GET.get('start'))
            length = int(self.request.GET.get('length'))
            limit = start + length
            products_qs = self.get_search_results(products_qs)
            products_qs = products_qs.order_by('-updated_on', '-total_units_sold')[start:limit]
            response = [product.to_dict() for product in products_qs]
            return HttpResponse(
                json.dumps(response),
                'content-type: text/json',
                **response_kwargs
            )
        else:
            return super(ProviderProductList, self).render_to_response(context, **response_kwargs)

    def get_search_results(self, queryset):
        search_term = self.request.GET.get('q')
        if search_term and len(search_term) >= 2:
            search_term = search_term.lower()
            for word in search_term.split(' '):
                word = slugify(word)[:4]
                if word:
                    queryset = queryset.filter(name__icontains=word)
                    if queryset.count() > 0:
                        break
        return queryset


class ProviderProductDetail(BaseView):
    template_name = 'kako/product_detail.html'

    def get_context_data(self, **kwargs):
        context = super(ProviderProductDetail, self).get_context_data(**kwargs)
        provider_id = kwargs['provider_id']
        service = OperatorProfile.objects.using(UMBRELLA).get(pk=provider_id).service
        add_database_to_settings(service.database)
        product_id = kwargs['product_id']
        context['categories'] = ProductCategory.objects.using(service.database).filter(items_count__gt=0)
        context['product'] = Product.objects.using(service.database).get(pk=product_id)
        return context


class CategoryList(HybridListView):
    template_name = 'kako/category_list.html'
    model = ProductCategory
    ordering = ('-appear_in_menu', 'order_of_appearance', '-id',)
    search_field = 'slug'
    context_object_name = 'category_list'

    def get_context_data(self, **kwargs):
        context = super(CategoryList, self).get_context_data(**kwargs)
        if self.request.GET.get('smart_link'):
            smart_object_id = self.request.GET['smart_object_id']
            try:
                smart_object = Banner.objects.get(pk=smart_object_id)
            except Banner.DoesNotExist:
                smart_object = get_object_or_404(SmartCategory, pk=smart_object_id)
            context['smart_object'] = smart_object
        return context

    def get(self, request, *args, **kwargs):
        sorted_keys = request.GET.get('sorted')
        if sorted_keys:
            for token in sorted_keys.split(','):
                category_id, order_of_appearance = token.split(':')
                try:
                    ProductCategory.objects.filter(pk=category_id).update(order_of_appearance=order_of_appearance)
                except:
                    continue
            return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
        return super(CategoryList, self).get(request, *args, **kwargs)


class ChangeCategory(BaseView):
    template_name = 'kako/change_category.html'

    def get_context_data(self, **kwargs):
        context = super(ChangeCategory, self).get_context_data(**kwargs)
        category_id = kwargs.get('category_id')  # May be overridden with the one from GET data
        category_id = self.request.GET.get('category_id', category_id)
        category = None
        if category_id:
            category = get_object_or_404(ProductCategory, pk=category_id)
            category.items_count = category.product_set.all().count()
            category.save()
        category_admin = get_model_admin_instance(ProductCategory, ProductCategoryAdmin)
        ModelForm = modelform_factory(ProductCategory, fields=('name', 'description', 'badge_text',
                                                               'appear_in_menu', 'is_active'))
        form = ModelForm(instance=category)
        category_form = helpers.AdminForm(form, list(category_admin.get_fieldsets(self.request)),
                                          category_admin.get_prepopulated_fields(self.request),
                                          category_admin.get_readonly_fields(self.request, obj=category))
        context['category'] = category
        context['model_admin_form'] = category_form
        return context

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        smart_category_id = self.request.POST.get('smart_category_id')
        if not smart_category_id:
            smart_category_id = self.request.GET.get('smart_category_id')
        category_id = self.request.POST.get('category_id')
        category = None
        if category_id:
            category = get_object_or_404(ProductCategory, pk=category_id)
        category_admin = get_model_admin_instance(ProductCategory, ProductCategoryAdmin)
        ModelForm = category_admin.get_form(self.request)
        form = ModelForm(request.POST, instance=category)
        if form.is_valid():
            name = form.cleaned_data['name']
            description = form.cleaned_data['description']
            badge_text = form.cleaned_data['badge_text']
            image_url = request.POST.get('image_url')
            if not category:
                category = create_category(name)
            else:
                category.name = name
                category.slug = slugify(name)
                category.items_count = category.product_set.all().count()
            category.description = description
            category.badge_text = badge_text
            category.appear_in_menu = True if request.POST.get('appear_in_menu') else False
            category.is_active = True if request.POST.get('is_active') else False
            if image_url:
                if not category.image.name or image_url != category.image.url:
                    filename = image_url.split('/')[-1]
                    media_root = getattr(settings, 'MEDIA_ROOT')
                    media_url = getattr(settings, 'MEDIA_URL')
                    image_url = image_url.replace(media_url, '')
                    try:
                        with open(media_root + image_url, 'r') as f:
                            content = File(f)
                            destination = media_root + ProductCategory.UPLOAD_TO + "/" + filename
                            category.image.save(destination, content)
                        os.unlink(media_root + image_url)
                    except IOError as e:
                        if getattr(settings, 'DEBUG', False):
                            raise e
                        return {'error': 'File failed to upload. May be invalid or corrupted image file'}
            category.save()
            if smart_category_id:
                try:
                    smart_category = SmartCategory.objects.get(pk=smart_category_id)
                    if category.id not in smart_category.items_fk_list:
                        smart_category.items_fk_list.append(category.id)
                    smart_category.save()
                except:
                    pass
            if category_id:
                next_url = reverse('kako:change_category', args=(category_id, ))
                messages.success(request, _("Category %s successfully updated." % category.name))
            else:
                next_url = self.request.REQUEST.get('next')
                if not next_url:
                    next_url = reverse('kako:category_list')
                messages.success(request, _("Category %s successfully created." % category.name))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


@login_required
def toggle_category_attribute(request, *args, **kwargs):
    category_id = request.GET['category_id']
    attr = request.GET['attr']
    val = request.GET['val']
    category = ProductCategory.objects.get(pk=category_id)
    if val.lower() == 'true':
        category.__dict__[attr] = True
    else:
        category.__dict__[attr] = False
    category.save()
    response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


class CategoryListFilter(object):
    title = _('Category')
    parameter_name = 'category_slug'

    def lookups(self):
        choices = []
        for category in ProductCategory.objects.all():
            choice = (category.slug, category.name)
            choices.append(choice)
        return choices

    def queryset(self, request, queryset):
        value = request.GET.get(self.parameter_name)
        if value:
            category = ProductCategory.objects.get(slug=value)
            return queryset.filter(category=category)
        return queryset


class MerchantListFilter(object):
    title = _('Merchant')
    parameter_name = 'merchant_id'

    def lookups(self):
        choices = []
        for merchant in OperatorProfile.objects.filter(business_type=OperatorProfile.PROVIDER):
            try:
                choice = (merchant.service.id, merchant.service.project_name)
                choices.append(choice)
            except:
                continue
        return choices

    def queryset(self, request, queryset):
        value = request.GET.get(self.parameter_name)
        if value:
            return queryset.filter(provider=value)
        return queryset


class ProductList(HybridListView):
    template_name = 'kako/product_list.html'
    html_results_template_name = 'kako/snippets/product_list_results.html'
    queryset = Product.objects.filter(in_trash=False)
    ordering = ('-updated_on', '-total_units_sold')
    search_field = 'tags'
    context_object_name = 'product_list'
    list_filter = (MerchantListFilter, ) if getattr(settings, 'IS_BANK', False) else (CategoryListFilter, )

    def get_queryset(self):
        queryset = super(ProductList, self).get_queryset()
        collection_id = self.request.GET.get('collection_id')
        if collection_id:
            try:
                collection = SmartCategory.objects.get(pk=collection_id)
                queryset = collection.get_product_queryset()
            except SmartCategory.DoesNotExist:
                collection = get_object_or_404(ProductCategory, pk=collection_id)
                queryset = collection.product_set.all()
        return queryset

    def get_context_data(self, **kwargs):
        queryset = self.get_queryset()
        context = super(ProductList, self).get_context_data(**kwargs)
        paginator = Paginator(queryset, self.page_size)
        objects_page = paginator.page(1)
        context['q'] = self.request.GET.get('q')
        context['objects_page'] = objects_page
        if self.request.GET.get('smart_link'):
            smart_object_id = self.request.GET['smart_object_id']
            try:
                smart_object = Banner.objects.get(pk=smart_object_id)
            except Banner.DoesNotExist:
                smart_object = get_object_or_404(SmartCategory, pk=smart_object_id)
            context['smart_object'] = smart_object
        return context


@permission_required('kako.ik_manage_product')
def do_import_products(request, *args, **kwargs):
    """
    Import a list of :class:`kako.models.Product` chosen by :class:`people.models.Retailer`
    to his database from the :class:`people.models.Provider` database
    """
    provider_id = request.GET['provider_id']
    product_ids = request.GET['product_ids']
    product_ids = product_ids.strip(',').split(',')
    if len(product_ids) == 0:
        return
    provider_profile = OperatorProfile.objects.using(UMBRELLA).get(pk=provider_id)
    provider_service = provider_profile.service
    provider_member = provider_service.member
    provider_member.save(using='default')  # Save provider to local database to make product.provider not raise NotFoundError
    provider_service.save(using='default')
    provider_database = provider_service.database
    add_database_to_settings(provider_database)

    # Import this Provider Profile to the local database only for the ranking
    # Of most profitable providers in the RetailerDashboard listing
    try:
        OperatorProfile.objects.using('default').get(pk=provider_profile.id)
    except OperatorProfile.DoesNotExist:
        provider_profile.counters_reset_on = timezone.now()
        provider_profile.items_traded_history = []
        provider_profile.turnover_history = []
        provider_profile.earnings_history = []
        provider_profile.orders_count_history = []
        provider_profile.broken_products_history = []
        provider_profile.late_deliveries_history = []
        provider_profile.total_items_traded = 0
        provider_profile.total_turnover = 0
        provider_profile.total_earnings = 0
        provider_profile.total_orders_count = 0
        provider_profile.total_broken_products = 0
        provider_profile.total_late_deliveries = 0
        provider_profile.save(using='default')

    # Import Retailer to the provider's database for the same reasons as above
    service = get_service_instance()
    retailer_profile = service.config
    service.member.save(using=provider_database)
    service.save(using=provider_database)
    try:
        OperatorProfile.objects.using(provider_database).get(pk=retailer_profile.id)
    except OperatorProfile.DoesNotExist:
        retailer_profile.counters_reset_on = timezone.now()
        retailer_profile.items_traded_history = []
        retailer_profile.turnover_history = []
        retailer_profile.earnings_history = []
        retailer_profile.orders_count_history = []
        retailer_profile.broken_products_history = []
        retailer_profile.late_deliveries_history = []
        retailer_profile.total_items_traded = 0
        retailer_profile.total_turnover = 0
        retailer_profile.total_earnings = 0
        retailer_profile.total_orders_count = 0
        retailer_profile.total_broken_products = 0
        retailer_profile.total_late_deliveries = 0
        retailer_profile.save(using=provider_database)

    for product_id in product_ids:
        try:
            product = Product.objects.using(provider_database).get(pk=product_id)
            if product.retail_price:
                product.retail_price_is_modifiable = False
            else:
                product.retail_price_is_modifiable = True
            product.save(using='default')
            product.is_retailed = True
            product.save(using=provider_database)
        except Product.DoesNotExist:
            try:
                service = RecurringPaymentService.objects.using(provider_database).get(pk=product_id)
                if service.retail_price:
                    service.retail_price_is_modifiable = False
                else:
                    service.retail_price_is_modifiable = True
                service.save(using='default')
                service.is_retailed = True
                service.save(using=provider_database)
            except RecurringPaymentService.DoesNotExist:
                pass
    response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('kako.ik_manage_product')
def update_product_retail_price(request, *args, **kwargs):
    """
    Update price :class:`kako.models.Product` in the actual :class:`ikwen_kakocase.models.OperatorProfile` database.
    """
    product_id = request.GET['product_id']
    price = float(request.GET['price'])
    try:
        product = Product.objects.get(pk=product_id)
        if product.retail_price_is_modifiable:
            product.retail_price = price if price < product.max_price else product.max_price
            product.save()
    except Product.DoesNotExist:
        response = {'error': "Product not found."}
    else:
        response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('kako.ik_manage_product')
def update_product_stock(request, *args, **kwargs):
    """
    Update stock :class:`kako.models.Product` in the actual :class:`ikwen.ikwen_kakocase.models.OperatorProfile` database.
    This method assumes only provider can update stock. So the Product.save() is called only with the default database
    """
    product_id = request.GET['product_id']
    stock = float(request.GET['stock'])
    try:
        product = Product.objects.get(pk=product_id)
        product.stock = stock
        product.save()
        if stock == 0:
            mark_duplicates(product)
        operator_profile_umbrella = get_service_instance(UMBRELLA).config
        operator_profile_umbrella.stock_updated_on = timezone.now()
        operator_profile_umbrella.last_stock_update_method = OperatorProfile.MANUAL_UPDATE
        operator_profile_umbrella.save(using=UMBRELLA)
    except Product.DoesNotExist:
        response = {'error': "Product not found."}
    else:
        response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('kako.ik_manage_product')
def add_category(request, *args, **kwargs):
    """
    Adds a new :class:`ikwen.ikwen_kakocase.models.ProductCategory` in the actual
    :class:`ikwen.ikwen_kakocase.models.OperatorProfile` database.
    We start by searching the category with the given name in UMBRELLA database.
    If not found there, it is created and appended in the list of product_categories
    for the actual Operator business_category
    """
    name = request.GET['name']
    category = create_category(name)
    return HttpResponse(json.dumps(category.to_dict()), 'content-type: text/json')


@permission_required('kako.ik_manage_product')
def delete_category(request, *args, **kwargs):
    selection = request.GET['selection'].split(',')
    deleted = []
    for category_id in selection:
        try:
            category = ProductCategory.objects.get(pk=category_id)
            count = Product.objects.filter(category=category, in_trash=False).count()
            if count > 0:
                message = "Category %s contains %d item(s). Delete them first." % (category.name, count)
                break
            category.delete()
            deleted.append(category_id)
        except ProductCategory.DoesNotExist:
            message = "Category '%s' was not found." % category_id
            break
    else:
        message = "%d item(s) deleted." % len(selection)
    response = {'message': message, 'deleted': deleted}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


class ProductPhotoUploadBackend(DefaultUploadBackend):
    """
    Ajax upload handler for :class:`kako.models.Product` photos
    """
    def upload_complete(self, request, filename, *args, **kwargs):
        path = self.UPLOAD_DIR + "/" + filename
        self._dest.close()
        media_root = getattr(settings, 'MEDIA_ROOT')
        try:
            with open(media_root + path, 'r') as f:
                content = File(f)
                destination = media_root + Photo.UPLOAD_TO + "/" + filename
                photo = Photo()
                photo.image.save(destination, content)
                product_id = request.GET.get('product_id')
                if product_id:
                    try:
                        product = Product.objects.get(pk=product_id)
                        product.photos.append(photo)
                        product.save()
                    except:
                        pass

            os.unlink(media_root + path)
            return {
                'id': photo.id,
                'url': photo.image.small_url
            }
        except IOError as e:
            if getattr(settings, 'DEBUG', False):
                raise e
            return {'error': 'File failed to upload. May be invalid or corrupted image file'}


product_photo_uploader = AjaxFileUploader(ProductPhotoUploadBackend)


class ChangeProduct(BaseView):
    template_name = 'kako/change_product.html'

    def get_product_admin(self):
        default_site = AdminSite()
        product_admin = ProductAdmin(Product, default_site)
        return product_admin

    def get_context_data(self, **kwargs):
        context = super(ChangeProduct, self).get_context_data(**kwargs)
        collection_id = self.request.GET.get('collection_id')
        if collection_id:
            try:
                SmartCategory.objects.get(pk=collection_id)
                context['is_smart_category'] = True
            except SmartCategory.DoesNotExist:
                pass
        product_id = kwargs.get('product_id', self.request.GET.get('product_id'))
        product = None
        if product_id:
            product = get_object_or_404(Product, pk=product_id)
            if self.request.GET.get('duplicate'):
                product.id = ''
        product_admin = self.get_product_admin()
        ModelForm = product_admin.get_form(self.request, obj=product)
        form = ModelForm(instance=product)

        product_form = helpers.AdminForm(form, list(product_admin.get_fieldsets(self.request)),
                                         product_admin.get_prepopulated_fields(self.request),
                                         product_admin.get_readonly_fields(self.request, obj=product))
        context['product'] = product
        context['model_admin_form'] = product_form
        return context

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        service = get_service_instance()
        config = service.config
        product_id = kwargs.get('product_id', request.POST.get('product_id'))
        product_admin = self.get_product_admin()
        ModelForm = product_admin.get_form(request)
        if product_id:
            product = get_object_or_404(Product, pk=product_id)
            form = ModelForm(request.POST, instance=product)
        else:
            form = ModelForm(request.POST)
        if form.is_valid():
            name = request.POST.get('name')
            category_id = request.POST.get('category')
            brand = request.POST.get('brand')
            reference = request.POST.get('reference')
            original_id = request.POST.get('original_id')
            wholesale_price = float(request.POST.get('wholesale_price'))
            try:
                retail_price = float(request.POST.get('retail_price'))
            except:
                retail_price = 0
            max_price = request.POST.get('max_price')
            summary = request.POST.get('summary')
            description = request.POST.get('description')
            badge_text = request.POST.get('badge_text')
            size = request.POST.get('size')
            weight = request.POST.get('weight')
            stock = request.POST.get('stock')
            visible = request.POST.get('visible')
            photos_ids = request.POST.get('photos_ids')
            photos_ids_list = photos_ids.strip(',').split(',') if photos_ids else []
            category = ProductCategory.objects.get(pk=category_id)
            if retail_price and retail_price < wholesale_price:
                error = _("Retail price cannot be smaller than wholesale price.")
                context = self.get_context_data(**kwargs)
                context['error'] = error
                return render(request, self.template_name, context)
            if product_id:
                product = get_object_or_404(Product, pk=product_id)
                if getattr(settings, 'IS_PROVIDER', False):
                    if product.is_retailed:
                        error = _("Product already imported by some retailers. Delete and start again.")
                        context = self.get_context_data(**kwargs)
                        context['error'] = error
                        return render(request, self.template_name, context)

                if product.retail_price_is_modifiable and retail_price < product.retail_price:
                    product.previous_price = product.retail_price
                    product.on_sale = True
                else:
                    product.on_sale = False
                if product.category != category:
                    product.category.items_count -= 1
                    product.category.save()
            else:
                if not config.is_pro_version and config.max_products == Product.objects.filter(in_trash=False).count():
                    error = _("Product cannot be added because the limit of %d products is reached." % config.max_products)
                    context = self.get_context_data(**kwargs)
                    context['error'] = error
                    return render(request, self.template_name, context)
                category.items_count = category.product_set.all().count() + 1
                product = Product(units_sold_history=[0])
            # if product.id is not None and product.provider != operator:
            #     return HttpResponseForbidden("You don't have permission to access this resource.")
            product.name = name
            product.slug = slugify(name)
            product.brand = brand.strip()
            product.summary = summary
            product.description = description
            product.badge_text = badge_text
            product.category = category
            product.reference = reference
            product.original_id = original_id
            product.size = size
            product.weight = weight
            product.tags = product.slug.replace('-', ' ')
            try:
                product.stock = float(stock.strip())
            except:
                product.stock = 0
            if getattr(settings, 'IS_PROVIDER', False):
                product.wholesale_price = wholesale_price
                if max_price:
                    product.max_price = float(max_price.strip())
                product.retail_price_is_modifiable = True if request.POST.get('retail_price_is_modifiable') else False
            else:
                product.retail_price_is_modifiable = True
            product.photos = []
            if len(photos_ids_list) == 0:
                product.visible = False  # Product without photo are hidden
            else:
                product.visible = True if visible else False  # Product with photo has visibility chosen by user
                for photo_id in photos_ids_list:
                    if photo_id:
                        try:
                            photo = Photo.objects.get(pk=photo_id)
                            product.photos.append(photo)
                        except:
                            pass
            if retail_price:
                product.retail_price = retail_price
            product.provider = service
            product.save()
            category.save()
            if not config.is_pro_version:
                total_products_count = Product.objects.filter(in_trash=False).count()
                if config.max_products == (total_products_count - 10):
                    product_manager_list = get_members_having_permission(Product, 'ik_manage_product')
                    for m in product_manager_list:
                        add_event(service, PRODUCTS_LIMIT_ALMOST_REACHED_EVENT, m)
                if config.max_products == total_products_count - 10:
                    product_manager_list = get_members_having_permission(Product, 'ik_manage_product')
                    for m in product_manager_list:
                        add_event(service, PRODUCTS_LIMIT_REACHED_EVENT, m)
            if product_id:
                next_url = reverse('kako:change_product', args=(product_id, ))
                messages.success(request, _("Product %s successfully updated." % product.name))
            else:
                next_url = reverse('kako:product_list')
                messages.success(request, _("Product %s successfully created." % product.name))
            mark_duplicates(product)
            next_url = append_auth_tokens(next_url, request)
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            admin_form = helpers.AdminForm(form, list(product_admin.get_fieldsets(self.request)),
                                           product_admin.get_prepopulated_fields(self.request),
                                           product_admin.get_readonly_fields(self.request))
            context['model_admin_form'] = admin_form
            return render(request, self.template_name, context)


class ChangeRecurringPaymentServiceView(BaseView):
    template_name = 'kako/change_product.html'

    def get_recurring_payment_service_admin(self):
        default_site = AdminSite()
        service_admin = RecurringPaymentServiceAdmin(RecurringPaymentService, default_site)
        return service_admin

    def get_context_data(self, **kwargs):
        context = super(ChangeRecurringPaymentServiceView, self).get_context_data(**kwargs)
        product_id = self.request.GET.get('product_id')
        if product_id:
            product = get_object_or_404(RecurringPaymentService, pk=product_id)
            product_admin = self.get_recurring_payment_service_admin()
            ModelForm = product_admin.get_form(self.request)
            form = ModelForm(instance=product)

            product_form = helpers.AdminForm(form, list(product_admin.get_fieldsets(self.request)),
                                             product_admin.get_prepopulated_fields(self.request))
            context['product'] = product
            context['product_form'] = product_form
        return context

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        """
        Submit information of a product for save. Products without
        photo are made invisible so that they don't appear on the e-shop.
        If the operation is a product update, it won't work on a product that
        has already been imported on a retailer's site.
        """
        product_id = request.POST.get('product_id')
        name = request.POST.get('name')
        category_id = request.POST.get('category')
        reference = request.POST.get('reference')
        original_id = request.POST.get('original_id')
        wholesale_price = request.POST.get('wholesale_price')
        retail_price = request.POST.get('retail_price')
        max_price = request.POST.get('max_price')
        description = request.POST.get('description')
        duration = request.POST.get('duration')
        duration_text = request.POST.get('duration_text')
        # stock = request.POST.get('stock')
        visible = request.POST.get('visible')
        photos_ids = request.POST.get('photos_ids')
        photos_ids_list = photos_ids.strip(',').split(',') if photos_ids else []
        referrer = request.META['HTTP_REFERER']

        category = ProductCategory.objects.get(pk=category_id)
        if product_id:
            product = get_object_or_404(RecurringPaymentService, pk=product_id)
            if getattr(settings, 'IS_PROVIDER', False):
                if product.is_retailed:
                    error = _("Product already imported by some retailers. Delete and register a new one.")
                    context = ChangeProduct(request=request).get_context_data(product_id=product_id)
                    context['error'] = error
                    return render(request, 'kako/change_product.html', context)
        else:
            category.items_count = category.product_set.all().count() + 1
            product = RecurringPaymentService()
        product.duration = duration
        product.duration_text = duration_text

        product.name = name
        slug = slugify(name)
        pname = slug
        i = 1
        while True:
            try:
                RecurringPaymentService.objects.get(category=category, slug=pname)
                i += 1
                pname = "%s-%d" % (slug, i)
            except Product.DoesNotExist:
                slug = pname
                break
        product.slug = slug
        product.description = description
        product.category = category
        product.reference = reference
        product.original_id = original_id
        product.tags = product.slug.replace('-', ' ')
        # product.stock = stock
        if retail_price:
            product.retail_price = retail_price
        if getattr(settings, 'IS_PROVIDER', False):
            product.wholesale_price = wholesale_price
            if max_price:
                product.max_price = float(max_price)
            product.retail_price_is_modifiable = True if request.POST.get('retail_price_is_modifiable') else False
        else:
            # product.wholesale_price = 0
            product.retail_price_is_modifiable = True
        product.photos = []
        if len(photos_ids_list) == 0:
            product.visible = False  # Product without photo are hidden
        else:
            product.visible = True if visible else False  # Product with photo has visibility chosen by user
            for photo_id in photos_ids_list:
                if photo_id:
                    try:
                        photo = Photo.objects.get(pk=photo_id)
                        product.photos.append(photo)
                    except:
                        pass
        product.provider = get_service_instance()
        product.save()
        category.save()
        if product_id:
            next_url = reverse('kako:change_product', args=(product_id, )) + '?success=yes'
        else:
            next_url = reverse('kako:change_product') + '?success=yes'
        next_url = append_auth_tokens(next_url, request)
        return HttpResponseRedirect(next_url)


def delete_photo(request, *args, **kwargs):
    product_id = request.GET.get('product_id')
    photo_id = request.GET['photo_id']
    photo = Photo(id=photo_id)
    if product_id:
        product = Product.objects.get(pk=product_id)
        if photo in product.photos:
            product.photos.remove(photo)
            product.save()
    try:
        Photo.objects.get(pk=photo_id).delete()
    except:
        pass
    return HttpResponse(
        json.dumps({'success': True}),
        content_type='application/json'
    )


@permission_required('kako.ik_manage_product')
def put_product_in_trash(request, *args, **kwargs):
    # TODO: Implement Trash view itself so that people can view and restore the content of the trash
    config = get_service_instance().config
    selection = request.GET['selection'].split(',')
    deleted = []
    for product_id in selection:
        try:
            product = Product.objects.get(pk=product_id)
            product.in_trash = True
            product.visible = False
            product.save()
            deleted.append(product_id)
            if getattr(settings, 'IS_PROVIDER', False):
                connection = mail.get_connection()
                try:
                    connection.open()
                    connection_opened = True
                except:
                    connection_opened = False
                for retailer_profile in OperatorProfile.objects.filter(business_type=OperatorProfile.RETAILER):
                    member = retailer_profile.service.member
                    service = retailer_profile.service
                    db = service.database
                    add_database_to_settings(db)
                    Product.objects.using(db).get(pk=product_id).delete()
                    ProductCategory.objects.using(db).filter(pk=product.category.id).update(items_count=F('items_count')-1)
                    if product.is_retailed:
                        add_event(service, PROVIDER_REMOVED_PRODUCT_EVENT, member=member, object_id=product_id)
                        if connection_opened:
                            # TODO: Verify what mail looks like after tests once UIs are implemented
                            subject = _("Product taken out by %s" % config.company_name)
                            message = _("Hi %(member_name)s,<br/> The product below was"
                                        "removed by <strong>%(company_name)s.</strong> "
                                        "It won't appear on your website anymore." % {'member_name': member.first_name,
                                                                                      'company_name': config.company_name})
                            html_content = get_mail_content(subject, message,
                                                            template_name='kako/retailer/mails/product_removed.html',
                                                            extra_context={'product': product, 'service': service,
                                                                           'provider_id': config.id})
                            sender = '%s <no-reply@%s.com>' % (service.project_name, service.project_name_slug)
                            msg = EmailMessage(subject, html_content, sender, [member.email])
                            msg.content_subtype = "html"
                            Thread(target=lambda m: m.send(), args=(msg,)).start()

                try:
                    connection.close()
                except:
                    pass
        except Product.DoesNotExist:
            message = "Product %s was not found."
            break
    else:
        message = "%d product(s) moved to trash." % len(selection)
    response = {'message': message, 'deleted': deleted}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


def render_product_event(event, request):
    try:
        product = Product.objects.get(pk=event.object_id)
    except Product.DoesNotExist:
        return ''
    html_template = get_template('kako/events/product_notice.html')
    c = Context({'event': event, 'product': product})
    return html_template.render(c)


@permission_required('kako.ik_manage_product')
def load_product_from_url(request, *args, **kwargs):
    try:
        url = request.GET['url']
        product, merchant = get_product_from_url(url)
    except Exception as e:
        response = {'error': e.message}
    else:
        try:
            Service.objects.get(pk=merchant.id)
            image_url = from_provider(product.image, merchant)
            obj = product.to_dict()
            del(obj['photos'])
            obj['image'] = image_url
            obj['provider'] = merchant.project_name
            response = {'product': obj}
        except:
            response = {'error': _("You must add %s as a Partner Merchant to import his products." % merchant.config.company_name)}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('kako.ik_manage_product')
def save_product_from_url(request, *args, **kwargs):
    try:
        url = request.GET['url']
        product, merchant = get_product_from_url(url)
    except Exception as e:
        messages.error(request, e.message)
    else:
        try:
            Product.objects.get(pk=product.id)
        except Product.DoesNotExist:
            product.save(using='default')
        messages.success(request, _("%s successfully added" % product.name))
    return HttpResponseRedirect(reverse('kako:product_list'))


# def render_product_pushed_event(event):
#     try:
#         product = Product.objects.get(pk=event.object_id)
#     except Product.DoesNotExist:
#         return ''
#     html_template = get_template('kako/events/product_notice.html')
#     message = _("Provider removed this product. It won't appear on your website anymore.")
#     c = Context({'title': _(event.title), 'product': product, 'message': message})
#     return html_template.render(c)

