import os

from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.utils.translation import gettext_lazy as _
from djangotoolbox.fields import ListField, EmbeddedModelField

from ikwen.core.fields import MultiImageField
from ikwen.core.models import AbstractWatchModel, Service
from ikwen.core.utils import to_dict
from ikwen_kakocase.kakocase.models import ProductCategory, IS_PROVIDER, IS_RETAILER

wholesale_price_help_text = _("Your wholesale price. Retailers may set their own price.") if IS_PROVIDER\
    else _("Wholesale price of the provider")
retail_price_help_text = _("Price at which retailers must sell this product on their website. "
                           "If set, retailers will not be allowed to set their own price.") if IS_PROVIDER\
    else _("Your retail price.")
max_price_help_text = _("Maximum price at which retailers must sell this product on "
                        "their website. If given, then <em class='text-primary'>retail price</em> must be left blank.") if IS_PROVIDER\
    else _("Maximum retail price allowed by your provider.")


class AbstractProduct(AbstractWatchModel):
    """
    Base class for a :class:`Product` or :class:`RecurringPaymentService`
    offered by a :class:`profile.models.Provider` and retailed by other people.
    """
    provider = models.ForeignKey(Service, editable=IS_RETAILER, related_name='+')
    category = models.ForeignKey(ProductCategory)
    name = models.CharField(max_length=100, db_index=True,
                            help_text=_("Name of the product."))
    slug = models.SlugField(editable=False,
                            help_text=_("Slug of the product."))
    brand = models.CharField(max_length=60, db_index=True, blank=True, null=True,
                             help_text=_("Brand of the product."))
    summary = models.TextField(blank=True, null=True,
                               help_text=_("Summary of the product."))
    description = models.TextField(blank=True, null=True,
                                   help_text=_("Description of the product."))
    badge_text = models.CharField(max_length=25, blank=True, null=True,
                                  help_text=_("Text in the badge that appears on the product. "
                                              "<strong>E.g.:</strong> -20%, -30%, New, etc."))
    reference = models.CharField(max_length=60, db_index=True, blank=True, null=True, editable=IS_PROVIDER,
                                 help_text=_("Reference number of the product as in your current IS."))
    original_id = models.CharField(max_length=30, db_index=True, blank=True, null=True, editable=IS_PROVIDER,
                                   help_text=_("ID of the product in your current database."))
    photos = ListField(EmbeddedModelField('Photo'), editable=False)
    # PRICES
    wholesale_price = models.FloatField(blank=IS_RETAILER, null=IS_RETAILER, help_text=wholesale_price_help_text)
    retail_price = models.FloatField(blank=True, null=True, help_text=retail_price_help_text)
    max_price = models.FloatField(blank=True, null=True, help_text=max_price_help_text)
    retail_price_is_modifiable = models.BooleanField(_("modifiable price ?"), editable=IS_PROVIDER, default=True,
                                                     help_text="If True, retailer can set his own retail price. "
                                                               "Otherwise, retailer will be forced to set the retail "
                                                               "price you have set.")

    # SALE INFORMATION: They are automatically set whenever retail_price is updated
    on_sale = models.BooleanField(default=False, editable=False,
                                  help_text="Whether or not this product is on sale.")
    previous_price = models.IntegerField(blank=True, null=True, editable=False,
                                         help_text="Previous retail price when retail_price is updated.")

    total_rating = models.IntegerField(default=0, blank=True, null=True,
                                       help_text="The sum of all rating ever given.")
    rating_count = models.IntegerField(default=0, blank=True, null=True,
                                       help_text="The number of times product was rated.")

    # TODO: Deal with information below to manage wholesale purchases in next version
    # WHOLESALE INFORMATION
    # self_sale_price = models.FloatField(blank=True, null=True,
    #                                help_text=_("Retail price at which the provider sells on his own website."))
    # measurement = models.CharField(max_length=30, blank=True,
    #                                help_text=_("Unit of measurement to sell this product in wholesale. Eg: crate"))
    # measurement_units_equivalent = models.IntegerField(blank=True, null=True,
    #                                                    help_text=_("Number of units contained in one measurement."
    #                                                                "Eg: 1 crate=12 bottles, so input 12."))
    # measurement_unit_price = models.IntegerField(blank=True, null=True,
    #                                              help_text=_("Price of a unit of measurement of this product."))
    # min_quantity = models.IntegerField(default=1,
    #                                    help_text=_("Minimum number of units of measurement to purchase in wholesale."))

    # Accessibility information
    visible = models.BooleanField(default=True)
    tags = models.CharField(max_length=255, db_index=True, blank=True, editable=False)
    in_trash = models.BooleanField(default=False, editable=False)
    is_retailed = models.BooleanField(default=False, editable=False)  # If True, prices cannot be modified by Provider

    # A list of 366 integer values, each of which representing the number of units
    # of this product sold on a day of the 366 previous (current day being the last)
    units_sold_history = ListField()

    total_units_sold = models.IntegerField(default=0,
                                           help_text="Number of units sold since online.")

    class Meta:
        abstract = True

    def __unicode__(self):
        return self.name

    def _get_image(self):
        return self.photos[0].image if len(self.photos) > 0 else None
    image = property(_get_image)

    def get_photos_url_list(self):
        photo_list = []
        for photo in self.photos:
            photo_list.append({
                'original': photo.image.url,
                'small': photo.image.small_url,
                'thumb': photo.image.thumb_url
            })
        return photo_list

    def get_photos_ids_list(self):
        return ','.join([photo.id for photo in self.photos])

    def get_rating(self):
        if self.rating_count:
            return self.total_rating / self.rating_count
        return 0

    def delete(self, *args, **kwargs):
        for photo in self.photos:
            photo.delete(*args, **kwargs)
        from ikwen_kakocase.commarketing.models import Banner, SmartCategory
        for banner in Banner.objects.all():
            try:
                banner.items_fk_list.remove(self.id)
                banner.items_count = banner.get_product_queryset().count()
                banner.save()
            except ValueError:
                pass
        for smart_category in SmartCategory.objects.all():
            try:
                smart_category.items_fk_list.remove(self.id)
                smart_category.items_count = smart_category.get_product_queryset().count()
                smart_category.save()
            except ValueError:
                pass
        for obj in ProductCategory.objects.all():
            obj.items_count = obj.product_set.filter(in_trash=False).count()
            obj.save()
        super(AbstractProduct, self).delete(*args, **kwargs)

    def to_dict(self):
        var = to_dict(self)
        var['image'] = self.image.url if self.image and self.image.name else ''
        var['url'] = reverse('kako:change_product', args=(self.id, ))
        del(var['units_sold_history'])
        del(var['tags'])
        return var


class Product(AbstractProduct):
    size = models.CharField(max_length=30, blank=True, null=True,
                            help_text=_("Size in custom unit of measurement for this product."))
    # TODO: Manage colors the smooth way
    color = models.CharField(max_length=30, blank=True, null=True,
                             help_text=_("Color of product as hexadecimal code."))
    weight = models.CharField(max_length=30, blank=True, null=True,
                              help_text=_("Weight in grams."))
    stock = models.IntegerField(blank=True, null=True,
                                help_text=_("Stock of the product."))
    unit_of_measurement = models.CharField(max_length=60, blank=True, null=True,
                                           help_text=_("Unit of measurement for this product."))
    min_order = models.IntegerField(default=1,
                                    help_text=_("Minimum number of units one can order. Excellent for wholesale."))
    batch_upload = models.ForeignKey('BatchUpload', blank=True, null=True, editable=False)

    # Django ORM does not support .distinct() with MongoDB Backend.
    # This field helps track which objects are duplicates of another
    # The field is set upon the saving and deleting an object using
    # :func:`kako.utils.mark_duplicates`
    is_duplicate = models.BooleanField(default=False, editable=False)

    class Meta:
        permissions = (
            ("ik_manage_product", _("Manage products")),
        )

    def delete(self, *args, **kwargs):
        super(Product, self).delete(*args, **kwargs)
        from ikwen_kakocase.kako.utils import mark_duplicates
        mark_duplicates(self)

    def get_size_list(self):
        """
        Grabs sizes for product of the same category having the same slug
        """
        size_list = set([p.size for p in Product.objects.filter(category=self.category, brand=self.brand,
                                                                slug=self.slug, stock__gt=0).order_by('id')
                         if p.size])
        size_list_obj = []
        for size in size_list:
            try:
                obj = Product.objects.filter(category=self.category, brand=self.brand, slug=self.slug, size=size)[0]
                size_list_obj.append({'label': obj.size, 'stock': obj.stock, 'retail_price': obj.retail_price,
                                      'id': obj.pk, 'wholesale_price': obj.wholesale_price, 'max_price': obj.max_price})
            except:
                pass
        return size_list_obj

    def get_size_list_label(self):
        """
        A string version of get_size_list suited for display
        """
        return ' / '.join([obj['label'] for obj in self.get_size_list()])

    # def get_color_list(self):
    #     """
    #     Grabs colors for product of the same category having the same slug and same size
    #     """
    #     return list(set([p.color for p in Product.objects.filter(category=self.category, brand=self.brand, size=self.size,
    #                                                              slug=self.slug, stock__gte=0).order_by('id')
    #                      if p.color]))


class RecurringPaymentService(AbstractProduct):
    """
    Service an end user may subscribe to through the :class:`people.models.Retailer`

    :attr:duration duration in number of days that the payment covers
    :attr:duration_text Equivalent of the duration suitable for display
    """
    duration = models.IntegerField()
    duration_text = models.CharField(max_length=30)


class Photo(models.Model):
    UPLOAD_TO = 'kako/photos'
    PLACE_HOLDER = 'no_photo.png'
    image = MultiImageField(upload_to=UPLOAD_TO, max_size=800)

    def delete(self, *args, **kwargs):
        try:
            os.unlink(self.image.path)
            os.unlink(self.image.small_path)
            os.unlink(self.image.thumb_path)
        except:
            pass
        super(Photo, self).delete(*args, **kwargs)

    def __unicode__(self):
        return self.image.url


class BatchUpload(models.Model):
    UPLOAD_TO = 'kako/batch_uploads'
    spreadsheet = models.FileField(upload_to=UPLOAD_TO)

    def delete(self, *args, **kwargs):
        os.unlink(self.spreadsheet.path)
        super(BatchUpload, self).delete(*args, **kwargs)

    def __unicode__(self):
        return self.spreadsheet


def update_category_items_count(sender, **kwargs):
    """
    Receiver of the post_save signals of Product.
    It resets the ProductCategory.items_count accordingly
    """
    if sender != Product:  # Avoid unending recursive call
        return
    for obj in ProductCategory.objects.all():
        obj.items_count = obj.product_set.filter(in_trash=False).count()
        obj.save()


def update_product_containers_items_count(sender, **kwargs):
    """
    Receiver of the post_delete signals of Product. It resets the 
    ProductCategory.items_count and SmartCategory.items_fk_list accordingly
    """
    if sender != Product:  # Avoid unending recursive call
        return
    for obj in ProductCategory.objects.all():
        obj.items_count = obj.product_set.filter(in_trash=False).count()
        obj.save()
    instance = kwargs['instance']
    from ikwen_kakocase.commarketing.models import Banner, SmartCategory
    for obj in Banner.objects.all():
        if instance.id in obj.items_fk_list:
            obj.items_fk_list.remove(instance.id)
        obj.items_count = len(obj.items_fk_list)
        obj.save()
    for obj in SmartCategory.objects.all():
        if instance.id in obj.items_fk_list:
            obj.items_fk_list.remove(instance.id)
        obj.items_count = len(obj.items_fk_list)
        obj.save()

post_save.connect(update_category_items_count, dispatch_uid="product_post_save_id")
post_delete.connect(update_product_containers_items_count, dispatch_uid="product_post_delete_id")
