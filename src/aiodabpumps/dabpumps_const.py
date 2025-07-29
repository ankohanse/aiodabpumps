"""Constants for the DAB Pumps integration."""
import logging
import types

_LOGGER: logging.Logger = logging.getLogger(__package__)

DABCS_INIT_URL = "https://api.eu.dabcs.it/mobile/v1/initialconfig"
DABPUMPS_SSO_URL = "https://dabsso.dabpumps.com"
DABPUMPS_API_URL = "https://dconnect.dabpumps.com"
DABPUMPS_API_DOMAIN = "dconnect.dabpumps.com"
DABPUMPS_API_ACCESS_TOKEN_COOKIE = "dabcsauthtoken"
DABPUMPS_API_ACCESS_TOKEN_VALID = 5*60  # 5 minutes in seconds
DABPUMPS_API_REFRESH_TOKEN_VALID = 30*24*60*60 # 30 days in seconds
DABPUMPS_API_TOKEN_TIME_MIN = 10 # seconds remaining before we re-login
DABPUMPS_API_LOGIN_TIME_VALID = 30 * 60 # 30 minutes before we require re-login

DABPUMPS_DEFAULT_CLIENT_ID = 'h2d-mobile'
DABPUMPS_DEFAULT_TRANSLATIONS_URL = 'https://dconnect.dabpumps.com/resources/js/localization_{lang}.properties?format=JSON&fullmerge=1'
H2D_REDIRECT_URI = 'dabiopapp://Welcome'
H2D_CLIENT_ID = 'h2d-mobile'

API_LOGIN = types.SimpleNamespace()
API_LOGIN.ACCESS_TOKEN = 'Access_token'
API_LOGIN.REFRESH_TOKEN = 'Refresh_token'
API_LOGIN.H2D_APP = 'H2D_app'
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

# Known device statusses that normally don't hold a value until an action occurs
DEVICE_STATUS_STATIC = {
    "PowerShowerCountdown",
    "SleepModeCountdown",
}