from django.template.defaultfilters import slugify
from ikwen.core.admin import CustomBaseAdmin
from import_export import resources

from ikwen_kakocase.kakocase.models import ProductCategory
from ikwen_kakocase.kako.models import Product, RecurringPaymentService
from django.contrib import admin

from ikwen_kakocase.kakocase.models import IS_PROVIDER, IS_RETAILER


class ProductResource(resources.ModelResource):

    def import_field(self, field, obj, data):
        if field.column_name == 'category':
            slug = slugify(data['category'])
            try:
                category = ProductCategory.objects.get(slug=slug)
            except ProductCategory.DoesNotExist:
                name = data['category']
                from kako.utils import create_category
                category = create_category(name)
            data['category'] = category.id
        super(ProductResource, self).import_field(field, obj, data)

    def before_save_instance(self, instance, dry_run):
        slug = slugify(instance.name)
        instance.slug = slug
        instance.tags = slug.replace('-', ' ')
        instance.visible = False
        instance.provider = self.provider
        instance.retail_price_is_modifiable = self.retail_price_is_modifiable
        instance.batch_upload = self.batch_upload

    def skip_row(self, instance, original):
        try:
            if instance.reference:
                Product.objects.get(reference=instance.reference)
                return True
            return False
        except Product.DoesNotExist:
            return False

    class Meta:
        model = Product
        skip_unchanged = True
        # fields = ('category', 'name', 'reference', 'wholesale_price', 'retail_price', 'max_price')


class ProductAdmin(admin.ModelAdmin):
    fields = ('provider', 'category', 'name', 'brand', 'wholesale_price', 'retail_price', 'max_price', 'packing_price', 'size', 'color', 'weight', 'badge_text', 'stock', 'visible', 'summary', 'description', ) if IS_RETAILER \
        else ('category', 'name', 'brand', 'wholesale_price', 'retail_price', 'max_price', 'packing_price', 'retail_price_is_modifiable',
              'reference', 'original_id', 'size', 'color', 'weight', 'stock', 'unit_of_measurement', 'min_order', 'badge_text', 'summary', 'description','visible', )
    fieldsets = (
        (None, {'fields': ('provider', 'category', 'name', 'brand', 'wholesale_price', 'retail_price', 'max_price', 'packing_price', 'size', 'color', 'weight', 'badge_text', 'stock', 'visible', 'summary', 'description', ) if IS_RETAILER
        else ('category', 'name', 'brand', 'wholesale_price', 'retail_price', 'max_price', 'packing_price', 'retail_price_is_modifiable',
              'reference', 'original_id', 'size', 'color', 'weight', 'stock', 'unit_of_measurement', 'min_order', 'badge_text', 'summary', 'description',
              'visible',)}),
    )

    def get_readonly_fields(self, request, obj=None):
        if IS_PROVIDER:
            return ()
        ro = ['provider', 'category', 'name', 'brand', 'wholesale_price', 'summary', 'description',
              'max_price', 'packing_price', 'size', 'color', 'weight', 'stock', 'visible']
        if not obj.retail_price_is_modifiable:
            ro.append('retail_price')
        return ro


class RecurringPaymentServiceAdmin(CustomBaseAdmin):
    readonly_fields = ('provider', )
