# -*- coding: utf-8 -*-
import random

from bson.objectid import ObjectId
from django.conf import settings

from django.db import models
from django.db.models.signals import post_syncdb
from django.dispatch import receiver
from django.utils import timezone
from django_mongodb_engine.contrib import MongoDBManager
from djangotoolbox.fields import ListField, EmbeddedModelField
from django.utils.translation import gettext as _
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.templatetags.shared_media import from_provider
from ikwen.core.fields import MultiImageField
from ikwen.core.models import Model, AbstractWatchModel, Service
from ikwen.core.utils import to_dict, get_service_instance
from ikwen_shavida.conf.utils import is_content_vendor, is_vod_operator
from ikwen_shavida.sales.models import SalesConfig


def series_cmp_orders(s1, s2):
    if s1.orders > s2.orders:
        return 1
    elif s1.orders < s2.orders:
        return -1
    return 0


class Category(models.Model):
    """
    A category of movie
    """
    title = models.CharField(max_length=100, unique=True,
                             help_text=_("Title of the category."))
    slug = models.SlugField(max_length=100, unique=True,
                            help_text=_("Auto-filled. If edited, use only lowercase letters and -. Space is not allowed"
                                        " Eg: <strong>sci-fi</strong>"))
    is_adult = models.BooleanField(default=False,
                                   help_text=_("Check if it is supposed to contain adult movies."))
    smart = models.BooleanField(default=False,
                                help_text=_("Check if not a common category. Eg: 'Recent', 'Top 20' are good candidates"
                                            " for smart categories. They appear before normal categories in the list"
                                            " on the site."))
    order_of_appearance = models.IntegerField(help_text=_("Order of appearance in the list of categories."))
    appear_in_main = models.BooleanField(default=False,
                                         help_text=_("Check if you want it to be visible out of the 'More ...' section."))
    visible = models.BooleanField(default=True,
                                  help_text=_("Check if you want to make this category visible on the site"))
    previews_title = models.CharField(max_length=45, blank=True, null=True,
                                      help_text=_("Title you want to appear on the category preview on home page."
                                                  " If not set, the title will be used."))
    previews_length = models.PositiveSmallIntegerField(default=0,
                                                       help_text=_("Number of items you want to appear in the preview"
                                                                   " of the category on home page."))

    def get_movies_queryset(self):
        return Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(self.id)}}, 'visible': True}).order_by('-id')

    def get_series_queryset(self):
        return Series.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(self.id)}}, 'visible': True}).order_by('-id')

    def __unicode__(self):
        return self.title

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"


class MediaInterface():

    def _get_display_size(self):
        """
        Size of movie in a format suitable for display
        """
        return '%d MB' % self.size if self.size < 1024 else '%.2f GB' % (self.size / 1024.0)
    display_size = property(_get_display_size)
    _get_display_size.short_description = 'Size'

    def _get_display_duration(self):
        """
        Duration of the movie in a format suitable for display
        """
        duration = self.duration
        return '%dmn' % duration if duration < 60 else '%dh%dmn' % (duration / 60, duration % 60)
    display_duration = property(_get_display_duration)
    _get_display_duration.short_description = 'Duration'

    def _get_load(self):
        """
        Load represented by media depending on the unit of sales in sales.models.SalesConfig
        duration if unit == 'Broadcasting', size otherwise
        """
        if getattr(settings, 'IS_GAME_VENDOR', False):
            return self.price
        unit = getattr(settings, 'SALES_UNIT', SalesConfig.BROADCASTING_TIME)
        return self.duration if unit == SalesConfig.BROADCASTING_TIME else self.size
    load = property(_get_load)

    def _get_display_load(self):
        """
        Load in a format suitable for display depending on the unit of sales in sales.models.SalesConfig
        duration if unit == 'Broadcasting', size otherwise
        """
        if getattr(settings, 'IS_GAME_VENDOR', False):
            config = get_service_instance().config
            return "%s %d" % (config.currency_symbol, self.price)
        unit = getattr(settings, 'SALES_UNIT', SalesConfig.BROADCASTING_TIME)
        return self.display_duration if unit == SalesConfig.BROADCASTING_TIME else self.display_size
    display_load = property(_get_display_load)


class Media(AbstractWatchModel, MediaInterface):
    title = models.CharField(max_length=100,
                             help_text=_("Title of the media."))
    size = models.PositiveIntegerField(default=0,
                                       help_text=_("Size in MegaBytes (MB) of the file."))
    duration = models.PositiveIntegerField(default=0,
                                           help_text=_("Duration in minutes of the media file."))
    clicks = models.PositiveIntegerField(default=0,
                                         help_text=_("Number of times movie was clicked for streaming. Can be considered "
                                                     "as the number of view in a certain way."))

    class Meta:
        abstract = True

    def _get_filename(self):
        return self.resource

    def _set_filename(self, value):
        self.__dict__['resource'] = value

    filename = property(_get_filename, _set_filename)


class Trailer(Media):
    """
    Trailer of a Movie or Series
    """
    slug = models.SlugField(unique=True,
                            help_text=_("Auto-filled. If edited, use only lowercase letters and '-'. Space is not allowed"
                                        " Eg: <strong>trailer-tomorrow-never-dies</strong>"))
    resource = models.CharField(verbose_name=_("Media resource"), max_length=255, unique=True,
                                help_text=_("Filename (Eg: <strong>Avatar_Trailer.mp4</strong>) or "
                                            "URL (Eg: <strong>http://youtube.com/watch?v=2nYwryHPSs</strong>)"))
    resource_mob = models.CharField(verbose_name=_("Mobile media resource"), max_length=255, blank=True,
                                    help_text=_("Filename (Eg: <strong>Avatar_Trailer.mob.mp4</strong>) or "
                                                "URL (Eg: <strong>http://m.youtube.com/watch?v=2nYwryHPSs</strong>). "
                                                "Leave blank to copy the same value as above"))


class Movie(Media):
    objects = MongoDBManager()
    MAX_RECENT = 96
    TOTAL_RECOMMENDED = 12  # Number of items to recommend in a case where there are enough to recommend
    MIN_RECOMMENDED = 8  # Number of items to recommend in case where there are not enough after the normal algorithm
    slug = models.SlugField(unique=True,
                            help_text=_("Auto-filled. If edited, use only lowercase letters and -. Space is not allowed"
                                        " Eg: <strong>tomorrow-never-dies</strong>"))
    release = models.DateField(blank=True, null=True,
                               help_text=_("Date of release of movie in country of origin."))
    synopsis = models.TextField(blank=True)
    resource = models.CharField(verbose_name=_("Media resource"), max_length=255, blank=True,
                                help_text=_("Filename (Eg: <strong>Avatar.mp4</strong>) or "
                                            "URL (Eg: <strong>http://youtube.com/watch?v=2nYwryHPSs</strong>)"))
    resource_mob = models.CharField(verbose_name=_("Mobile media resource"), max_length=255, blank=True,
                                    help_text=_("Filename (Eg: <strong>Avatar.mob.mp4</strong>) or "
                                                "URL (Eg: <strong>http://m.youtube.com/watch?v=2nYwryHPSs</strong>). "
                                                "Leave blank to copy the same value as above"))
    poster = MultiImageField(upload_to='movies', blank=True, null=True)
    price = models.PositiveIntegerField(default=0, editable=is_content_vendor,
                                        help_text=_("Cost of sale of this movie to VOD operators."))
    view_price = models.FloatField(default=0,
                                   help_text=_("Cost to view this movie in streaming."))
    download_price = models.FloatField(default=0,
                                       help_text=_("Cost to download this movie."))
    trailer_resource = models.CharField(max_length=255, blank=True, null=True,
                               help_text=_("Filename (Eg: <strong>Avatar.mob.mp4</strong>), URL "
                                           "Embed code (Eg: <strong>&lt;iframe src='...'&gt;&lt;/iframe&gt;</strong>) "
                                           "for trailer of this movie."))
    provider = models.ForeignKey(Service, editable=False, blank=True, null=True, related_name='+',
                                 help_text=_("Provider of this movie."))
    fake_orders = models.IntegerField(default=0,
                                      help_text=_("Random value you want customers to think the movie was ordered "
                                                  "that number of times."))
    orders = models.IntegerField(default=0,
                                 help_text=_("Number of times movie was actually ordered."))
    fake_clicks = models.PositiveIntegerField(default=0,
                                              help_text=_("Random value you want customers to think the movie was "
                                                          "viewed that number of times."))
    visible = models.BooleanField(default=True,
                                  help_text=_("Check if you want the movie to be visible on the site."))
    categories = ListField(EmbeddedModelField('Category'),
                           help_text=_("Categories the movie is part of."))
    # Tells whether this Movie is part of an Adult category.
    # Set automatically upon Movie.save() by checking categories
    is_adult = models.BooleanField(default=False, verbose_name=_("Adult content"))
    groups = models.CharField(max_length=100, default='', blank=True,
                              help_text=_("Group the movie belongs to (write lowercase). Will be used for suggestions "
                                          "Eg: Write <strong>matrix</strong> for all movies Matrix 1, 2 and 3"))
    tags = models.CharField(max_length=150,
                            help_text=_("Key words used to retrieve the movie in search. Typically title of movie written "
                                        "lowercase and main actors, all separated by space. Eg: <strong>matrix keanu reaves</strong>"))
    # Random field used for random selections in MongoDB
    rand = models.FloatField(default=random.random, db_index=True, editable=False)

    owner_fk_list = ListField()

    count_history = ListField()  # count can be the number of orders or views of this Media
    download_history = ListField()
    earnings_history = ListField()

    total_count = models.IntegerField(default=0)
    total_download = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)
    current_earnings = models.IntegerField(default=0,
                                           help_text="Earnings generated by the movie since the last reset. Differs "
                                                     "from total_earnings by the fact that it can be reset at times.")

    class Meta:
        if getattr(settings, 'IS_GAME_VENDOR', False):
            verbose_name = 'Product'

    def _get_display_orders(self):
        """
        Number of orders(based on fake_orders) of movie in a format suitable for display
        """
        if self.fake_orders < 1000:
            return self.fake_orders
        else:
            num500 = self.fake_orders / 500
            return "%d+" % (num500 * 500)
    display_orders = property(_get_display_orders)

    def _get_display_clicks(self):
        """
        Number of clicks(based on fake_clicks) of movie in a format suitable for display
        """
        if self.fake_clicks < 1000:
            return self.fake_clicks
        else:
            num500 = self.fake_clicks / 500
            return "%d+" % (num500 * 500)
    display_clicks = property(_get_display_clicks)

    def _get_categories_to_string(self):
        categories = [category.title for category in self.categories]
        return ", ".join(categories)
    categories_to_string = property(_get_categories_to_string)

    def _get_type(self):
        return "movie"
    type = property(_get_type)

    def _get_trailer(self):
        """
        Gets the trailer of this movie
        """
        if self.trailer_resource:
            return Trailer(title='', slug='', size=0, duration=3, resource=self.trailer_resource)
    trailer = property(_get_trailer)

    def _get_owner_list(self):
        owner_list = []
        for pk in self.owner_fk_list:
            try:
                owner_list.append(Member.objects.get(pk=pk))
            except:
                pass
        return owner_list
    owner_list = property(_get_owner_list)

    def to_dict(self):
        var = to_dict(self)
        var['poster'] = {
            'url': from_provider(self.poster.url, self.provider) if self.poster.name else 'default_poster.jpg',
            'small_url': from_provider(self.poster.small_url, self.provider) if self.poster.name else 'default_poster.jpg',
            'thumb_url': from_provider(self.poster.thumb_url, self.provider) if self.poster.name else 'default_poster.jpg'
        }
        var['type'] = self.type
        var['display_orders'] = self.display_orders
        var['display_clicks'] = self.display_clicks
        var['load'] = self.load
        var['display_load'] = self.display_load
        del(var['resource'])
        del(var['resource_mob'])
        del(var['synopsis'])
        del(var['provider_id'])
        del(var['visible'])
        del(var['fake_orders'])
        del(var['fake_clicks'])
        del(var['categories'])
        del(var['groups'])
        del(var['rand'])
        return var

    def __unicode__(self):
        return self.title


class Series(AbstractWatchModel, MediaInterface):
    objects = MongoDBManager()
    SLUG = 'series'
    title = models.CharField(max_length=100,
                             help_text=_("Title of the series."))
    season = models.PositiveSmallIntegerField()
    slug = models.SlugField(unique=True,
                            help_text=_("Auto filled. But add -seasonX manually. Eg: <strong>arrow-saison3</strong>"))
    release = models.DateField(blank=True, null=True,
                               help_text=_("Date of release of movie in country of origin."))
    episodes_count = models.PositiveIntegerField(help_text="Number of episodes of this series.")  # Number of episodes
    synopsis = models.TextField()
    poster = MultiImageField(upload_to='series', blank=True, null=True)
    provider = models.ForeignKey(Service, editable=False, blank=True, null=True, related_name='+',
                                 help_text=_("Provider of this series."))
    price = models.IntegerField(default=0, editable=is_content_vendor,
                                help_text=_("Cost of sale of this series to VOD operators."))
    view_price = models.IntegerField(default=0,
                                     help_text=_("Cost to view all episodes of this series in streaming."))
    download_price = models.FloatField(default=0,
                                       help_text=_("Cost to download all episodes of this series."))
    # Tells whether this Movie is part of an Adult category.
    # Set automatically upon Series.save() by checking categories
    is_adult = models.BooleanField(default=False, verbose_name=_("Adult content"))
    trailer_resource = models.CharField(max_length=255, blank=True, null=True,
                               help_text=_("Filename (Eg: <strong>Avatar.mob.mp4</strong>), URL "
                                           "Embed code (Eg: <strong>&lt;iframe src='...'&gt;&lt;/iframe&gt;</strong>) "
                                           "for trailer of this movie."))
    categories = ListField(EmbeddedModelField('Category'),
                           help_text=_("Categories the series is part of."))
    visible = models.BooleanField(default=True)
    groups = models.CharField(max_length=100, default='', blank=True,
                              help_text=_("Group the series belongs to (write lowercase). Will be used for suggestions "
                                          "Eg: Write <strong>scandal</strong> for Scandal season 1, 2, 3 ..."))
    tags = models.CharField(max_length=150,
                            help_text=_("Key words used to retrieve the series in search. Typically title of movie written "
                                        "lowercase and main actors, all separated by space. Eg: <strong>scandal keanu reaves</strong>"))
    # Random field used for random selections in MongoDB
    rand = models.FloatField(default=random.random, db_index=True, editable=False)

    owner_fk_list = ListField()

    count_history = ListField()  # count can be the number of orders or views of this Media
    download_history = ListField()
    earnings_history = ListField()

    total_count = models.IntegerField(default=0)
    total_download = models.IntegerField(default=0)
    total_earnings = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Series'
        unique_together = ('title', 'season', )

    def _get_full_title(self):
        """
        Gets full title of the Series; that is the title followed by "Season X"
        """
        return "%s - %s %d" % (self.title, _('Season'), self.season)
    full_title = property(_get_full_title)

    def _get_display_orders(self):
        """
        Number of orders(based on fake_orders) of the series.
        Is arbitrarily considered as the number of fake_orders of the first episode of the series.
        It is returned in a format suitable for display
        """
        query_set = SeriesEpisode.objects.filter(series=self.id)
        first_episode = query_set[0] if len(query_set) > 0 else None
        if first_episode:
            if first_episode.fake_orders < 1000:
                return first_episode.fake_orders
            else:
                num500 = first_episode.fake_orders / 500
                return "%d+" % (num500 * 500)
        else:
            return 20  # This is an arbitrary value
    display_orders = property(_get_display_orders)

    def _get_display_clicks(self):
        """
        Number of clicks(based on fake_clicks) of the series.
        Is arbitrarily considered as the number of fake_clicks of the first episode of the series.
        It is returned in a format suitable for display
        """
        query_set = SeriesEpisode.objects.filter(series=self.id)
        first_episode = query_set[0] if len(query_set) > 0 else None
        if first_episode:
            if first_episode.fake_clicks < 1000:
                return first_episode.fake_clicks
            else:
                num500 = first_episode.fake_clicks / 500
                return "%d+" % (num500 * 500)
        else:
            return 150  # This is an arbitrary value
    display_clicks = property(_get_display_clicks)

    def _get_orders(self):
        """
        Calculate the number of orders of the series as the average number of orders of the episodes.
        """
        episodes = SeriesEpisode.objects.filter(series=self.id)
        if len(episodes) == 0:
            return 0
        total_orders = 0
        for episode in episodes:
            total_orders += episode.orders
        return total_orders / len(episodes)
    orders = property(_get_orders)
    _get_orders.short_description = 'Orders'

    def _get_clicks(self):
        """
        Calculate the number of clicks of the series as the average number of clicks of the episodes.
        """
        episodes = SeriesEpisode.objects.filter(series=self.id)
        if len(episodes) == 0:
            return 0
        total_clicks = 0
        for episode in episodes:
            total_clicks += episode.orders
        return total_clicks / len(episodes)
    clicks = property(_get_clicks)
    _get_clicks.short_description = 'Clicks'

    def _get_size(self):
        """
        Calculate the size of the series by summing up the size of episodes individual files.
        """
        sizes = [series_episode.size for series_episode in SeriesEpisode.objects.filter(series=self)]
        return reduce(lambda x, y: x + y, sizes) if len(sizes) > 0 else 0
    size = property(_get_size)

    def _get_duration(self):
        """
        Calculate the duration of the series by summing up the duration of episodes individual files.
        """
        durations = [series_episode.duration for series_episode in SeriesEpisode.objects.filter(series=self)]
        return reduce(lambda x, y: x + y, durations) if len(durations) > 0 else 0
    duration = property(_get_duration)

    def _get_categories_to_string(self):
        categories = [category.title for category in self.categories]
        return ", ".join(categories)
    categories_to_string = property(_get_categories_to_string)

    def _get_episodes(self):
        """
        Gets the list of episodes of this series
        """
        return [series_episode for series_episode in SeriesEpisode.objects.filter(series=self)]
    episodes = property(_get_episodes)

    def _get_seriesepisode_set(self):
        """
        Gets the query_set containing all episodes of this series. This naturally exists
        in django, but this backward query was intentionally by declaring the field series
        in class SeriesEpisode as such:
            series = models.ForeignKey(Series, related_name='+')
        It was removed because it causes error "RelatedObject has no attribute get_internal_type()"
        when running lookups like "Series.object.filter(title__contains=some_value)".
        Since this is internally used by the admin app. We manually restored it
        by creating the property seriesepisode_set below
        """
        return SeriesEpisode.objects.filter(series=self)
    seriesepisode_set = property(_get_seriesepisode_set)

    def _get_trailer(self):
        """
        Gets the trailer of this series
        """
        if self.trailer_resource:
            return Trailer(title='', slug='', size=0, duration=3, resource=self.trailer_resource)
    trailer = property(_get_trailer)

    def _get_type(self):
        return "series"
    type = property(_get_type)

    def _get_owner_list(self):
        owner_list = []
        for pk in self.owner_fk_list:
            try:
                owner_list.append(Member.objects.get(pk=pk))
            except:
                pass
        return owner_list
    owner_list = property(_get_owner_list)

    def to_dict(self):
        var = to_dict(self)
        var['poster'] = {
            'url': from_provider(self.poster.url, self.provider) if self.poster.name else 'default_poster.jpg',
            'small_url': from_provider(self.poster.small_url, self.provider) if self.poster.name else 'default_poster.jpg',
            'thumb_url': from_provider(self.poster.thumb_url, self.provider) if self.poster.name else 'default_poster.jpg'
        }
        var['type'] = self.type
        var['display_orders'] = self.display_orders
        var['display_clicks'] = self.display_clicks
        var['display_load'] = self.display_load
        var['full_title'] = self.full_title
        del(var['rand'])
        del(var['synopsis'])
        del(var['provider_id'])
        del(var['visible'])
        del(var['groups'])
        del(var['categories'])
        return var

    def __unicode__(self):
        return "%s Season %d" % (self.title, self.season)


class SeriesEpisode(Media):
    series = models.ForeignKey(Series, related_name='+')
    slug = models.SlugField(help_text=_("Auto-filled. If edited, use only lowercase letters and -. Space is not allowed"
                                        " Eg: <strong>arrow-s03e04</strong>"))
    resource = models.CharField(verbose_name=_("Media resource"), max_length=255, blank=True,
                                help_text=_("Full filename (Eg: <strong>Scandal/Scandal-season3/Scandal-S03E05.mp4</strong>) or "
                                            "URL (Eg: <strong>http://youtube.com/watch?v=2nYwryHPSs</strong>)"))
    resource_mob = models.CharField(verbose_name=_("Mobile media resource"), max_length=255, blank=True,
                                    help_text=_("Full filename (Eg: <strong>Scandal/Scandal-season3/Scandal-S03E05.mob.mp4</strong>) or "
                                                "URL (Eg: <strong>http://m.youtube.com/watch?v=2nYwryHPSs</strong>). "
                                                "Leave blank to copy the same value as above"))
    fake_orders = models.IntegerField(default=0)
    orders = models.IntegerField(default=0)
    fake_clicks = models.PositiveIntegerField(default=0)
    # Tells whether this Movie is part of an Adult category.
    # Set automatically upon Movie.save() by checking categories
    is_adult = models.BooleanField(default=False)

    def _get_view_price(self):
        return self.series.view_price
    view_price = property(_get_view_price)

    def _get_poster(self):
        return self.series.poster
    poster = property(_get_poster)

    def _get_type(self):
        return "series"
    type = property(_get_type)

    def to_dict(self):
        poster = {
            'url': from_provider(self.poster.url, self.series.provider) if self.poster.name else 'default_poster.jpg',
            'small_url': from_provider(self.poster.small_url, self.series.provider) if self.poster.name else 'default_poster.jpg',
            'thumb_url': from_provider(self.poster.thumb_url, self.series.provider) if self.poster.name else 'default_poster.jpg'
        }
        var = to_dict(self)
        var['poster'] = poster
        var['type'] = self.type
        var['orders'] = 'fake_orders'
        var['clicks'] = 'fake_clicks'
        var['load'] = self.load
        del(var['resource'])
        del(var['resource_mob'])
        del(var['fake_orders'])
        return var

    def __unicode__(self):
        return self.title


@receiver(post_syncdb)
def create_text_index_on_tags_and_groups(sender, **kwargs):
    from pymongo import MongoClient
    client = MongoClient()
    db_name = getattr(settings, 'DATABASES')['default']['NAME']
    db = client[db_name]
    db.movies_movie.create_index([('tags', 'text'), ('groups', 'text')])
    db.movies_series.create_index([('tags', 'text'), ('groups', 'text')])
