# -*- coding: utf-8 -*-
import json

import os

from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.template.defaultfilters import urlencode
from django.utils.unittest import TestCase
from django.test.client import Client
from django.test.utils import override_settings
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_service_instance
from ikwen_shavida.movies.models import Category, Movie, Series
from ikwen_shavida.movies.utils import EXCLUDE_LIST_KEYS_KEY
from ikwen_shavida.sales.models import VODPrepayment, UnitPrepayment, Prepayment

__author__ = "Kom Sihon"


def wipe_test_data():
    """
    This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
    each test. So the flush is performed manually with this custom tearDown()
    """
    import ikwen_shavida.shavida.models
    import ikwen_shavida.movies.models
    import ikwen_shavida.sales.models
    import ikwen_shavida.reporting.models
    for name in ('OperatorProfile', 'Customer'):
        model = getattr(ikwen_shavida.shavida.models, name)
        model.objects.all().delete()
    for name in ('Category', 'Movie', 'Series', 'SeriesEpisode'):
        model = getattr(ikwen_shavida.movies.models, name)
        model.objects.all().delete()
    for name in ('RetailBundle', 'VODBundle', 'VODPrepayment', 'UnitPrepayment', 'RetailPrepayment', 'ContentUpdate'):
        model = getattr(ikwen_shavida.sales.models, name)
        model.objects.all().delete()
    for name in ('StreamLogEntry',):
        model = getattr(ikwen_shavida.reporting.models, name)
        model.objects.all().delete()


class MoviesViewsTest(TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['setup_data.yaml', 'members.yaml', 'categories.yaml', 'movies.yaml',
                'prepayments.yaml', 'config_and_bundles.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            if fixture == 'members.yaml':
                call_command('loaddata', fixture, database='umbrella')
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()

    @override_settings(CACHES={  # Override the CACHES settings to avoid interference if running tests on prod server
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
            'LOCATION': '127.0.0.1:11211'
        }
    }, IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_get_media(self):
        """
        Must return a list of media in JSON format and cache the returned response
        :return:
        """
        cache.delete('56eb6d04b37b3379b531e092-0-0-5')
        url = reverse('movies:get_media')
        category_western = Category.objects.get(pk='56eb6d04b37b3379b531e092')
        for movie in Movie.objects.all():
            movie.categories.append(category_western)
            movie.save()
        for series in Series.objects.all():
            series.categories.append(category_western)
            series.save()
        data = {'category_id': '56eb6d04b37b3379b531e092', 'start_movies': 0, 'start_series': 0, 'length': 5, 'shuffle': 'yes'}
        response = self.client.get(url, data)
        media = json.loads(response.content)
        movies_count = 0
        for item in media:
            if item['type'] == 'movie':
                movies_count += 1
        self.assertEqual(len(media), 5)
        self.assertEqual(movies_count, 3)
        cache.delete('56eb6d04b37b3379b531e092-0-0-5')

    @override_settings(CACHES={  # Override the CACHES settings to avoid interference if running tests on prod server
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
            'LOCATION': '127.0.0.1:11211'
        }
    }, IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_get_recommended_for_single_category(self):
        """
        This view should return a list of Media in JSON format that are not in a provided exclude_list. The so
        recommended items must be put in cache
        :return:
        """
        category_id = '56eb6d04b37b3379b531e092'
        exclude_list_keys_key = 'member1:' + EXCLUDE_LIST_KEYS_KEY
        cache_key_test = 'member1:test'
        cache_key_recommended = u'member1:recommended-%s' % category_id
        cache.delete(exclude_list_keys_key)
        cache.delete(cache_key_test)
        cache.delete(cache_key_recommended)
        self.client.login(username='member1@ikwen.com', password='admin')
        category_western = Category.objects.get(pk=category_id)
        for movie in Movie.objects.all():
            movie.categories.append(category_western)
            movie.save()
        for series in Series.objects.all():
            series.categories.append(category_western)
            series.save()
        exclude_list_keys = {cache_key_test}
        items_to_exclude = [Movie.objects.get(pk=pk) for pk in ('56eb6d04b37b3379b531e085', '56eb6d04b37b3379b531e086')]
        cache.set(exclude_list_keys_key, exclude_list_keys)
        cache.set(cache_key_test, items_to_exclude)
        url = reverse('movies:get_recommended_for_single_category')
        response = self.client.get(url, {'category_id': category_id})
        media = json.loads(response.content)
        expected_media = [Movie.objects.get(pk=pk).to_dict() for pk in ('56eb6d04b37b3379b531e084', '56eb6d04b37b3379b531e083', '56eb6d04b37b3379b531e082')]
        expected_media.extend([Series.objects.get(pk=pk).to_dict() for pk in ('56eb6d04b37b3379b531e074', '56eb6d04b37b3379b531e073')])
        cached_recommended = cache.get(cache_key_recommended)
        json_cached_recommended = [item.to_dict() for item in cached_recommended]
        cached_ex_list_keys = cache.get(exclude_list_keys_key)
        for item in media:
            self.assertIn(item, expected_media)
        for item in media:
            self.assertIn(item, json_cached_recommended)
        for key in cached_ex_list_keys:
            self.assertIn(key, [cache_key_test, cache_key_recommended])
        cache.delete(exclude_list_keys_key)
        cache.delete(cache_key_test)
        cache.delete(cache_key_recommended)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Search_with_anonymous_user_adult_movie_and_json_results(self):
        """
        Adult movies do not appear in anonymous users results even if tags match
        :return:
        """
        adult_movie = Movie.objects.get(pk='56eb6d04b37b3379b531e083')
        adult_movie.tags = 'good bad ugly'  # Same tags as the expected movie but won't be found with anonymous user
        adult_movie.save()
        terms = 'useless  ugly goodies '
        response = self.client.get(reverse('movies:search'), {'q': terms, 'format': 'json'})
        media = json.loads(response.content)
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]['id'], '56eb6d04b37b3379b531e086')

    @override_settings(DEBUG=True, IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Search_with_authenticated_adult_movie_user_and_json_results(self):
        """
        Adult movies can appear in authenticated users results if tags match and user can access adult content
        :return:
        """
        adult_movie = Movie.objects.get(pk='56eb6d04b37b3379b531e083')
        adult_movie.tags = 'good bad ugly'  # Same tags as the expected movie but won't be found with anonymous user
        adult_movie.save()
        terms = 'useless      ugly goodies '
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:search'), {'q': terms, 'format': 'json'})
        media = json.loads(response.content)
        self.assertEqual(len(media), 2)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Search_with_anonymous_user_adult_movie_and_results_in_a_page(self):
        """
        Adult movies do not appear in anonymous users results even if tags match
        :return:
        """
        adult_movie = Movie.objects.get(pk='56eb6d04b37b3379b531e083')
        adult_movie.tags = 'good bad ugly'  # Same tags as the expected movie but won't be found with anonymous user
        adult_movie.save()
        terms = 'useless  ugly goodies '
        response = self.client.get(reverse('movies:search'), {'q': terms}, HTTP_USER_AGENT='Mozilla 5.1')
        media = response.context['items']
        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]['id'], '56eb6d04b37b3379b531e086')

    @override_settings(DEBUG=True, IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Search_with_authenticated_adult_movie_user_and_results_in_a_page(self):
        """
        Adult movies can appear in authenticated users results if tags match and user can access adult content
        :return:
        """
        adult_movie = Movie.objects.get(pk='56eb6d04b37b3379b531e083')
        adult_movie.tags = 'good bad ugly'  # Same tags as the expected movie but won't be found with anonymous user
        adult_movie.save()
        terms = 'useless      ugly goodies '
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:search'), {'q': terms}, HTTP_USER_AGENT='Mozilla 5.1')
        media = response.context['items']
        self.assertEqual(len(media), 2)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_MediaList_with_normal_category(self):
        """
        Normal category shows the MediaList without any issue
        :return:
        """
        origin = reverse('movies:media_list', args=('western', ))
        response = self.client.get(origin, HTTP_USER_AGENT='Mozilla 5.1')
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_MediaList_with_category_adult_and_anonymous_user(self):
        """
        Anonymous user is redirected to login page when trying to access the MediaList view with an adult Category
        :return:
        """
        origin = reverse('movies:media_list', args=('adult', ))
        response = self.client.get(origin, follow=True, HTTP_USER_AGENT='Mozilla 5.1')
        final = response.redirect_chain[-1]
        signInUrl = 'http://testserver' + reverse('ikwen:sign_in') + '?next_url=' + urlencode(origin)
        self.assertEqual(final[0], signInUrl)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_MovieDetail(self):
        """
        MovieDetail view page should correctly grab suggestions
        :return:
        """
        category_western = Category.objects.get(pk='56eb6d04b37b3379b531e092')
        for movie in Movie.objects.all():
            if movie.id not in ['56eb6d04b37b3379b531e081', '56eb6d04b37b3379b531e083']:
                movie.categories.append(category_western)
            movie.groups = 'sample group'
            movie.save()
        movie = Movie.objects.get(pk='56eb6d04b37b3379b531e082')
        response = self.client.get(reverse('movies:movie_detail'), {'slug': movie.slug, 'format': 'ajax_html'}, HTTP_USER_AGENT='Mozilla 5.1')
        self.assertEqual(response.status_code, 200)
        suggestions = response.context['suggestions']
        self.assertEqual(len(suggestions), 5)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_SeriesDetail(self):
        """
        MovieDetail view page should correctly grab series episodes and suggestions
        :return:
        """
        series = Series.objects.get(pk='56eb6d04b37b3379b531e073')
        response = self.client.get(reverse('movies:series_detail'), {'slug': series.slug, 'format': 'ajax_html'}, HTTP_USER_AGENT='Mozilla 5.1')
        self.assertEqual(response.status_code, 200)
        suggestions = response.context['suggestions']
        episodes = response.context['episodes']
        self.assertEqual(len(suggestions), 3)
        self.assertEqual(len(episodes), 2)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Bundles(self):
        response = self.client.get(reverse('movies:bundles'), HTTP_USER_AGENT='Mozilla 5.1')
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Home(self):
        response = self.client.get(reverse('movies:home'), HTTP_USER_AGENT='Mozilla 5.1')
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_Home_with_logged_in_member(self):
        self.client.login(username='member1@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:home'), HTTP_USER_AGENT='Mozilla 5.1')
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_with_direct_access(self):
        """
        Attempting to hit the URL directly should return a 403 Forbidden error
        """
        self.client.login(username='member1@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e081', 'is_check': 'yes'})
        self.assertEqual(response.status_code, 403)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_with_empty_balance(self):
        """
        Hiting stream url with empty balance returns a JSON error message
        """
        member = Member.objects.get(pk='56eb6d04b37b3379b531e014')
        lp = member.customer.get_last_vod_prepayment()
        lp.balance = 0
        lp.save()
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e081', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertEqual(json_content['error'], "Sorry, your VOD bundle is sold out. Please buy a new one.")

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_with_expired_prepayment(self):
        """
        Hiting stream url with an expired VODPrepayment returns a JSON error message
        """
        member = Member.objects.get(pk='56eb6d04b37b3379b531e014')
        lp = member.customer.get_last_vod_prepayment()
        lp.paid_on = datetime.now() - timedelta(days=10)
        lp.duration = 7
        lp.save()
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e081', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertEqual(json_content['error'], "Sorry, your VOD bundle is expired. Please buy a new one.")

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_without_prepayment(self):
        """
        Hiting stream url without having a paid VODPrepayment sends a JSON response error
        """
        member = Member.objects.get(pk='56eb6d04b37b3379b531e014')
        lp = member.customer.get_last_vod_prepayment()
        lp.status = VODPrepayment.PENDING
        lp.save()
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e081', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertEqual(json_content['error'], "Sorry, you don't have any valid bundle. Please buy one.")

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_with_adult_movie_and_vod_prepayment_without_adult_authorized(self):
        """
        Return a JSON error message when attempting to read an adult movie without the correct prepayment
        """
        self.client.login(username='member3@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e083', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertEqual(json_content['error'], "Sorry, only bundles as from XAF 2500 give you access to this content")

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_with_movie_file_unavailable(self):
        """
        Return a JSON error message if movie file is unavailable
        """
        self.client.login(username='member3@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e084', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertEqual(json_content['error'], "Resource temporarily unavailable. Please try again later.")

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_check_without_vodprepayment_and_valid_temp_prepayment(self):
        """
        Hiting stream url without having a paid VODPrepayment works
        if we have a valid TempPrepayment to watch a single media
        """
        member = Member.objects.get(pk='56eb6d04b37b3379b531e014')
        movie = Movie.objects.get(pk='56eb6d04b37b3379b531e084')
        VODPrepayment.objects.all().delete()
        path = getattr(settings, 'STATIC_ROOT') + movie.resource
        fh = open(path, 'w')
        fh.write('some data')
        fh.close()
        now = datetime.now()
        expiry = now + timedelta(days=2)
        UnitPrepayment.objects.create(member=member, media_type='movie', media_id='56eb6d04b37b3379b531e084',
                                      amount=300, duration=2, paid_on=now, expiry=expiry, status=Prepayment.CONFIRMED)
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e084', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertTrue(json_content['media_url'])
        os.unlink(path)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_check_with_free_media(self):
        """
        Hiting stream url requesting a media which view_price = 0 should not perform any
        pricing related check. So should return {'success': True} even if there's no VODPrepayment.
        """
        movie = Movie.objects.get(pk='56eb6d04b37b3379b531e084')
        movie.view_price = 0
        movie.save()
        VODPrepayment.objects.all().delete()
        path = getattr(settings, 'STATIC_ROOT') + movie.resource
        fh = open(path, 'w')
        fh.write('some data')
        fh.close()
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e084', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertTrue(json_content['media_url'])
        os.unlink(path)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_check_with_everything_ok(self):
        """
        Return JSON {'success': true} if everything goes well and if queried with parameter is_check=yes
        """
        movie = Movie.objects.get(pk='56eb6d04b37b3379b531e084')
        path = getattr(settings, 'STATIC_ROOT') + movie.resource
        fh = open(path, 'w')
        fh.write('some data')
        fh.close()
        self.client.login(username='member4@ikwen.com', password='admin')
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e084', 'is_check': 'yes'}, HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertTrue(json_content['media_url'])
        os.unlink(path)

    @override_settings(IKWEN_SERVICE_ID = '54ad2bd9b37b335a18fe5801')
    def test_stream_with_everything_ok(self):
        """
        Redirected to the actual file if everything is OK.
        """
        movie = Movie.objects.get(pk='56eb6d04b37b3379b531e084')
        path = getattr(settings, 'STATIC_ROOT') + movie.resource
        fh = open(path, 'w')
        fh.write('some data')
        fh.close()
        config = get_service_instance().config
        file_url = config.data_sources.split(',')[1].strip() + movie.resource
        print file_url
        response = self.client.get(reverse('movies:stream'), {'type': 'movie', 'item_id': '56eb6d04b37b3379b531e084'}, HTTP_REFERER='referer')
        self.assertEqual(response.status_code, 302)
        os.unlink(path)
