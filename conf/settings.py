"""
Django settings for Kobhio project.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.6/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.6/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '&t3y$750-6atn949l3!rkjw#84346_hdi%%*3ekp#q2(ppbqs!'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
# DEBUG = False
TESTING = False
LOCAL_DEV = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = ['*']

SESSION_COOKIE_NAME = 'svd_sessionid'


# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.webdesign',

    # Third parties
    'ajaxuploader',
    'djangotoolbox',
    'permission_backend_nonrel',
    'django_user_agents',
    'import_export',
    'tracking',

    # ikwen
    'ikwen.core',
    'ikwen.cashout',
    'ikwen.billing',
    'ikwen.accesscontrol',
    'ikwen.partnership',
    'ikwen.flatpages',
    'ikwen.theming',

    # Shavida
    'ikwen_shavida.shavida',
    'ikwen_shavida.movies',
    'ikwen_shavida.reporting',
    'ikwen_shavida.sales',
    # 'ikwen_shavida.vod',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_user_agents.middleware.UserAgentMiddleware',
    'tracking.middleware.VisitorTrackingMiddleware',
    'ikwen.core.middleware.ServiceStatusCheckMiddleware',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    "django.contrib.auth.context_processors.auth",
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
    "django.core.context_processors.media",
    "django.core.context_processors.static",
    "django.contrib.messages.context_processors.messages",
    'django.core.context_processors.request',
    'ikwen_shavida.shavida.context_processors.project_settings',
)

ROOT_URLCONF = 'ikwen_shavida.conf.urls'

WSGI_APPLICATION = 'ikwen_shavida.conf.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.6/ref/settings/#databases

if DEBUG or TESTING:
    WALLETS_DB = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/home/komsihon/Dropbox/PycharmProjects/ikwen/db.sqlite3',
    }
else:
    WALLETS_DB = {  # ikwen_kakocase.ikwen_kakocase relational database used to store sensitive objects among which CashOutRequest
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '',
        'USER': '',
        'PASSWORD': ''
    }

DATABASES = {
    'default': {
        'ENGINE': 'django_mongodb_engine',
        'NAME': '',
    },
    'umbrella': {
        'ENGINE': 'django_mongodb_engine',
        'NAME': '',
    },
    'wallets': WALLETS_DB
}

# Internationalization
# https://docs.djangoproject.com/en/1.6/topics/i18n/

LANGUAGE_CODE = 'en'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = False

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/var/www/example.com/media/"
MEDIA_ROOT = '/home/komsihon/Dropbox/PycharmProjects/Shavida/media/'

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://example.com/media/", "http://media.example.com/"
MEDIA_URL = '/shavida/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT = '/home/komsihon/Dropbox/PycharmProjects/Shavida/static/'

# URL prefix for static files.
# Example: "http://example.com/static/", "http://static.example.com/"
STATIC_URL = '/shavida/static/'

TEMPLATE_DIRS = (os.path.join(BASE_DIR,  'templates'),)

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': '127.0.0.1:11211',
        'TIMEOUT': 60,
        'KEY_PREFIX': 'svdlocal',  # Use rather svdprod for Production
        'VERSION': '1'
    }
}

IKWEN_SERVICE_ID = '56ad2bd9b37b335a18fe5861'

# IS_IKWEN = True
# IS_UMBRELLA = True

AUTH_USER_MODEL = 'accesscontrol.Member'

AUTHENTICATION_BACKENDS = (
    'permission_backend_nonrel.backends.NonrelPermissionBackend',
    'ikwen.accesscontrol.backends.LocalDataStoreBackend',
)

IKWEN_REGISTER_EVENTS = (
    'ikwen_shavida.shavida.views.create_member_profile',
)

LOGIN_URL = 'ikwen:sign_in'
LOGOUT_REDIRECT_URL = 'movies:home'
LOGIN_REDIRECT_URL = 'movies:home'

STAFF_ROUTER = (
    ('sales.ik_view_dashboard', 'dashboard'),
    ('sales.ik_manage_media', 'admin:app_list', ('movies', )),
)

IKWEN_LOGIN_EVENTS = (
    'ikwen_shavida.shavida.views.create_member_profile',
    'ikwen_shavida.shavida.views.set_additional_session_info',
)

IKWEN_CONFIG_MODEL = 'shavida.OperatorProfile'
IKWEN_CONFIG_MODEL_ADMIN = 'ikwen_shavida.shavida.admin.OperatorProfileAdmin'

IKWEN_BASE_URL = 'http://localhost/ikwen'  # Used only for dev purposes (DEBUG = False)
WSGI_SCRIPT_ALIAS = '/shavida'  # Used only for dev purposes (DEBUG = False)

#  *******       SHAVIDA CONFIGURATION       *******  #
IS_VOD_OPERATOR = True
# IS_CONTENT_VENDOR = True
IS_GAME_VENDOR = True

SALES_UNIT = "Volume"
# SALES_UNIT = "Broadcasting"

# Path of the function to execute when querying a file that is not in MP4. Your function will be called as such:
# your_function(request, media, *args, **kwargs)
# media is an instance of either Movie or SeriesEpisode.
# Your function can return either None (in this case the movies.stream() function will pursue its execution) or
# return a JSON error message of the form HttpResponse(json.dumps({'error': "Your error message"}))
NOT_MP4_HANDLER = 'ikwen_shavida.movies.views.queue_for_transcode'

EMAIL_HOST = ''
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
EMAIL_PORT = 587
EMAIL_USE_TLS = True


#  *******       JUMBOPAY MOMO API      *******  #

DEBUG_MOMO = True  # Sets the cashout amount to XAF 100 regardless of the real value
MOMO_BEFORE_CASH_OUT = 'ikwen_shavida.sales.views.set_momo_order_checkout'
MOMO_AFTER_CASH_OUT = 'ikwen_shavida.sales.views.confirm_payment'
JUMBOPAY_API_URL = 'https://154.70.100.194/api/sandbox/v2/' if DEBUG else 'https://154.70.100.194/api/live/v2/'
MTN_MOMO_API_URL = 'https://developer.mtn.cm/OnlineMomoWeb/faces/transaction/transactionRequest.xhtml'