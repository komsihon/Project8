# -*- coding: utf-8 -*-
from django.test.utils import override_settings
from ikwen.accesscontrol.models import Member

import shavida.models
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.utils.unittest import TestCase
from django.test.client import Client

__author__ = "Kom Sihon"


def wipe_test_data(db='default'):
    """
    This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
    each test. So the flush is performed manually with this custom tearDown()
    """
    import ikwen_shavida.movies.models
    import ikwen_shavida.reporting.models
    import ikwen_shavida.sales.models
    import ikwen_shavida.shavida.models
    import ikwen.partnership.models
    import ikwen.core.models
    for name in ('Category', 'Trailer', 'Movie', 'SeriesEpisode', 'Series'):
        model = getattr(ikwen_shavida.movies.models, name)
        model.objects.using(db).all().delete()
    for name in ('StreamLogEntry', 'HistoryEntry'):
        model = getattr(ikwen_shavida.reporting.models, name)
        model.objects.using(db).all().delete()
    for name in ('SalesConfig', 'VODBundle', 'RetailBundle', 'VODPrepayment', 'RetailPrepayment', 'ContentUpdate', 'UnitPrepayment'):
        model = getattr(ikwen_shavida.sales.models, name)
        model.objects.using(db).all().delete()
    for name in ('OperatorProfile', 'Customer'):
        model = getattr(ikwen_shavida.shavida.models, name)
        model.objects.using(db).all().delete()
    for name in ('Application', 'Service', 'Config', 'ConsoleEventType', 'ConsoleEvent', 'Country', ):
        model = getattr(ikwen.core.models, name)
        model.objects.using(db).all().delete()
    for name in ('PartnerProfile', 'ApplicationRetailConfig'):
        model = getattr(ikwen.partnership.models, name)
        model.objects.using(db).all().delete()


class CMSTest(TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['cms.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        """
        This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
        each test. So the flush is performed manually with this custom tearDown()
        """
        for name in ('Config', 'FlatPage'):
            model = getattr(shavida.models, name)
            model.objects.all().delete()

            # def test_is_first_refill_with_member_who_never_refilled(self):
            #     customer = Member.objects.create_user(account_type=Member.CUSTOMER, username='77777777', password='123456',
            #                                        email='roddy@red.com', postpaid_plan=None,
            #                                        storage_provider='CVB')
            #     self.assertTrue(customer.is_first_refill)

            # def test_is_first_refill_with_member_who_refilled_once(self):
            #     prepaid_plan = PrepaidPlan(id=2, name='plan1', cost=5000)
            #     storage = Storage(name='storage', size=32000, size_label=32000, type=Storage.FLASH_DISK)
            #     prepaid_plan.save()
            #     storage.save()
            #     customer = Member.objects.create_user(account_type=Member.CUSTOMER, username='77777777', password='123456',
            #                                        email='roddy@red.com', postpaid_plan=None, prepaid_plan=prepaid_plan,
            #                                        storage_provider='CVB', storage_status=Storage.ACQUIRING)
            #     when = datetime.now() - timedelta(days=12)
            #     latest_prepayment = RetailPrepayment(member=customer, when=when, amount=5000, storage=storage, duration=30, balance=20000)
            #     latest_prepayment.save()
            #     self.assertFalse(customer.can_order_adult)

            # def test_can_order_adult_with_member_having_prepaid_plan_and_max_orders_reached(self):
            #     customer = Member.objects.create_user(account_type=Member.CUSTOMER, username='77777777', password='123456',
            #                                        email='roddy@red.com', postpaid_plan=None,
            #                                        storage_provider='CVB' )
            #     latest_prepayment = RetailPrepayment(member=customer, amount=5000, duration=30, balance=20000)
            #     latest_prepayment.save()
            #     for i in range(4):
            #         order = CVBOrder(member=customer, cost=5000, status=CVBOrder.PENDING,
            #                          storage_amount=0, movies_amount=0, delivery_amount=0,copy_amount=0)
            #         order.save()
            #     self.assertTrue(customer.can_order_adult)
            #
            # def test_can_order_adult_with_member_having_prepaid_plan_and_max_orders_not_reached(self):
            #     customer = Member.objects.create_user(account_type=Member.CUSTOMER, username='77777777', password='123456',
            #                                        email='roddy@red.com', postpaid_plan=None,
            #                                        storage_provider='CVB')
            #     latest_prepayment = RetailPrepayment(member=customer, amount=5000, duration=30, balance=20000)
            #     latest_prepayment.save()
            #     for i in range(2):
            #         order = CVBOrder(member=customer, cost=5000,  status=CVBOrder.PENDING,
            #                          storage_amount=0, movies_amount=0, delivery_amount=0,copy_amount=0)
            #         order.save()
            #     self.assertFalse(customer.can_order_adult)
            #
            # def test_can_order_adult_with_member_having_prepaid_plan_and_prepayment_expired(self):
            #     customer = Member.objects.create_user(account_type=Member.CUSTOMER, username='77777777', password='123456',
            #                                        email='roddy@red.com', postpaid_plan=None,
            #                                        storage_provider='CVB')
            #     when = datetime.now() - timedelta(days=40)
            #     latest_prepayment = RetailPrepayment(member=customer, when=when, amount=5000, duration=30, balance=20000)
            #     latest_prepayment.save()
            #     self.assertTrue(customer.can_order_adult)
            #
            # def test_can_order_adult_with_member_having_prepaid_plan_and_prepayment_not_expired(self):
            #     customer = Member.objects.create_user(account_type=Member.CUSTOMER, username='77777777', password='123456',
            #                                        email='roddy@red.com', postpaid_plan=None,
            #                                        storage_provider='CVB')
            #     when = datetime.now() - timedelta(days=12)
            #     latest_prepayment = RetailPrepayment(member=customer, when=when, amount=5000, duration=30, balance=20000)
            #     latest_prepayment.save()
            #     self.assertFalse(customer.can_order_adult)
