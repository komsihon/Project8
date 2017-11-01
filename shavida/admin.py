# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from ikwen.billing.admin import Product, Subscription
from ikwen.billing.models import InvoicingConfig, Invoice, Payment
from import_export.admin import ExportMixin
from ikwen.accesscontrol.backends import ARCH_EMAIL
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance

from ikwen_shavida.sales.models import RetailPrepayment, Prepayment, VODPrepayment
from ikwen_shavida.shavida.models import OperatorProfile, Customer
from tracking.models import BannedIP, UntrackedUserAgent

if getattr(settings, 'IS_IKWEN', False):
    _fieldsets = [
        (_('Company'), {'fields': ('company_name', 'short_description', 'slogan', 'description')}),
        (_('Business'), {'fields': ('ikwen_share_rate', 'ikwen_share_fixed', 'cash_out_min',)}),
        (_('Platform'), {'fields': ('is_pro_version',)}),
        (_('SMS'), {'fields': ('sms_api_script_url', 'sms_api_username', 'sms_api_password',)}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature',)}),
        (_('Website'), {'fields': ('theme',)})
    ]
    _readonly_fields = ()
else:
    service = get_service_instance()
    config = service.config
    _readonly_fields = ('is_certified',)
    _fieldsets = [
        (_('Company'), {'fields': ('company_name', 'short_description', 'slogan', 'description',)}),
        (_('Website'), {'fields': ('guard_image_landscape', 'guard_image_portrait',)}),
        (_('Address & Contact'), {'fields': ('contact_email', 'contact_phone', 'address', 'country', 'city')}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature',)}),
        (_('Social'), {'fields': ('facebook_link', 'twitter_link', 'youtube_link',
                                  'google_plus_link', 'instagram_link', 'tumblr_link', 'linkedin_link',)}),
        (_('External scripts'), {'fields': ('scripts', )})
    ]
    if getattr(settings, 'IS_VOD_OPERATOR', False):
        _fieldsets.insert(2, (_('VOD'), {'fields': ('data_sources', 'movies_timeout', 'series_timeout',
                                                    'allow_unit_prepayment', 'allow_cash_payment')}))


class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = ('service', 'company_name', 'ikwen_share_fixed', 'ikwen_share_rate', 'cash_out_min')
    fieldsets = _fieldsets
    readonly_fields = _readonly_fields
    search_fields = ('company_name', 'contact_email', )
    save_on_top = True

    def delete_model(self, request, obj):
        self.message_user(request, "You are not allowed to delete Configuration of the platform")


class CustomerAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('member',)
    readonly_fields = ('member', 'adult_authorized', 'created_on', 'updated_on',)
    search_fields = ('member_email', 'phone',)
    ordering = ('-id',)
    actions = ('set_retail_prepayment', 'set_vod_prepayment',)

    def set_retail_prepayment(self, request, queryset):
        """
        Give a RetailPrepayment of 0MB to the Member. The balance of the RetailPrepayment must be later
        manually updated by the admin by editing the object. And so the client can order content.
        The Member must ABSOLUTELY be a VOD Operator and have no prior Pending RetailPrepayment
        """
        for profile in queryset:
            if not profile.is_vod_operator:
                self.message_user(request, "%s is not a VOD Operator." % profile.member)
                return
        for profile in queryset:
            RetailPrepayment.objects.create(member=profile.member, amount=0, balance=0, status=Prepayment.CONFIRMED)
            self.message_user(request,
                              "%s Retail Prepayment were created. Edit balance and amount from the RetailPrepayment admin page." % queryset.count())

    set_retail_prepayment.short_description = _(
        "Create and give a Retail Prepayment to member (Applicable to VOD Operators only).")

    def set_vod_prepayment(self, request, queryset):
        """
        Give a VODPrepayment of 0MB to the Member. The balance of the VODPrepayment must be later
        manually updated by the admin by editing the object. And so the client can order content.
        The Member MUST NO BE a VOD Operator and have no prior Pending VODPrepayment
        """
        for profile in queryset:
            if profile.is_vod_operator:
                self.message_user(request, "%s is a VOD Operator." % profile.member)
                return
        for profile in queryset:
            VODPrepayment.objects.create(member=profile.member, amount=0, balance=0, status=Prepayment.CONFIRMED)
            self.message_user(request,
                              "%s VOD Prepayment were created. Edit balance and amount from the VODPrepayment admin page." % queryset.count())

    set_vod_prepayment.short_description = _(
        "Create and give VOD Prepayment for member (Not applicable to VOD Operators).")

    def get_queryset(self, request):
        arch = Member.objects.get(email=ARCH_EMAIL)
        qs = Customer.objects.exclude(member=arch)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def get_search_results(self, request, queryset, search_term):
        arch = Member.objects.get(email=ARCH_EMAIL)
        try:
            int(search_term)
            members = list(Member.objects.filter(
                Q(phone__contains=search_term) | Q(email__icontains=search_term.lower())
            ).exclude(email=ARCH_EMAIL))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        except ValueError:
            members = list(Member.objects.filter(email__icontains=search_term.lower()).exclude(email=ARCH_EMAIL))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        return queryset, use_distinct

try:
    from currencies.models import Currency
    admin.site.unregister(Currency)
except NotRegistered:
    pass

# Unregister ikwen billing models
if not getattr(settings, 'IS_UMBRELLA', False):
    try:
        admin.site.unregister(InvoicingConfig)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(Invoice)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(Payment)
    except NotRegistered:
        pass

try:
    admin.site.unregister(BannedIP)
except NotRegistered:
    pass
try:
    admin.site.unregister(UntrackedUserAgent)
except NotRegistered:
    pass

if getattr(settings, 'IS_IKWEN', False):
    admin.site.register(OperatorProfile, OperatorProfileAdmin)
else:
    try:
        admin.site.unregister(Product)
    except NotRegistered:
        pass
    try:
        admin.site.unregister(Subscription)
    except NotRegistered:
        pass

