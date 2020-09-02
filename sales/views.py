import json
from copy import copy

from datetime import datetime

from django.core.urlresolvers import reverse
from django.core.paginator import Paginator
from django.contrib import messages
from django.utils.translation import gettext as _
from django.forms.models import modelform_factory
from django.http.response import HttpResponse
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib.admin import helpers
from django.views.generic import TemplateView
from import_export.formats.base_formats import XLS

from ikwen.core.views import HybridListView, ChangeObjectBase
from ikwen.core.utils import get_model_admin_instance

from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kakocase.models import ProductCategory
from ikwen_kakocase.sales.models import Promotion, PromoCode, CustomerEmail
from ikwen_kakocase.sales.admin import PromotionAdmin, PromoCodeAdmin, CustomerEmailResource


class PromotionList(HybridListView):
    template_name = 'sales/promotion_list.html'
    html_results_template_name = 'sales/snippets/promotion_list_results.html'
    queryset = Promotion.objects.all()
    ordering = ('-updated_on', )
    search_field = 'title'
    context_object_name = 'promotion_list'

    def get_context_data(self, **kwargs):
        queryset = self.get_queryset()
        context = super(PromotionList, self).get_context_data(**kwargs)
        paginator = Paginator(queryset, self.page_size)
        objects_page = paginator.page(1)
        context['q'] = self.request.GET.get('q')
        context['objects_page'] = objects_page
        return context


class PromoCodeList(HybridListView):
    model = PromoCode
    search_field = 'code'


class ChangePromoCode(ChangeObjectBase):
    model = PromoCode
    model_admin = PromoCodeAdmin


class ChangePromotion(TemplateView):
    template_name = 'sales/change_promotion.html'

    def get_context_data(self, **kwargs):
        context = super(ChangePromotion, self).get_context_data(**kwargs)
        promotion_id = kwargs.get('promotion_id')  # May be overridden with the one from GET data
        promotion_id = self.request.GET.get('promotion_id', promotion_id)
        promotion = None
        if promotion_id:
            promotion = get_object_or_404(Promotion, pk=promotion_id)
        promotion_admin = get_model_admin_instance(Promotion, PromotionAdmin)
        ModelForm = modelform_factory(Promotion, fields=('title', 'start_on', 'end_on', 'rate', 'is_active', 'item',
                                                         'category'))
        form = ModelForm(instance=promotion)
        promotion_form = helpers.AdminForm(form, list(promotion_admin.get_fieldsets(self.request)),
                                           promotion_admin.get_prepopulated_fields(self.request),
                                           promotion_admin.get_readonly_fields(self.request, obj=promotion))
        context['promotion'] = promotion
        context['model_admin_form'] = promotion_form
        return context

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        promotion_id = request.POST.get('promotion_id')
        if promotion_id:
            promotion = get_object_or_404(Promotion, pk=promotion_id)
        else:
            promotion = Promotion()
        promotion_admin = get_model_admin_instance(Promotion, PromotionAdmin)
        ModelForm = promotion_admin.get_form(self.request)
        form = ModelForm(request.POST, instance=promotion)
        start_date = request.POST.get('start_on')
        end_date = request.POST.get('end_on')
        if len(start_date) > 16:
            start_date = start_date[:-3].strip()
        if len(end_date) > 16:
            end_date = end_date[:-3].strip()
        start_on = datetime.strptime(start_date, '%Y-%m-%d %H:%M')
        end_on = datetime.strptime(end_date, '%Y-%m-%d %H:%M')

        title = request.POST.get('title')
        rate = request.POST.get('rate')
        is_active = request.POST.get('is_active')
        category_id = request.POST.get('category')
        item_id = request.POST.get('item')
        if title:
            promotion.title = title
            promotion.start_on = start_on
            promotion.end_on = end_on
            promotion.rate = rate
            promotion.is_active = is_active
            if category_id:
                promotion.category = get_object_or_404(ProductCategory, pk=category_id)
            else:
                promotion.category = None
            if item_id:
                promotion.item = get_object_or_404(Product, pk=item_id)
            else:
                promotion.item = None
            promotion.save()
            next_url = reverse('sales:promotion_list')
            if promotion_id:
                messages.success(request, _("Promotion %s successfully updated." % promotion.title))
            else:
                messages.success(request, _("Promotion %s successfully created." %  promotion.title))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


def apply_promotion_discount(product_list):
    # product_list = list(product_list)
    copy_product_list = copy(product_list)
    final_product_result = []
    now = datetime.now()
    for product in copy_product_list:
        # Promotion on specific items
        try:
            promo = Promotion.objects.filter(item=product, rate__gt=0, start_on__lte=now,
                                             end_on__gt=now, is_active=True).order_by('-id')[0]
        except IndexError:
            continue
        else:
            product.on_sale = True
            product.previous_price = product.retail_price
            retail_price = product.retail_price - product.retail_price * promo.rate / 100
            product.retail_price = retail_price

            final_product_result.append(product)
            product_list.remove(product)

    copy_product_list = copy(product_list)
    for product in copy_product_list:
        # Promotion on specific category
        category = product.category
        try:
            promo = Promotion.objects.filter(category=category, rate__gt=0, start_on__lte=now,
                                             end_on__gt=now, is_active=True).order_by('-id')[0]
        except IndexError:
            continue
        else:
            product.on_sale =True
            product.previous_price = product.retail_price
            retail_price = product.retail_price - product.retail_price * promo.rate / 100
            product.retail_price = retail_price

            final_product_result.append(product)
            product_list.remove(product)

    copy_product_list = copy(product_list)
    try:
        # promotion on the whole website
        promo = Promotion.objects.filter(item=None, rate__gt=0, category=None, start_on__lte=now,
                                         end_on__gt=now, is_active=True).order_by('-id')[0]
        for product in copy_product_list:
            product.on_sale = True
            product.previous_price = product.retail_price
            retail_price = product.retail_price - product.retail_price * promo.rate / 100
            product.retail_price = retail_price

            final_product_result.append(product)
            product_list.remove(product)
    except IndexError:
        pass

    for product in product_list:
        final_product_result.append(product)
    return final_product_result


def find_promo_code(request, *args, **kwargs):
    code = request.GET.get('code')
    try:
        promo_code = PromoCode.objects.get(code__iexact=code)
    except PromoCode.DoesNotExist:
        response = HttpResponse(json.dumps({
            'error': 'Invalid promo code',
            'message': 'Invalid promo code',
        }), 'content-type: text/json')
    else:
        request.session['promo_code'] = promo_code.to_dict()
        response = HttpResponse(json.dumps({'success': True}), 'content-type: text/json')
    return response


def toggle_object_attribute(request, *args, **kwargs):
    object_id = request.GET['object_id']
    attr = request.GET['attr']
    val = request.GET['val']
    try:
        obj = PromoCode.objects.get(pk=object_id)
    except PromoCode.DoesNotExist:
        obj = Promotion.objects.get(pk=object_id)
    if val.lower() == 'true':
        obj.__dict__[attr] = True
    else:
        obj.__dict__[attr] = False
    obj.save()
    response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


def delete_promo_object(request, *args, **kwargs):
    pk = request.GET.get('selection')
    try:
        PromoCode.objects.get(pk=pk).delete()
        message = "Item successfully deleted."
    except PromoCode.DoesNotExist:
        try:
            Promotion.objects.get(pk=pk).delete()
            message = "Item successfully deleted."
        except Promotion.DoesNotExist:
            message = "Object was not found."

    response = {'message': message}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


def save_customer_email(request, *args, **kwargs):
    email = (request.GET.get('email')).lower()
    try:
        CustomerEmail.objects.get(email=email)
    except CustomerEmail.DoesNotExist:
        customer_email = CustomerEmail(email=email)
        customer_email.save()
        response = HttpResponse(json.dumps(
            {'success': True,}), 'content-type: text/json')
    else:
        response = HttpResponse(json.dumps(
            {'error': 'Existing email',}), 'content-type: text/json')
    return response


class EmailList(HybridListView):
    template_name = 'sales/email_list.html'
    model = CustomerEmail
    queryset = CustomerEmail.objects.all()
    ordering = ('id', )
    context_object_name = 'email_list'

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'export':
            return self.export(request, *args, **kwargs)
        return super(EmailList, self).get(request, *args, **kwargs)

    def get_export_filename(self, file_format):
        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = "%s-%s.%s" % (self.model.__name__,
                                 date_str,
                                 file_format.get_extension())
        return filename

    def export(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        file_format = XLS()
        data = CustomerEmailResource().export(queryset)
        export_data = file_format.export_data(data)
        content_type = file_format.get_content_type()
        # Django 1.7 uses the content_type kwarg instead of mimetype
        try:
            response = HttpResponse(export_data, content_type=content_type)
        except TypeError:
            response = HttpResponse(export_data, mimetype=content_type)
        response['Content-Disposition'] = 'attachment; filename=%s' % (
            self.get_export_filename(file_format),
        )
        return response

    def get_context_data(self, **kwargs):
        context = super(EmailList, self).get_context_data(**kwargs)
        queryset = self.get_queryset().all()
        page_size = 15 if self.request.user_agent.is_mobile else 25
        paginator = Paginator(queryset, page_size)
        emails_page = paginator.page(1)
        context['emails_page'] = emails_page
        return context
