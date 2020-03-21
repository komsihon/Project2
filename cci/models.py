import os

from django.utils.translation import gettext_lazy as _
from django.db import models
from ikwen.core.utils import to_dict

from ikwen.accesscontrol.models import Member
from ikwen.core.models import Model


class CloudCashIn(Model):
    customer = models.ForeignKey(Member, blank=True)
    cashier = models.ForeignKey(Member, related_name="cashier_set")
    amount = models.IntegerField(help_text=_("Sales Cost"))
    tags = models.CharField(max_length=240)

