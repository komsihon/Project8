# -*- coding: utf-8 -*-

__author__ = 'Kom Sihon'

from django.conf.urls import *
from ikwen_shavida.reporting.views import start_auto_selection, get_repo_files_update, check_auto_selection_status

urlpatterns = patterns(
    '',
    url(r'^start_auto_selection$', start_auto_selection, name='start_auto_selection'),
    url(r'^check_auto_selection_status$', check_auto_selection_status, name='check_auto_selection_status'),
    url(r'^get_repo_files_update$', get_repo_files_update, name='get_repo_files_update'),
)
