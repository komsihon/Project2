from django.db import models
from django.db.utils import DatabaseError
from djangotoolbox.fields import ListField, EmbeddedModelField

from ikwen.accesscontrol.models import Member
from ikwen.core.models import Model, AbstractWatchModel, Country
from ikwen_kakocase.kako.models import Product


class AnonymousBuyerManager(models.Manager):

    def create(self, **kwargs):
        try:
            auto_inc = AnonymousBuyer.objects.all().order_by('-id')[0].auto_inc
        except IndexError:
            auto_inc = 0
        while True:
            auto_inc += 1
            try:
                anonymous_buyer = super(AnonymousBuyerManager, self).create(auto_inc=auto_inc, **kwargs)
                return anonymous_buyer
            except DatabaseError:
                continue


class AnonymousBuyer(Model):
    """
    Buyer that purchases without creating an account
    or without logging in.
    """
    name = models.CharField(max_length=100, blank=True, db_index=True)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=30, db_index=True)
    delivery_addresses = ListField(EmbeddedModelField('shopping.DeliveryAddress'))

    # This auto_inc field is used to keep the order number of this anonymous buyer
    # it is not declared as models.AutoField() to avoid overriding the default id
    # set by the ORM. Value will be manually set upon creation of the object by
    # determining how many AnonymousBuyer were previously created and incrementing
    # that value by 1.
    # We will use it in the generation of AOTC by passing the mongo_id
    # of the order and this auto_inc value to trade.utils.generate_tx_code()
    auto_inc = models.IntegerField(default=0, unique=True, db_index=True)

    objects = AnonymousBuyerManager()

    def __unicode__(self):
        return self.name + ': ' + self.email


class Customer(AbstractWatchModel):
    """
    Profile information for a Buyer on whatever retail website

    :attr:delivery_cities : List of delivery cities subsequently set by client. The last in the list is the current
    :attr:delivery_addresses : List of delivery addresses subsequently set by client. The last in the list is the current
    """
    member = models.OneToOneField(Member)
    delivery_addresses = ListField(EmbeddedModelField('shopping.DeliveryAddress'))

    orders_count_history = ListField()
    items_purchased_history = ListField()
    turnover_history = ListField()
    earnings_history = ListField()

    total_orders_count = models.IntegerField(default=0)
    total_items_purchased = models.IntegerField(default=0)
    total_turnover = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)


class DeliveryAddress(Model):
    name = models.CharField(max_length=100)
    country = models.ForeignKey(Country)
    city = models.CharField(max_length=100)
    details = models.CharField(max_length=255)
    phone = models.CharField(max_length=30)
    postal_code = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField()


class Review(Model):
    product = models.ForeignKey(Product)
    member = models.ForeignKey(Member, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    rating = models.FloatField( blank=True, null=True)  # Value comprised between 0 .. 1 (Because we use jstarbox client side for display)
    comment = models.TextField(blank=True, null=True)
