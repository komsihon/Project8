# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import admin
from django.db.models import Q
from django.utils.translation import gettext as _
from ikwen.core.utils import get_service_instance
from import_export import resources
from import_export.admin import ExportMixin
from ikwen.accesscontrol.models import Member

from ikwen_shavida.conf.utils import is_vod_operator, is_content_vendor
from ikwen_shavida.reporting.utils import sync_changes
from ikwen_shavida.sales.models import SalesConfig, RetailBundle, RetailPrepayment, VODBundle, VODPrepayment, Prepayment, \
    ContentUpdate, UnitPrepayment


class RetailPrepaymentResource(resources.ModelResource):

    class Meta:
        model = RetailPrepayment
        skip_unchanged = True
        exclude = ('id',)
        export_id_fields = ('member__username', 'created_on', 'paid_on', 'amount', 'duration', 'balance', 'status')


class VODPrepaymentResource(resources.ModelResource):

    class Meta:
        model = VODPrepayment
        skip_unchanged = True
        exclude = ('id',)
        export_id_fields = ('member__username', 'created_on', 'paid_on', 'amount', 'duration', 'balance', 'status')


class SalesConfigAdmin(admin.ModelAdmin):
    list_display = ('max_inactivity', 'welcome_offer', 'welcome_offer_duration')

    def save_model(self, request, obj, form, change):
        """
        Do not save more than one SalesConfig object.
        """
        configs_count = SalesConfig.objects.all().count()
        if configs_count >= 1:
            if not obj.id:
                return
        super(SalesConfigAdmin, self).save_model(request, obj, form, change)


class RetailBundleAdmin(admin.ModelAdmin):
    list_display = ('name', 'quantity', 'cost', 'comment')
    readonly_fields = ('created_on', )
    ordering = ('cost', )


class VODBundleAdmin(admin.ModelAdmin):
    list_display = ('cost', 'duration', 'adult_authorized', 'comment')
    readonly_fields = ('created_on', )
    ordering = ('cost', )


class RetailPrepaymentAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = RetailPrepaymentResource
    list_display = ('member', 'created_on', 'paid_on', 'amount', 'balance', 'duration', 'status')
    list_filter = ('created_on', 'status', )
    search_fields = ('member_email', 'member_phone', )
    readonly_fields = ('member', 'created_on', 'paid_on')

    def get_search_results(self, request, queryset, search_term):
        try:
            int(search_term)
            members = list(Member.objects.filter(
                Q(phone__contains=search_term) | Q(email__icontains=search_term.lower())
            ))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        except ValueError:
            members = list(Member.objects.filter(email__icontains=search_term.lower()))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        return queryset, use_distinct


class VODPrepaymentAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = VODPrepaymentResource
    list_display = ('member', 'created_on', 'paid_on', 'amount', 'balance', 'duration', 'status')
    list_filter = ('created_on', 'amount', 'status', )
    search_fields = ('member_email', 'member_phone',)

    def get_readonly_fields(self, request, obj=None):
        if obj.status == Prepayment.PENDING:
            return 'member', 'amount', 'created_on', 'paid_on', 'teller'
        else:
            return 'member', 'amount', 'status', 'created_on', 'paid_on', 'teller'

    def save_model(self, request, obj, form, change):
        if change:
            if obj.status == Prepayment.CONFIRMED:
                obj.teller = request.user
                obj.paid_on = datetime.now()
        super(VODPrepaymentAdmin, self).save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        try:
            int(search_term)
            members = list(Member.objects.filter(
                Q(phone__contains=search_term) | Q(email__icontains=search_term.lower())
            ))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        except ValueError:
            members = list(Member.objects.filter(email__icontains=search_term.lower()))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        return queryset, use_distinct


class UnitPrepaymentAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('member', 'get_media', 'amount', 'created_on', 'paid_on', 'teller')
    list_filter = ('created_on', 'paid_on', 'status', )
    search_fields = ('member_email', 'member_phone',)
    readonly_fields = ('member', 'amount', 'duration', 'teller',
                       'media_type', 'media_id', 'created_on', 'paid_on', 'expiry')

    def save_model(self, request, obj, form, change):
        if change:
            if obj.status == Prepayment.CONFIRMED:
                obj.teller = request.user
                obj.paid_on = datetime.now()
                obj.expiry = obj.paid_on + timedelta(days=obj.duration)
        super(UnitPrepaymentAdmin, self).save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        try:
            int(search_term)
            members = list(Member.objects.filter(
                Q(phone__contains=search_term) | Q(email__icontains=search_term.lower())
            ))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        except ValueError:
            members = list(Member.objects.filter(email__icontains=search_term.lower()))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        return queryset, use_distinct


class ClientListFilter(admin.SimpleListFilter):
    """
    Implements the filtering of ContentUpdate by member on Content Vendor website
    """

    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('client')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'member_id'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        choices = []
        for update in ContentUpdate.objects.all():
            choice = (update.member.id, update.member.get_full_name())
            choices.append(choice)
        return choices

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value():
            member = Member.objects.get(pk=self.value())
            return queryset.filter(member=member)
        return queryset


class ContentUpdateAdmin(admin.ModelAdmin, ExportMixin):
    list_display = ('add_list_size', 'delete_list_size', 'cost', 'status', 'provider_website') if is_vod_operator()\
        else ('member', 'add_list_size', 'delete_list_size', 'cost', 'status', )
    list_filter = ('status', 'provider_website', ) if is_vod_operator()\
        else ('status', ClientListFilter, )
    search_fields = ('provider_website', ) if is_vod_operator()\
        else ('member_email', )
    readonly_fields = ('add_list', 'add_list_size', 'delete_list', 'delete_list_size', 'cost', 'provider_website', 'status', 'created_on', 'updated_on', ) if is_vod_operator()\
        else ('member', 'add_list', 'add_list_size', 'delete_list', 'delete_list_size', 'created_on', 'updated_on')

    def save_model(self, request, obj, form, change):
        if is_vod_operator():  # VOD Operators cannot edit ContentUpdate
            return
        if obj.status == ContentUpdate.RUNNING:
            return
        if obj.status == ContentUpdate.AUTHORIZED:
            obj.provider = request.user
        elif obj.status == ContentUpdate.DELIVERED:
            size = obj.add_list_size
            prepayment = obj.member.customer.get_last_retail_prepayment()
            prepayment.balance -= size
            prepayment.save()
            from threading import Thread
            thread = Thread(target=sync_changes, args=(obj, ))  # Syncing changes may last long, so run it in another thread.
            thread.start()
        super(ContentUpdateAdmin, self).save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        if is_vod_operator():
            # Leave it as such in this case because it is a search on provider_website
            queryset, use_distinct = super(ContentUpdateAdmin, self).get_search_results(request, queryset, search_term)
        else:
            members = list(Member.objects.filter(email__icontains=search_term.lower()))
            queryset = self.model.objects.filter(member__in=members)
            use_distinct = False
        return queryset, use_distinct


if getattr(settings, 'IS_VOD_OPERATOR', False):
    admin.site.register(SalesConfig, SalesConfigAdmin)
    admin.site.register(VODBundle, VODBundleAdmin)
    admin.site.register(VODPrepayment, VODPrepaymentAdmin)
    admin.site.register(UnitPrepayment, UnitPrepaymentAdmin)
else:
    admin.site.register(ContentUpdate, ContentUpdateAdmin)
    admin.site.register(RetailBundle, RetailBundleAdmin)
    admin.site.register(RetailPrepayment, RetailPrepaymentAdmin)

