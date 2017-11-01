# -*- coding: utf-8 -*-
import json

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.http.response import HttpResponseForbidden
from django.utils.translation import gettext as _

from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance

from ikwen_shavida.conf.files_selector import collect_movies, collect_series
from ikwen_shavida.movies.models import Movie, SeriesEpisode
from ikwen_shavida.movies.views import CustomerView
from ikwen_shavida.reporting.models import StreamLogEntry, HistoryEntry
from ikwen_shavida.sales.models import ContentUpdate
from ikwen_shavida.sales.models import SalesConfig

__author__ = "Kom Sihon"


def get_history_data(request):
    updates = ContentUpdate.objects.filter(member=request.user).order_by('-id')
    response = [update.to_dict() for update in updates]
    return HttpResponse(json.dumps(response), 'content-type: text/json')


def get_filename(file_path):
    """
    Gets the filename only part of a file path
    get_filename('/home/root/Documents/somefile.avi') = 'somefile.avi'
    """
    idx = file_path.rfind('/') + 1
    return file_path[idx:]


def get_series_folder(filename):
    naked_filename = get_filename(filename)
    rel_folder = filename.replace(naked_filename, '')
    return rel_folder


def get_series_from_episodes(episodes):
    """
    Gets the list of Series matching the list of episodes provided
    :param episodes: a list of SeriesEpisode
    :return: list of Series
    """
    series = set()
    for episode in episodes:
        series.add(episode.series)
    return list(series)


def auto_select_media(request, *args, **kwargs):
    service = get_service_instance()
    provider_website = service.project_name
    provider = service.member
    member = request.user
    # Delete any prior "RUNNING" ContentUpdate for this member
    ContentUpdate.objects.filter(member=member, status=ContentUpdate.RUNNING).delete()

    movies_max_load = request.GET.get('movies_max_load')
    series_max_load = request.GET.get('series_max_load')
    unit = getattr(settings, 'SALES_UNIT', SalesConfig.DATA_VOLUME)
    base_categories_slugs = request.GET.get('base_categories_slugs')
    preferred_categories_slugs = request.GET.get('preferred_categories_slugs')
    base_categories_slugs = base_categories_slugs.split(',') if base_categories_slugs else []
    preferred_categories_slugs = preferred_categories_slugs.split(',') if base_categories_slugs else []
    movies_max_load = int(movies_max_load)
    series_max_load = int(series_max_load)
    movies_exclude_list_ids = []
    series_exclude_list = []
    for update in ContentUpdate.objects.filter(member=member).exclude(status=ContentUpdate.RUNNING):
        movies_exclude_list_ids.extend([movie.id for movie in update.movies_add_list])
        series_exclude_list.extend(get_series_from_episodes(update.series_episodes_add_list))
    media_selection = collect_movies(movies_max_load, unit, base_categories_slugs,
                                     preferred_categories_slugs, movies_exclude_list_ids)
    media_selection.extend(collect_series(series_max_load, unit, series_exclude_list))
    add_list = []
    add_list_size = 0
    add_list_duration = 0
    for item in media_selection:
        add_list_size += item.size
        add_list_duration += item.duration
        filenames = item.filename.split(',')  # Some movies have filename in multiple parts separated by comma
        for filename in filenames:
            filename = filename.strip()
            add_list.append(filename)
    update = ContentUpdate(member=member, status=ContentUpdate.RUNNING, provider=provider, provider_website=provider_website,
                           add_list=','.join(add_list), add_list_size=add_list_size, add_list_duration=add_list_duration)
    update.movies_add_list = []
    update.series_episodes_add_list = []
    current_series = None
    for media in media_selection:
        if type(media).__name__ == "Movie":
            update.cost += media.price
            update.movies_add_list.append(media)
        elif type(media).__name__ == "SeriesEpisode":
            if current_series != media.series:
                update.cost += media.series.price
                current_series = media.series
            update.series_episodes_add_list.append(media)
    update.save()


@login_required
def start_auto_selection(request, *args, **kwargs):
    # if getattr(settings, 'DEBUG', False):
    #     auto_select_media(request, *args, **kwargs)
    # else:
    from threading import Thread
    thread = Thread(target=auto_select_media, args=(request, args), kwargs=kwargs)
    thread.start()
    return HttpResponse(json.dumps({'success': True}), 'content-type: text/json')


@login_required
def check_auto_selection_status(request, *args, **kwargs):
    # TODO: Write scripts and cron to wipe out stale ContentUpdate with status RUNNING
    member = request.user
    try:
        update = ContentUpdate.objects.get(member=member, status=ContentUpdate.RUNNING)
    except ContentUpdate.DoesNotExist:
        response = {'error': "No such Content update"}
    else:
        response = []
        for movie in update.movies_add_list:
            response.append(movie.to_dict())
        for episode in update.series_episodes_add_list:
            response.append(episode.to_dict())
    return HttpResponse(json.dumps(response), 'content-type: text/json')


def get_repo_files_update(request, *args, **kwargs):
    username = request.GET.get('username')
    password = request.GET.get('password')
    provider = authenticate(username=username, password=password)
    if not provider:
        response = {'error': "Could not authenticate user %s with password." % username}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    available_space = request.GET.get('available_space')
    operator_username = request.GET.get('operator_username')
    try:
        member = Member.objects.get(email=operator_username)
        database = get_service_instance().database
        update = ContentUpdate.objects.get(member=member, status=ContentUpdate.AUTHORIZED)
    except Member.DoesNotExist:
        response = {'error': "Member not found with username %s" % operator_username}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    except ContentUpdate.DoesNotExist:
        response = {'error': "No update placed by member with username %s" % operator_username}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    total_available_space = int(available_space) + update.delete_list_size
    if total_available_space < update.add_list_size:
        needed_space = update.add_list_size - total_available_space
        if needed_space >= 1000:
            needed_space_str = "%.2f GB" % (needed_space / 1000.0)
        else:
            needed_space_str = "%d MB" % needed_space
        response = {'error': "Insufficient space on drive to run this update, Need %s more." % needed_space_str}
        return HttpResponse(json.dumps(response), 'content-type: text/json')
    latest_prepayment = member.customer.get_last_retail_prepayment()
    latest_prepayment.balance -= update.add_list_size
    latest_prepayment.save()
    update.provider = provider
    update.save()
    if not getattr(settings, 'UNIT_TESTING', False):
        update.save(using=database)
    response = {
        'add_list': update.add_list.split(','),
        'delete_list': update.delete_list.split(',')
    }
    return HttpResponse(json.dumps(response), 'content-type: text/json')


@login_required
def debit_vod_balance(request, *args, **kwargs):
    referrer = request.META.get('HTTP_REFERER')
    if not referrer:
        return HttpResponseForbidden("You don't have permission to access this resource.")
    member = request.user
    last_vod_prepayment = member.customer.get_last_vod_prepayment()
    response = {'success': True}
    try:
        bytes = int(request.GET.get('bytes'))
        duration = int(request.GET.get('duration'))
        type = request.GET.get('type')
        media_id = request.GET.get('media_id')
        if bytes and bytes > 0:
            if bytes >= last_vod_prepayment.balance:
                last_vod_prepayment.balance = 0
                response['error'] = _("Sorry, you just ran out of balance. Please refill your account.")
            else:
                last_vod_prepayment.balance -= bytes
            StreamLogEntry.objects.create(member=member, media_type=type, media_id=media_id, duration=duration, bytes=bytes)
            last_vod_prepayment.save()
    finally:
        response['balance'] = last_vod_prepayment.balance
        return HttpResponse(json.dumps(response), 'content-type: text/json')


class History(CustomerView):
    template_name = 'reporting/history.html'

    def get_context_data(self, **kwargs):
        context = super(History, self).get_context_data(**kwargs)
        watched = []
        for entry in HistoryEntry.objects.filter(member=self.request.user).order_by('-id')[:10]:
            try:
                media = Movie.objects.get(pk=entry.media_id)
            except Movie.DoesNotExist:
                try:
                    media = SeriesEpisode.objects.get(pk=entry.media_id)
                    media.slug = media.series.slug
                except SeriesEpisode.DoesNotExist:
                    continue
            entry.media = media
            watched.append(entry)
        context['watched'] = watched
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'monitor':
            member = request.user
            if member.is_authenticated():
                media_id = request.GET['media_id']
                percentage = request.GET['percentage']
                entry, created = HistoryEntry.objects.get_or_create(member=request.user, media_id=media_id)
                if percentage > entry.percentage:
                    entry.percentage = percentage
                entry.save()
                response = {"success": True}
            else:
                response = {"error": _("Your session was closed. May be you logged in elsewhere.")}
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        return super(History, self).get(request, *args, **kwargs)
