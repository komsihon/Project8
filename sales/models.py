# -*- coding: utf-8 -*-
from copy import copy

from datetime import timedelta, datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.translation import gettext as _
from djangotoolbox.fields import ListField, EmbeddedModelField
from ikwen.accesscontrol.models import Member
from ikwen.billing.models import PaymentMean
from ikwen.core.models import Model
from ikwen.core.utils import to_dict
from ikwen_shavida.conf.utils import is_vod_operator


class SalesConfig(Model):
    BROADCASTING_TIME = "Broadcasting"
    DATA_VOLUME = "Volume"
    UNITS_CHOICES = (
        (BROADCASTING_TIME, _("Broadcasting Time")),
        (DATA_VOLUME, _("Data Volume")),
    )
    max_inactivity = models.PositiveIntegerField(default=14,
                                                 help_text=_("Number of days after which user is considered inactive."))
    welcome_offer = models.BooleanField(default=200,
                                        help_text=_("Number of MegaBytes offered for free trial."))
    welcome_offer_duration = models.IntegerField(default=7,
                                                 help_text=_("Number of days left to use free trial."))
    # unit = models.CharField(max_length=30, choices=UNITS_CHOICES, editable=getattr(settings, 'IS_CONTENT_VENDOR', False),
    #                         help_text=_("Your trade measurement."))


class RetailBundle(Model):
    name = models.CharField(unique=True, max_length=30,
                            help_text=_("How you call this plan."))
    quantity = models.PositiveIntegerField(unique=True,
                                           help_text=_("Number of hours or Number of MegaBytes depending "
                                                       "on your unit of trade."))
    cost = models.PositiveIntegerField(help_text=_("Cost of this bundle."))
    adult_authorized = models.BooleanField(default=False,
                                           help_text=_("Check it this bundle gives access to adult content."))
    duration = models.PositiveIntegerField(default=3,
                                           help_text=_("Number of days the customer must take to view empty his bundle."
                                                       "After that it is automatically brought back to 0."))
    comment = models.CharField(max_length=60, blank=True, null=True,
                               help_text=_("Additional information about this bundle that may help user."))

    class Meta:
        verbose_name = 'Bundle'

    def __unicode__(self):
        return self.name


class Plan(Model):
    bundle = EmbeddedModelField('RetailBundle')
    start = models.DateTimeField()
    finish = models.DateTimeField()
    duration = models.PositiveIntegerField()
    total_cost = models.PositiveIntegerField()

    def __unicode__(self):
        return self.bundle.name


class VODBundle(Model):
    volume = models.PositiveSmallIntegerField(default=1000, editable=False,
                                              help_text=_("Amount of MegaBytes of available for the customer "
                                                          "(1 GigaBytes = 1000 MegaBytes)."))
    cost = models.FloatField(unique=True,
                             help_text=_("Cost of the bundle."))
    duration = models.PositiveSmallIntegerField(help_text=_("Number of days the customer must take to view empty his bundle. "
                                                            "After that it is automatically brought back to 0."))
    adult_authorized = models.BooleanField(default=False,
                                           help_text=_("Check it this bundle gives access to adult content."))
    comment = models.CharField(max_length=60, blank=True, null=True,
                               help_text=_("Additional information about this bundle that may help user."))

    class Meta:
        verbose_name = 'VOD Bundle'
        verbose_name_plural = 'VOD Bundles'


class Prepayment(Model):
    PENDING = "Pending"
    CONFIRMED = "Confirmed"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (CONFIRMED, "Confirmed"),
    )
    member = models.ForeignKey(Member)
    amount = models.PositiveIntegerField()
    paid_on = models.DateTimeField(blank=True, null=True)
    currency = EmbeddedModelField('currencies.Currency', blank=True, null=True, editable=False)  # Currency used when placing this Order
    payment_mean = models.ForeignKey(PaymentMean, null=True, editable=False)
    duration = models.PositiveSmallIntegerField(default=30,
                                                help_text=_("Number of days for this to expire."))
    status = models.CharField(choices=STATUS_CHOICES, max_length=15, default=PENDING)

    class Meta:
        abstract = True

    def __unicode__(self):
        return self.member.email

    def get_expiry(self):
        if not self.paid_on:
            # Unpaid prepayment are considered expired, this is
            # why their expiry will be set to 2 days before now.
            return datetime.now() - timedelta(days=2)
        expiry = self.paid_on + timedelta(days=self.duration)
        return expiry

    def _get_days_left(self):
        """
        Number of days left for this RetailPrepayment to expire
        """
        if self.paid_on:
            spent = datetime.now() - self.paid_on
            return self.duration - spent.days
        return -1  # Return an arbitrary value of -1 day as long as the user didn't pay. The counter starts upon payment
    days_left = property(_get_days_left)


class RetailPrepayment(Prepayment):
    balance = models.PositiveIntegerField(help_text=_("Quantity you allow your customer to order depending on "
                                                      "your unit of sales. If selling volumes of data, give the value in "
                                                      "<strong>MegaBytes</strong> else give value in <strong>Broadcasting hours</strong>."))
    adult_authorized = models.BooleanField(default=False,
                                           help_text=_("Check if you want customer to access adult content."))

    class Meta:
        verbose_name = 'Bundle Purchase'
        verbose_name_plural = "Bundles' Purchases"


class VODPrepayment(Prepayment):
    balance = models.PositiveIntegerField(default=1000,
                                          help_text=_("The number of bytes of streaming remaining to the client. "
                                                      "(1 GigaBytes = 1,000,000,000 Bytes)"))
    adult_authorized = models.BooleanField(default=False,
                                           help_text=_("Check if you want customer to access adult content."))
    teller = models.ForeignKey(Member, blank=True, null=True, related_name='teller',
                               help_text=_("Staff who actually confirmed this Prepayment."))

    class Meta:
        verbose_name = "Bundle Payment"
        verbose_name_plural = "Bundle Payments"


# class Provider(models.Model):
#     member = models.ForeignKey(Member)
#     share = models.PositiveIntegerField(default=0,
#                                         help_text=_("Percentage you earn out of sales of the provider's content"))
#     created_on = models.DateTimeField(default=timezone.now)
#     updated_on = models.DateTimeField(default=timezone.now, auto_now_add=True)


class ContentUpdate(Model):
    RUNNING = "Running"  # Status used to indicate that this ContentUpdate is an auto-select currently running
    PENDING = "Pending"
    AUTHORIZED = "Authorized"
    DELIVERED = "Delivered"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (AUTHORIZED, "Authorized"),
        (DELIVERED, "Delivered")
    )
    member = models.ForeignKey(Member)
    add_list = models.TextField(blank=True)
    movies_add_list = ListField(EmbeddedModelField('movies.Movie'), blank=True, null=True, editable=False)
    series_episodes_add_list = ListField(EmbeddedModelField('movies.SeriesEpisode'), blank=True, null=True, editable=False)
    add_list_size = models.PositiveIntegerField(default=0)
    add_list_duration = models.PositiveIntegerField(default=0)
    delete_list = models.TextField(blank=True)
    movies_delete_list = ListField(EmbeddedModelField('movies.Movie'), blank=True, null=True, editable=False)
    series_episodes_delete_list = ListField(EmbeddedModelField('movies.SeriesEpisode'), blank=True, null=True, editable=False)
    delete_list_size = models.PositiveIntegerField(default=0)
    cost = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30, default=PENDING, choices=STATUS_CHOICES,
                              help_text=_("Status of the update. ** DO NOT CHANGE IF IT IS 'Running' **"))
    provider = models.ForeignKey(Member, related_name="provider", blank=True, null=True, editable=False,
                                 help_text="Provider of this update.")
    provider_website = models.CharField(max_length=60, blank=True, null=True, editable=is_vod_operator,
                                        help_text="Website name of the provider of this update.")

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'

    def get_categories_share(self):
        from movies.models import Series
        share = {}
        count = 0
        for movie in self.movies.all():
            for category in movie.categories.all():
                count += 1
                if category.natural:
                    if share.get(category.slug):
                        share[category.slug] += 1
                    else:
                        share[category.slug] = 1

        share[Series.SLUG] = len(self.series_episodes_add_list)

        share_copy = copy(share)
        l = share.values()
        l.sort(reverse=True)
        sorted_share = []
        for i in range(len(l)):
            for key in share.keys():
                if share_copy.get(key) == l[i]:
                    sorted_share.append(key)
                    del(share_copy[key])
        return sorted_share

    def get_series(self):
        series = set()
        for series_episode in self.series_episodes_add_list:
            series.add(series_episode.series)
        return list(series)

    def to_dict(self, target=None):
        movies_add_list = self.movies_add_list
        series_episodes_add_list = self.series_episodes_add_list
        movies_delete_list = self.movies_delete_list
        series_episodes_delete_list = self.series_episodes_delete_list
        member = self.member.to_dict()
        var = to_dict(self)
        var['member'] = member
        var['display_created_on'] = self.created_on.strftime('%Y-%m-%d %H:%M')
        media_add_list = [movie.to_dict() for movie in movies_add_list]
        media_add_list.extend([episode.to_dict() for episode in series_episodes_add_list])
        media_delete_list = [movie.to_dict() for movie in movies_delete_list]
        media_delete_list.extend([episode.to_dict() for episode in series_episodes_delete_list])
        var['movies_add_list'] = media_add_list
        var['movies_delete_list'] = media_delete_list
        return var


class UnitPrepayment(Prepayment):
    """
    Prepayment made to watch a single movie or Series.
    In case of Series, it allows to watch all episodes.
    """
    MOVIE = 'movie'
    SERIES = 'series'
    media_type = models.CharField(max_length=10)
    media_id = models.CharField(max_length=24)
    expiry = models.DateTimeField(blank=True, null=True)
    teller = models.ForeignKey(Member, blank=True, null=True, related_name='cashier',
                               help_text=_("Staff who actually confirmed this Prepayment."))
    download_link = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Single Item Payment"
        verbose_name_plural = "Single Item Payments"

    def get_media(self):
        from ikwen_shavida.movies.models import Movie, Series
        try:
            if self.media_type == 'movie':
                return Movie.objects.get(pk=self.media_id).title
            series = Series.objects.get(pk=self.media_id)
            return _(u"%s season %d" % (series.title, series.season))
        except ObjectDoesNotExist:
            return _('N/A: Media deleted')
    get_media.short_description = 'Media'
