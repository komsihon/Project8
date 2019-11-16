# -*- coding: utf-8 -*-
import re
import random

from django.conf import settings
from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify
from django.utils.translation import gettext_lazy as _
from ikwen.core.utils import get_service_instance
from import_export import resources
from import_export.admin import ImportExportMixin
from ikwen.accesscontrol.models import Member

from ikwen_shavida.conf.utils import is_vod_operator
from ikwen_shavida.movies.models import Movie, Category, Series, SeriesEpisode, Trailer
from ikwen_shavida.sales.models import ContentUpdate


# TODO: Filter Movie and Series per Category

def add_movies_to_top20(modeladmin, request, queryset):
    top_category = Category.objects.get(slug='top')
    for movie in queryset:
        movie_categories = list(movie.categories.all())
        if top_category in movie_categories:
            return False
        else:
            movie.categories.add(top_category)


def remove_movies_from_top20(modeladmin, request, queryset):
    top_category = Category.objects.get(slug='top')
    for movie in queryset:
        movie_categories = list(movie.categories.all())
        if top_category not in movie_categories:
            return
        movie.categories.remove(top_category)


def add_media_to_delete_list(modeladmin, request, queryset):
    member = request.user
    try:
        update = ContentUpdate.objects.get(member=member, status=ContentUpdate.PENDING)
    except ContentUpdate.DoesNotExist:
        update = ContentUpdate(member=member)
    delete_list = []
    delete_list_size = 0
    update.movies_delete_list.clear()
    update.series_episodes_delete_list.clear()
    for media in queryset:
        if type(media).__name__ == 'Movie':
            update.movies_delete_list.add(media)
        else:
            update.series_episodes_delete_list.add(media)
        delete_list_size += media.size
        for filename in media.resource.split(','):
            delete_list.append(filename.strip())
    update.delete_list = ','.join(delete_list)
    update.delete_list_size = delete_list_size
    update.save()


add_movies_to_top20.short_description = "Add selected movies in Top 20"
remove_movies_from_top20.short_description = "Remove selected movies from Top 20"
add_media_to_delete_list.short_description = "Mark for deletion"


def remove_special_words(s):
    s = re.sub("^the ", '', s)
    s = re.sub("^at ", '', s)
    s = re.sub("^in ", '', s)
    s = re.sub("^le ", '', s)
    s = re.sub("^la ", '', s)
    s = re.sub("^les ", '', s)
    s = re.sub("^l'", '', s)
    s = re.sub("^un ", '', s)
    s = re.sub("^une ", '', s)
    s = re.sub("^des ", '', s)
    s = re.sub("^d'", '', s)
    s = re.sub("^de ", '', s)
    s = re.sub("^du ", '', s)
    s = re.sub("^a ", '', s)
    s = re.sub("^et ", '', s)
    s = re.sub("^en ", '', s)
    s = s.replace(" the ", " ")\
        .replace(" at ", " ")\
        .replace(" in ", " ")\
        .replace(" of ", " ")\
        .replace(" le ", " ")\
        .replace(" la ", " ")\
        .replace(" les ", " ")\
        .replace(" l'", " ")\
        .replace(" un ", " ")\
        .replace(" une ", " ")\
        .replace(" des ", " ")\
        .replace(" d'", " ")\
        .replace(" de ", " ")\
        .replace(" du ", " ")\
        .replace(" a ", " ")\
        .replace(" et ", " ")\
        .replace(" en ", " ")\
        .replace(" 1", "")\
        .replace(" 2", "")\
        .replace(" 3", "")\
        .replace(" 4", "")\
        .replace(" 5", "")\
        .replace(" 6", "")\
        .replace(" 7", "")\
        .replace(" 8", "")\
        .replace(" 9", "")
    return s


def get_title_from_filename(filename):
    PREFIXES = ['cine_', 'da_', 'clip_', 'tuto_', 'Hd_', 'comedie_', 'oms_', 'gag_', 'xxl_', 'doc_', 'Xcamer_']
    # Strip extension
    title = filename
    idx = title.rfind('.')
    title = title[:idx]

    # Strip custom prefix
    for prefix in PREFIXES:
        title = title.replace(prefix, '')
    title = title.replace('.', ' ').replace('_', ' ')
    return title


class MovieResource(resources.ModelResource):

    def before_save_instance(self, instance, dry_run):
        title = get_title_from_filename(instance.resource)
        instance.resource = instance.resource.replace(' ', '.')
        slug = slugify(title)
        instance.slug = slug
        fake_bonus = int(random.random() * 1000) * 2
        instance.fake_orders += fake_bonus
        instance.fake_clicks = instance.fake_orders + fake_bonus
        if instance.trailer_resource:
            instance.trailer = get_object_or_404(Trailer, slug=instance.trailer_resource)
        instance.visible = False
        instance.tags = remove_special_words(title.lower()) + " " + instance.tags.lower()
        instance.title = 'IMP ' + title.capitalize()
        instance.provider = get_service_instance()

    def skip_row(self, instance, original):
        if '/' in instance.resource:
            return True
        title = get_title_from_filename(instance.resource)
        slug = slugify(title)
        try:
            Movie.objects.get(resource=instance.resource)
            return True
        except Movie.DoesNotExist:
            try:
                Movie.objects.get(slug=slug)
                return True
            except Movie.DoesNotExist:
                return False

    class Meta:
        model = Movie
        skip_unchanged = True
        exclude = ('poster', 'synopsis', 'visible', 'categories')
        import_id_fields = ('resource', 'view_price', 'size', 'duration', 'groups', 'tags')\
            if is_vod_operator() else ('resource', 'price', 'size', 'duration', 'groups', 'tags')


class SeriesResource(resources.ModelResource):

    def before_save_instance(self, instance, dry_run):
        slug = slugify(instance.title)
        instance.slug = slug
        if instance.trailer_resource:
            instance.trailer = get_object_or_404(Trailer, slug=instance.trailer_resource)
        instance.visible = False
        instance.tags = remove_special_words(instance.title.lower()) + " " + instance.tags.lower()
        instance.title = 'IMP ' + instance.title.capitalize()
        instance.provider = get_service_instance()

    def skip_row(self, instance, original):
        slug = slugify(instance.title)
        try:
            Series.objects.get(slug=slug)
            return True
        except Series.DoesNotExist:
            return False

    class Meta:
        model = Series
        skip_unchanged = True
        exclude = ('poster', 'synopsis', 'visible', 'categories')
        import_id_fields = ('title', 'season', 'view_price', 'episodes_count', 'groups', 'tags')\
            if is_vod_operator() else ('title', 'season', 'price', 'view_price', 'episodes_count', 'groups', 'tags')


class SeriesEpisodeResource(resources.ModelResource):

    def before_save_instance(self, instance, dry_run):
        filename = instance.resource
        idx = filename.rfind('/')
        naked_filename = filename[idx + 1:]
        idx = naked_filename.rfind('.')
        title = naked_filename[:idx]
        instance.title = title
        instance.slug = slugify(title)
        fake_bonus = int(random.random() * 300)
        fake_bonus = min(fake_bonus, 200)
        instance.fake_orders += fake_bonus
        instance.fake_clicks = instance.fake_orders + fake_bonus
        instance.provider = get_service_instance()

    def skip_row(self, instance, original):
        if '/' not in instance.resource:
            return True
        return False

    class Meta:
        model = SeriesEpisode
        skip_unchanged = True
        import_id_fields = ('series', 'resource', 'size', 'duration')


class TrailerResource(resources.ModelResource):

    def before_save_instance(self, instance, dry_run):
        instance.title = get_title_from_filename(instance.resource)
        instance.slug = slugify(instance.title)

    def skip_row(self, instance, original):
        try:
            Trailer.objects.get(resource=instance.resource)
            return True
        except Trailer.DoesNotExist:
            return False

    class Meta:
        model = Trailer
        skip_unchanged = True
        import_id_fields = ('resource', 'size', 'duration')


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'previews_title', 'smart', 'previews_length', 'order_of_appearance', 'appear_in_main')
    list_filter = ('smart', 'appear_in_main', 'visible')
    prepopulated_fields = {"slug": ("title",)}

    def save_model(self, request, obj, form, change):
        obj.title = obj.title.strip()
        obj.slug = obj.slug.strip()
        obj.previews_title = obj.previews_title.strip()
        super(CategoryAdmin, self).save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if obj.slug == 'top' or obj.slug == 'series':
            return
        super(CategoryAdmin, self).delete_model(request, obj)


class CategoryListFilter(admin.SimpleListFilter):
    """
    Implements the filtering of Movie or Series by Category
    """

    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('category')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'category_id'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        choices = []
        for category in Category.objects.all():
            choice = (category.id, category.title)
            choices.append(choice)
        return choices


class MovieCategoryListFilter(CategoryListFilter):
    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value():
            result_ids = []
            for m in list(queryset):
                category = Category.objects.get(pk=self.value())
                if category in m.categories:
                    result_ids.append(m.id)
            return Movie.objects.filter(pk__in=result_ids)
        return queryset


_base_fields = ('title', 'slug', 'release', 'synopsis', 'size', 'duration', 'poster')
if getattr(settings, 'IS_GAME_VENDOR', False):
    _list_display = ('title', 'price', 'orders', 'visible')
    _base_fields = ('title', 'slug', 'release', 'synopsis', 'poster')
    _meta = ('visible', 'price', 'trailer_resource', 'groups', 'tags')
elif getattr(settings, 'IS_VOD_OPERATOR', False):
    _list_display = ('title', 'size', 'duration', 'view_price', 'download_price', 'clicks', 'resource', 'visible')
    _meta = ('visible', 'is_adult', 'resource', 'resource_mob', 'view_price', 'download_price',
             'trailer_resource', 'groups', 'tags', 'current_earnings')
else:
    _list_display = ('title', 'size', 'duration', 'price', 'orders', 'resource', 'visible')
    _meta = ('visible', 'is_adult', 'resource', 'price', 'trailer_resource', 'groups', 'tags', )


class MovieAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = MovieResource
    list_display = _list_display
    list_filter = (MovieCategoryListFilter, 'provider', 'visible', 'created_on', )
    fieldsets = (
        (None, {'fields': _base_fields}),
        ('Meta', {'fields': _meta}),
        ('Important dates', {'fields': ('created_on', 'updated_on',)}),
    )
    ordering = ('-id', '-title', '-release', '-clicks', '-orders')
    search_fields = ('title', 'resource', )
    readonly_fields = ('created_on', 'updated_on', 'provider') if getattr(settings, 'IS_GAME_VENDOR', False)\
        else ('is_adult', 'created_on', 'updated_on', 'provider')
    save_on_top = True
    prepopulated_fields = {"slug": ("title",), "tags": ("title",), "groups": ("title",)}
    # actions = [add_movies_to_top20, remove_movies_from_top20]

    def save_model(self, request, obj, form, change):
        obj.title = obj.title.strip()
        obj.slug = obj.slug.strip()
        if obj.trailer_resource:
            obj.trailer_resource = obj.trailer_resource.strip()
        obj.resource = obj.resource.strip()
        if not change:  # Set provider to 'Myself' if the media is added by the owner of the website
            obj.provider = get_service_instance()
        obj.categories = []
        is_adult = False
        for category in Category.objects.all():
            if request.POST.get('cat_%s' % category.id):
                obj.categories.append(category)
                if category.is_adult:
                    is_adult = True
        obj.is_adult = is_adult
        owners = request.POST.get('owners')
        if owners:
            owner_fk_list = [pk.strip() for pk in owners.split(',')]
            obj.owner_fk_list = owner_fk_list
            obj.save()
        super(MovieAdmin, self).save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        search_term = search_term.split(' ')[0][:4]  # Search is narrowed to maximum 4 chars before space
        return super(MovieAdmin, self).get_search_results(request, queryset, search_term)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context['categories'] = Category.objects.all()
        context['owner_fk_list'] = ','.join(obj.owner_fk_list)
        return super(MovieAdmin, self).render_change_form(request, context, add, change, form_url, obj)


class SeriesCategoryListFilter(CategoryListFilter):
    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if self.value():
            result_ids = []
            for m in list(queryset):
                category = Category.objects.get(pk=self.value())
                if category in m.categories:
                    result_ids.append(m.id)
            return Series.objects.filter(pk__in=result_ids)
        return queryset


class SeriesEpisodeInline(admin.TabularInline):
    model = SeriesEpisode
    extra = 0
    fields = ('title', 'slug', 'size', 'duration', 'resource', 'fake_clicks')


class SeriesAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = SeriesResource
    list_display = ('title', 'season', 'clicks', 'display_size', 'display_duration', 'view_price', 'download_price', 'visible') if is_vod_operator()\
        else ('title', 'season', 'display_duration', 'display_size', 'orders', 'clicks', 'price', 'visible')
    list_filter = (SeriesCategoryListFilter, 'provider', 'visible', 'created_on', )
    fieldsets = (
        (None, {'fields': ('title', 'season', 'slug', 'episodes_count', 'release', 'synopsis', 'poster', )}),
        ('Meta', {'fields': ('visible', 'is_adult', 'view_price', 'download_price', 'trailer_resource', 'groups', 'tags', ) if is_vod_operator()
                            else ('visible', 'is_adult', 'price', 'trailer_resource', 'groups', 'tags', )}),
        ('Important dates', {'fields': ('created_on', 'updated_on',)}),
    )
    readonly_fields = ('is_adult', 'created_on', 'updated_on', 'provider')
    ordering = ('-id', '-title', '-release')
    search_fields = ('title', )
    inlines = (SeriesEpisodeInline, )
    save_on_top = True
    prepopulated_fields = {"slug": ("title",), "tags": ("title",), "groups": ("title",)}
    # actions = [add_movies_to_top20, remove_movies_from_top20]

    def save_model(self, request, obj, form, change):
        obj.title = obj.title.strip()
        obj.slug = obj.slug.strip()
        if obj.trailer_resource:
            obj.trailer_resource = obj.trailer_resource.strip()
        if not change:  # Set provider to 'Myself' if the media is added by the owner of the website
            obj.provider = get_service_instance()
        is_adult = False
        obj.categories = []
        for category in Category.objects.all():
            if request.POST.get('cat_%s' % category.id):
                obj.categories.append(category)
                if category.is_adult:
                    is_adult = True
        obj.is_adult = is_adult
        for episode in obj.seriesepisode_set.all():
            episode.is_adult = obj.is_adult
            episode.release = obj.release
            episode.save()
        super(SeriesAdmin, self).save_model(request, obj, form, change)

    def get_search_results(self, request, queryset, search_term):
        search_term = search_term.split(' ')[0][:4]  # Search is narrowed to maximum 4 chars before space
        return super(SeriesAdmin, self).get_search_results(request, queryset, search_term)

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        context['categories'] = Category.objects.all()
        return super(SeriesAdmin, self).render_change_form(request, context, add, change, form_url, obj)


class SeriesEpisodeAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = SeriesEpisodeResource
    list_display = ('series', 'title', 'orders', 'clicks', 'resource')
    list_filter = ('series', 'created_on')
    fieldsets = (
        (None, {'fields': ('series', 'title', 'slug', 'size', 'duration', 'resource', 'resource_mob')}),
        ('Meta', {'fields': ('is_adult', )}),
        ('Interest', {'fields': ('clicks', ) if is_vod_operator() else ('orders', )}),
        ('Important dates', {'fields': ('created_on', 'updated_on',)}),
    )
    ordering = ('-id', '-title')
    search_fields = ('series', 'title', 'resource', )
    save_on_top = True
    prepopulated_fields = {"slug": ("title",)}

    def get_readonly_fields(self, request, obj=None):
        if getattr(settings, 'IS_VOD_OPERATOR', False):
            return 'is_adult', 'clicks', 'size', 'created_on', 'updated_on'
        else:
            return 'is_adult', 'orders', 'size', 'created_on', 'updated_on'

    def save_model(self, request, obj, form, change):
        obj.title = obj.title.strip()
        obj.slug = obj.slug.strip()
        obj.resource = obj.resource.strip()
        if not obj.resource_mob:
            obj.resource_mob = obj.resource
        obj.is_adult = obj.series.is_adult
        obj.release = obj.series.release
        super(SeriesEpisodeAdmin, self).save_model(request, obj, form, change)


class TrailerAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = TrailerResource
    list_display = ('title', 'slug', 'resource', 'size', 'duration', )
    readonly_fields = ('clicks',)
    ordering = ('-id', '-title')
    prepopulated_fields = {"slug": ("title",)}


if not getattr(settings, 'IS_IKWEN', False):
    admin.site.register(Movie, MovieAdmin)
    admin.site.register(Category, CategoryAdmin)
    if not getattr(settings, 'IS_GAME_VENDOR', False):
        admin.site.register(Series, SeriesAdmin)
        admin.site.register(SeriesEpisode, SeriesEpisodeAdmin)
    # admin.site.register(Trailer, TrailerAdmin)



