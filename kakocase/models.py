import os

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from djangotoolbox.fields import ListField, EmbeddedModelField
from ikwen.core.fields import MultiImageField
from ikwen.billing.models import SupportBundle, CloudBillingPlan

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.models import Model, AbstractConfig, AbstractWatchModel, Service
from ikwen.theming.models import Theme
from ikwen.core.utils import to_dict, add_database_to_settings, set_counters, increment_history_field

# Number of seconds since the Order was issued, that the Retailer
# has left to commit to deliver the customer himself. After that
# time, delivery will be automatically assigned to a logistics company
TIME_LEFT_TO_COMMIT_TO_SELF_DELIVERY = 6 * 3600
CASH_OUT_MIN = getattr(settings, 'KAKOCASE_CASH_OUT_MIN', 5000)

# ikwen.ikwen_kakocase.ConsoleEventType Code names
PROVIDER_ADDED_PRODUCTS_EVENT = 'ProviderAddedProductsEvent'
PROVIDER_REMOVED_PRODUCT_EVENT = 'ProviderRemovedProductEvent'
PROVIDER_PUSHED_PRODUCT_EVENT = 'ProviderPushedProductEvent'
LOW_STOCK_EVENT = 'LowStockEvent'
SOLD_OUT_EVENT = 'SoldOutEvent'
INSUFFICIENT_STOCK_EVENT = 'InsufficientStockEvent'
NEW_ORDER_EVENT = 'NewOrderEvent'
ORDER_SHIPPED_EVENT = 'OrderShippedEvent'
ORDER_PACKAGED_EVENT = 'OrderPackagedEvent'  # Case of Pick up in store
PRODUCTS_LIMIT_ALMOST_REACHED_EVENT = 'ProductsLimitAlmostReached'
PRODUCTS_LIMIT_REACHED_EVENT = 'ProductsLimitReached'
PRODUCT_PUBLISHED_EVENT = 'ProductPublished'
# End Code names


IS_PROVIDER = getattr(settings, 'IS_PROVIDER', False)
IS_RETAILER = getattr(settings, 'IS_RETAILER', False)
IS_DELIVERY_COMPANY = getattr(settings, 'IS_DELIVERY_COMPANY', False)
PRODUCTS_PREVIEWS_PER_ROW = getattr(settings, 'PRODUCTS_PREVIEWS_PER_ROW', 4)
CATEGORIES_PREVIEWS_PER_ROW = getattr(settings, 'CATEGORIES_PREVIEWS_PER_ROW', 3)


class TsunamiBundle(Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.CharField(max_length=100, unique=True)
    sms_count = models.IntegerField()
    early_payment_sms_count = models.IntegerField(default=0)
    mail_count = models.IntegerField()
    early_payment_mail_count = models.IntegerField(default=0)
    cost = models.IntegerField()
    support_bundle = models.ForeignKey(SupportBundle, blank=True, null=True)
    billing_plan = models.ForeignKey(CloudBillingPlan, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)


class City(Model):
    name = models.CharField(max_length=60)

    class Meta:
        app_label = 'kakocase'

    def __unicode__(self):
        return self.name


class ProductCategory(AbstractWatchModel):
    """
    Category of :class:`kako.models.Product`. User must select the category from
    a list so, upon installation of the project some categories must be set.
    """
    UPLOAD_TO = 'kakocase/categories'
    PLACE_HOLDER = 'no_photo.png'
    name = models.CharField(_("name"), max_length=100, unique=True,
                            help_text=_("Name of the category."))
    slug = models.SlugField(unique=True,
                            help_text=_("Slug of the category."))
    description = models.TextField(_("description"), blank=True,
                                   help_text=_("Description of the category."))
    badge_text = models.CharField(_("badge text"), max_length=25, blank=True,
                                  help_text=_("Text in the badge that appears on the category. "
                                              "<strong>E.g.:</strong> -20%, -30%, New, etc."))
    appear_in_menu = models.BooleanField(_("appear in menu"), default=False,
                                         help_text=_("Category will appear in main menu if checked."))
    is_active = models.BooleanField(verbose_name="Active ?", default=True,
                                    help_text=_("Make it visible or no."))
    order_of_appearance = models.IntegerField(default=1,
                                              help_text=_("Order of appearance in a list of categories."))
    previews_count = models.IntegerField(_("elements in preview"), default=PRODUCTS_PREVIEWS_PER_ROW,
                                         help_text=_("Number of elements in the category preview on home page. "
                                                     "Must be a multiple of 4."))
    items_count = models.IntegerField(default=0, editable=False,
                                      help_text="Number of products in this category.")
    image = MultiImageField(upload_to=UPLOAD_TO, blank=True, null=True, max_size=500)
    # A list of 366 integer values, each of which representing the number of items of this category
    # that were traded (sold or delivered) on a day out of the 366 previous (current day being the last)
    items_traded_history = ListField()
    turnover_history = ListField()
    earnings_history = ListField()
    orders_count_history = ListField()

    # SUMMARY INFORMATION
    total_items_traded = models.IntegerField(default=0)
    total_turnover = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)
    total_orders_count = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = 'product categories'

    def __unicode__(self):
        return self.name

    def report_counters_to_umbrella(self):
        try:
            umbrella_obj = ProductCategory.objects.using(UMBRELLA).get(slug=self.slug)
        except:
            umbrella_obj = ProductCategory.objects.using(UMBRELLA).create(name=self.name, slug=self.slug)
        set_counters(umbrella_obj)
        increment_history_field(umbrella_obj, 'items_traded_history')
        increment_history_field(umbrella_obj, 'turnover_history')
        increment_history_field(umbrella_obj, 'orders_count_history')
        umbrella_obj.save(using=UMBRELLA)

    def delete(self, *args, **kwargs):
        try:
            os.unlink(self.image.path)
            os.unlink(self.image.small_path)
            os.unlink(self.image.thumb_path)
        except:
            pass
        from ikwen_kakocase.commarketing.models import Banner, SmartCategory
        for banner in Banner.objects.all():
            try:
                banner.items_fk_list.remove(self.id)
                banner.items_count = banner.get_category_queryset().count()
                banner.save()
            except ValueError:
                pass
        for smart_category in SmartCategory.objects.all():
            try:
                smart_category.items_fk_list.remove(self.id)
                smart_category.items_count = smart_category.get_category_queryset().count()
                smart_category.save()
            except ValueError:
                pass
        super(ProductCategory, self).delete(*args, **kwargs)

    def get_visible_items(self):
        product_queryset = self.get_visible_products()
        service_queryset = self.get_visible_recurring_payment_services()
        if product_queryset.count() > 0:
            return list(product_queryset)
        else:
            return list(service_queryset)

    def get_visible_products(self):
        return self.product_set.filter(visible=True, is_duplicate=False)

    def get_visible_recurring_payment_services(self):
        return self.recurringpaymentservice_set.filter(visible=True)

    def get_suited_previews_count(self):
        count = len(self.get_visible_items()) / PRODUCTS_PREVIEWS_PER_ROW
        return count * PRODUCTS_PREVIEWS_PER_ROW


class BusinessCategory(Model):
    """
    Type of products that a provider sells.
    """
    name = models.CharField(max_length=100, unique=True,
                            help_text=_("Name of the category."))
    slug = models.SlugField(unique=True,
                            help_text=_("Slug of the category."))
    description = models.TextField(blank=True,
                                   help_text=_("Description of the category."))
    product_categories = ListField(EmbeddedModelField('ProductCategory'))

    class Meta:
        verbose_name_plural = "Business Categories"

    def __unicode__(self):
        return self.name


class DeliveryOption(Model):
    """
    Delivery options applicable to all kakocase retail websites.

    :attr:`company`: Company offering that option
    :attr:`name`: Name of the option
    :attr:`slug`: Slug of the option
    :attr:`description`: Description
    :attr:`cost`: How much the customer pays
    :attr:`max_delay`: Max duration (in hours) it should take to deliver the package.
    """
    UPLOAD_TO = 'kakocase/delivery_options'
    PICK_UP_IN_STORE = 'PickUpInStore'
    HOME_DELIVERY = 'HomeDelivery'
    TYPE_CHOICES = (
        (PICK_UP_IN_STORE, _('Pick up in store')),
        (HOME_DELIVERY, _('Home delivery')),
    )
    company = models.ForeignKey(Service, related_name='+')
    auth_code = models.CharField(max_length=60, blank=True, null=True,
                                 help_text=_("Get this code from the Logistics company."))
    type = models.CharField(_("type"), max_length=30, choices=TYPE_CHOICES)
    name = models.CharField(_("name"), max_length=100,
                            help_text=_("Name of the option."))
    slug = models.SlugField(help_text=_("Slug of the option."))
    short_description = models.CharField(_("short description"), max_length=30, blank=True,
                                         help_text=_("Short description of the option."
                                                     "Typically max delay as a text value."))
    description = models.TextField(_("description"), blank=True,
                                   help_text=_("Description of the option. Typically coverage and conditions."))
    icon = models.ImageField(upload_to=UPLOAD_TO, width_field=24, height_field=24, blank=True, null=True,
                             help_text=_("24x24 PNG icon to illustrate the option."))
    cost = models.FloatField(_("cost"), help_text="Cost of the option.")
    max_delay = models.IntegerField(_("max delay"),
                                    help_text="Max duration (in hours) it should take to deliver the package.")
    checkout_min = models.IntegerField(_("checkout minimum"), default=0,
                                       help_text=_("Minimum checkout to make this option available."))
    is_active = models.BooleanField(_("active"), default=True,
                                    help_text=_("Check/Uncheck to make it active on you webshop."))

    def __unicode__(self):
        return self.name

    def _get_company_name(self):
        return self.company.config.company_name
    company_name = property(_get_company_name)

    def get_delay_as_string(self):
        if self.max_delay > 72:
            return _('%d days' % (self.max_delay / 24))
        return _('%d hours' % self.max_delay)

    def save(self, **kwargs):
        for operator in OperatorProfile.objects.filter(business_type=OperatorProfile.RETAILER):
            db = operator.service.database
            add_database_to_settings(db)
            slug = slugify(self.name)
            try:
                obj_mirror = DeliveryOption.objects.using(db).get(pk=self.id)
                obj_mirror.name = self.name
                obj_mirror.slug = slug
                obj_mirror.short_description = self.short_description
                obj_mirror.description = self.description
                obj_mirror.icon = self.icon
                obj_mirror.cost = self.cost
                obj_mirror.checkout_min = self.checkout_min
                obj_mirror.max_delay = self.max_delay
            except ProductCategory.DoesNotExist:
                obj_mirror = DeliveryOption(company=self.company, name=self.name, slug=slug,
                                            short_description=self.short_description, description=self.description,
                                            icon=self.icon, cost=self.cost, max_delay=self.max_delay,
                                            checkout_min=self.checkout_min)
            super(DeliveryOption, obj_mirror).save(using=db)
        super(DeliveryOption, self).save(**kwargs)


class DelayReason(models.Model):
    """
    Possible delivery delay reason that must be preset
    by kakocase platform administrators so that end user
    may choose among them.
    """
    value = models.CharField(max_length=255)


class OperatorProfile(AbstractConfig):
    PROVIDER = 'Provider'
    RETAILER = 'Retailer'
    LOGISTICS = 'Logistics'
    BANK = 'Bank'

    MANUAL_UPDATE = 'Manual'
    AUTO_UPDATE = 'Auto'

    STRAIGHT = 'Straight'
    UPON_CONFIRMATION = 'Confirmation'
    PAYMENT_DELAY_CHOICES = (
        (STRAIGHT, _('Straight')),
        (UPON_CONFIRMATION, _('Upon buyer confirmation')),
    )
    rel_id = models.IntegerField(default=0, unique=True,
                                 help_text="Id of this object in the relational database, since these objects are kept"
                                           "in the relational database with traditional autoincrement Ids.")
    bundle = models.ForeignKey(TsunamiBundle, blank=True, null=True)
    # Managed by ikwen staff
    business_type = models.CharField(_("business type"), max_length=30)  # PROVIDER, RETAILER, DELIVERY_MAN or BANK
    ikwen_share_rate = models.FloatField(_("ikwen share rate"), default=0,
                                         help_text=_("Percentage ikwen collects on the turnover made by this person."))
    ikwen_share_fixed = models.FloatField(_("ikwen share fixed"), default=0,
                                          help_text=_("Fixed amount ikwen collects on the turnover made by this person."))

    is_certified = models.BooleanField(_("certified"), default=False)
    can_manage_delivery_options = models.BooleanField(_("Manage delivery options"), default=False,
                                                      help_text=_("If checked, IAO of the platform will be able to set "
                                                                  "delivery options like <strong>FREE SHIPPING</strong>"
                                                                  " or <strong>PICK-UP IN STORE</strong> besides those"
                                                                  " offered by ikwen delivery company partners."))

    # Managed by Service owner
    is_ecommerce_active = models.BooleanField(_("Activate shopping ?"), default=False)
    theme = models.ForeignKey(Theme, blank=True, null=True, related_name='+')
    checkout_min = models.IntegerField(_("checkout minimum"), default=getattr(settings, 'CHECKOUT_MIN', 3000),
                                       help_text=_("Minimum amount you allow to customers to buy."))
    auto_manage_sales = models.BooleanField(_("Auto-manage sales"), default=True,
                                            help_text=_("If checked, may show a strike-through <em>previous price</em> "
                                                        "right before the current <em>retail price</em> and a "
                                                        "<em>'SALE'</em> badge on the product image whenever a product "
                                                        "retail price is updated by a smaller value."))
    show_prices = models.BooleanField(_("show prices"), default=True)
    allow_shopping = models.BooleanField(_("allow shopping"), default=True)
    is_active = models.BooleanField(_("active"), default=True)
    separate_billing_cycle = models.BooleanField(default=False, editable=False,
                                                 help_text="Separate billing cycle allows operator to define a cost "
                                                           "per month on a product. Else the cost and duration of the "
                                                           "service are directly bound to the product.")
    payment_delay = models.CharField(_("payment delay"), max_length=30, choices=PAYMENT_DELAY_CHOICES, default=STRAIGHT,
                                     help_text=_("When cash should be deposited on trader's account. Right when the "
                                                 "buyer pays or when he acknowledges reception of the order."))

    # REPORT INFORMATION
    # The following fields ending with _history are list of 366 values, each of which
    # representing the value of the variable on a day of the 366 previous (current day being the last)
    # Keeping these values this way allows us to easily and rapidly determine report on the yesterday,
    # past 7 days, and past 30 days, without having to run complex and resource-greedy DB queries.
    items_traded_history = ListField()
    turnover_history = ListField()
    earnings_history = ListField()
    orders_count_history = ListField()

    # SUMMARY INFORMATION
    total_items_traded = models.IntegerField(default=0)
    total_turnover = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)
    total_orders_count = models.IntegerField(default=0)

    counters_reset_on = models.DateTimeField(blank=True, null=True)

    # Information below apply to PROVIDER only
    business_category = models.ForeignKey(BusinessCategory, blank=True, null=True)
    stock_updated_on = models.DateTimeField(blank=True, null=True,
                                            help_text=_("Last time provider updated the stock"))
    last_stock_update_method = models.CharField(max_length=10, blank=True, null=True)  # MANUAL_UPDATE or AUTO_UPDATE
    avg_collection_delay = models.IntegerField(default=120, blank=True,
                                               help_text="When provider runs his own retail website, this is the "
                                                         "average delay in minutes before the user can come and "
                                                         "collect his order.")
    media_url = models.CharField(max_length=150, blank=True,
                                 help_text="MEDIA_URL in the Django settings of this Provider. The purpose of this "
                                           "is to allow retailer websites to retrieve images in the provider's "
                                           "data. URL of an image of an image on a retailer website will be obtained "
                                           "by replacing the current media root with the one of the provider of the "
                                           "product.")
    max_products = models.IntegerField(default=100,
                                       help_text="Max number of products this provider may have.")
    notification_email = models.CharField(_("Notification email(s)"), max_length=150, blank=True, null=True, default='',
                                           help_text="Emails to which order notifications are sent. "
                                                     "Separate with coma if many. Eg: boss@email.com, account@email.com")
    notification_phone = models.CharField(_("Notification phone(s)"), max_length=150, blank=True, null=True, default='',
                                           help_text="Phone numbers to which order notifications are sent. "
                                                     "Separate with coma if many. Eg: 677010203, 699010203")
    return_url = models.URLField(blank=True,
                                 help_text="Order details are routed to this URL upon checkout confirmation. See "
                                           "<a href='http://support.ikwen.com/kakocase/configuration-return-url'>"
                                           "support.ikwen.com/kakocase/configuration-return-url</a> for more details.")
    auth_code = models.CharField(max_length=60,
                                 editable=getattr(settings, 'IS_DELIVERY_COMPANY', False), blank=True, null=True,
                                 help_text="Your partners will need this code to add you as their delivery company.")

    # Banks Data for CashFlex URL
    website_url = models.URLField(_("Website URL"), blank=True, null=True,
                                  help_text="Your Website URL")
    create_account_url = models.URLField(_("Create Bank Account URL"), blank=True, null=True,
                                         help_text="Create account page URL on your website")
    cashflex_terms_url = models.URLField(_("CashFlex Terms URL"), blank=True, null=True,
                                         help_text="Your Terms for buying through CashFlex")

    class Meta:
        verbose_name = 'Operator'

    def __unicode__(self):
        return self.company_name

    def _get_ikwen_share(self):
        return self.ikwen_share_rate
    ikwen_share = property(_get_ikwen_share)

    def report_counters_to_umbrella(self):
        umbrella_obj = OperatorProfile.objects.using(UMBRELLA).get(pk=self.id)
        umbrella_obj.items_traded_history = self.items_traded_history
        umbrella_obj.turnover_history = self.turnover_history
        umbrella_obj.earnings_history = self.earnings_history
        umbrella_obj.orders_count_history = self.orders_count_history
        umbrella_obj.total_items_traded = self.total_items_traded
        umbrella_obj.total_turnover = self.total_turnover
        umbrella_obj.total_earnings = self.total_earnings
        umbrella_obj.total_orders_count = self.total_orders_count
        umbrella_obj.save(using=UMBRELLA)

    def save(self, *args, **kwargs):
        using = kwargs.get('using')
        if using:
            del(kwargs['using'])
        else:
            using = 'default'
        if getattr(settings, 'IS_IKWEN', False):
            db = self.service.database
            add_database_to_settings(db)
            try:
                obj_mirror = OperatorProfile.objects.using(db).get(pk=self.id)
                obj_mirror.currency_code = self.currency_code
                obj_mirror.currency_symbol = self.currency_symbol
                obj_mirror.ikwen_share_rate = self.ikwen_share_rate
                obj_mirror.ikwen_share_fixed = self.ikwen_share_fixed
                obj_mirror.payment_delay = self.payment_delay
                obj_mirror.cash_out_min = self.cash_out_min
                obj_mirror.is_certified = self.is_certified
                obj_mirror.can_manage_delivery_options = self.can_manage_delivery_options
                obj_mirror.can_manage_currencies = self.can_manage_currencies
                obj_mirror.is_pro_version = self.is_pro_version
                obj_mirror.max_products = self.max_products
                obj_mirror.sms_api_script_url = self.sms_api_script_url
                super(OperatorProfile, obj_mirror).save(using=db)
            except OperatorProfile.DoesNotExist:
                pass
        else:
            settings_checkout_min = getattr(settings, 'CHECKOUT_MIN', 3000)
            can_set_min_checkout = self.is_pro_version or self.business_type == OperatorProfile.PROVIDER
            if self.checkout_min < settings_checkout_min and not can_set_min_checkout:
                self.checkout_min = settings_checkout_min
        super(OperatorProfile, self).save(using=using, *args, **kwargs)

    def to_dict(self):
        var = to_dict(self)
        del(var['ikwen_share_rate'])
        del(var['ikwen_share_fixed'])
        del(var['payment_delay'])
        del (var['cash_out_min'])
        return var
