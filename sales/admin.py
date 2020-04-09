from django.conf import settings
from django.contrib import admin
from ikwen_kakocase.sales.models import Promotion, PromoCode, CustomerEmail

from import_export import resources, fields


class CustomerEmailResource(resources.ModelResource):
    email = fields.Field(column_name='Email')
    created_on = fields.Field(column_name='Created on')

    class Meta:
        model = CustomerEmail
        fields = ('email', 'created_on', )
        export_order = ('email', 'created_on', )

    def dehydrate_email(self, obj):
        return obj.email

    def dehydrate_created_on(self, obj):
        return obj.created_on.strftime('%y-%m-%d %H:%M')


class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_on', 'end_on', 'rate', 'item', 'category')
    search_fields = ('title', 'item', )
    save_on_top = True


class PromoCodeAdmin(admin.ModelAdmin):
    fields = ('code', 'start_on', 'end_on', 'rate', 'is_active')


class GrouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'item', 'cost', 'objective', 'actual_count', 'start_on', 'end_on', 'is_active')
    search_fields = ('code',)
    save_on_top = True


if not getattr(settings, 'IS_IKWEN', False):
    admin.site.register(Promotion, PromotionAdmin)
    admin.site.register(PromoCode, PromoCodeAdmin)
