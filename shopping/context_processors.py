from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils.http import urlquote

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import AccessRequest, Member
from ikwen.core.utils import get_service_instance, add_database_to_settings
from ikwen.rewarding.models import CROperatorProfile, Coupon, CumulatedCoupon, CouponSummary
from ikwen.rewarding.utils import get_coupon_summary_list


def user_coupon_list(request):
    service = get_service_instance()
    member = request.user
    coupon_list = []
    coupon_qs = Coupon.objects.using(UMBRELLA).filter(service=service, is_active=True)
    if member.is_authenticated():
        try:
            coupon_summary = CouponSummary.objects.using(UMBRELLA).get(service=service, member=member)
            for coupon in coupon_qs:
                try:
                    cumul = CumulatedCoupon.objects.using(UMBRELLA).get(coupon=coupon, member=member)
                    coupon.count = cumul.count
                    coupon.ratio = float(cumul.count) / coupon.heap_size * 100
                except CumulatedCoupon.DoesNotExist:
                    coupon.count = 0
                    coupon.ratio = 0
                coupon_list.append(coupon)
        except:
            coupon_summary = CouponSummary(service=service, member=member, count=0)

        url = getattr(settings, 'PROJECT_URL') + reverse('ikwen:company_profile', args=(service.project_name_slug,))

        url += '?referrer=' + member.id
        coupon_summary_list = get_coupon_summary_list(member)

        return {
            'url': urlquote(url),
            'coupon_list': coupon_list,
            'coupon_summary_list': coupon_summary_list,
            'coupon_summary': coupon_summary,
            'total_coupons': coupon_summary.count,
            'profile_name': service.project_name
        }
    return {

    }


def allowed_users(request):
    if not request.user.is_authenticated:
        return {
            'is_allowed': False
        }
    try:
        email = request.user.email
        if email in ['rsihon@gmail.com', 'wilfriedwillend@gmail.com', 'silatchomsiaka@gmail.com', 'rmbogning@gmail.com']:
            return {
                'is_allowed': True
            }
        else:
            return {
                'is_allowed': False
            }
    except:
        return {
            'is_allowed': False
        }

