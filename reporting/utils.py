# -*- coding: utf-8 -*-
import shutil
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from ikwen.core.models import Service
from ikwen.core.utils import get_service_instance, add_database_to_settings

from ikwen_shavida.movies.models import SeriesEpisode, Movie, Trailer
from ikwen_shavida.reporting.models import StreamLogEntry
from ikwen_shavida.sales.models import ContentUpdate
from ikwen_shavida.shavida.models import OperatorProfile

__author__ = 'Kom Sihon'


def generate_add_list_info(serialized_items):
    serialized_items = serialized_items[:-1]
    serialized_items_list = serialized_items.split(',')
    add_list = []
    add_list_size, add_list_duration = 0, 0
    for serialized_item in serialized_items_list:
        tokens = serialized_item.split('|')
        try:
            if tokens[1] == "movie":
                media = Movie.objects.get(pk=tokens[0])
                add_list_size += media.size
                add_list_duration += media.duration
                for filename in media.resource.split(','):
                    add_list.append(filename.strip())
            else:
                media = SeriesEpisode.objects.get(pk=tokens[0])
                add_list_size += media.size
                add_list_duration += media.duration
                for filename in media.resource.split(','):
                    add_list.append(filename.strip())
        except ObjectDoesNotExist:
            continue
    return {
        'add_list': ','.join(add_list),
        'add_list_size': add_list_size,
        'add_list_duration': add_list_duration,
    }


def add_media_to_update(serialized_items, update):
    """
    Add actual media objects to ContentUpdate. Since the ContentUpdate.add_list contains just a list of filenames,
    this functions helps save more than just the filename, but the whole media object that allow more processing
    :param serialized_items:
    :param update:
    :return:
    """
    serialized_items = serialized_items[:-1]
    serialized_items_list = serialized_items.split(',')
    update.movies_add_list = []
    update.series_episodes_add_list = []
    for serialized_item in serialized_items_list:
        tokens = serialized_item.split('|')
        try:
            if tokens[1] == "movie":
                media = Movie.objects.get(pk=tokens[0])
                update.movies_add_list.append(media)
            else:
                media = SeriesEpisode.objects.get(pk=tokens[0])
                update.series_episodes_add_list.append(media)
        except ObjectDoesNotExist:
            continue
    update.save()


def sync_changes(content_update):
    """
    Syncs meta data from provider database to operator database to reflect changes in the ContentUpdate.
    Media in add_list are copied in the operator database and media marked for deletion by the operator
    are set visible=False
    :param content_update:
    :return:
    """
    service = get_service_instance()
    customer_service = content_update.member.customer.service
    db = customer_service.database
    # Add the VOD Operator's database to the settings
    add_database_to_settings(db)
    try:
        Service.objects.using(db).get(pk=service.id)
    except Service.DoesNotExist:
        config = service.config
        service.save(using=db)
        config.save(using=db)

    if content_update.movies_add_list:
        for movie in content_update.movies_add_list:
            movie.orders += 1
            movie.fake_orders += 1
            movie.save()
            movie.save(using=db)
            # dst_poster = operator.media_root + movie.poster.name
            # dst_poster_small = operator.media_root + movie.poster.small_name
            # dst_poster_thumb = operator.media_root + movie.poster.thumb_name
            # shutil.copy(movie.poster.path, dst_poster)
            # shutil.copy(movie.poster.small_path, dst_poster_small)
            # shutil.copy(movie.poster.thumb_path, dst_poster_thumb)

    if content_update.series_episodes_add_list:
        current_series = None
        for episode in content_update.series_episodes_add_list:
            if current_series != episode.series:
                current_series = episode.series
                current_series.save(using=db)
                # dst_poster = operator.media_root + current_series.poster.name
                # dst_poster_small = operator.media_root + current_series.poster.small_name
                # dst_poster_thumb = operator.media_root + current_series.poster.thumb_name
                # shutil.copy(current_series.poster.path, dst_poster)
                # shutil.copy(current_series.poster.small_path, dst_poster_small)
                # shutil.copy(current_series.poster.thumb_path, dst_poster_thumb)
            episode.orders += 1
            episode.fake_orders += 1
            episode.save()
            episode.save(using=db)

    # Make media in delete_lists invisible rather than deleting them in the user database
    if content_update.movies_delete_list:
        for movie in content_update.movies_delete_list:
            movie.visible = False
            movie.save(using=db)
    if content_update.series_episodes_delete_list:
        for episode in content_update.series_episodes_delete_list:
            episode.series.visible = False
            episode.series.save(using=db)

    content_update.status = ContentUpdate.DELIVERED
    content_update.save()
    content_update.save(using=db)


def reduce_stream_log_entries(member):
    entries = list(StreamLogEntry.objects.filter(member=member, status=StreamLogEntry.SINGLE).order_by('id'))
    if len(entries) <= 0:
        return
    start_entry = entries[0]
    for entry in entries[1:]:
        if entry.media_id == start_entry.media_id:
            start_entry.duration += entry.duration
            start_entry.bytes += entry.bytes
            start_entry.save()
            entry.bytes = 0  # Mark for deletion by setting bytes to 0
            entry.save()
        else:
            start_entry.status = StreamLogEntry.REDUCED
            start_entry.save()
            start_entry = entry  # Restart over with the next log entry
    else:
        start_entry.status = StreamLogEntry.REDUCED
        start_entry.save()

    for entry in StreamLogEntry.objects.filter(member=member, bytes=0):
        entry.delete()  # Delete Single entries


# def generate_share_log_entries():
#     members = Member.objects.all()
#     for member in members:
#         reduce_stream_log_entries(member)
#     provider_entries = ProviderShareLogEntry.objects.all().order_by('-id')
#     start_date = provider_entries[0].created_on if len(provider_entries) > 0 else None
#     if not start_date:
#         service_id = getattr(settings, 'IKWEN_SERVICE_ID')
#         start_date = Service.objects.get(pk=service_id).since
#     now = datetime.now()
#     start_date = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
#     yesterday_midnight = datetime(now.year, now.month, now.day, 0, 0, 0)
#     while start_date < yesterday_midnight:
#         end_date = start_date + timedelta(seconds=86400)
#         stream_log_entries = StreamLogEntry.objects.filter(
#             Q(created_on__gte=start_date) & Q(created_on_lt=end_date),
#             status=StreamLogEntry.REDUCED
#         )
#
#         var = {}
#         for entry in stream_log_entries:
#             media = Movie.objects.get(pk=entry.media_id) if entry.media_type.lower() == 'movie' else SeriesEpisode.objects.get(pk=entry.media_id)
#             provider = media.provider
#             if var.get(provider.id):
#                 var[provider.id]['total_duration'] += entry.duration
#                 var[provider.id]['total_bytes'] += entry.bytes
#             else:
#                 var[provider.id] = {
#                     'total_duration': entry.duration,
#                     'total_bytes': entry.bytes
#                 }
#
#
# def calculate_provider_percentage(provider, start_date, end_date):
#     """
#     Calculates the percentage of streaming time represented by videos of the provider between start_date and end_date
#     :param provider:
#     :param start_date:
#     :param end_date:
#     :return:
#     """
#     pass


def get_ordered(member):
    """
    Gets movies already ordered by the member on the platform
    :param member:
    :return: list of movies already ordered by the member
    """
    updates = ContentUpdate.objects.filter(member=member)
    print '%d updates found' % updates.count()
    ordered = set()
    for update in updates:
        for movie in update.movies_add_list:
            ordered.add(movie)
        for episode in update.series_episodes_add_list:
            ordered.add(episode.series)
    return list(ordered)


def get_watched(member):
    """
    Gets movies already viewed by the member on the platform
    :param member:
    :return: list of movies already viewed by the member
    """
    reduce_stream_log_entries(member)
    entries = StreamLogEntry.objects.filter(member=member, status=StreamLogEntry.REDUCED).order_by('-id')
    watched = []
    for entry in entries:
        if entry.media_type.lower() == 'movie':
            try:
                movie = Movie.objects.get(pk=entry.media_id)
                if movie not in watched:
                    watched.append(movie)
            except Movie.DoesNotExist:
                pass
        else:
            try:
                episode = SeriesEpisode.objects.get(pk=entry.media_id)
                if episode.series not in watched:
                    watched.append(episode.series)
            except Movie.DoesNotExist:
                pass
    return watched
