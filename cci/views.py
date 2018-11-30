import json
import logging
from threading import Thread

from ajaxuploader.views import  render
from django.contrib.auth.decorators import login_required
from django.core.mail.message import EmailMessage
from django.core.urlresolvers import reverse
from django.http.response import HttpResponseRedirect, HttpResponse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.generic.base import TemplateView

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance, get_mail_content
from ikwen.rewarding.models import Reward, CumulatedCoupon, Coupon
from ikwen.rewarding.utils import reward_member, use_coupon
from ikwen_kakocase.cci.models import CloudCashIn

logger = logging.getLogger('ikwen')


class CCI(TemplateView):
    template_name = 'cci/cloud_cash_in.html'

    def get_context_data(self, **kwargs):
        context = super(CCI, self).get_context_data(**kwargs)
        return context

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        amount = self.request.POST.get('amount')
        customer_id = self.request.POST.get('customer_id')
        member = Member.objects.get(pk=customer_id)
        service = get_service_instance()
        # coupon_list = list(Coupon.objects.using('umbrella').filter(service=service))
        # cumul = CumulatedCoupon.objects.using('umbrella').filter(member=member, coupon__in=coupon_list)
        cci = CloudCashIn(member=member, amount=amount)
        cci.save()
        reward_type = Reward.PAYMENT
        reward_member(service, member, reward_type, amount=amount)
        next_url = reverse('cci:home')
        return HttpResponseRedirect(next_url)


@login_required
def save_cloud_cashin_payment(request):
    amount = request.GET.get('amount')
    customer_id = request.GET.get('customer_id')
    coupon_id = request.GET.get('coupon_id')
    has_use_coupon = False

    member = Member.objects.using('umbrella').get(pk=customer_id)
    service = get_service_instance()
    cci = CloudCashIn(member=member, amount=amount)
    if coupon_id:
        try:
            used_cumulated_coupon = CumulatedCoupon.objects.using('umbrella').get(pk=coupon_id)
        except Coupon.DoesNotExist:
            pass
        else:
            use_coupon(member, used_cumulated_coupon.coupon, None)
            # cci.cumulated_coupon = used_cumulated_coupon
            #todo control and remove the used cummulated coupon from the database or set it as used
            subject = _("Your coupon has been used.")
            has_use_coupon = True
            # send_confirmation_email(subject, member.get_short_name(), member.email, cci, message=None)
    cci.save()
    reward_type = Reward.PAYMENT
    reward_pack_list = reward_member(service, member, reward_type, amount=amount)
    subject = _("Payment successfully proceeded")
    template_name = 'cci/snippets/user_coupon_list.html'
    if has_use_coupon:
        subject = _("Payment successfully proceeded and you use a coupon.")
        msg = _(u"Payment successfully proceeded.")
    send_confirmation_email(subject, member.get_short_name(), member.email, cci, template_name, message=None)

    response = HttpResponse(json.dumps(
        {'success': True,
         }), 'content-type: text/json')
    return response


@login_required
def get_member_cumulated_coupon(request, *args, **kwargs):

    member_id = request.GET.get('customer_id')
    member = Member.objects.using('umbrella').get(pk=member_id)
    service = get_service_instance()
    coupon_list = list(Coupon.objects.using('umbrella').filter(service=service))
    coupons = CumulatedCoupon.objects.using('umbrella').filter(member=member)
    context = {'coupons': coupons,}
    return render(request, 'cci/snippets/user_coupon_list.html', context)


def send_confirmation_email(subject, buyer_name, buyer_email, order, template_name, message=None):
    service = get_service_instance()
    html_content = get_mail_content(subject, '', template_name=template_name,
                                    extra_context={'buyer_name': buyer_name, 'order': order, 'message': message})
    sender = '%s <no-reply@%s>' % (service.project_name, service.domain)
    msg = EmailMessage(subject, html_content, sender, [buyer_email])
    bcc = [service.member.email, service.config.contact_email]
    msg.bcc = list(set(bcc))
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg, )).start()


def createCoupons(request, *args, **kwargs):
    service = get_service_instance()
    coupon_list = list(Coupon.objects.using('umbrella').all())
    if not coupon_list:
        c = Coupon.objects.create(service=service,slug='reduction', month_quota=500, type='Discount', coefficient=10, is_active=True)
        c1 = Coupon.objects.create(service=service,slug='Purchase-order', month_quota=500,  type='PurchaseOrder', coefficient=5000, is_active=True)
        coupon_list = list(Coupon.objects.using('umbrella').all())
    return coupon_list


def getCumulatedCoupons(request, *args, **kwargs):
    member = request.user
    m = Member.objects.using('umbrella').get(username=member.username)
    cumulated_coupon = CumulatedCoupon.objects.using('umbrella').all()
    coupon1 = Coupon.objects.using('umbrella').all()[0]
    coupon2 = Coupon.objects.using('umbrella').all()[1]
    if not cumulated_coupon:
        c = CumulatedCoupon(count=68,member=m, coupon=coupon1)
        c.save(using='umbrella')
        c1 = CumulatedCoupon(count=97,member=m, coupon=coupon2)
        c1.save(using='umbrella')
        cumulated_coupon = CumulatedCoupon.objects.all()
    return cumulated_coupon