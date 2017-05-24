from django.conf.urls import patterns, include, url

from django.contrib import admin
from django.contrib.auth.decorators import permission_required, login_required
from ikwen.accesscontrol.views import SignIn
from ikwen.flatpages.views import FlatPageView
from ikwen_shavida.sales.views import Dashboard
from ikwen_shavida.shavida.views import PhoneConfirmation

admin.autodiscover()


__author__ = "Kom Sihon"

urlpatterns = patterns(
    '',
    url(r'^$', SignIn.as_view(), name='home'),
    url(r'^i18n/', include('django.conf.urls.i18n')),

    url(r'^ikwen/admin/', include(admin.site.urls)),
    url(r'^ikwen/dashboard/$', permission_required('accesscontrol.sudo')(Dashboard.as_view()), name='dashboard'),
    url(r'^ikwen/theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^ikwen/cashout/', include('ikwen.cashout.urls', namespace='cashout')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),

    url(r'^reporting/', include('ikwen_shavida.reporting.urls', namespace='reporting')),
    url(r'^sales/', include('ikwen_shavida.sales.urls', namespace='sales')),
    url(r'^page/(?P<slug>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),

    url(r'^', include('ikwen_shavida.movies.urls', namespace='movies')),
    url(r'^', include('ikwen_shavida.shavida.urls', namespace='shavida')),
    url(r'^phoneConfirmation$', login_required(PhoneConfirmation.as_view()), name='phone_confirmation'),
)
