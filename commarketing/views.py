import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.core.urlresolvers import reverse
from django.forms.models import modelform_factory
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import TemplateView

from ikwen_kakocase.commarketing.admin import SmartCategoryAdmin, BannerAdmin
from ikwen_kakocase.kakocase.views import SortableListMixin

from ikwen.accesscontrol.templatetags.auth_tokens import append_auth_tokens

from ikwen_kakocase.commarketing.models import Banner, SmartCategory, CATEGORIES, SLIDE, POPUP, FULL_WIDTH_SECTION, \
    FULL_SCREEN_POPUP, TILES
from ikwen.core.utils import get_model_admin_instance
from ikwen.core.views import HybridListView
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kakocase.models import ProductCategory

BANNER = 'banner'
SMART_CATEGORY = 'smartcategory'


class BannerList(SortableListMixin, TemplateView):
    template_name = 'commarketing/banner_list.html'
    model = Banner
    search_field = 'title'
    ordering = ('-updated_on', )

    def get_context_data(self, **kwargs):
        context = super(BannerList, self).get_context_data(**kwargs)
        context['slide_list'] = Banner.objects.filter(display=SLIDE).order_by('order_of_appearance')
        context['tiles_list'] = Banner.objects.filter(display=TILES).order_by('order_of_appearance')
        context['popup_list'] = Banner.objects.filter(display=POPUP)
        context['fw_section_list'] = Banner.objects.filter(display=FULL_WIDTH_SECTION)
        context['fs_popup_list'] = Banner.objects.filter(display=FULL_SCREEN_POPUP)
        return context


class SmartCategoryList(SortableListMixin, HybridListView):
    template_name = 'commarketing/smart_category_list.html'
    model = SmartCategory
    search_field = 'title'
    ordering = ('order_of_appearance', '-updated_on', )
    context_object_name = 'smart_category_list'


class ChangeSmartObject(TemplateView):
    template_name = 'commarketing/change_smart_object.html'

    def get_context_data(self, **kwargs):
        context = super(ChangeSmartObject, self).get_context_data(**kwargs)
        object_type = kwargs.get('object_type')
        smart_object_id = kwargs.get('smart_object_id')  # May be overridden with the one from GET data
        smart_object_id = self.request.GET.get('smart_object_id', smart_object_id)
        smart_object = None
        if object_type == BANNER:
            model = Banner
            model_admin = BannerAdmin
            fields = ("title", "display", "cta", "content_type")
        else:
            model = SmartCategory
            model_admin = SmartCategoryAdmin
            fields = ("title", "content_type", "description", "badge_text")
        if smart_object_id:
            smart_object = get_object_or_404(model, pk=smart_object_id)
            if smart_object.content_type == CATEGORIES:
                smart_object.content = [ProductCategory.objects.get(pk=pk) for pk in smart_object.items_fk_list]
            else:
                try:
                    smart_object.content = [Product.objects.get(pk=pk) for pk in smart_object.items_fk_list]
                except Product.DoesNotExist:
                    # smart_object.content = [RecurringPaymentService.objects.get(pk=pk) for pk in smart_object.items_fk_list]
                    smart_object.content = []
        object_admin = get_model_admin_instance(model, model_admin)
        ModelForm = modelform_factory(model, fields=fields)
        form = ModelForm(instance=smart_object)
        model_admin_form = helpers.AdminForm(form, list(object_admin.get_fieldsets(self.request)),
                                             object_admin.get_prepopulated_fields(self.request))
        context['object_type'] = object_type
        context['smart_object'] = smart_object
        context['model_admin_form'] = model_admin_form
        return context

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        object_type = kwargs.get('object_type')
        smart_object_id = request.POST['smart_object_id']
        smart_object = None
        if object_type == BANNER:
            model = Banner
            model_admin = BannerAdmin
        else:
            model = SmartCategory
            model_admin = SmartCategoryAdmin
        if smart_object_id:
            smart_object = get_object_or_404(model, pk=smart_object_id)
        category_admin = get_model_admin_instance(model, model_admin)
        ModelForm = category_admin.get_form(self.request)
        form = ModelForm(request.POST, instance=smart_object)
        if form.is_valid():
            title = form.cleaned_data['title']
            slug = slugify(title)
            try:
                model.objects.get(slug=slug)
                context = self.get_context_data(**kwargs)
                context['errors'] = _("Smart object with title %s already exists" % title)
                return render(request, self.template_name, context)
            except ObjectDoesNotExist:
                pass
            content_type = form.cleaned_data['content_type']
            description = form.cleaned_data.get('description')
            badge_text = form.cleaned_data.get('badge_text')
            order = form.cleaned_data.get('order_of_appearance')
            display = form.cleaned_data.get('display')
            image_url = request.POST.get('image_url')
            cta = request.POST.get('cta')
            if not smart_object:
                smart_object = model()
            smart_object.title = title
            smart_object.content_type = content_type
            smart_object.slug = slug
            if description:
                smart_object.description = description
            if badge_text:
                smart_object.badge_text = badge_text
            if order:
                smart_object.order_of_appearance = order
            if display:
                smart_object.display = display
            if cta:
                smart_object.cta = cta
            smart_object.save()

            if image_url:
                if not smart_object.image.name or image_url != smart_object.image.url:
                    filename = image_url.split('/')[-1]
                    media_root = getattr(settings, 'MEDIA_ROOT')
                    media_url = getattr(settings, 'MEDIA_URL')
                    image_url = image_url.replace(media_url, '')
                    try:
                        with open(media_root + image_url, 'r') as f:
                            content = File(f)
                            destination = media_root + SmartCategory.UPLOAD_TO + "/" + filename
                            smart_object.image.save(destination, content)
                        os.unlink(media_root + image_url)
                    except IOError as e:
                        if getattr(settings, 'DEBUG', False):
                            raise e
                        return {'error': 'File failed to upload. May be invalid or corrupted image file'}
            if smart_object_id:
                next_url = reverse('marketing:change_smart_object', args=(object_type, smart_object_id, ))
                messages.success(request, _("Category %s successfully updated." % smart_object.title))
            else:
                next_url = reverse('marketing:change_smart_object', args=(object_type, ))
                messages.success(request, _("Category %s successfully created." % smart_object.title))
            next_url = append_auth_tokens(next_url, request)
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


@permission_required('commarketing.ik_manage_marketing')
def set_smart_object_content(request, action, *args, **kwargs):
    smart_object_id = request.GET['smart_object_id']
    selection = request.GET['selection'].split(',')
    try:
        smart_object = Banner.objects.get(pk=smart_object_id)
        next_url = reverse('marketing:change_smart_object', args=(BANNER, smart_object_id, ))
        messages.success(request, _("Banner %s successfully saved." % smart_object.title))
    except Banner.DoesNotExist:
        smart_object = get_object_or_404(SmartCategory, pk=smart_object_id)
        next_url = reverse('marketing:change_smart_object', args=(SMART_CATEGORY, smart_object_id, ))
        messages.success(request, _("Smart Category %s successfully saved." % smart_object.title))
    if action == 'add':
        smart_object.items_fk_list = selection
        response = HttpResponseRedirect(next_url)
    elif action == 'remove':
        deleted = []
        for pk in selection:
            try:
                smart_object.items_fk_list.remove(pk)
                deleted.append(pk)
            except ValueError:
                pass
        message = "%d item(s) deleted." % len(deleted)
        response = HttpResponse(json.dumps({'message': message, 'deleted': deleted}), 'content-type: text/json')
    smart_object.items_count = len(smart_object.items_fk_list)
    smart_object.save()
    return response


@permission_required('commarketing.ik_manage_marketing')
def toggle_smart_object_attribute(request, *args, **kwargs):
    object_id = request.GET['object_id']
    attr = request.GET['attr']
    val = request.GET['val']
    try:
        obj = SmartCategory.objects.get(pk=object_id)
    except SmartCategory.DoesNotExist:
        obj = Banner.objects.get(pk=object_id)
    if val.lower() == 'true':
        obj.__dict__[attr] = True
    else:
        obj.__dict__[attr] = False
    obj.save()
    response = {'success': True}
    return HttpResponse(json.dumps(response), 'content-type: text/json')


@permission_required('commarketing.ik_manage_marketing')
def delete_smart_object(request, *args, **kwargs):
    selection = request.GET['selection'].split(',')
    deleted = []
    for pk in selection:
        try:
            Banner.objects.get(pk=pk).delete()
            deleted.append(pk)
        except Banner.DoesNotExist:
            try:
                SmartCategory.objects.get(pk=pk).delete()
                deleted.append(pk)
            except SmartCategory.DoesNotExist:
                message = "Object %s was not found."
                break
    else:
        message = "%d item(s) deleted." % len(deleted)
    response = {'message': message, 'deleted': deleted}
    return HttpResponse(json.dumps(response), 'content-type: text/json')
