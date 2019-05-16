from threading import Thread

from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.shortcuts import render
from django.utils.http import urlquote
from django.views.generic import TemplateView
from django.utils.translation import gettext as _

from ikwen.core.models import Service
from ikwen.core.constants import MALE, FEMALE
from ikwen.core.utils import get_service_instance, get_mail_content
from ikwen.accesscontrol.models import Member
from ikwen.revival.models import ProfileTag, MemberProfile
from ikwen.rewarding.models import Reward, ReferralRewardPack, CouponSummary, Coupon, CumulatedCoupon, CROperatorProfile
from ikwen.rewarding.utils import reward_member
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen_webnode.web.models import Banner, SLIDE, HomepageSection


class Home(TemplateView):
    template_name = 'webnode/improve/home.html'

    def get_context_data(self, **kwargs):
        context = super(Home, self).get_context_data(**kwargs)
        context['slideshow'] = Banner.objects.filter(display=SLIDE, is_active=True).order_by('order_of_appearance')
        context['homepage_section_list'] = HomepageSection.objects.filter(is_active=True).order_by('order_of_appearance')
        referrer_id = self.request.GET.get('referrer')
        member = self.request.user
        service = get_service_instance()

        coupon_qs = Coupon.objects.filter(status=Coupon.APPROVED, is_active=True)
        if member.is_authenticated():
            url = 'http://tchopetyamo.com/?referrer=' + member.id
            context['url'] = urlquote(url)
            coupon_list = []
            for coupon in coupon_qs:
                try:
                    cumul = CumulatedCoupon.objects.get(coupon=coupon, member=member)
                    coupon.count = cumul.count
                    coupon.ratio = float(cumul.count) / coupon.heap_size * 100
                except CumulatedCoupon.DoesNotExist:
                    coupon.count = 0
                    coupon.ratio = 0
                coupon_list.append(coupon)
            coupon_summary_list = member.couponsummary_set.filter(service=service)
            context['coupon_summary_list'] = coupon_summary_list
            context['coupon_list'] = coupon_list
        else:
            context['coupon_list'] = coupon_qs
        if referrer_id:
            try:
                referrer = Member.objects.get(pk=referrer_id)
            except Member.DoesNotExist:
                context['referrer'] = "Unknown user"
            else:
                context['referrer'] = referrer.get_short_name
        return context


def reward_referrer(request, *args, **kwargs):
    referrer_id = request.GET['referrer_id']
    member = request.user
    service = get_service_instance()
    if referrer_id:
        referrer = Member.objects.get(pk=referrer_id)
        referrer_profile, update = MemberProfile.objects.get_or_create(member=referrer)
        men_tag, update = ProfileTag.objects.get_or_create(name='Men', slug='men', is_reserved=True)
        women_tag, update = ProfileTag.objects.get_or_create(name='Women', slug='women', is_reserved=True)

        referrer_tag_fk_list = referrer_profile.tag_fk_list
        if men_tag.id in referrer_tag_fk_list:
            referrer_tag_fk_list.remove(men_tag.id)
        if women_tag.id in referrer_tag_fk_list:
            referrer_tag_fk_list.remove(women_tag.id)
        member_profile, update = MemberProfile.objects.get_or_create(member=member)
        member_profile.tag_fk_list.extend(referrer_tag_fk_list)
        if member.gender == MALE:
            member_profile.tag_fk_list.append(men_tag.id)
        elif member.gender == FEMALE:
            member_profile.tag_fk_list.append(women_tag.id)
        member_profile.save()
        referral_pack_list, coupon_count = reward_member(service, referrer, Reward.REFERRAL)
        if referral_pack_list:
            sender = 'Tchopetyamo <info@tchopetyamo.com>'
            referrer_subject = _("%s is offering you %d coupons for your referral to %s" % (service.project_name, coupon_count, member.full_name))
            template_name = 'rewarding/mails/referral_reward.html'
            CouponSummary.objects.using(UMBRELLA).get(service=service, member=referrer)
            html_content = get_mail_content(referrer_subject, template_name=template_name,
                                            extra_context={'referral_pack_list': referral_pack_list, 'coupon_count': coupon_count,
                                                           'joined_service': service, 'referee_name': member.full_name,
                                                           'joined_logo': service.config.logo})
            msg = EmailMessage(referrer_subject, html_content, sender, [referrer.email])
            msg.content_subtype = "html"
            Thread(target=lambda m: m.send(), args=(msg, )).start()