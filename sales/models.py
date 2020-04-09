from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db import models
from django.utils.translation import gettext_lazy as _
from ikwen.core.utils import to_dict
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kakocase.models import ProductCategory

from ikwen.core.models import Model


class Promotion(Model):
    """

    """
    title = models.CharField(max_length=100,
                            help_text=_("Title of the promotion"))
    start_on = models.DateTimeField(help_text=_("First day of the promotion"))
    end_on = models.DateTimeField(help_text=_("Last day of the promotion"))
    rate = models.SmallIntegerField(help_text=_("Discount percentage"))
    item = models.ForeignKey(Product, blank=True, null=True,
                             help_text=_("Product where the discount is going to be apply to"))
    category = models.ForeignKey(ProductCategory, blank=True, null=True,
                                 help_text=_("Category where the discount is going to be apply to"))
    is_active = models.NullBooleanField(default=True, blank=True, null=True,
                                 help_text=_("Allow to activate or no the promotion"))


class PromoCode(Model):
    code = models.CharField(max_length=100,
                            help_text=_("Title of the discount coupon"))
    start_on = models.DateTimeField(help_text=_("First day of the discount coupon"))
    end_on = models.DateTimeField(help_text=_("Last day of the discount coupon"))
    rate = models.SmallIntegerField(help_text=_("Discount coupon percentage"))
    is_active = models.BooleanField(default=True,
                                    help_text=_("Allow to activate or no the promo code"))

    def __unicode__(self):
        return self.code

    def get_obj_details(self):
        return '<strong>%s%%</strong>: %s - %s' % (self.rate, self.start_on, self.end_on)


class CustomerEmail(Model):
    """

    """
    email = models.EmailField()
