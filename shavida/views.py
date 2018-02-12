# -*- coding: utf-8 -*-
import json
import random
import string
from datetime import datetime

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.http import HttpResponseRedirect
from django.template.defaultfilters import slugify
from django.utils.decorators import method_decorator
from django.utils.http import urlquote
from django.utils.translation import gettext as _
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import TemplateView
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.billing.models import CloudBillingPlan, IkwenInvoiceItem, InvoiceEntry
from ikwen.core.models import Service, Application
from ikwen.core.utils import get_service_instance
from ikwen.partnership.models import ApplicationRetailConfig
from ikwen.theming.models import Template, Theme

from ikwen_shavida.sales.models import SalesConfig, VODPrepayment, Prepayment
from ikwen_shavida.shavida.cloud_setup import DeploymentForm, deploy
from ikwen_shavida.shavida.models import Customer
from ikwen_shavida.movies.models import Category, Series


class BaseView(TemplateView):

    def get_context_data(self, **kwargs):
        context = super(BaseView, self).get_context_data(**kwargs)
        categories_qs = Category.objects.filter(visible=True).order_by('order_of_appearance')
        context['smart_categories'] = categories_qs.filter(smart=True)
        context['main_categories'] = categories_qs.filter(smart=False, appear_in_main=True)
        context['more_categories'] = categories_qs.filter(smart=False).exclude(appear_in_main=True)
        context['all_categories'] = categories_qs
        context['sign_in_url'] = reverse('ikwen:sign_in')
        context['bundles_url'] = reverse('movies:bundles')
        if self.request.user.is_authenticated():
            last_vod_prepayment = self.request.user.customer.get_last_vod_prepayment()
            if last_vod_prepayment:
                last_vod_prepayment.balance /= 1000.0
            context['last_vod_prepayment'] = last_vod_prepayment
        return context


def offer_welcome_bundle(request, *args, **kwargs):
    sales_config = SalesConfig.objects.all()[0]
    if sales_config.free_trial:
        bytes_balance = sales_config.welcome_offer * 1000000
        VODPrepayment.objects.create(member=request.user, balance=bytes_balance, amount=0, paid_on=datetime.now(),
                                     duration=sales_config.welcome_offer_duration, status=Prepayment.CONFIRMED)


@login_required
def set_additional_session_info(request, *args, **kwargs):
    request.user.can_access_adult_content = request.user.customer.get_can_access_adult_content()
    request.user.has_pending_update = request.user.customer.get_has_pending_update()


@login_required
def create_member_profile(request, *args, **kwargs):
    member = request.user
    try:
        customer = Customer.objects.get(member=member)
    except Customer.DoesNotExist:
        code = random.random() * 10000
        code = int(code)
        customer = Customer.objects.create(member=member)
    city = request.POST.get('city')
    if city:
        customer.city = city
        customer.save()


class History(BaseView):
    template_name = 'me/history.html'
    # TODO: Correct the display of history client side


@login_required
def authorize_adult(request, *args, **kwargs):
    member = request.user
    member.customer.adult_authorized = True
    member.customer.save()
    return HttpResponse(
        json.dumps({'success': True}),
        content_type='application/json'
    )


class PhoneConfirmation(BaseView):
    template_name = 'accesscontrol/phone_confirmation.html'

    def send_code(self, request, new_code=False):
        member = request.user
        code = ''.join([random.SystemRandom().choice(string.digits) for _ in range(4)])
        do_send = False
        try:
            current = request.session['code']
            if new_code:
                request.session['code'] = code
                do_send = True
        except KeyError:
            request.session['code'] = code
            do_send = True

        if do_send:
            phone = slugify(member.phone).replace('-', '')
            if len(phone) == 9:
                phone = '237' + phone
            service = get_service_instance()
            requests.get('http://5.39.75.139:22090/message', params={
                'user': 'creolink',
                'pass': 'creolink@2016',
                'from': service.project_name,
                'to': phone,
                'text': 'Confirmation code: ' + code,
                'dlrreq': 0
            })

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated() and request.user.phone_verified:
            return HttpResponseRedirect(reverse('movies:home'))
        context = self.get_context_data(**kwargs)
        if getattr(settings, 'DEBUG', False):
            self.send_code(request)
        else:
            try:
                self.send_code(request)
            except:
                context['error_message'] = _('Could not send code. Please try again later')
        return render(request, self.template_name, context)

    def render_to_response(self, context, **response_kwargs):
        response = {'success': True}
        if self.request.GET.get('action') == 'new_code':
            if getattr(settings, 'DEBUG', False):
                self.send_code(self.request, new_code=True)
            else:
                try:
                    self.send_code(self.request, new_code=True)
                except:
                    response = {'error': _('Could not send code. Please try again later')}
            return HttpResponse(json.dumps(response), 'content-type: text/json', **response_kwargs)
        else:
            return super(PhoneConfirmation, self).render_to_response(context, **response_kwargs)

    def post(self, request, *args, **kwargs):
        member = request.user
        code = request.session.get('code')
        if code != request.POST['code']:
            context = self.get_context_data(**kwargs)
            context['error_message'] = _('Invalid code. Please try again')
            return render(request, self.template_name, context)
        member.phone_verified = True
        member.save()
        try:
            VODPrepayment.objects.filter(member=member).order_by('-id')[0]
            return HttpResponseRedirect(reverse('movies:home'))
        except:
            return HttpResponseRedirect(reverse('movies:bundles'))


class DeployCloud(TemplateView):
    template_name = 'shavida/cloud_setup/deploy.html'

    def get_context_data(self, **kwargs):
        context = super(DeployCloud, self).get_context_data(**kwargs)
        context['billing_cycles'] = Service.BILLING_CYCLES_CHOICES
        app = Application.objects.using(UMBRELLA).get(slug='shavida')
        context['app'] = app
        template_list = list(Template.objects.using(UMBRELLA).filter(app=app))
        context['theme_list'] = Theme.objects.using(UMBRELLA).filter(template__in=template_list)
        context['can_choose_themes'] = True
        if getattr(settings, 'IS_IKWEN', False):
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner__isnull=True)
            if billing_plan_list.count() == 0:
                setup_months_count = 3
                context['ikwen_setup_cost'] = app.base_monthly_cost * setup_months_count
                context['ikwen_monthly_cost'] = app.base_monthly_cost
                context['setup_months_count'] = setup_months_count
        else:
            service = get_service_instance()
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner=service)
            if billing_plan_list.count() == 0:
                retail_config = ApplicationRetailConfig.objects.using(UMBRELLA).get(app=app, partner=service)
                setup_months_count = 3
                context['ikwen_setup_cost'] = retail_config.ikwen_monthly_cost * setup_months_count
                context['ikwen_monthly_cost'] = retail_config.ikwen_monthly_cost
                context['setup_months_count'] = setup_months_count
        if billing_plan_list.count() > 0:
            context['billing_plan_list'] = billing_plan_list
            context['setup_months_count'] = billing_plan_list[0].setup_months_count
        return context

    def get(self, request, *args, **kwargs):
        member = request.user
        uri = request.META['REQUEST_URI']
        next_url = reverse('ikwen:sign_in') + '?next=' + urlquote(uri)
        if member.is_anonymous():
            return HttpResponseRedirect(next_url)
        if not getattr(settings, 'IS_IKWEN', False):
            if not member.has_perm('accesscontrol.sudo'):
                return HttpResponseForbidden("You are not allowed here. Please login as an administrator.")
        return super(DeployCloud, self).get(request, *args, **kwargs)

    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        form = DeploymentForm(request.POST)
        if form.is_valid():
            app_id = form.cleaned_data.get('app_id')
            project_name = form.cleaned_data.get('project_name')
            business_type = form.cleaned_data.get('business_type')
            billing_cycle = form.cleaned_data.get('billing_cycle')
            billing_plan_id = form.cleaned_data.get('billing_plan_id')
            domain = form.cleaned_data.get('domain')
            theme_id = form.cleaned_data.get('theme_id')
            partner_id = form.cleaned_data.get('partner_id')
            app = Application.objects.using(UMBRELLA).get(pk=app_id)
            theme = Theme.objects.using(UMBRELLA).get(pk=theme_id)
            billing_plan = CloudBillingPlan.objects.using(UMBRELLA).get(pk=billing_plan_id)

            is_ikwen = getattr(settings, 'IS_IKWEN', False)
            if not is_ikwen or (is_ikwen and request.user.is_staff):
                customer_id = form.cleaned_data.get('customer_id')
                customer = Member.objects.using(UMBRELLA).get(pk=customer_id)
                setup_cost = form.cleaned_data.get('setup_cost')
                monthly_cost = form.cleaned_data.get('monthly_cost')
                if setup_cost < billing_plan.setup_cost:
                    return HttpResponseForbidden("Attempt to set a Setup cost lower than allowed.")
                if monthly_cost < billing_plan.monthly_cost:
                    return HttpResponseForbidden("Attempt to set a monthly cost lower than allowed.")
            else:
                # User self-deploying his website
                customer = Member.objects.using(UMBRELLA).get(pk=request.user.id)
                setup_cost = billing_plan.setup_cost
                monthly_cost = billing_plan.monthly_cost

            partner = Service.objects.using(UMBRELLA).get(pk=partner_id) if partner_id else None
            invoice_entries = []
            domain_name = IkwenInvoiceItem(label='Domain name')
            domain_name_entry = InvoiceEntry(item=domain_name, short_description=domain)
            invoice_entries.append(domain_name_entry)
            website_setup = IkwenInvoiceItem(label='Website setup', price=billing_plan.setup_cost, amount=setup_cost)
            short_description = "%d products" % billing_plan.max_objects
            website_setup_entry = InvoiceEntry(item=website_setup, short_description=short_description, total=setup_cost)
            invoice_entries.append(website_setup_entry)
            i = 0
            while True:
                try:
                    label = request.POST['item%d' % i]
                    amount = float(request.POST['amount%d' % i])
                    if not (label and amount):
                        break
                    item = IkwenInvoiceItem(label=label, amount=amount)
                    entry = InvoiceEntry(item=item, total=amount)
                    invoice_entries.append(entry)
                    i += 1
                except:
                    break
            if getattr(settings, 'DEBUG', False):
                service = deploy(app, customer, business_type, project_name, billing_plan,
                                 theme, monthly_cost, invoice_entries, billing_cycle, domain,
                                 partner_retailer=partner)
            else:
                try:
                    service = deploy(app, customer, business_type, project_name, billing_plan,
                                     theme, monthly_cost, invoice_entries, billing_cycle, domain,
                                     partner_retailer=partner)
                except Exception as e:
                    context = self.get_context_data(**kwargs)
                    context['error'] = e.message
                    return render(request, 'shavida/cloud_setup/deploy.html', context)
            if is_ikwen:
                if request.user.is_staff:
                    next_url = reverse('partnership:change_service', args=(service.id, ))
                else:
                    next_url = reverse('ikwen:console')
            else:
                next_url = reverse('change_service', args=(service.id, ))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['form'] = form
            return render(request, 'shavida/cloud_setup/deploy.html', context)


def pick_samples():
    l = ['ninja-assassin',
    'next',
    'son-batman',
    'red-2',
    'homefront',
    '47-ronin',
    'planes',
    'da-vinci-code',
    'ange-et-demon',
    'la-passion-du-christ',
    'thor'
    'nymphomaniac-vol-2',
    'last-days-mars',
    'constantine',
    'killing-kennedy',
    'zulu',
    'hunger-games-lembrasement',
    'man-steel',
    'man-tai-chi',
    'wanted',
    'home',
    'vampire-academy',
    'son-god',
    'kung-fu-panda-1',
    'true-blood-saison1',
    'stargate-sg-1-saison5',
    'good-wife-saison3',
    'strike-back-saison1',
    'prison-break-saison4',
    'under-dome-saison1',
    'supernatural-saison6',
    'tudors-saison1']

    for s in Series.objects.all():
        if s.slug not in l:
            for se in s.seriesepisode_set.all():
                se.delete()
            s.delete()
