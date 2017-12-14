from django.conf import settings
from django.contrib.admin.sites import NotRegistered
from django.utils.text import slugify
from djangotoolbox.admin import admin
from django.utils.translation import gettext as _
from ikwen.accesscontrol.backends import UMBRELLA

from ikwen.flatpages.models import FlatPage

from ikwen.core.models import Service

from ikwen.billing.models import Product, Subscription, Invoice, Payment, InvoicingConfig

from ikwen.core.admin import CustomBaseAdmin

from ikwen.core.utils import get_service_instance, add_database_to_settings

from ikwen_kakocase.kakocase.models import OperatorProfile, DeliveryOption, ProductCategory

if getattr(settings, 'IS_IKWEN', False):
    _fieldsets = [
        (_('Company'), {'fields': ('company_name', 'short_description', 'slogan', 'description')}),
        (_('Business'), {'fields': ('ikwen_share_fixed', 'ikwen_share_rate',
                                    'payment_delay', 'cash_out_min', 'is_certified', )}),
        (_('Platform'), {'fields': ('can_manage_delivery_options', 'is_pro_version', 'can_manage_currencies')}),
        (_('SMS'), {'fields': ('sms_api_script_url', 'sms_api_username', 'sms_api_password', )}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature',)})
    ]
    _readonly_fields = ()
else:
    service = get_service_instance()
    config = service.config
    _readonly_fields = ('is_certified',)
    _website_fields = {'fields': ()}
    if getattr(settings, 'IS_PROVIDER', False):
        if config.is_pro_version:
            _website_fields = {'fields': ('checkout_min', 'auto_manage_sales', 'show_prices',
                                          'allow_shopping', 'return_url', 'is_certified',)}
        else:
            _website_fields = {'fields': ('checkout_min', 'auto_manage_sales', 'show_prices',
                                          'allow_shopping', 'is_certified',)}
    elif getattr(settings, 'IS_RETAILER', False):
        _website_fields = {'fields': ('checkout_min', 'auto_manage_sales', 'is_certified',)}
    elif getattr(settings, 'IS_DELIVERY_COMPANY', False):
        _website_fields = {'fields': ('auth_code', 'return_url', 'is_certified',)}
    elif getattr(settings, 'IS_BANK', False):
        _website_fields = {'fields': ('website_url', 'create_account_url', 'cashflex_eula_url', 'return_url', )}
    _fieldsets = [
        (_('Company'), {'fields': ('company_name', 'short_description', 'slogan', 'description')}),
        (_('Website'), _website_fields),
        (_('Address & Contact'), {'fields': ('contact_email', 'contact_phone', 'address', 'country', 'city')}),
        (_('Social'), {'fields': ('facebook_link', 'twitter_link', 'google_plus_link',
                                  'youtube_link', 'instagram_link', 'tumblr_link', 'linkedin_link', )}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature', )}),
    ]
    _fieldsets.extend([
        (_('External scripts'), {'fields': ('scripts', )}),
    ])


class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = ('service', 'company_name', 'ikwen_share_fixed', 'ikwen_share_rate', 'cash_out_min')
    fieldsets = _fieldsets
    readonly_fields = _readonly_fields
    search_fields = ('company_name', 'contact_email', )
    save_on_top = True

    def delete_model(self, request, obj):
        self.message_user(request, "You are not allowed to delete Configuration of the platform")


class DeliveryOptionAdmin(CustomBaseAdmin):
    add_form_template = 'admin/deliveryoption/change_form.html'
    change_form_template = 'admin/deliveryoption/change_form.html'
    list_display = ('company_name', 'type', 'short_description', 'cost', 'max_delay', 'checkout_min', 'is_active')
    fields = ('company', 'auth_code', 'type', 'name', 'short_description', 'description',
              'cost', 'max_delay', 'checkout_min', 'is_active', )
    raw_id_fields = ('company', )

    def save_model(self, request, obj, form, change):
        if not change:
            if obj.type == DeliveryOption.PICK_UP_IN_STORE:
                if DeliveryOption.objects.filter(type=DeliveryOption.PICK_UP_IN_STORE).count() >= 1:
                    self.message_user(request, _("Only one option of type <strong>Pick up in store</strong> is allowed."))
                    return
            company_id = request.POST.get('company')
            delcom = Service.objects.using(UMBRELLA).get(pk=company_id)
            delcom_config = delcom.config
            if delcom != service:
                if obj.auth_code != delcom_config.auth_code:
                    self.message_user(request, _("AUTH CODE is invalid, please verify. If the problem persists, please "
                                                 "contact %s to get the good one." % delcom_config.company_name))
                    return

            add_database_to_settings(delcom.database)
            try:
                Service.objects.using(delcom.database).get(pk=service.id)
            except Service.DoesNotExist:
                config = service.config
                service.save(using=delcom.database)
                config.save(using=delcom.database)

        obj.slug = slugify(obj.name)
        super(DeliveryOptionAdmin, self).save_model(request, obj, form, change)


class ProductCategoryAdmin(admin.ModelAdmin):
    if getattr(settings, 'IS_IKWEN', False):
        list_display = ('name', 'description', 'total_items_traded', 'total_orders_count',)
        fields = ('name', 'description', 'total_items_traded', 'total_orders_count',)
        readonly_fields = ('total_items_traded', 'total_orders_count',)
    else:
        fields = ('name', 'description', 'badge_text', 'is_active',)
        if getattr(settings, 'IS_RETAILER', False):
            readonly_fields = ('name', 'description', )

# Unregister ikwen billing models
if not getattr(settings, 'IS_UMBRELLA', False):
    try:
        admin.site.unregister(Product)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(Subscription)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(Invoice)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(Payment)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(InvoicingConfig)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(FlatPage)
    except NotRegistered:
        pass

admin.site.register(OperatorProfile, OperatorProfileAdmin)

if getattr(settings, 'IS_IKWEN', False):
    admin.site.register(ProductCategory, ProductCategoryAdmin)
else:
    admin.site.register(DeliveryOption, DeliveryOptionAdmin)
