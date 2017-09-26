# -*- coding: utf-8 -*-
import json
from datetime import datetime
from random import shuffle

import requests
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.template.defaultfilters import slugify
from django.utils.module_loading import import_by_path
from django.utils.translation import gettext as _
from ikwen.billing.models import PaymentMean
from ikwen.conf.settings import MOMO_SLUG
from ikwen.core.utils import get_service_instance
from ikwen_shavida.movies.models import *
from ikwen_shavida.movies.utils import get_all_recommended, EXCLUDE_LIST_KEYS_KEY, get_recommended_for_category, \
    get_movies_series_share, is_in_temp_prepayment, render_suggest_payment_template, extract_resource_url
from ikwen_shavida.reporting.models import StreamLogEntry
from ikwen_shavida.sales.models import RetailBundle, VODBundle, VODPrepayment, Prepayment, UnitPrepayment, \
    RetailPrepayment
from ikwen_shavida.shavida.views import BaseView


class CustomerView(BaseView):

    def get_context_data(self, **kwargs):
        context = super(CustomerView, self).get_context_data(**kwargs)
        member = self.request.user
        if member.is_authenticated():
            last_prepayment = member.customer.get_last_retail_prepayment()
            last_vod_prepayment = member.customer.get_last_vod_prepayment()
            context['last_prepayment'] = last_prepayment
            context['last_vod_prepayment'] = last_vod_prepayment
            context['is_iOS'] = 'OS' in self.request.user_agent.os.family
            available_quota = 0
            if last_prepayment:
                if last_prepayment.days_left > 0:
                    available_quota = last_prepayment.balance
            unit = getattr(settings, 'SALES_UNIT', SalesConfig.BROADCASTING_TIME)
            if unit == SalesConfig.DATA_VOLUME:
                display_available_quota = "%.2f GB" % (available_quota / 1000.0)
            else:
                display_available_quota = "%dh" % available_quota
            context['SALES_UNIT'] = unit  # Deprecated. Moved to shavida.context_processors.settings.SALES_UNIT
            context['SALES_UNIT_STR'] = _("GigaBytes") if unit == SalesConfig.DATA_VOLUME else _("Brodcasting hours")
            context['available_quota'] = available_quota
            context['display_available_quota'] = display_available_quota
        return context


class Home(CustomerView):
    template_name = 'movies/home.html'

    def get_context_data(self, **kwargs):
        context = super(Home, self).get_context_data(**kwargs)
        member = self.request.user
        recommended_items = []
        if member.is_authenticated():
            recommended_items = get_all_recommended(member, 12)
            if len(recommended_items) < Movie.MIN_RECOMMENDED:
                additional = Movie.MIN_RECOMMENDED - len(recommended_items)
                additional_items = Movie.objects.filter(visible=True).order_by('-release')[:additional]
                recommended_items.extend(additional_items)
        else:
            try:
                top = Category.objects.get(slug='top')
                recommended_items = list(Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(top.id)}}, 'visible': True}))
                recommended_items.extend(list(Series.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(top.id)}}, 'visible': True})))
                context['top_title'] = top.previews_title if top.previews_title else top.title
            except Category.DoesNotExist:
                pass

        context['recommended_items'] = recommended_items
        recent_releases = list(Movie.objects.filter(visible=True).order_by('-release', '-id')[:Movie.MAX_RECENT])
        shuffle(recent_releases)
        sample_media = recent_releases[0] if len(recent_releases) > 0 else None
        og_url = ''
        hash = self.request.GET.get('_escaped_fragment_')
        if hash:
            media_type = 'movie' if hash.startswith('movie-') else 'series'
            slug = hash.replace('movie-', '') if media_type == 'movie' else hash.replace('series-', '')
            try:
                if media_type == 'movie':
                    sample_media = Movie.objects.get(slug=slug)
                    og_url = '/#!movie-' + slug
                else:
                    sample_media = Series.objects.get(slug=slug)
                    og_url = '/#!series-' + slug
            except ObjectDoesNotExist:
                pass
        context['og_item'] = sample_media
        context['og_url'] = og_url

        return context

    def render_to_response(self, context, **response_kwargs):
        if is_touch_device(self.request):
            self.template_name = 'movies/touch/home.html'
        return super(Home, self).render_to_response(context, **response_kwargs)


class MediaList(CustomerView):
    template_name = 'movies/media_list.html'

    def get_context_data(self, **kwargs):
        context = super(MediaList, self).get_context_data(**kwargs)
        slug = kwargs['slug']
        category = Category.objects.get(slug=slug)
        context['current_category'] = category
        context['category_top'] = Category.objects.get(slug='top')
        movies_qs = category.get_movies_queryset()
        series_qs = category.get_series_queryset()
        sample_media = None
        og_url = ''
        if movies_qs.count() > 0:
            sample_media = movies_qs[0]
        elif series_qs.count() > 0:
            sample_media = series_qs[0]
        hash = self.request.GET.get('_escaped_fragment_')
        if hash:
            media_type = 'movie' if hash.startswith('movie-') else 'series'
            slug = hash.replace('movie-', '') if media_type == 'movie' else hash.replace('series-', '')
            try:
                if media_type == 'movie':
                    sample_media = Movie.objects.get(slug=slug)
                    og_url = '/#!movie-' + slug
                else:
                    sample_media = Series.objects.get(slug=slug)
                    og_url = '/#!series-' + slug
            except ObjectDoesNotExist:
                pass
        context['og_item'] = sample_media
        context['og_url'] = og_url
        return context

    def get(self, request, *args, **kwargs):
        slug = kwargs['slug']
        category = get_object_or_404(Category, slug=slug)
        if category.is_adult and not self.request.user.is_authenticated():
            next_url = reverse("ikwen:sign_in") + '?next_url=' + reverse('movies:media_list', args=(category.slug, ))
            return HttpResponseRedirect(next_url)
        context = self.get_context_data(**kwargs)
        if is_touch_device(self.request):
            self.template_name = 'movies/touch/movie_by_category.html'
        return render(request, self.template_name, context)

    def render_to_response(self, context, **response_kwargs):
        if is_touch_device(self.request):
            self.template_name = 'movies/touch/movie_by_category.html'
        return super(MediaList, self).render_to_response(context, **response_kwargs)


class Bundles(CustomerView):
    template_name = 'movies/bundles.html'

    def get_context_data(self, **kwargs):
        context = super(Bundles, self).get_context_data(**kwargs)
        if getattr(settings, 'IS_VOD_OPERATOR', False):
            vod_bundles = VODBundle.objects.all().order_by('volume')
            for bundle in vod_bundles:
                bundle.volume /= 1000
            context['bundles'] = vod_bundles
        else:
            bundles = RetailBundle.objects.all().order_by('quantity')
            for bundle in bundles:
                if getattr(settings, 'SALES_UNIT', SalesConfig.DATA_VOLUME) == SalesConfig.DATA_VOLUME:
                    bundle.quantity /= 1000
                else:
                    bundle.quantity /= 60
            context['bundles'] = bundles
        context['is_bundle_page'] = True
        return context

    def get(self, request, *args, **kwargs):
        # Wipe Prepayment resulting from an incomplete checkout operation
        VODPrepayment.objects.filter(member=request.user, status=Prepayment.PENDING).delete()
        UnitPrepayment.objects.filter(member=request.user, status=Prepayment.PENDING).delete()
        RetailPrepayment.objects.filter(member=request.user, status=Prepayment.PENDING).delete()
        return super(Bundles, self).get(request, *args, **kwargs)

    def render_to_response(self, context, **response_kwargs):
        if is_touch_device(self.request):
            self.template_name = 'movies/touch/bundles.html'
        return super(Bundles, self).render_to_response(context, **response_kwargs)


class MoMoCheckout(CustomerView):
    template_name = 'movies/momo_checkout.html'

    # def get_context_data(self, **kwargs):
    #     context = super(MoMoCheckout, self).get_context_data(**kwargs)
    #     retail_bundles = RetailBundle.objects.all().order_by('quantity')
    #     vod_bundles = VODBundle.objects.all().order_by('volume')
    #     context['retail_bundles'] = retail_bundles
    #     for bundle in vod_bundles:
    #         bundle.volume /= 1000
    #     context['vod_bundles'] = vod_bundles
    #     context['is_bundle_page'] = True
    #     return context


class MovieDetail(CustomerView):
    MAX_SUGGESTIONS = 8
    template_name = 'movies/movie_detail.html'

    def get_context_data(self, *args, **kwargs):
        context = super(MovieDetail, self).get_context_data(**kwargs)
        slug = self.request.GET.get('slug')
        if not slug:
            slug = self.kwargs.get('slug', None)
        movie = get_object_or_404(Movie, slug=slug)
        context['media'] = movie
        groups = ' '.join([val.strip() for val in movie.groups.split(' ') if val != ''])
        suggestions = []
        if groups:
            suggestions = [movie for movie in
                           Movie.objects.raw_query(
                               {'$text': {'$search': groups}, 'visible': True}
                           ).exclude(pk=movie.id).order_by("-id")]
        if len(suggestions) < MovieDetail.MAX_SUGGESTIONS:
            limit = MovieDetail.MAX_SUGGESTIONS - len(suggestions)
            categories_ids = [ObjectId(category.id) for category in movie.categories]
            exclude_ids = [item.id for item in suggestions]
            exclude_ids.append(movie.id)
            categories_suggestions = [movie for movie in
                                      Movie.objects.raw_query(
                                          {'categories': {'$elemMatch': {'id': {'$in': categories_ids}}}, 'visible': True}
                                      ).exclude(pk__in=exclude_ids).order_by("-id")[:limit]]
            suggestions.extend(categories_suggestions)
        context['suggestions'] = [movie.to_dict() for movie in suggestions]
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'ajax_html':
            return render(self.request, 'movies/snippets/media_detail.html', context)
        return super(MovieDetail, self).render_to_response(context, **response_kwargs)


class SeriesDetail(CustomerView):
    MAX_SUGGESTIONS = 5
    template_name = 'movies/series_detail.html'

    def get_context_data(self, *args, **kwargs):
        context = super(SeriesDetail, self).get_context_data(**kwargs)
        slug = self.request.GET.get('slug')
        if not slug:
            slug = self.kwargs.get('slug', None)
        current_series = get_object_or_404(Series, slug=slug)
        context['episodes'] = [ep for ep in SeriesEpisode.objects.filter(series=current_series).order_by('id')]
        context['media'] = current_series
        groups = ' '.join([val.strip() for val in current_series.groups.split(' ') if val != ''])
        suggestions = []
        if groups:
            suggestions = [series for series in
                           Series.objects.raw_query(
                               {'$text': {'$search': groups}, 'visible': True}
                           ).exclude(pk=current_series.id).order_by("-id")]
        if len(suggestions) < SeriesDetail.MAX_SUGGESTIONS:
            limit = SeriesDetail.MAX_SUGGESTIONS - len(suggestions)
            categories_ids = [ObjectId(category.id) for category in current_series.categories]
            exclude_ids = [item.id for item in suggestions]
            exclude_ids.append(current_series.id)
            categories_suggestions = [series for series in
                                      Series.objects.raw_query(
                                          {'categories': {'$elemMatch': {'id': {'$in': categories_ids}}}, 'visible': True}
                                      ).exclude(pk__in=exclude_ids).order_by("-id")[:limit]]
            suggestions.extend(categories_suggestions)
        context['suggestions'] = [series.to_dict() for series in suggestions]
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'ajax_html':
            return render(self.request, 'movies/snippets/media_detail.html', context)
        return super(SeriesDetail, self).render_to_response(context, **response_kwargs)


class Search(CustomerView):
    template_name = 'movies/search.html'

    def get_context_data(self, **kwargs):
        context = super(Search, self).get_context_data(**kwargs)
        context['page_title'] = ''
        radix = self.request.GET.get('q')
        results = [item.to_dict() for item in self.grab_items_by_radix(radix)]
        sample_media = None
        og_url = ''
        hash = self.request.GET.get('_escaped_fragment_')
        if hash:
            media_type = 'movie' if hash.startswith('movie-') else 'series'
            slug = hash.replace('movie-', '') if media_type == 'movie' else hash.replace('series-', '')
            try:
                if media_type == 'movie':
                    sample_media = Movie.objects.get(slug=slug)
                    og_url = '/#!movie-' + slug
                else:
                    sample_media = Series.objects.get(slug=slug)
                    og_url = '/#!series-' + slug
            except ObjectDoesNotExist:
                pass
        context['og_item'] = sample_media
        context['og_url'] = og_url
        context['results'] = results
        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('format') == 'json':
            terms = self.request.GET.get('q')
            response = [item.to_dict() for item in self.grab_items_by_radix(terms, use_limit=True)]
            return HttpResponse(
                json.dumps(response),
                'content-type: text/json',
                **response_kwargs
            )
        else:
            if is_touch_device(self.request):
                self.template_name = 'movies/touch/search.html'
            return super(Search, self).render_to_response(context, **response_kwargs)

    def grab_items_by_radix(self, terms, use_limit=False):
        total = 10 if use_limit else 10000
        if use_limit:
            limit_movies, limit_series = get_movies_series_share(total)
        else:
            limit_movies, limit_series = 10000, 10000
        items = set()
        if terms and len(terms) >= 2:
            word = slugify(terms)
            if word:
                movies = [movie for movie in
                          Movie.objects.filter(tags__icontains=word, visible=True)[:limit_movies]]
                items = items.union(movies)
                if len(items) < total:
                    limit_series = total - len(items) if use_limit else 10000
                    series = [series for series in Series.objects.filter(tags__icontains=word, visible=True)[:limit_series]]
                    items = items.union(series)
        # if terms and len(terms) >= 2:
        #     stripped_terms = ' '.join([term.strip()[:4] for term in terms.split(' ') if term])
        #     if limit_movies > 0:
        #         movies = [movie for movie in Movie.objects.raw_query(
        #             {'$text': {'$search': stripped_terms}, 'visible': True}
        #         )[:limit_movies]]
        #         items.extend(movies)
        #     if limit_series:
        #         series = [series for series in Series.objects.raw_query(
        #             {'$text': {'$search': stripped_terms}, 'visible': True}
        #         )[:limit_series]]
        #         items.extend(series)
        show_adult = self.request.user.is_authenticated() and self.request.user.customer.get_can_access_adult_content()
        items = list(items)
        for item in items:
            if type(item).__name__ == "Movie" and item.is_adult:
                if not show_adult:
                    items.remove(item)
        return items


def get_media(request, *args, **kwargs):
    """
    :param request:
    :return: list of media (movies and/or series)
    """
    category_id = request.GET.get('category_id') if request.GET.get('category_id') else None
    start_movies = request.GET.get('start_movies') if request.GET.get('start_movies') else ''
    start_series = request.GET.get('start_series') if request.GET.get('start_series') else ''
    length = int(request.GET.get('length')) if request.GET.get('length') else None

    category = Category.objects.get(pk=category_id)
    if not length:
        length = category.previews_length
    response = []
    if category_id and length and (start_movies != '' or start_series != ''):
        start_movies = int(start_movies)
        start_series = int(start_series)
        cache_key = '%s-%d-%d-%d' % (category_id, start_movies, start_series, length)
        media = cache.get(cache_key)
        if not media:
            movies_length, series_length = get_movies_series_share(length)
            movies_qs = Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).order_by('-id')
            series_qs = Series.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).order_by('-id')
            movies_qs_count = movies_qs.count()
            series_qs_count = series_qs.count()
            if movies_qs_count < movies_length:
                series_length += (movies_length - movies_qs_count)
            if series_qs_count < series_length:
                movies_length += (series_length - series_qs_count)
            limit_movies = start_movies + movies_length
            limit_series = start_series + series_length
            media = list(movies_qs[start_movies:limit_movies])
            series = list(series_qs[start_series:limit_series])
            media.extend(series)
            cache.set(cache_key, media, 10 * 60)
        if request.GET.get('shuffle'):
            shuffle(media)
        response = [item.to_dict() for item in media]
    return HttpResponse(
        json.dumps(response),
        'content-type: text/json'
    )


def stream(request, *args, **kwargs):
    # TODO: Handle the reading of multipart files, else only the first part will be streamed
    media_type = request.GET['type']
    item_id = request.GET['item_id']
    referrer = request.META.get('HTTP_REFERER')
    if not referrer:
        return HttpResponseForbidden("You don't have permission to access this resource.")
    try:
        config = get_service_instance().config
        is_check = request.GET.get('is_check')
        member = request.user
        if media_type == 'movie':
            media = Movie.objects.get(pk=item_id)
        elif media_type == 'series':
            media = SeriesEpisode.objects.get(pk=item_id)
        else:
            try:
                media = Movie.objects.get(pk=item_id).trailer
            except ObjectDoesNotExist:
                try:
                    media = Series.objects.get(pk=item_id).trailer
                except ObjectDoesNotExist:
                    response = {"error": _("Resource temporarily unavailable. Please try again later.")}
                    return HttpResponse(json.dumps(response), 'content-type: text/json')

        if is_check:
            media.clicks += 1
            media.save()
            if member.is_authenticated():
                # Saving a LogEntry with duration=0 and bytes=0.
                # This is just to make the history aware that user was interested
                # in this media; and later use it in the suggestion algorithm.
                StreamLogEntry.objects.create(member=member, media_type=media_type, media_id=item_id, duration=0,
                                              bytes=0)

        if media_type != 'trailer' and media.view_price > 0:
            if not member.is_authenticated():
                response = {"error": _("Please login first.")}
                return HttpResponse(json.dumps(response), 'content-type: text/json')
            latest_vod_prepayment = member.customer.get_last_vod_prepayment(VODPrepayment.CONFIRMED)
            if not is_in_temp_prepayment(member, media):
                if not latest_vod_prepayment:
                    response = {
                        "error": _("Sorry, you don't have any valid bundle. Please buy one."),
                        "html": render_suggest_payment_template(media)
                    }
                    return HttpResponse(json.dumps(response), 'content-type: text/json')
                elif latest_vod_prepayment.get_expiry() < datetime.now():
                    response = {
                        "error": _("Sorry, your VOD bundle is expired. Please buy a new one."),
                        "html": render_suggest_payment_template(media)
                    }
                    return HttpResponse(json.dumps(response), 'content-type: text/json')
                elif latest_vod_prepayment.balance <= 0:
                    response = {
                        "error": _("Sorry, your VOD bundle is sold out. Please buy a new one."),
                        "html": render_suggest_payment_template(media)
                    }
                    return HttpResponse(json.dumps(response), 'content-type: text/json')
                if media.is_adult:
                    if not latest_vod_prepayment.adult_authorized:
                        vod_bundles = list(VODBundle.objects.filter(adult_authorized=True).order_by('cost'))
                        vod_bundle = vod_bundles[0] if len(vod_bundles) > 0 else None
                        currency = config.currency_symbol
                        if vod_bundle:
                            response = {"error": _("Sorry, only bundles as from %s %d give you access to this content" % (currency, vod_bundle.cost))}
                            return HttpResponse(json.dumps(response), 'content-type: text/json')
                        else:
                            response = {"error": _("Sorry, you can't access this content. Please contact your provider.")}
                            return HttpResponse(json.dumps(response), 'content-type: text/json')
        item_url = ''
        found = False
        resource_to_use = None
        media_sources = config.data_sources.split(',')
        for folder in media_sources:
            path = getattr(settings, 'MAKE_MEDIA_URL', 'ikwen_shavida.movies.views.make_media_url')
            url_maker = import_by_path(path)
            item_url = url_maker(request, folder, media, *args, **kwargs)
            resource_to_use = get_resource_to_use(request, folder, media)
            try:
                if requests.head(item_url).status_code == 200:
                    found = True
                    break
            except:
                continue
        if is_check:
            if not found:
                response = {"error": _("Resource unavailable. Please try again later."), "item_url": item_url}
                return HttpResponse(json.dumps(response), 'content-type: text/json')
            if '<iframe ' in resource_to_use:
                response = {'html': resource_to_use}
                return HttpResponse(json.dumps(response), 'content-type: text/json')
            response = {'media_url': item_url}
            return HttpResponse(json.dumps(response), 'content-type: text/json')

        return HttpResponseRedirect(item_url)
    except Exception as e:
        response = {'error': e.message}
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class TestVideoBytesCounter(BaseView):
    template_name = "movies/test_video_bytes_counter.html"


class Checkout(CustomerView):
    template_name = "movies/checkout.html"

    def render_to_response(self, context, **response_kwargs):
        if is_touch_device(self.request):
            self.template_name = 'movies/touch/checkout.html'
        return super(Checkout, self).render_to_response(context, **response_kwargs)


def is_touch_device(request):
    ANDROID = 'Android'
    BLACKBERRY = 'Blackberry'
    IPhone = 'iPhone'
    IPAD = 'iPad'
    is_touch = False

    user_agent = request.META['HTTP_USER_AGENT']
    if user_agent.find(ANDROID) != -1 or user_agent.find(BLACKBERRY) != -1 or user_agent.find(IPhone) != -1 or user_agent.find(IPAD) != -1:
        is_touch = True
    return False


def get_recommended_for_single_category(request, *args, **kwargs):
    category_id = request.GET.get('category_id')
    response = []
    if category_id:
        category = Category.objects.get(pk=category_id)
        member = request.user
        cache_key = member.username + ':recommended-' + category_id
        recommended = cache.get(cache_key)
        if not recommended:
            exclude_list_keys = cache.get(member.username + ':' + EXCLUDE_LIST_KEYS_KEY)
            exclude_list = []
            if not exclude_list_keys:
                exclude_list_keys = set()
            else:
                for key in exclude_list_keys:
                    items = cache.get(key)
                    if items:
                        exclude_list.extend(items)
            recommended = get_recommended_for_category(category, category.previews_length, exclude_list)
            exclude_list_keys.add(cache_key)
            cache.set(cache_key, recommended)
            cache.set(member.username + ':' + EXCLUDE_LIST_KEYS_KEY, exclude_list_keys)
        response = [item.to_dict() for item in recommended]
    return HttpResponse(
        json.dumps(response),
        'content-type: text/json'
    )


# MAKE_MEDIA_URL
def make_media_url(request, folder, media, *args, **kwargs):
    if folder and folder[-1] != '/':
        folder += '/'
    if request.user_agent.is_mobile:
        if media.resource_mob:
            if '<iframe ' in media.resource_mob:
                return extract_resource_url(media.resource_mob)
            if '://' in media.resource_mob:
                return media.resource_mob
            return folder + media.resource_mob
    if '<iframe ' in media.resource:
        return extract_resource_url(media.resource)
    if '://' in media.resource:  # Test whether resource is a URL, then return it as such.
        return media.resource
    return folder + media.resource


def get_resource_to_use(request, folder, media):
    """
    Returns the resource as it will be used client side by javascript.
    This merely means that when the media.resource turns out to be
    a iframe code. The iframe code is returned as such.
    """
    if request.user_agent.is_mobile:
        if media.resource_mob:
            if '<iframe ' in media.resource_mob:
                return media.resource_mob
            if '://' in media.resource_mob:  # Test whether resource is a URL, then return it as such.
                return media.resource_mob
            return folder + media.resource_mob
    if '<iframe ' in media.resource:
        return media.resource
    if '://' in media.resource:  # Test whether resource is a URL, then return it as such.
        return media.resource
    return folder + media.resource


# NOT_MP4_HANDLER
def queue_for_transcode(request, media, *args, **kwargs):
    # Put in the transcode queue here
    response = {"error": _("Sorry, file under process, please try again very soon.")}
    return HttpResponse(json.dumps(response), 'content-type: text/json')
