# -*- coding: utf-8 -*-
import base64
import hashlib
import time
from bson import ObjectId
from datetime import datetime

from currencies.context_processors import currencies
from django.conf import settings
from django.core.cache import cache

from django.core.urlresolvers import reverse
from django.template import Context
from django.template.loader import get_template
from ikwen.core.utils import get_service_instance

from ikwen_shavida.movies.models import Category, Movie, Series, SeriesEpisode
from ikwen_shavida.reporting.models import StreamLogEntry
from ikwen_shavida.reporting.utils import get_watched
from ikwen_shavida.sales.models import UnitPrepayment, Prepayment

__author__ = 'komsihon'

# Cache key for the exclude_list. Exclude_list contains a pipe separated values of keys of list already computed
#  and cached. Those lists should be excluded when computing subsequent recommended movies
EXCLUDE_LIST_KEYS_KEY = 'exclude_list_keys'
MAX_CATEGORIES_IN_RECOMMENDATIONS = 5
TOTAL_RECOMMENDED = 12


def get_all_recommended(member, count):
    """
    Gets Media recommended for a Member based on the recently watched media categories
    :param member:
    :param count: Total number of media to grab
    :return: list of Movies and/or Series
    """
    if StreamLogEntry.objects.filter(member=member).count() == 0:
        recommended = []
    else:
        exclude_list_keys = set()
        cache_key_recommended = member.username + ':recommended'
        recommended = cache.get(cache_key_recommended)
        if recommended:
            return recommended
        else:
            recommended = []

        cache_key_watched = member.username + ':already_watched'
        already_watched = cache.get(cache_key_watched)
        if not already_watched:
            already_watched = get_watched(member)
            if len(already_watched) > 0:
                cache.set(cache_key_watched, already_watched)
                exclude_list_keys.add(cache_key_watched)
        exclude_list = already_watched

        categories = get_watched_categories(already_watched)
        if len(categories) > 0:
            # Main category is the category of the media most recently watched
            main_category = categories[0]
            cnt = count - (len(categories) - 1)
            media = get_recommended_for_category(main_category, cnt, exclude_list)
            recommended = media
            exclude_list.extend(media)
        categories = categories[1:]
        for category in categories:  # Grab one item for each category other than the main
            media = get_recommended_for_category(category, 1, exclude_list)
            recommended.extend(media)
            exclude_list.extend(media)
        cache.set(cache_key_recommended, recommended)
        exclude_list_keys.add(cache_key_recommended)
        cache.set(member.username + ':' + EXCLUDE_LIST_KEYS_KEY, exclude_list_keys)
    return recommended


def get_recommended_for_category(category, count, exclude_list):
    """
    Pulls media recommended for given category. It merely consists of pulling media that are not in the exclude_list,
    which in this case stands for media that were already watched by the user. It is performed this way:
    We search for elements in the category. While items found are less than count, then search continues.
    We stop if we have been through all the movies or if we reach count items

    :param category: A "natural" (category.smart=False) categories to recommend from
    :param count: total number of elements to collect
    :param exclude_list: an arbitrary list of movies to exclude from the result
    :return: list of recommended movies and series
    """
    movies_count, series_count = get_movies_series_share(count)
    recommended = []
    if movies_count > 0:
        movies_qs = Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True})
        for movie in movies_qs.order_by('-release', '-fake_clicks', '-fake_orders', '-id'):
            if movie not in recommended and movie not in exclude_list and len(recommended) < movies_count:
                recommended.append(movie)
    if series_count > 0:
        series_qs = Series.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True})
        for series in series_qs.order_by('-release', '-season', '-id'):
            if series not in recommended and series not in exclude_list and len(recommended) < count:
                recommended.append(series)
    return recommended


def get_movies_series_share(count, category=None):
    """
    Gives the number of movies and series to pull from the database whenever we want to get a total of "count" media
    It calculates the ratio of each type of media based of their respective total items in the given category.
    :param count:
    :param category:
    :return: tuple movies_count, series_count
    """
    if category:
        total_movies = Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).count()
        total_series = Series.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).count()
    else:
        total_movies = Movie.objects.filter(visible=True).count()
        total_series = Series.objects.filter(visible=True).count()
    if count == 1:
        if total_movies > total_series:
            return 1, 0
        else:
            return 0, 1
    if total_movies + total_series == count:
        return total_movies, total_series
    total_media = total_movies + total_series
    movies_count = total_movies * count / total_media
    series_count = count - movies_count
    return movies_count, series_count


def get_watched_categories(watched_media):
    categories = []
    for media in watched_media:
        for category in media.categories:
            # Media categories are embedded, so check the smart status
            # from the original category. So re-get from the database
            if not Category.objects.get(pk=category.id).smart:
                categories.append(category)
    return categories


def clear_user_cache(member):
    """
    Delete all the exclude list from the cache, as well as the list containing their keys
    :param member:
    :return:
    """
    elk_key = member.username + ':' + EXCLUDE_LIST_KEYS_KEY
    exclude_list_keys = cache.get(elk_key)
    if exclude_list_keys:
        exclude_list_keys.add(elk_key)
        cache.delete_many(exclude_list_keys)


def get_unit_prepayment(member, media):
    now = datetime.now()
    for tp in UnitPrepayment.objects.filter(member=member, status=Prepayment.CONFIRMED, expiry__gte=now):
        if type(media).__name__ == "Movie":
            if media.id == tp.media_id:
                return tp
        elif media.series.id == tp.media_id:
            return tp


def extract_resource_url(iframe_code):
    """
    Extract the resource URL from a iframe embed code
    :param iframe_code:
    :return: Returns url contains in src attribute of the iframe code
    """
    s = iframe_code.find(' src="')
    e = iframe_code.find('"', s + 7)
    if s < 0:
        s = iframe_code.find(" src='")
        e = iframe_code.find("'", s + 7)
    return iframe_code[s+6:e]


def render_suggest_payment_template(request, media):
    config = get_service_instance().config
    html_template = get_template('movies/snippets/suggest_payment.html')
    if isinstance(media, SeriesEpisode):
        media = media.series
        media.type = 'series'
    try:
        CURRENCY = currencies(request)['CURRENCY']
    except:
        CURRENCY = None
    d = Context({
        'media': media,
        'config': config,
        'choose_temp_bundle_url': "%s?media_type=%s&media_id=%s" % (reverse('sales:choose_temp_bundle'), media.type, media.id),
        'CURRENCY': CURRENCY
    })
    return html_template.render(d)


def as_matrix(movies_list, column_count):
    row = []
    matrix = []
    for elt in movies_list:
        if len(row) < column_count - 1:
            row.append(elt)
        else:
            row.append(elt)
            matrix.append(row)
            row = []
    return matrix


def generate_download_link(filename, expires):
    if not filename:
        return
    secret = getattr(settings, 'SECURE_LINK_SECRET', 'enigma')
    movies_base_folder = getattr(settings, 'MOVIES_BASE_FOLDER', 'movies/')
    input_string = '%d%s %s' % (expires, movies_base_folder + filename, secret)
    m = hashlib.md5()
    m.update(input_string)
    md5 = base64.b64encode(m.digest())
    md5 = md5.replace('=', '').replace('+', '-').replace('/', '_')
    static_url = getattr(settings, 'SECURE_LINK_BASE_URL', 'http://cdn.ikwen.com/')
    link = static_url + filename + '?md5=' + md5 + '&expires=%d' % expires
    return link
