# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from djangotoolbox.fields import ListField
from ikwen.accesscontrol.models import Member
from ikwen.core.models import AbstractConfig, AbstractWatchModel, Service
from ikwen.core.utils import to_dict, add_database_to_settings
from ikwen.theming.models import Theme
from ikwen_shavida.conf.utils import is_content_vendor
from ikwen_shavida.sales.models import ContentUpdate, SalesConfig, RetailPrepayment, VODPrepayment


class Customer(AbstractWatchModel):
    """
    Customer profile
    """
    member = models.OneToOneField(Member)
    # User must activate this from his profile to access adult content
    adult_authorized = models.BooleanField(default=False, editable=False)
    service = models.ForeignKey(Service, blank=True, null=True, related_name='+',
                                help_text=_("Website of this Operator."))

    turnover_history = ListField()
    orders_count_history = ListField()

    total_turnover = models.IntegerField(default=0)
    total_orders_count = models.IntegerField(default=0)

    def __unicode__(self):
        return 'Profile ' + self.member.email

    def _get_is_operator(self):
        return self.service
    is_operator = property(_get_is_operator)

    def _get_days_passed_since_latest_order(self):
        orders = ContentUpdate.objects.filter(member=self.member).order_by('-id')
        latest_order = orders[0] if len(orders) > 0 else None
        now = timezone.now()
        passed_days = None
        if latest_order:
            passed_days = now - latest_order.when
        if passed_days is not None:
            return passed_days.days
        else:
            return None

    days_passed_since_latest_order = property(_get_days_passed_since_latest_order)

    _get_days_passed_since_latest_order.admin_order_field = 'days_passed_since_latest_order'
    _get_days_passed_since_latest_order.short_description = 'Days without order'

    def ordered_recently(self):
        sales_config = SalesConfig.objects.all()[0]
        if self.days_passed_since_latest_order is not None:
            if self.days_passed_since_latest_order <= sales_config.max_inactivity:
                return True
        return False

    ordered_recently.boolean = True
    ordered_recently.short_description = 'Ordered recently?'

    def get_last_retail_prepayment(self):
        prepayments = RetailPrepayment.objects.filter(member=self.member).order_by('-id')
        return prepayments[0] if len(prepayments) > 0 else None

    def get_last_vod_prepayment(self, status=None):
        if status:
            vod_prepayments = VODPrepayment.objects.filter(member=self.member, status=status).order_by('-id')
        else:
            vod_prepayments = VODPrepayment.objects.filter(member=self.member).order_by('-id')
        return vod_prepayments[0] if len(vod_prepayments) > 0 else None

    def get_has_pending_update(self):
        return ContentUpdate.objects.filter(status=ContentUpdate.PENDING, member=self.member).count()

    def get_last_update(self):
        from ikwen_shavida.sales.models import ContentUpdate
        updates = ContentUpdate.objects.filter(member=self.member).order_by('-id')
        return updates[0] if len(updates) > 0 else None

    def get_can_access_adult_content(self):
        if not self.is_operator:
            last_vod_prepayment = self.get_last_vod_prepayment(VODPrepayment.CONFIRMED)
            if last_vod_prepayment:
                return self.adult_authorized and last_vod_prepayment.adult_authorized
            return self.adult_authorized
        return True

    def to_dict(self):
        var = to_dict(self)
        var['can_access_adult_content'] = self.get_can_access_adult_content()
        return var


class OperatorProfile(AbstractConfig):
    theme = models.ForeignKey(Theme, blank=True, null=True, related_name='+')
    allow_unit_prepayment = models.BooleanField(default=True,
                                                help_text=_("Check if you want customers to pay for a single movie or "
                                                            "series. Then you will have to set <em>View price</em> "
                                                            "for item you want to be paid single."))
    allow_cash_payment = models.BooleanField(default=False,
                                             help_text=_("Check if you want customers to pay in cash on a POS."))
    movies_timeout = models.IntegerField(default=2,
                                         help_text=_("Time given to watch a movie purchased single."))
    series_timeout = models.IntegerField(default=5,
                                         help_text=_("Time given to watch a series purchased single."))
    data_sources = models.TextField(blank=True,
                                    help_text=_("List of sources to check to retrieve video URL from resource. "
                                                "Separate by commas. (Eg: http://myserver.net/vod1, https://src.net/vod2)"))
    media_url = models.CharField(max_length=150, blank=True,
                                 help_text="MEDIA_URL in the Django settings of this Operator. The purpose of this "
                                           "is to allow retailer websites to retrieve images in the provider's "
                                           "data. URL of an image of an image on a retailer website will be obtained "
                                           "by replacing the current media root with the one of the provider of the "
                                           "product.")
    ikwen_share_rate = models.FloatField(_("ikwen share rate"), default=0,
                                         help_text=_("Percentage ikwen collects on the turnover made by this person."))
    ikwen_share_fixed = models.FloatField(_("ikwen share fixed"), default=0,
                                          help_text=_("Fixed amount ikwen collects on the turnover made by this person."))
    max_products = models.FloatField(default=0,
                                     help_text=_("Maximum number of media in the library."))

    class Meta:
        verbose_name = 'Operator'

    def save(self, *args, **kwargs):
        using = kwargs.get('using')
        if using:
            del(kwargs['using'])
        else:
            using = 'default'
        if getattr(settings, 'IS_IKWEN', False):
            db = self.service.database
            add_database_to_settings(db)
            try:
                obj_mirror = OperatorProfile.objects.using(db).get(pk=self.id)
                obj_mirror.currency_code = self.currency_code
                obj_mirror.currency_symbol = self.currency_symbol
                obj_mirror.ikwen_share_rate = self.ikwen_share_rate
                obj_mirror.ikwen_share_fixed = self.ikwen_share_fixed
                obj_mirror.is_pro_version = self.is_pro_version
                obj_mirror.max_products = self.max_products
                super(OperatorProfile, obj_mirror).save(using=db)
            except OperatorProfile.DoesNotExist:
                pass
        super(OperatorProfile, self).save(using=using, *args, **kwargs)


class SubscriptionWatch(AbstractWatchModel):
    count_history = ListField()
    total_count = models.IntegerField(default=0)
