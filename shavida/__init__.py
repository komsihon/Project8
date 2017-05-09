from django.conf import settings
from ikwen_shavida.shavida.signals import kick_my_other_sessions
from django.contrib.auth.signals import user_logged_in

if getattr(settings, 'IS_VOD_OPERATOR', False):
    user_logged_in.connect(kick_my_other_sessions)
