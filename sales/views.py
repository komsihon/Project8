# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta

from currencies.models import Currency
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template import Context
from django.template.loader import get_template
from django.utils.translation import gettext as _
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import SUDO, Member
from ikwen.billing.models import MoMoTransaction
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen.billing.orangemoney.views import ORANGE_MONEY
from ikwen.conf.settings import FALLBACK_SHARE_RATE
from ikwen.core.models import Service
from ikwen.core.utils import get_service_instance, add_database_to_settings, set_counters, increment_history_field, \
    add_event, calculate_watch_info, rank_watch_objects
from ikwen.core.views import DashboardBase
from ikwen.partnership.models import ApplicationRetailConfig, PartnerProfile
from ikwen_shavida.movies.models import Movie, Series
from ikwen_shavida.movies.views import CustomerView
from ikwen_shavida.reporting.utils import generate_add_list_info, add_media_to_update, sync_changes
from ikwen_shavida.sales.models import ContentUpdate
from ikwen_shavida.sales.models import VODBundle, Prepayment, VODPrepayment, RetailBundle, RetailPrepayment, UnitPrepayment, \
    SalesConfig
from ikwen_shavida.shavida.events import NEW_ORDER, BUNDLE_PURCHASE
from ikwen_shavida.shavida.models import Customer
from math import ceil


def set_momo_order_checkout(request, payment_mean, *args, **kwargs):
    """
    This function has no URL associated with it.
    It serves as ikwen setting "MOMO_BEFORE_CHECKOUT"
    """
    service = get_service_instance()
    member = request.user
    signature = request.session['signature']
    bundle_id = request.POST.get('bundle_id')
    media_id = request.POST.get('media_id')
    media_type = request.POST.get('media_type')
    currency = Currency.active.base()
    if bundle_id:
        if getattr(settings, 'IS_VOD_OPERATOR', False):
            request.session['model_name'] = 'sales.VODPrepayment'
            bundle = get_object_or_404(VODBundle, pk=bundle_id)
            prepayment = VODPrepayment.objects.create(member=member, amount=bundle.cost, duration=bundle.duration,
                                                      adult_authorized=bundle.adult_authorized, currency=currency,
                                                      payment_mean=payment_mean)
        else:
            request.session['model_name'] = 'sales.RetailPrepayment'
            bundle = get_object_or_404(RetailBundle, pk=bundle_id)
            prepayment = RetailPrepayment.objects.create(member=member, amount=bundle.cost, balance=bundle.quantity,
                                                         duration=bundle.duration, adult_authorized=bundle.adult_authorized,
                                                         currency=currency, payment_mean=payment_mean)
        request.session['amount'] = bundle.cost
    else:
        if media_type == 'movie':
            media = get_object_or_404(Movie, pk=media_id)
            request.session['media_type'] = 'movie'
        else:
            media = get_object_or_404(Series, pk=media_id)
            request.session['media_type'] = 'series'
        config = service.config
        duration = config.movies_timeout if media_type == UnitPrepayment.MOVIE else config.series_timeout
        prepayment = UnitPrepayment.objects.create(media_type=media_type, media_id=media_id,  member=member,
                                                   amount=media.view_price, duration=duration, currency=currency,
                                                   payment_mean=payment_mean)
        request.session['amount'] = media.view_price
        request.session['model_name'] = 'sales.UnitPrepayment'
        request.session['is_unit_prepayment'] = True
    request.session['object_id'] = prepayment.id

    mean = request.GET.get('mean', MTN_MOMO)
    if mean is None or mean == MTN_MOMO:
        request.session['is_momo_payment'] = True
    elif mean == ORANGE_MONEY:
        request.session['notif_url'] = service.url + reverse('movies:home')  # Unused. Callback is run by querying transation status
        request.session['return_url'] = service.url + reverse('movies:home')
        request.session['cancel_url'] = service.url + reverse('movies:bundles')
        request.session['is_momo_payment'] = False


def confirm_payment(request, *args, **kwargs):
    if request.session.get('is_momo_payment'):
        signature = kwargs.get('signature')
        no_check_signature = request.GET.get('ncs')
        if getattr(settings, 'DEBUG', False):
            if not no_check_signature:
                if signature != request.session['signature']:
                    return HttpResponse('Invalid transaction signature')
        else:
            if signature != request.session['signature']:
                return HttpResponse('Invalid transaction signature')
    else:
        try:
            data = json.loads(request.body)
            tx_id = data['txnid']
            momo_tx_id = kwargs['momo_tx_id']
            MoMoTransaction.objects.using('wallets').filter(pk=momo_tx_id).update(tx_id=tx_id)
        except:
            pass

    is_unit_prepayment = request.session.get('is_unit_prepayment')

    if is_unit_prepayment:
        pay_cash, next_url = choose_temp_bundle(request, payment_successful=True, **kwargs)
    elif getattr(settings, 'IS_VOD_OPERATOR', False):
        pay_cash, next_url = choose_vod_bundle(request, payment_successful=True, **kwargs)
    else:
        pay_cash = False
        next_url = choose_retail_bundle(request, payment_successful=True, **kwargs)

    if not pay_cash and request.session.get('is_momo_payment'):
        return {'success': True, 'next_url': next_url}
    else:
        return HttpResponseRedirect(next_url)


@login_required
def choose_vod_bundle(request, *args, **kwargs):
    config = get_service_instance().config
    member = request.user

    pay_cash = False
    if config.allow_cash_payment:
        pay_cash = request.POST.get('pay_cash') == 'yes'
    bundle_id = request.POST.get('bundle_id')
    if bundle_id:
        bundle = VODBundle.objects.get(pk=bundle_id)
        status = request.POST.get('status', Prepayment.PENDING)
        prepayment = VODPrepayment(member=member, amount=bundle.cost, duration=bundle.duration,
                                   adult_authorized=bundle.adult_authorized, status=status)
    else:
        object_id = request.session.get('object_id')
        if not object_id:
            object_id = kwargs['object_id']
        prepayment = VODPrepayment.objects.get(pk=object_id)
    if kwargs.get('payment_successful', False):
        prepayment.status = Prepayment.CONFIRMED
        prepayment.paid_on = datetime.now()
        prepayment.save()
        service = get_service_instance()
        sudo_group = Group.objects.get(name=SUDO)
        add_event(service, BUNDLE_PURCHASE, group_id=sudo_group.id, object_id=prepayment.id)
        add_event(service, BUNDLE_PURCHASE, member=request.user, object_id=prepayment.id)
        share_payment_and_set_stats(member.customer, prepayment.amount)
    elif pay_cash:
        prepayment.save()

    messages.success(request, _("Your bundle was successfully activated."))
    next_url = reverse('movies:home')
    return pay_cash, next_url


@login_required
def choose_retail_bundle(request, *args, **kwargs):
    member = request.user
    # if not member.profile.is_vod_operator:
    #     return HttpResponseForbidden("You are not allowed to order retail bundle.")
    bundle_id = request.POST.get('bundle_id')
    if bundle_id:
        bundle = RetailBundle.objects.get(pk=bundle_id)
        status = request.POST.get('status', Prepayment.PENDING)
        purchased_quantity = bundle.quantity
        prepayment = RetailPrepayment(member=member, amount=bundle.cost, duration=bundle.duration,
                                      adult_authorized=bundle.adult_authorized, status=status)
    else:
        object_id = request.session.get('object_id')
        if not object_id:
            object_id = kwargs['object_id']
        prepayment = RetailPrepayment.objects.get(pk=object_id)
        purchased_quantity = prepayment.balance
    last_retail_prepayment = member.customer.get_last_retail_prepayment()
    if last_retail_prepayment:
        if last_retail_prepayment.days_left > 0:
            balance = last_retail_prepayment.balance + purchased_quantity
        else:
            balance = purchased_quantity
    else:
        balance = purchased_quantity

    if kwargs.get('payment_successful', False):
        prepayment.balance = balance
        prepayment.status = Prepayment.CONFIRMED
        prepayment.paid_on = datetime.now()
        prepayment.save()
        service = get_service_instance()
        sudo_group = Group.objects.get(name=SUDO)
        add_event(service, BUNDLE_PURCHASE, group_id=sudo_group.id, object_id=prepayment.id)
        add_event(service, BUNDLE_PURCHASE, member=request.user, object_id=prepayment.id)
        share_payment_and_set_stats(member.customer, prepayment.amount)

    messages.success(request, _("Your bundle was successfully activated."))
    next_url = reverse('movies:home')
    return next_url


@login_required
def choose_temp_bundle(request, *args, **kwargs):
    config = get_service_instance().config
    member = request.user
    media_id = request.POST.get('media_id')
    if media_id:
        try:
            media = Movie.objects.get(pk=media_id)
            amount = media.view_price
            media_type = 'movie'
            hashbang = 'movie-' + media.slug
        except Movie.DoesNotExist:
            media = get_object_or_404(Series, pk=media_id)
            amount = media.view_price
            media_type = 'series'
            hashbang = 'series-' + media.slug
        duration = config.movies_timeout if media_type == UnitPrepayment.MOVIE else config.series_timeout
        prepayment = UnitPrepayment.objects.create(member=member, media_type=media_type, media_id=media_id,
                                                   amount=amount, duration=duration)
    else:
        object_id = request.session.get('object_id')
        if not object_id:
            object_id = kwargs['object_id']
        prepayment = UnitPrepayment.objects.get(pk=object_id)
        try:
            media = Movie.objects.get(pk=prepayment.media_id)
            hashbang = 'movie-' + media.slug
        except Movie.DoesNotExist:
            media = Series.objects.get(pk=prepayment.media_id)
            hashbang = 'series-' + media.slug
    pay_cash = False
    if config.allow_cash_payment:
        pay_cash = request.POST.get('pay_cash') == 'yes'
    now = datetime.now()
    expiry = now + timedelta(days=prepayment.duration)
    if kwargs.get('payment_successful', False):
        prepayment.paid_on = now
        prepayment.expiry = expiry
        prepayment.status = Prepayment.CONFIRMED
        prepayment.save()
        service = get_service_instance()
        sudo_group = Group.objects.get(name=SUDO)
        add_event(service, BUNDLE_PURCHASE, group_id=sudo_group.id, object_id=prepayment.id)
        add_event(service, BUNDLE_PURCHASE, member=request.user, object_id=prepayment.id)
        share_payment_and_set_stats(member.customer, prepayment.amount)
    elif pay_cash:
        prepayment.save()

    messages.success(request, _("Your bundle was successfully activated."))
    next_url = reverse('movies:home') + '#!' + hashbang
    return pay_cash, next_url


def share_payment_and_set_stats(customer, amount):
    service = get_service_instance()
    service_umbrella = get_service_instance(UMBRELLA)
    app_umbrella = service_umbrella.app
    profile_umbrella = service_umbrella.config
    ikwen_earnings_rate = amount * profile_umbrella.ikwen_share_rate / 100
    ikwen_earnings_fixed = profile_umbrella.ikwen_share_fixed
    if ikwen_earnings_fixed > (amount / 10):
        fallback_rate = max(profile_umbrella.ikwen_share_rate, FALLBACK_SHARE_RATE)
        ikwen_earnings_fixed = amount * fallback_rate / 100
    ikwen_earnings = ikwen_earnings_rate + ikwen_earnings_fixed
    operator_earnings = amount - ikwen_earnings

    service.raise_balance(operator_earnings)

    partner = service_umbrella.retailer
    if partner:
        retail_config = ApplicationRetailConfig.objects.using(UMBRELLA).get(partner=partner, app=app_umbrella)
        partner_earnings = ikwen_earnings * (100 - retail_config.ikwen_tx_share_rate) / 100
        ikwen_earnings -= partner_earnings

        partner.raise_balance(partner_earnings)

        service_partner = Service.objects.using(partner.database).get(pk=service_umbrella.id)
        app_partner = service_partner.app

        set_counters(service_partner)
        increment_history_field(service_partner, 'earnings_history', partner_earnings)
        increment_history_field(service_partner, 'transaction_earnings_history', partner_earnings)
        increment_history_field(service_partner, 'transaction_count_history')

        set_counters(app_partner)
        increment_history_field(app_partner, 'earnings_history', partner_earnings)
        increment_history_field(app_partner, 'transaction_earnings_history', partner_earnings)
        increment_history_field(app_partner, 'transaction_count_history')

        set_counters(partner)
        increment_history_field(partner, 'turnover_history', amount)
        increment_history_field(partner, 'earnings_history', ikwen_earnings)
        increment_history_field(partner, 'transaction_earnings_history', ikwen_earnings)
        increment_history_field(partner, 'transaction_count_history')

        partner_app = partner.app  # This is going to be the ikwen core/retail app
        set_counters(partner_app)
        increment_history_field(partner_app, 'turnover_history', amount)
        increment_history_field(partner_app, 'earnings_history', ikwen_earnings)
        increment_history_field(partner_app, 'transaction_earnings_history', ikwen_earnings)
        increment_history_field(partner_app, 'transaction_count_history')

    set_counters(service)
    increment_history_field(service, 'turnover_history', amount)
    increment_history_field(service, 'earnings_history', operator_earnings)
    increment_history_field(service, 'transaction_count_history')

    set_counters(service_umbrella)
    increment_history_field(service_umbrella, 'turnover_history', amount)
    increment_history_field(service_umbrella, 'earnings_history', ikwen_earnings)
    increment_history_field(service_umbrella, 'transaction_earnings_history', ikwen_earnings)
    increment_history_field(service_umbrella, 'transaction_count_history')

    app_umbrella = service_umbrella.app  # The app powering the site that is receiving this payment (Shavida)
    set_counters(app_umbrella)
    increment_history_field(app_umbrella, 'turnover_history', amount)
    increment_history_field(app_umbrella, 'earnings_history', ikwen_earnings)
    increment_history_field(app_umbrella, 'transaction_earnings_history', ikwen_earnings)
    increment_history_field(app_umbrella, 'transaction_count_history')

    set_counters(customer)
    increment_history_field(customer, 'turnover_history', amount)
    increment_history_field(customer, 'orders_count_history')


@login_required
def confirm_order(request, *args, **kwargs):
    service = get_service_instance()
    member = request.user
    sudo_group = Group.objects.get(name=SUDO)
    if member.customer.get_has_pending_update():
        return HttpResponse(json.dumps({'error': "You have a pending order."}))
    last_prepayment = member.customer.get_last_retail_prepayment()
    items = request.GET.get('items')
    auto_selection = request.GET.get('auto_selection')
    if auto_selection:
        try:
            update = ContentUpdate.objects.get(member=member, status=ContentUpdate.RUNNING)
        except ContentUpdate.DoesNotExist:
            response = {'error': "Could not find any recent Auto-Selection."}
        else:
            update.status = ContentUpdate.PENDING
            update.save()
            add_event(service, NEW_ORDER, group_id=sudo_group.id, object_id=update.id)
            add_event(service, NEW_ORDER, member=member, object_id=update.id)
            response = {'success': True}
        return HttpResponse(json.dumps(response))

    info = generate_add_list_info(items)
    add_list_size = info['add_list_size']
    add_list_duration = info['add_list_duration']
    if not last_prepayment or last_prepayment.days_left < 0:
        return HttpResponse(json.dumps({'error': _("You don't have any retail bundle. Contact your vendor.")}))
    if getattr(settings, 'SALES_UNIT') == SalesConfig.BROADCASTING_TIME:
        if last_prepayment.balance < add_list_duration:
            return HttpResponse(json.dumps({'error': _("Your update bundle contains only %d hours." % (last_prepayment.balance / 60))}))
    else:
        if last_prepayment.balance < add_list_size:
            return HttpResponse(json.dumps({'error': _("Your update bundle contains only %.2f GB." % (last_prepayment.balance / 1000.0))}))
    try:
        update = ContentUpdate.objects.get(member=member, status=ContentUpdate.PENDING)
    except ContentUpdate.DoesNotExist:
        update = ContentUpdate.objects.create(member=member)
    add_media_to_update(items, update)
    update.add_list = (update.add_list + ',' + info['add_list']).strip(',')
    update.add_list_size += add_list_size
    update.save()
    add_event(service, NEW_ORDER, group_id=sudo_group.id, object_id=update.id)
    add_event(service, NEW_ORDER, member=member, object_id=update.id)

    set_counters(service)  # We use custom_service_count_history to count orders
    increment_history_field(service, 'custom_service_count_history')

    if member.customer.is_operator:
        db = member.customer.service.database
        add_database_to_settings(db)
        update.save(using=db)
    return HttpResponse(json.dumps({'success': True}))


class OrderDetail(CustomerView):
    template_name = 'sales/order_detail.html'

    def get_context_data(self, **kwargs):
        order_id = kwargs['order_id']
        order = get_object_or_404(ContentUpdate, pk=order_id)
        context = super(OrderDetail, self).get_context_data(**kwargs)
        if getattr(settings, 'SALES_UNIT', SalesConfig.DATA_VOLUME):
            size = "%.2f GB" % (order.add_list_size / 1000.0)
        else:
            size = "%d H" % ceil(order.add_list_size / 60.0)
        context['order'] = order
        context['size'] = size
        context['member'] = order.member
        context['media_list'] = order.movies_add_list + order.series_episodes_add_list
        context['show_button'] = order.status == ContentUpdate.PENDING
        return context


def cancel_order(request, *args, **kwargs):
    member = Member.objects.get(pk=request.GET['member_id'])
    callback = request.GET['callback']
    last_update = member.customer.get_last_update()
    if last_update.status == ContentUpdate.PENDING:
        last_update.delete()
    response = {"success": True}
    jsonp = callback + '(' + json.dumps(response) + ')'
    return HttpResponse(jsonp, content_type='application/json')


def confirm_processed(request, *args, **kwargs):
    order = ContentUpdate.objects.get(pk=request.GET['order_id'])
    callback = request.GET['callback']
    if order.status == ContentUpdate.PENDING:
        size = order.add_list_size
        prepayment = order.member.customer.get_last_retail_prepayment()
        prepayment.balance -= size
        prepayment.save()
        # from threading import Thread
        # thread = Thread(target=sync_changes, args=(order, ))  # Syncing changes may last long, so run it in another thread.
        # thread.start()
        order.status = ContentUpdate.DELIVERED
        order.save()
    response = {"success": True}
    jsonp = callback + '(' + json.dumps(response) + ')'
    return HttpResponse(jsonp, content_type='application/json')


def render_bundle_purchased_event(event, request):
    request_user = Member.objects.get(pk=request.GET['member_id'])
    try:
        if getattr(settings, 'IS_VOD_OPERATOR', False):
            try:
                prepayment = VODPrepayment.objects.get(pk=event.object_id)
            except VODPrepayment.DoesNotExist:
                prepayment = UnitPrepayment.objects.get(pk=event.object_id)
        else:
            prepayment = RetailPrepayment.objects.get(pk=event.object_id)
    except ObjectDoesNotExist:
        return ''
    currency_symbol = get_service_instance().config.currency_symbol
    html_template = get_template('sales/events/bundle_purchased.html')
    member = prepayment.member
    if request_user == member:
        member = None
    from ikwen.conf import settings as ikwen_settings
    c = Context({'event': event, 'prepayment': prepayment, 'currency_symbol': currency_symbol, 'member': member,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
    return html_template.render(c)


def render_order_event(event, request):
    user_id = request.GET['member_id']  # User in session, not customer of the order. WATCH OUT !
    try:
        order = ContentUpdate.objects.get(pk=event.object_id)
    except ContentUpdate.DoesNotExist:
        return ''
    if getattr(settings, 'SALES_UNIT', SalesConfig.DATA_VOLUME):
        size = "%.2f GB" % (order.add_list_size / 1000.0)
    else:
        size = "%d H" % ceil(order.add_list_size / 60.0)
    member = order.member
    title = _("New order")
    if event.member:
        title = _("Your order")
        member = None
    media_list = order.movies_add_list + order.series_episodes_add_list
    more = 0
    if len(media_list) > 15:
        more = len(media_list) - 15
    html_template = get_template('sales/events/order_notice.html')
    service = get_service_instance()
    from ikwen.conf import settings as ikwen_settings
    c = Context({'event': event, 'order': order, 'title': title, 'size': size, 'more': more,
                 'show_button': order.status == ContentUpdate.PENDING, 'user_id': user_id, 'service': service,
                 'media_list': media_list, 'MEDIA_URL': getattr(settings, 'MEDIA_URL'), 'member': member,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL,
                 'IS_GAME_VENDOR': getattr(settings, 'IS_GAME_VENDOR', False)})

    return html_template.render(c)


class Dashboard(DashboardBase):
    template_name = 'sales/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        earnings_today = context['earnings_report']['today']
        earnings_yesterday = context['earnings_report']['yesterday']
        earnings_last_week = context['earnings_report']['last_week']
        earnings_last_28_days = context['earnings_report']['last_28_days']

        service = get_service_instance()
        set_counters(service)
        orders_count_today = calculate_watch_info(service.custom_service_count_history)
        orders_count_yesterday = calculate_watch_info(service.custom_service_count_history, 1)
        orders_count_last_week = calculate_watch_info(service.custom_service_count_history, 7)
        orders_count_last_28_days = calculate_watch_info(service.custom_service_count_history, 28)

        # AEPO stands for Average Earning Per Order
        aepo_today = earnings_today['total'] / orders_count_today['total'] if orders_count_today['total'] else 0
        aepo_yesterday = earnings_yesterday['total'] / orders_count_yesterday['total']\
            if orders_count_yesterday and orders_count_yesterday['total'] else 0
        aepo_last_week = earnings_last_week['total'] / orders_count_last_week['total']\
            if orders_count_last_week and orders_count_last_week['total'] else 0
        aepo_last_28_days = earnings_last_28_days['total'] / orders_count_last_28_days['total']\
            if orders_count_last_28_days and orders_count_last_28_days['total'] else 0

        orders_report = {
            'today': {
                'count': orders_count_today['total'] if orders_count_today else 0,
                'aepo': '%.2f' % aepo_today,  # AEPO: Avg Earning Per Order
            },
            'yesterday': {
                'count': orders_count_yesterday['total'] if orders_count_yesterday else 0,
                'aepo': '%.2f' % aepo_yesterday,  # AEPO: Avg Earning Per Order
            },
            'last_week': {
                'count': orders_count_last_week['total'] if orders_count_last_week else 0,
                'aepo': '%.2f' % aepo_last_week,  # AEPO: Avg Earning Per Order
            },
            'last_28_days': {
                'count': orders_count_last_28_days['total']if orders_count_last_28_days else 0,
                'aepo': '%.2f' % aepo_last_28_days,  # AEPO: Avg Earning Per Order
            }
        }
        customers = list(Customer.objects.all())
        for customer in customers:
            set_counters(customer)
        customers_report = {
            'today': rank_watch_objects(customers, 'turnover_history'),
            'yesterday': rank_watch_objects(customers, 'turnover_history', 1),
            'last_week': rank_watch_objects(customers, 'turnover_history', 7),
            'last_28_days': rank_watch_objects(customers, 'turnover_history', 28)
        }

        context['orders_report'] = orders_report
        context['customers_report'] = customers_report
        return context
