# -*- coding: utf-8 -*-

from django.conf.urls import *
from django.contrib.auth.decorators import permission_required
from ikwen_shavida.sales.views import confirm_order, cancel_order, confirm_processed, OrderDetail, PartnerDashboard, \
    PartnerWalletList

from ikwen_shavida.sales.views import choose_retail_bundle, choose_vod_bundle, choose_temp_bundle

urlpatterns = patterns(
    '',
    url(r'^choose_retail_bundle$', choose_retail_bundle, name='choose_retail_bundle'),
    url(r'^choose_vod_bundle$', choose_vod_bundle, name='choose_vod_bundle'),
    url(r'^choose_temp_bundle$', choose_temp_bundle, name='choose_temp_bundle'),
    url(r'^confirm_order$', confirm_order, name='confirm_order'),
    url(r'^cancel_order$', cancel_order, name='cancel_order'),
    url(r'^confirm_processed$', confirm_processed, name='confirm_processed'),
    url(r'^orderDetail/(?P<order_id>[-\w]+)/$', OrderDetail.as_view(), name='order_detail'),
    url(r'^partnerDashboard/$', permission_required('sales.ik_access_partner_dashboard')(PartnerDashboard.as_view()), name='partner_dashboard'),
    url(r'^partnerWalletList/$', permission_required('sales.ik_view_partner_wallets')(PartnerWalletList.as_view()), name='partner_wallet_list'),
)
