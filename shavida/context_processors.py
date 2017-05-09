from django.conf import settings
from django.utils.translation import gettext as _
from ikwen.core.context_processors import project_settings as ikwen_settings

from ikwen_shavida.sales.models import SalesConfig


def project_settings(request):
    """
    Adds utility project url and ikwen base url context variable to the context.
    """
    unit = getattr(settings, 'SALES_UNIT', SalesConfig.BROADCASTING_TIME)
    SALES_UNIT_STR = _("GigaBytes") if unit == SalesConfig.DATA_VOLUME else _("Hours")
    SALES_UNIT_STR_XS = "GB" if unit == SalesConfig.DATA_VOLUME else "H"
    shavida_settings = ikwen_settings(request)['settings']
    shavida_settings.update({
        'VOD_COUNTER_INTERVAL': getattr(settings, 'VOD_COUNTER_INTERVAL', 5),
        'IS_VOD_OPERATOR': getattr(settings, 'IS_VOD_OPERATOR', False),
        'IS_CONTENT_VENDOR': getattr(settings, 'IS_CONTENT_VENDOR', False),
        'IS_GAME_VENDOR': getattr(settings, 'IS_GAME_VENDOR', False),
        'SALES_UNIT': getattr(settings, 'SALES_UNIT', SalesConfig.BROADCASTING_TIME),
        'SALES_UNIT_STR': SALES_UNIT_STR,
        'SALES_UNIT_STR_XS': SALES_UNIT_STR_XS,
    })
    return {
        'settings': shavida_settings
    }
