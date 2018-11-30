import os

from django.utils.translation import gettext_lazy as _
from django.db import models
from ikwen.core.utils import to_dict

from ikwen.accesscontrol.models import Member
from ikwen.core.models import Model


class CloudCashIn(Model):
    member = models.ForeignKey(Member, blank=True)
    amount = models.IntegerField(help_text=_("Sales Cost"))

