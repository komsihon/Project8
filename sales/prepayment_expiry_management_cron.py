#!/usr/bin/env python
import sys, os

# sys.path.append("/home/komsihon/PycharmProjects/CVraimentBien")
sys.path.append("/home/cinemax/apps/prod")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Cinemax.settings")
from ikwen.accesscontrol.models import Member


customers = Member.objects.filter(account_type=Member.CUSTOMER)
for customer in customers:
    latest_prepayment = customer.get_last_retail_prepayment()
    if latest_prepayment and latest_prepayment.days_left < 0:
        latest_prepayment.balance = 0
        latest_prepayment.save()
