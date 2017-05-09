# -*- coding: utf-8 -*-

from django.db import models
from django.utils import timezone
from ikwen.accesscontrol.models import Member
from ikwen.core.models import Model

__author__ = "Kom Sihon"


class StreamLogEntry(models.Model):
    """
    As a file is streamed to the client, a log is created at regular intervals to keep how
    much bytes where streamed within that interval. Entries are created with the status Single.
    Summing up successive Single entries for the same media_id give the total of time and bytes
    the media was streamed.
    """
    SINGLE = 'Single'
    REDUCED = 'Reduced'
    member = models.ForeignKey('accesscontrol.Member')
    media_type = models.CharField(max_length=15)
    media_id = models.CharField(max_length=24)
    bytes = models.PositiveIntegerField()
    duration = models.PositiveIntegerField()
    status = models.CharField(max_length=15, default=SINGLE)
    created_on = models.DateTimeField(default=timezone.now)
    updated_on = models.DateTimeField(default=timezone.now, auto_now_add=True)


class HistoryEntry(Model):
    member = models.ForeignKey(Member)
    media_type = models.CharField(max_length=15)
    media_id = models.CharField(max_length=24)
    percentage = models.IntegerField(default=0,
                                     help_text="Percentage watched")

    class Meta:
        unique_together = ('member', 'media_id')
