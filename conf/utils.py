# -*- coding: utf-8 -*-

from django.conf import settings

__author__ = 'Kom Sihon'


def is_content_vendor():
    """
    Helper function to check what is the platform main activity
    """
    content_vendor = getattr(settings, 'IS_CONTENT_VENDOR', False)
    if content_vendor:
        return content_vendor
    vod_operator = getattr(settings, 'IS_VOD_OPERATOR', True)
    return not vod_operator


def is_vod_operator():
    return not is_content_vendor()