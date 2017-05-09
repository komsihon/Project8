# -*- coding: utf-8 -*-

"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""
import json

import time
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test import Client
from django.utils.unittest import TestCase
from django.test.utils import override_settings
from ikwen.accesscontrol.models import Member
from ikwen_shavida.movies.models import Movie, SeriesEpisode, Trailer

from ikwen_shavida.movies.tests_views import wipe_test_data
from ikwen_shavida.sales.models import ContentUpdate, SalesConfig
from ikwen_shavida.sales.models import RetailPrepayment


class ReportingViewsTest(TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['setup_data.yaml', 'members.yaml', 'categories.yaml', 'movies.yaml', 'content_updates.yaml',
                'prepayments.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            if fixture == 'members.yaml':
                call_command('loaddata', fixture, database='umbrella')
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()

    @override_settings(UNIT_TESTING=True,  # Avoid trying to save in database other than default
                       SALES_UNIT=SalesConfig.DATA_VOLUME, IKWEN_SERVICE_ID='54ad2bd9b37b335a18fe5801')
    def test_auto_select_media(self):
        """
        Auto-select movies and series, binds them to a ContentUpdate object
        and save it to the database
        """
        ContentUpdate.objects.all().delete()
        self.client.login(username='member2@ikwen.com', password='admin')
        response = self.client.get(reverse('reporting:start_auto_selection'),
                                   {'movies_max_load': '200000', 'series_max_load': '450000'})
        json_resp = json.loads(response.content)
        self.assertTrue(json_resp['success'])
        media_files1, media_objects = set(), []
        for movie in Movie.objects.all():
            for filename in movie.resource.split(','):
                media_files1.add(filename.strip())
                if movie.trailer_slug:
                    trailer = Trailer.objects.get(slug=movie.trailer_slug)
                    media_files1.add(trailer.resource)
            media_objects.append(movie.to_dict())
        for episode in SeriesEpisode.objects.all():
            media_files1.add(episode.resource)
            if episode.series.trailer_slug:
                trailer = Trailer.objects.get(slug=episode.series.trailer_slug)
                media_files1.add(trailer.resource)
            media_objects.append(episode.to_dict())
        trials = 0
        json_response = []
        while trials < 10:
            time.sleep(1)
            trials += 1
            response = self.client.get(reverse('reporting:check_auto_selection_status'))
            json_response = json.loads(response.content)
            if type(json_response).__name__ == 'list':
                break
            else:
                continue
        member = Member.objects.get(email='member2@ikwen.com')
        update = ContentUpdate.objects.get(member=member, status=ContentUpdate.RUNNING)
        media_files2, media_objects2 = [], []
        for filename in update.add_list.split(','):
            filename = filename.strip()
            media_files2.append(filename)

        self.assertEqual(len(media_files1), len(media_files2))
        for m in media_files1:
            self.assertIn(m, media_files2)
        self.assertEqual(len(media_objects), len(json_response))
        for m in media_objects:
            self.assertIn(m, json_response)

    def test_get_repo_files_update_with_wrong_provider_credentials(self):
        """
        Return a JSON error message if wrong username and/or password
        """
        username = 'simo'
        response = self.client.get(reverse('reporting:get_repo_files_update'), {'username': username, 'password': 'admin'})
        json_resp = json.loads(response.content)
        self.assertEqual(json_resp['error'], "Could not authenticate user %s with password." % username)

    def test_get_repo_files_update_with_unexisting_operator_username(self):
        """
        Return a JSON error message if wrong operator_username
        """
        operator_username = 'simo'
        response = self.client.get(reverse('reporting:get_repo_files_update'),
                                   {'username': 'member1@ikwen.com', 'password': 'admin', 'operator_username': operator_username})
        json_resp = json.loads(response.content)
        self.assertEqual(json_resp['error'], "Member not found with username %s" % operator_username)

    @override_settings(UNIT_TESTING=True,  # Avoid trying to save in database other than default
                       SALES_UNIT=SalesConfig.DATA_VOLUME, IKWEN_SERVICE_ID='54ad2bd9b37b335a18fe5801')
    def test_get_repo_files_update_with_insufficient_space(self):
        """
        Return a JSON error message if wrong insufficient space
        """
        member = Member.objects.get(email='member2@ikwen.com')
        add_list = ['top-movie.part1.mp4', 'top-movie.part2.mp4', 'Daredevil.saison1/Daredevil-s01e01.mp4']
        delete_list = ['hd-movie.mp4', 'western-movie.mp4']
        ContentUpdate.objects.get(member=member).delete()
        ContentUpdate.objects.create(member=member, add_list=','.join(add_list), add_list_size=100000,
                                     delete_list=','.join(delete_list), delete_list_size=15000, status=ContentUpdate.AUTHORIZED)
        response = self.client.get(reverse('reporting:get_repo_files_update'),
                                   {'username': 'member1@ikwen.com', 'password': 'admin', 'operator_username': 'member2@ikwen.com',
                                    'available_space': '35000'})
        needed_space_str = "%.2f GB" % (50000 / 1000.0)
        json_resp = json.loads(response.content)
        self.assertEqual(json_resp['error'], "Insufficient space on drive to run this update, Need %s more." % needed_space_str)

    @override_settings(UNIT_TESTING=True,  # Avoid trying to save in database other than default
                       SALES_UNIT=SalesConfig.DATA_VOLUME, IKWEN_SERVICE_ID='54ad2bd9b37b335a18fe5801')
    def test_get_repo_files_update_with_everything_ok(self):
        """
        Return a JSON list of filename
        """
        member = Member.objects.get(email='member2@ikwen.com')
        add_list = ['top-movie.part1.mp4', 'top-movie.part2.mp4', 'Daredevil.saison1/Daredevil-s01e01.mp4']
        delete_list = ['hd-movie.mp4', 'western-movie.mp4']
        RetailPrepayment.objects.create(member=member, balance=100000, amount=0)
        ContentUpdate.objects.get(member=member).delete()
        ContentUpdate.objects.create(member=member, add_list=','.join(add_list), add_list_size=40000,
                                     delete_list=','.join(delete_list), delete_list_size=15000, status=ContentUpdate.AUTHORIZED)
        response = self.client.get(reverse('reporting:get_repo_files_update'),
                                   {'username': 'member1@ikwen.com', 'password': 'admin', 'operator_username': 'member2@ikwen.com',
                                    'available_space': '35000'})
        update = json.loads(response.content)
        self.assertDictEqual(update, {'add_list': add_list, 'delete_list': delete_list})
        update = ContentUpdate.objects.order_by('-id')[0]
        prepayment = RetailPrepayment.objects.filter(member=member).order_by('-id')[0]
        self.assertEqual(update.status, ContentUpdate.AUTHORIZED)
        self.assertEqual(prepayment.balance, 60000)

    def test_debit_user_with_direct_url_hit(self):
        """
        Hitting the URL directly should return an http 403 Forbidden error
        """
        response = self.client.get(reverse('reporting:debit_vod_balance'), {'bytes': '3000000'})
        self.assertTrue(response.status_code, 403)

    def test_debit_user(self):
        """
        Debiting user should cause VODPrepayment.balance to decrease by the number of bytes passed as parameter
        """
        self.client.login(username='member3@ikwen.com', password='admin')
        response = self.client.get(reverse('reporting:debit_vod_balance'), {'bytes': 3000000, 'duration': 3, 'type': 'movie', 'media_id': '56eb6d04b37b3379b531e081'},
                                   HTTP_REFERER='referer')
        json_content = json.loads(response.content)
        self.assertEqual(json_content['balance'], 197000000)
