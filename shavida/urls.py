# -*- coding: utf-8 -*-

from django.conf.urls import *
from ikwen_shavida.shavida.views import authorize_adult, DeployCloud
from ikwen_shavida.reporting.views import History

urlpatterns = patterns(
    '',
    url(r'^deployCloud/$', DeployCloud.as_view(), name='deploy_cloud'),
    url(r'^history/$', History.as_view(), name='history'),
    url(r'^authorize_adult$', authorize_adult, name='authorize_adult'),
)
