import json
from threading import Thread

from ajaxuploader.views import  render

from django.contrib.auth.decorators import login_required
from django.core.mail.message import EmailMessage
from django.http.response import HttpResponse
from django.utils.translation import gettext as _
from django.views.generic.base import TemplateView

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance, get_mail_content
from ikwen.core.views import HybridListView
from ikwen.rewarding.models import Reward, CumulatedCoupon, Coupon
from ikwen.rewarding.utils import reward_member, use_coupon
from ikwen_kakocase.cci.models import CloudCashIn


class CCI(TemplateView):
    template_name = 'cci/cloud_cash_in.html'


class CCIList(HybridListView):
    model = CloudCashIn
    search_field = 'tags'
    list_filter = ('cashier', )
    page_size = 25


@login_required
def save_cloud_cashin_payment(request):
    amount = request.GET.get('amount')
    customer_id = request.GET.get('customer_id')
    coupon_id = request.GET.get('coupon_id')
    has_use_coupon = False

    member = Member.objects.using('umbrella').get(pk=customer_id)
    service = get_service_instance()

    customer = Member.objects.get(pk=customer_id)
    cashier = request.user
    tags = member.tags
    cci = CloudCashIn(customer=customer, cashier=cashier, amount=amount, tags=tags)
    remaining_cumulated_coupon_count = 0
    try:
        Member.objects.get(pk=customer_id)
    except Member.DoesNotExist:
        response = HttpResponse(json.dumps(
            {'error': True,
             'msg': _("This user is not yet registered; invite him to join your community first."),
             }), 'content-type: text/json')
        return response
    if coupon_id:
        try:
            coupon = Coupon.objects.using('umbrella').get(pk=coupon_id)
            used_cumulated_coupon = CumulatedCoupon.objects.using('umbrella').get(coupon=coupon, member=member)
        except Coupon.DoesNotExist:
            pass
        else:
            use_coupon(member, used_cumulated_coupon.coupon, None)
            remaining_cumulated_coupon = CumulatedCoupon.objects.using('umbrella').get(coupon=coupon, member=member)
            remaining_cumulated_coupon_count = remaining_cumulated_coupon.count
            subject = _("Your coupons have been used.")
            has_use_coupon = True
            # send_confirmation_email(subject, member.get_short_name(), member.email, cci, message=None)
    cci.save()
    reward_type = Reward.PAYMENT
    reward_pack_list = reward_member(service, member, reward_type, amount=amount)
    subject = _("Successful payment")
    template_name = 'cci/tsunami_used_coupon_email.html'
    if has_use_coupon:
        subject = _("Successful payment with coupon used.")
        msg = _("Payment successfully proceeded.")
    send_confirmation_email(subject, member.get_short_name(), member.email, cci, template_name, message=None)
    response = HttpResponse(json.dumps( {'success': True,}), 'content-type: text/json')
    if has_use_coupon:
        response = HttpResponse(json.dumps(
            {'success': True,
             'remaining_cumulated_coupon_count': remaining_cumulated_coupon_count
             }), 'content-type: text/json')
    return response


@login_required
def get_member_cumulated_coupon(request, *args, **kwargs):

    member_id = request.GET.get('customer_id')
    member = Member.objects.using('umbrella').get(pk=member_id)
    service = get_service_instance()

    coupon_qs = Coupon.objects.using('umbrella').filter(service=service, status=Coupon.APPROVED, is_active=True)
    coupon_list = []
    for coupon in coupon_qs:
        try:
            cumul = CumulatedCoupon.objects.using('umbrella').get(coupon=coupon, member=member)
            coupon.count = cumul.count
            coupon.ratio = float(cumul.count) / coupon.heap_size * 100
        except CumulatedCoupon.DoesNotExist:
            coupon.count = 0
            coupon.ratio = 0
        coupon_list.append(coupon)

    context = {'coupons': coupon_list,}
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