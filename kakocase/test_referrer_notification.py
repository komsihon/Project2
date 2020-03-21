# import unittest
#
#
# class MyTestCase(unittest.TestCase):
#     def test_something(self):
#         self.assertEqual(True, False)
#
#
# if __name__ == '__main__':
#     unittest.main()
import os
import logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'ikwen.conf.settings')

from threading import Thread
from ikwen.core.utils import get_mail_content

from django.utils.translation import gettext as _, activate
from django.contrib.humanize.templatetags.humanize import intcomma

from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.models import Service
from ikwen.core.utils import XEmailMessage
from django.core.mail import EmailMessage
from daraja.models import Dara

logger = logging.getLogger('kakocase')

dara_member = Member.objects.get(phone=691467782)
dara = Dara.objects.using(UMBRELLA).get(member=dara_member)
template_name = 'daraja/mails/remind_referrer.html'
dara_earnings = 3200
invoice_total = 29000
activate(dara_member.language)

member = Member.objects.using(UMBRELLA).get(phone='675187705')
phone = member.phone
if len(phone) == 9 and not phone.startswith('237'):
    member.phone = '237' + member.phone

try:
    service = Service.objects.using(UMBRELLA).get(domain='adidas.kakocase.com')
    extra_context = {'referee': member, 'amount': dara_earnings, 'deployed_service': service, 'dara_name': dara_member.full_name}
    subject = _("Congratulations ! %s CFA is waiting for you." % intcomma(dara_earnings))
    html_content = get_mail_content(subject, template_name=template_name, extra_context=extra_context)
    sender = 'ikwen Daraja <no-reply@ikwen.com>'
    msg = EmailMessage(subject, html_content, sender, [dara_member.email])
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg,)).start()
    print "Did you reach here ?"
except:
    print("Failed to notify %s Dara after follower deployed Kakocase website." % dara_member.full_name)
