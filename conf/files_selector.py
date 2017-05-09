#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Mar 22, 2014

@author: Kom Sihon
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ikwen_shavida.conf.settings")

from bson import ObjectId

from ikwen_shavida.sales.models import SalesConfig
from ikwen_shavida.movies.models import Category, Movie, SeriesEpisode, Trailer

PREFIXES = ['cine', 'da', 'xxl', 'comedie', 'concert', 'doc', 'gag', 'oms']
EXTENSION = 'cnmx'


def get_unit_string(unit):
    return 'h' if unit == SalesConfig.BROADCASTING_TIME else 'MB'


def get_unit_field_name(unit):
    return 'duration' if unit == SalesConfig.BROADCASTING_TIME else 'size'


def collect_movies(max_load, unit, base_categories_slugs=[], preferred_categories_slugs=[], exclude_list_ids=[]):
    """
    Iterate over all other categories
    For each of them:
        grab 2 movies if category slug is in base_categories_slug or preferred_categories_slugs
        grab 1 movie for any other category
        after any grab, test and make sure we are not exceeding the allowed space
    """
    total_load = 0
    selection = []
    unit_string = get_unit_string(unit)
    unit_field_name = get_unit_field_name(unit)
    base_categories = [Category.objects.get(slug=slug) for slug in base_categories_slugs]
    for category in base_categories:
        for movie in Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}):
            selection.append(movie)
            try:
                selection.append(movie.trailer)
                total_load += movie.trailer.__dict__[unit_field_name]
                print u"Adding trailer %s: %d%s in all" % (movie.slug, total_load, unit_string)
            except Trailer.DoesNotExist:
                pass
            exclude_list_ids.append(movie.id)
            total_load += movie.__dict__[unit_field_name]
        print "%d movies collected in %s. %d movies: %d%s in all" % (Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).count(), category.title, len(selection), total_load, unit_string)

    main_categories = [Category.objects.get(slug=slug) for slug in preferred_categories_slugs]
    previous_total_load = -1
    while previous_total_load < total_load:
        previous_total_load = total_load
        for category in Category.objects.exclude(slug__in=base_categories_slugs):
            if category in main_categories:
                movies = Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).exclude(pk__in=exclude_list_ids).order_by('-orders', '-release', '-id')[:2]
                for movie in movies:
                    if movie.__dict__[unit_field_name] == 0:
                        exclude_list_ids.append(movie.id)
                        continue
                    if total_load + movie.__dict__[unit_field_name] > max_load:
                        break
                    selection.append(movie)
                    try:
                        selection.append(movie.trailer)
                        total_load += movie.trailer.__dict__[unit_field_name]
                        print u"Adding trailer %s: %d%s in all" % (movie.slug, total_load, unit_string)
                    except Trailer.DoesNotExist:
                        pass
                    exclude_list_ids.append(movie.id)
                    total_load += movie.__dict__[unit_field_name]
                    print u"Adding %s. %d movies: %d%s in all" % (movie.slug, len(selection), total_load, unit_string)
            else:
                movies = list(Movie.objects.raw_query({'categories': {'$elemMatch': {'id': ObjectId(category.id)}}, 'visible': True}).exclude(pk__in=exclude_list_ids).order_by('-orders', '-release', '-id'))
                if len(movies) >= 1:
                    movie = movies[0]
                    if movie.__dict__[unit_field_name] == 0:
                        exclude_list_ids.append(movie.id)
                        continue
                    if total_load + movie.__dict__[unit_field_name] > max_load:
                        break
                    selection.append(movie)
                    exclude_list_ids.append(movie.id)
                    total_load += movie.__dict__[unit_field_name]
                    print u"Adding %s. %d movies: %d%s in all" % (movie.slug, len(selection), total_load, unit_string)
    return selection


def collect_series(max_load, unit, exclude_list=[]):
    """
    Grab all SeriesEpisode and order them by orders DESCENDANT. Iterate over them, retrieve the matching Series,
    if there's enough space left, add that series to the list
    :param max_load:
    :param unit:
    :param exclude_list:
    :return:
    """
    total_load = 0
    selection = []
    unit_string = get_unit_string(unit)
    while True:
        try:
            episode = SeriesEpisode.objects.all().exclude(series__in=exclude_list).order_by('-orders')[0]
            series = episode.series
            series_load = series.duration if unit == SalesConfig.BROADCASTING_TIME else series.size
            if series_load == 0:
                exclude_list.append(series)
                continue
            if total_load + series_load > max_load:
                break
            total_load += series_load
            exclude_list.append(series)
            for episode in series.seriesepisode_set.all():
                selection.append(episode)
            print u"Adding %s. %d series: %d%s in all" % (episode.series, len(exclude_list), total_load, unit_string)
        except IndexError:
            break
    return selection


if __name__ == "__main__":
    import sys
    movies_exclude_list = []
    series_exclude_list = []
    movies_max_size = sys.argv[1]
    series_max_size = sys.argv[2]
    if len(sys.argv) == 5:
        exclude_list_file = sys.argv[3]
        output = sys.argv[4]

        fh = open(exclude_list_file, 'r')
        if exclude_list_file[-3:].lower() == 'csv':
            filenames = [line.decode('utf8').split(';')[0].strip('"') for line in fh.readlines()]
        else:
            filenames = [line.decode('utf8').strip() for line in fh.readlines()]
        fh.close()

        for filename in filenames:
            try:
                movie = Movie.objects.get(filename=filename)
            except Movie.DoesNotExist:
                pass
            else:
                movies_exclude_list.append(movie)
    else:  # if len(sys.argv) == 4:
        output = sys.argv[3]

    items_selection = collect_movies(int(movies_max_size), movies_exclude_list)
    series_selection = collect_series(int(series_max_size), series_exclude_list)
    items_selection.extend(series_selection)
    fh = open(output, 'w')
    for item in items_selection:
        fh.write('%s\n' % item.filename.encode('utf8'))
    fh.close()