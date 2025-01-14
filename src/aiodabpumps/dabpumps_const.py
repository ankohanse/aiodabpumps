"""Constants for the DAB Pumps integration."""
import logging
import types

_LOGGER: logging.Logger = logging.getLogger(__package__)

DABPUMPS_SSO_URL = "https://dabsso.dabpumps.com"
DABPUMPS_API_URL = "https://dconnect.dabpumps.com"
DABPUMPS_API_DOMAIN = "dconnect.dabpumps.com"
DABPUMPS_API_TOKEN_COOKIE = "dabcsauthtoken"
DABPUMPS_API_TOKEN_TIME_MIN = 10 # seconds remaining before we re-login

API_LOGIN = types.SimpleNamespace()
API_LOGIN.DABLIVE_APP_0 = 'DabLive_app_0'
API_LOGIN.DABLIVE_APP_1 = 'DabLive_app_1'
API_LOGIN.DCONNECT_APP = 'DConnect_app'
API_LOGIN.DCONNECT_WEB = 'DConnect_web'

# Period to prevent status updates when value was recently updated
STATUS_UPDATE_HOLD = 30 # seconds

# Extra device attributes that are not in install info, but retrieved from statusses
DEVICE_ATTR_EXTRA = {
    "mac_address": ['MacWlan'],
    "sw_version": ['LvFwVersion', 'ucVersion']
}
