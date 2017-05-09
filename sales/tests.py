"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""
import json

from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.utils.unittest import TestCase
from django.test.utils import override_settings
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.core.models import OperatorWallet, Service
from ikwen.core.utils import add_database_to_settings, get_service_instance
from ikwen_shavida.shavida.tests import wipe_test_data


class SalesViewsTest(TestCase):
    fixtures = ['svd_setup_data.yaml', 'svd_members.yaml', 'config_and_bundles.yaml']

    def setUp(self):
        self.client = Client()
        add_database_to_settings('test_kc_partner_jumbo')
        wipe_test_data()
        wipe_test_data('test_kc_partner_jumbo')
        wipe_test_data(UMBRELLA)
        for fixture in self.fixtures:
            call_command('loaddata', fixture)
            call_command('loaddata', fixture, database=UMBRELLA)

    def tearDown(self):
        wipe_test_data()
        wipe_test_data('test_kc_partner_jumbo')
        wipe_test_data(UMBRELLA)
        OperatorWallet.objects.using('wallets').all().update(balance=0)
        # cache.clear()

    @override_settings(IKWEN_SERVICE_ID='54ad2bd9b37b335a18fe5801',
                       EMAIL_BACKEND='django.core.mail.backends.filebased.EmailBackend',
                       EMAIL_FILE_PATH='test_emails/sales/', DEBUG=True,
                       JUMBOPAY_API_URL='https://154.70.100.194/api/sandbox/v2/')
    def test_choose_bundle_with_partner_retailer(self):
        """
        Checking out with Mobile Money should work well too
        """
        call_command('loaddata', 'svd_members.yaml', database='test_kc_partner_jumbo')
        call_command('loaddata', 'svd_setup_data.yaml', database='test_kc_partner_jumbo')
        call_command('loaddata', 'partners.yaml')
        call_command('loaddata', 'partners.yaml', database=UMBRELLA)
        call_command('loaddata', 'partners.yaml', database='test_kc_partner_jumbo')
        call_command('loaddata', 'partner_app_retail_config.yaml', database=UMBRELLA)
        call_command('loaddata', 'partner_app_retail_config.yaml', database='test_kc_partner_jumbo')

        service_umbrella = get_service_instance(UMBRELLA)
        partner = Service.objects.using(UMBRELLA).get(pk='56eb6d04b9b531b10537b331')
        service_umbrella.retailer = partner
        service_umbrella.save(using=UMBRELLA)
        cache.clear()

        self.client.login(username='member4', password='admin')
        self.client.post(reverse('billing:momo_set_checkout'), {'bundle_id': '579b6eb6d0e0124b37b33532'})
        response = self.client.get(reverse('billing:init_momo_cashout'), data={'phone': '655003321'})
        json_resp = json.loads(response.content)
        tx_id = json_resp['tx_id']
        response = self.client.get(reverse('billing:check_momo_transaction_status'), data={'tx_id': tx_id})
        json_resp = json.loads(response.content)
        self.assertTrue(json_resp['success'])


        # Check counters
        cache.clear()
        operator_wallet = OperatorWallet.objects.using('wallets').get(nonrel_id=service_umbrella.id)
        self.assertEqual(operator_wallet.balance, 94000)

        # Assuming IKWEN collects 1000 on revenue of provider and one of retailer
        service_umbrella = get_service_instance(UMBRELLA)
        self.assertEqual(service_umbrella.turnover_history, [100000])
        self.assertEqual(service_umbrella.earnings_history, [2400])
        self.assertEqual(service_umbrella.transaction_count_history, [1])
        self.assertEqual(service_umbrella.transaction_earnings_history, [2400])

        app_umbrella = service_umbrella.app
        self.assertEqual(app_umbrella.turnover_history, [100000])
        self.assertEqual(app_umbrella.earnings_history, [2400])
        self.assertEqual(app_umbrella.transaction_count_history, [1])
        self.assertEqual(app_umbrella.transaction_earnings_history, [2400])

        service_mirror_partner = Service.objects.using('test_kc_partner_jumbo').get(pk=service_umbrella.id)
        self.assertEqual(service_mirror_partner.earnings_history, [3600])
        self.assertEqual(service_mirror_partner.transaction_count_history, [1])
        self.assertEqual(service_mirror_partner.transaction_earnings_history, [3600])

        app_mirror_partner = service_mirror_partner.app
        self.assertEqual(app_mirror_partner.earnings_history, [3600])
        self.assertEqual(app_mirror_partner.transaction_count_history, [1])
        self.assertEqual(app_mirror_partner.transaction_earnings_history, [3600])

        partner_wallet = OperatorWallet.objects.using('wallets').get(nonrel_id='56eb6d04b9b531b10537b331')
        self.assertEqual(partner_wallet.balance, 3600)

        customer = Member.objects.get(username='member4').customer
        self.assertEqual(customer.orders_count_history, [1])
        self.assertEqual(customer.turnover_history, [100000])
