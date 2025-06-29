"""api.py: DabPumps API for DAB Pumps integration."""

import copy
import math
import aiohttp
import httpx
import json
import jwt
import logging
import re
import time

from collections import namedtuple
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from yarl import URL


from .dabpumps_const import (
    DABPUMPS_SSO_URL,
    DABPUMPS_API_URL,
    DABPUMPS_API_DOMAIN,
    DABPUMPS_API_LOGIN_TIME_VALID,
    DABPUMPS_API_TOKEN_COOKIE,
    DABPUMPS_API_TOKEN_TIME_MIN,
    API_LOGIN,
    DEVICE_ATTR_EXTRA,
    STATUS_UPDATE_HOLD,
)

from .dabpumps_client import (
    DabPumpsClient_Httpx,
    DabPumpsClient_Aiohttp,
)


_LOGGER = logging.getLogger(__name__)

DabPumpsInstall = namedtuple('DabPumpsInstall', 'id, name, description, company, address, role, devices')
DabPumpsDevice = namedtuple('DabPumpsDevice', 'id, serial, name, vendor, product, hw_version, sw_version, mac_address, config_id, install_id')
DabPumpsConfig = namedtuple('DabPumpsConfig', 'id, label, description, meta_params')
DabPumpsParams = namedtuple('DabPumpsParams', 'key, type, unit, weight, values, min, max, family, group, view, change, log, report')
DabPumpsStatus = namedtuple('DabPumpsStatus', 'serial, key, code, value, unit, status_ts, update_ts')

class DabPumpsRet(Enum):
    NONE = 0
    DATA = 1
    RAW = 2
    BOTH = 3


# DabPumpsAPI to detect device and get device info, fetch the actual data from the device, and parse it
class DabPumpsApi:
    
    def __init__(self, username, password, client:httpx.AsyncClient|aiohttp.ClientSession|None = None):
        # Configuration
        self._username: str = username
        self._password: str = password

        # Retrieved data
        self._login_method: str|None = None
        self._login_time: float = 0
        self._install_map: dict[str, DabPumpsInstall] = {}
        self._device_map: dict[str, DabPumpsDevice] = {}
        self._config_map: dict[str, DabPumpsConfig] = {}
        self._status_actual_map: dict[str, DabPumpsStatus] = {}
        self._status_static_map: dict[str, DabPumpsStatus] = {}
        self._string_map: dict[str, str] = {}
        self._string_map_lang: str = None
        self._user_role: str = 'CUSTOMER'

        self._install_map_ts: datetime = datetime.min
        self._device_map_ts: datetime = datetime.min
        self._device_detail_ts: datetime = datetime.min
        self._config_map_ts: datetime = datetime.min
        self._status_actual_map_ts: datetime = datetime.min
        self._status_static_map_ts: datetime = datetime.min
        self._string_map_ts: datetime = datetime.min
        self._user_role_ts: datetime = datetime.min

        # Client (aiohttp or httpx) to keep track of cookies during login and subsequent calls
        # We keep the same client for the whole life of the api instance.
        if isinstance(client, httpx.AsyncClient):
            _LOGGER.debug(f"using passed httpx client")
            self._client = DabPumpsClient_Httpx(client)

        elif isinstance(client, aiohttp.ClientSession):
            _LOGGER.debug(f"using passed aiohttp client")
            self._client = DabPumpsClient_Aiohttp(client)

        else:
            #_LOGGER.debug(f"using new aiohttp client")
            #self._client = DabPumpsClient_Aiohttp()
            #
            _LOGGER.debug(f"using new httpx client")
            self._client = DabPumpsClient_Httpx()

        # To pass diagnostics data back to our parent
        self._diagnostics_callback = None


    def set_diagnostics(self, callback):
        self._diagnostics_callback = callback


    @staticmethod
    def create_id(*args):
        str = '_'.join(args).strip('_')
        str = re.sub(' ', '_', str)
        str = re.sub('[^a-z0-9_-]+', '', str.lower())
        return str            
    
    
    @property
    def login_method(self) -> str:
        return self._login_method
    
    @property
    def install_map(self) -> dict[str, DabPumpsInstall]:
        return self._install_map
    
    @property
    def device_map(self) -> dict[str, DabPumpsDevice]:
        return self._device_map
    
    @property
    def config_map(self) -> dict[str, DabPumpsConfig]:
        return self._config_map
    
    @property
    def status_map(self) -> dict[str, DabPumpsStatus]:
        return self._status_static_map | self._status_actual_map
    
    @property
    def string_map(self) -> dict[str, str]:
        return self._string_map
    
    @property
    def string_map_lang(self) -> str:
        return self._string_map_lang
    
    @property
    def user_role(self) -> str:
        return self._user_role

    @property
    def install_map_ts(self) -> datetime:
        return self._install_map_ts
    
    @property
    def device_map_ts(self) -> datetime:
        return self._device_map_ts
    
    @property
    def device_detail_ts(self) -> datetime:
        return self._device_detail_ts
    
    @property
    def config_map_ts(self) -> datetime:
        return self._config_map_ts
    
    @property
    def status_map_ts(self) -> datetime:
        return max( [self._status_static_map_ts, self._status_actual_map_ts] )
    
    @property
    def string_map_ts(self) -> datetime:
        return self._string_map_ts
    
    @property
    def user_role_ts(self) -> datetime:
        return self._user_role_ts

    @property
    def closed(self) -> bool:
        if self._client:
            return self._client.closed
        else:
            return True

    async def async_close(self):
        if self._client:
            await self._client.async_close()


    async def async_login(self):
        """Login to DAB Pumps by trying each of the possible login methods"""

        # Step 0: do we still have a cookie with a non-expired auth token?
        token = await self._client.async_get_cookie(DABPUMPS_API_DOMAIN, DABPUMPS_API_TOKEN_COOKIE)
        if token:
            token_payload = jwt.decode(jwt=token, options={"verify_signature": False})
            token_exp = token_payload.get("exp", 0)
            token_iat = token_payload.get("iat", 0)
            epoch_now = time.time()

            # The DAB Pumps server UTC time is observed to be out by an hour (either before or behind), 
            # so we cannot not trust the expiry time in the token!
            # Instead we just check that the last login was not too long ago
            if epoch_now - self._login_time < DABPUMPS_API_LOGIN_TIME_VALID:
                #_LOGGER.debug(f"Token reuse; login={self._login_time}, now={epoch_now}, exp={token_exp}, iat={token_iat}")
                await self._async_update_diagnostics(datetime.now(), "token reuse", None, None, token_payload)
                return
            #else:
                #_LOGGER.debug(f"Token renew; login={self._login_time}, now={epoch_now}, exp={token_exp}, iat={token_iat}")
            
            # if token_exp - epoch_now > DABPUMPS_API_TOKEN_TIME_MIN:
            #     # still valid for another 10 seconds
            #     _LOGGER.debug(f"Token reuse; exp={token_exp}, now={epoch_now}")
            #     await self._async_update_diagnostics(datetime.now(), "token reuse", None, None, token_payload)
            #     return
            
            # else:
            #     _LOGGER.debug(f"Token expired; exp={token_exp}, now={epoch_now}")

        # Make sure to have been logged out of previous sessions.
        # DAB Pumps service does not handle multiple logins from same account very well
        await self.async_logout()
        
        # We have four possible login methods that all seem to work for both DConnect (non-expired) and for DAB Live
        # First try the method that succeeded last time!
        error = None
        methods = [self._login_method, API_LOGIN.DABLIVE_APP_1, API_LOGIN.DABLIVE_APP_0, API_LOGIN.DCONNECT_APP, API_LOGIN.DCONNECT_WEB]
        for method in methods:
            try:
                match method:
                    case API_LOGIN.DABLIVE_APP_1: 
                        # Try the simplest method first
                        await self._async_login_dablive_app(isDabLive=1)
                    case API_LOGIN.DABLIVE_APP_0:
                        # Try the alternative simplest method
                        await self._async_login_dablive_app(isDabLive=0)
                    case API_LOGIN.DCONNECT_APP:
                        # Try the method that uses 2 steps
                        await self._async_login_dconnect_app()
                    case API_LOGIN.DCONNECT_WEB:
                        # Finally try the most complex and unreliable one
                        await self._async_login_dconnect_web()
                    case _:
                        # No previously known login method was set yet
                        continue

                # if we reached this point then a login method succeeded
                # keep using this client and its cookies and remember which method had success
                _LOGGER.debug(f"DAB Pumps login succeeded using method {method}")
                self._login_method = method
                self._login_time = time.time()
                return 
            
            except Exception as ex:
                error = ex

            # Clear any login cookies before the next try
            await self.async_logout()

        # if we reached this point then all methods failed.
        if error:
            raise error
        

    async def _async_login_dablive_app(self, isDabLive=1):
        """Login to DAB Pumps via the method as used by the DAB Live app"""

        # Step 1: get authorization token
        context = f"login DabLive_app (isDabLive={isDabLive})"
        request = {
            "method": "POST",
            "url": DABPUMPS_API_URL + f"/auth/token",
            "params": {
                'isDabLive': isDabLive,     # required param, though actual value seems to be completely ignored
            },
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'username': self._username, 
                'password': self._password,
            },
        }
        
        _LOGGER.debug(f"DAB Pumps login for '{self._username}' via {request["method"]} {request["url"]} with isDabLive={isDabLive}")
        result = await self._async_send_request(context, request)

        token = result.get('access_token') or ""
        if not token:
            error = f"No access token found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsApiAuthError(error)

        # if we reach this point then the token was OK
        # Store returned access-token as cookie so it will automatically be passed in next calls
        await self._client.async_set_cookie(DABPUMPS_API_DOMAIN, DABPUMPS_API_TOKEN_COOKIE, token)

        
    async def _async_login_dconnect_app(self):
        """Login to DAB Pumps via the method as used by the DConnect app"""

        # Step 1: get authorization token
        context = f"login DConnect_app"
        request = {
            "method": "POST",
            "url": DABPUMPS_SSO_URL + f"/auth/realms/dwt-group/protocol/openid-connect/token",
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'client_id': 'DWT-Dconnect-Mobile',
                'client_secret': 'ce2713d8-4974-4e0c-a92e-8b942dffd561',
                'scope': 'openid',
                'grant_type': 'password',
                'username': self._username, 
                'password': self._password 
            },
        }
        
        _LOGGER.debug(f"DAB Pumps login for '{self._username}' via {request["method"]} {request["url"]}")
        result = await self._async_send_request(context, request)

        token = result.get('access_token') or ""
        if not token:
            error = f"No access token found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsApiAuthError(error)

        # Step 2: Validate the auth token against the DABPumps Api
        context = f"login DConnect_app validatetoken"
        request = {
            "method": "GET",
            "url": DABPUMPS_API_URL + f"/api/v1/token/validatetoken",
            "params": { 
                'email': self._username,
                'token': token,
            },
        }

        _LOGGER.debug(f"DAB Pumps validate token via {request["method"]} {request["url"]}")
        result = await self._async_send_request(context, request)

        # if we reach this point then the token was OK
        # Store returned access-token as cookie so it will automatically be passed in next calls
        await self._client.async_set_cookie(DABPUMPS_API_DOMAIN, DABPUMPS_API_TOKEN_COOKIE, token)


    async def _async_login_dconnect_web(self):
        """Login to DAB Pumps via the method as used by the DConnect website"""

        # Step 1: get login url
        context = f"login DConnect_web home"
        request = {
            "method": "GET",
            "url": DABPUMPS_API_URL,
        }

        _LOGGER.debug(f"DAB Pumps retrieve login page via GET {request["url"]}")
        text = await self._async_send_request(context, request)
        
        match = re.search(r'action\s?=\s?\"(.*?)\"', text, re.MULTILINE)
        if not match:    
            error = f"Unexpected response while retrieving login url from {request["url"]}: {text}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsApiAuthError(error)
        
        # Step 2: Login
        context = f"login DConnect_web login"
        request = {
            "method": "POST",
            "url": match.group(1).replace('&amp;', '&'),
            "headers": {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            "data": {
                'username': self._username, 
                'password': self._password 
            },
        }
        
        _LOGGER.debug(f"DAB Pumps login for '{self._username}' via {request["method"]} {request["url"]}")
        await self._async_send_request(context, request)

        # Verify the client access_token cookie has been set
        token = await self._client.async_get_cookie(DABPUMPS_API_DOMAIN, DABPUMPS_API_TOKEN_COOKIE)
        if not token:
            error = f"No access token found in response from {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsApiAuthError(error)

        # if we reach this point without exceptions then login was successfull
        # client access_token is already set by the last call

        
    async def async_logout(self):
        """Logout from DAB Pumps"""

        # Home Assistant will issue a warning when calling aclose() on the async aiohttp client.
        # Instead of closing we will simply forget all cookies. The result is that on a next
        # request, the client will act like it is a new one.
        await self._client.async_clear_cookies()
        self._login_time = 0
        
        
    async def async_fetch_install_list(self, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """Get installation list"""

        # Retrieve data via REST request
        if raw is None:
            context = f"installation list"
            request = {
                "method": "GET",
                #"url": DABPUMPS_API_URL + '/getInstallationList',
                "url": DABPUMPS_API_URL + '/api/v1/installation',
            }

            _LOGGER.debug(f"DAB Pumps retrieve installation list for '{self._username}' via {request["method"]} {request["url"]}")
            raw = await self._async_send_request(context, request)  

        # Process the resulting raw data
        install_map = {}
        installations = raw.get('values', None) or raw.get('rows', None) or []
        
        for install_idx, installation in enumerate(installations):
            
            install_id = installation.get('installation_id', '')
            install_name = installation.get('name', None) or installation.get('description', None) or f"installation {install_idx}"

            _LOGGER.debug(f"DAB Pumps installation found: {install_name}")
            install = DabPumpsInstall(
                id = install_id,
                name = install_name,
                description = installation.get('description', None) or '',
                company = installation.get('company', None) or '',
                address = installation.get('address', None) or '',
                role = installation.get('user_role', None) or 'CUSTOMER',
                devices = len(installation.get('dums', None) or []),
            )
            install_map[install_id] = install

        # Sanity check. # Never overwrite a known install_map with empty lists
        if len(install_map)==0:
            raise DabPumpsApiDataError(f"No installations found in data")

        # Remember this data
        self._install_map_ts = datetime.now()
        self._install_map = install_map

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return install_map
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (install_map, raw)


    async def async_fetch_install(self, install_id: str):
        """
        Fetch all details from an installation.
        Includes list of devices, and config meta data for each device
        """

        # Retrieve list of devices within this install
        await self.async_fetch_install_details(install_id)

        for device in self._device_map.values():
                # First retrieve device config
                await self.async_fetch_device_config(device.config_id)

                # Then retrieve device details
                await self.async_fetch_device_details(device.serial)


    async def async_fetch_install_details(self, install_id: str, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """Get installation details"""

        # Retrieve data via REST request
        if raw is None:
            context = f"installation {install_id}"
            request = {
                "method": "GET",
                #"url": DABPUMPS_API_URL + f"/getInstallation/{install_id}",
                "url": DABPUMPS_API_URL + f"/api/v1/installation/{install_id}",
            }
            
            _LOGGER.debug(f"DAB Pumps retrieve installation details via {request["method"]} {request["url"]}")
            raw = await self._async_send_request(context, request)

        # Process the resulting raw data
        installation_id = raw.get('installation_id', '')
        if installation_id != install_id: 
            raise DabPumpsApiDataError(f"Expected installation id {install_id} was not found in returned installation details")

        device_map = {}
        serial_list = []
        config_list = []

        ins_dums = raw.get('dums', [])

        for dum_idx, dum in enumerate(ins_dums):
            dum_serial = dum.get('serial', None) or ''
            dum_name = dum.get('name', None) or dum.get('ProductName', None) or f"device {dum_idx}"
            dum_product = dum.get('ProductName', None) or f"device {dum_idx}"
            dum_version = dum.get('configuration_name', None) or ''
            dum_config = dum.get('configuration_id', None) or ''

            if not dum_serial: 
                raise DabPumpsApiDataError(f"Could not find installation attribute 'serial'")
            if not dum_config: 
                raise DabPumpsApiDataError(f"Could not find installation attribute 'configuration_id'")

            device = DabPumpsDevice(
                vendor = 'DAB Pumps',
                name = dum_name,
                id = self.create_id(dum_name),
                serial = dum_serial,
                product = dum_product,
                hw_version = dum_version,
                config_id = dum_config,
                install_id = install_id,
                # Attributes below are retrieved later on via async_fetch_device_details
                sw_version = None,
                mac_address = None,
            )
            device_map[dum_serial] = device

            # Keep track of config_id's and serials we have seen
            if dum_config not in config_list:
                config_list.append(dum_config) 
            
            if dum_serial not in serial_list:
                serial_list.append(dum_serial)
            
            _LOGGER.debug(f"DAB Pumps device found: {dum_name} with serial {dum_serial}")
            
        # Also detect the user role within this installation
        user_role = raw.get('user_role', 'CUSTOMER')

        # Cleanup device config and device statusses to only keep values that are still part of a device in this installation
        config_map = { k: v for k, v in self._config_map.items() if v.id in config_list }
        status_actual_map = { k: v for k, v in self._status_actual_map.items() if v.serial in serial_list }
        status_static_map = { k: v for k, v in self._status_static_map.items() if v.serial in serial_list }

        # Sanity check. # Never overwrite a known device_map, config_map or status_map with empty lists
        if len(device_map) == 0:
            raise DabPumpsApiDataError(f"No devices found for installation id {install_id}")

        # Remember/update the found maps.
        self._device_map_ts = datetime.now()
        self._device_map = device_map
        self._config_map = config_map
        self._status_actual_map = status_actual_map
        self._status_static_map = status_static_map

        self._user_role_ts = datetime.now()
        self._user_role = user_role

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return device_map
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (device_map, raw)


    async def async_fetch_device_details(self, serial: str, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """
        Fetch the extra details for a DAB Pumps device

        This function should be run AFTER async_fetch_device_config
        """
    
        # Retrieve data via REST request
        # This is actually the same data as used for statusses
        if raw is None:
            raw = await self.async_fetch_device_statusses(serial, raw=raw, ret=DabPumpsRet.RAW)
        
        # Process the resulting raw data
        device = self._device_map[serial]
        device_dict = device._asdict()
        device_changed = False

        # Search for specific statusses
        for attr,keys in DEVICE_ATTR_EXTRA.items():
            for key in keys:

                # Try to find a status for this key and device
                status = next( (status for status in self._status_actual_map.values() if status.serial==serial and status.key==key), None)
                
                if status is not None and status.value is not None:
                    # Found it. Update the device attribute (workaround via dict because it is a namedtuple)
                    if getattr(device, attr) != status.value:
                        _LOGGER.debug(f"Found extra device attribute {serial} {attr} = {status.value}")
                        device_dict[attr] = status.value
                        device_changed = True

        # Remember/update the found device details
        if device_changed:
            self._device_map[serial] = DabPumpsDevice(**device_dict)

        self._device_detail_ts = datetime.now()

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return self._device_map[serial]
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (self._device_map[serial], raw)


    async def async_fetch_device_config(self, config_id: str, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """Fetch the statusses for a DAB Pumps device, which then constitues the Sensors"""

        # Retrieve data via REST request
        if raw is None:
            context = f"configuration {config_id}"
            request = {
                "method": "GET",
                "url":  DABPUMPS_API_URL + f"/api/v1/configuration/{config_id}",
                # or    DABPUMPS_API_URL + f"/api/v1/configure/paramsDefinition?version=0&doc={config_name}",
            }
            
            _LOGGER.debug(f"DAB Pumps retrieve device config for '{config_id}' via {request["method"]} {request["url"]}")
            raw = await self._async_send_request(context, request)

        # Process the resulting raw data
        config_map = {}

        conf_id = raw.get('configuration_id', '')
        conf_name = raw.get('name') or f"config{conf_id}"
        conf_label = raw.get('label') or f"config{conf_id}"
        conf_descr = raw.get('description') or f"config {conf_id}"
        conf_params = {}

        if conf_id != config_id: 
            raise DabPumpsApiDataError(f"Expected configuration id {config_id} was not found in returned configuration data")
            
        meta = raw.get('metadata') or {}
        meta_params = meta.get('params') or []
        
        for meta_param_idx, meta_param in enumerate(meta_params):
            # get param details
            param_name = meta_param.get('name') or f"param{meta_param_idx}"
            param_type = meta_param.get('type') or ''
            param_unit = meta_param.get('unit')
            param_weight = meta_param.get('weight')
            param_min = meta_param.get('min') or meta_param.get('warn_low')
            param_max = meta_param.get('max') or meta_param.get('warn_hi')
            param_family = meta_param.get('family') or ''
            param_group = meta_param.get('group') or ''
            
            values = meta_param.get('values') or []
            param_values = { str(v[0]): str(v[1]) for v in values if len(v) >= 2 }
            
            param = DabPumpsParams(
                key = param_name,
                type = param_type,
                unit = param_unit,
                weight = param_weight,
                values = param_values,
                min = param_min,
                max = param_max,
                family = param_family,
                group = param_group,
                view = ''.join([ s[0] for s in (meta_param.get('view') or []) ]),
                change = ''.join([ s[0] for s in (meta_param.get('change') or []) ]),
                log = ''.join([ s[0] for s in (meta_param.get('log') or []) ]),
                report = ''.join([ s[0] for s in (meta_param.get('report') or []) ])
            )
            conf_params[param_name] = param
        
        config = DabPumpsConfig(
            id = conf_id,
            label = conf_label,
            description = conf_descr,
            meta_params = conf_params
        )
        config_map[conf_id] = config
        
        _LOGGER.debug(f"DAB Pumps configuration found: {conf_name} with {len(conf_params)} metadata params")        

        # Merge with configurations from other devices
        self._config_map_ts = datetime.now()
        self._config_map.update(config_map)

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return config
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (config, raw)
        
        
    async def async_fetch_device_statusses(self, serial: str, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """Fetch the statusses for a DAB Pumps device"""

        # also re-generate static statusses for this device serial
        await self._async_fetch_static_statusses(serial)

        (data, raw) = await self._async_fetch_device_statusses(serial, raw, ret=DabPumpsRet.BOTH)

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return self.status_map
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (self.status_map, raw)


    async def _async_fetch_static_statusses(self, serial: str):
        """Fetch the static statusses for a DAB Pumps device"""

        # Check for static statusses that have been modified
        for status_key in self._status_static_map.keys():

            # Does this static status have a related actual/modified status?
            status_mod = self._status_actual_map.get(status_key, None)
            if status_mod and \
               status_mod.update_ts is not None and \
               (datetime.now(timezone.utc) - status_mod.update_ts).total_seconds() > STATUS_UPDATE_HOLD:
                
                # Remove the actual/modified value
                self._status_actual_map.pop(status_key, None)

        # Process the existing data
        status_map = {}

        device = self._device_map.get(serial, None)
        if not device:
            return

        config = self._config_map.get(device.config_id)
        if not config or not config.meta_params:
            return

        for params in config.meta_params.values():
            is_static = False
            code = None
            value = ""

            # Detect 'button' params (type 'enum' with only one possible value)
            if params.type == 'enum' and len(params.values or []) == 1:
                is_static = True
                code = str(params.min) if params.min is not None else "0"
                value = ""

            # Add other static params types here in future
            pass

            if is_static:
                status_key = DabPumpsApi.create_id(device.serial, params.key)
                status_new = DabPumpsStatus(
                    serial = device.serial,
                    key = params.key,
                    code = code,
                    value = value,
                    unit = params.unit,
                    status_ts = datetime.now(timezone.utc),
                    update_ts = None,
                )
                status_map[status_key] = status_new 

        # Merge with statusses from other devices
        self._status_static_map_ts = datetime.now()
        self._status_static_map.update(status_map)
        
        
    async def _async_fetch_device_statusses(self, serial: str, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """Fetch the statusses for a DAB Pumps device"""
    
        # Retrieve data via REST request
        if raw is None:
            context = f"statusses {serial}"
            request = {
                "method": "GET",
                "url": DABPUMPS_API_URL + f"/dumstate/{serial}",
                # or   DABPUMPS_API_URL + f"/api/v1/dum/{serial}/state",
            }
            
            _LOGGER.debug(f"DAB Pumps retrieve device statusses for '{serial}' via {request["method"]} {request["url"]}")
            raw = await self._async_send_request(context, request)
        
        # Process the resulting raw data
        status_map = {}
        status = raw.get('status') or "{}"
        values = json.loads(status)

        statusts = raw.get('statusts') or ""
        status_ts = datetime.fromisoformat(statusts) if statusts else datetime.now(timezone.utc)

        for item_key, item_code in values.items():
            # the code 'h' is used when a property is not available/supported
            if item_code=='h':
                continue

            # Check if this item was recently updated in our current status_map
            status_key = DabPumpsApi.create_id(serial, item_key)
            status_old = self._status_actual_map.get(status_key, None)

            if status_old and \
            status_old.update_ts is not None and \
            (datetime.now(timezone.utc) - status_old.update_ts).total_seconds() < STATUS_UPDATE_HOLD:

                _LOGGER.debug(f"Skip refresh of recently updated status ({status_key})")
                continue

            # Resolve the coded value into the real world value
            (item_val, item_unit) = self._decode_status_value(serial, item_key, item_code)

            # Add it to our statusses
            status_new = DabPumpsStatus(
                serial = serial,
                key = item_key,
                code = item_code,
                value = item_val,
                unit = item_unit,
                status_ts = status_ts,
                update_ts = None,
            )
            status_map[status_key] = status_new

        if len(status_map) == 0:
            raise DabPumpsApiDataError(f"No statusses found for '{serial}'")
        
        _LOGGER.debug(f"DAB Pumps statusses found for '{serial}' with {len(status_map)} values")

        # Merge with statusses from other devices
        self._status_actual_map_ts = datetime.now()
        self._status_actual_map.update(status_map)

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return status_map
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (status_map, raw)
        
        
    async def async_change_device_status(self, serial: str, key: str, code: str|None=None, value: Any|None=None):
        """
        Set a new status value for a DAB Pumps device.

        Either code (the value as expected by Dab Pumps backend) or value (the real world value)
        needs to be supplied.
        """

        # Sanity check
        if code is None and value is None:
            
            _LOGGER.warning(f"To change device status either 'code' or 'value' needs to be specified")
            return False
        
        status_key = DabPumpsApi.create_id(serial, key)  

        status = self._status_actual_map.get(status_key, None) or self._status_static_map.get(status_key, None)
        if not status:
            # Not found
            return False
        
        # If needed encode the value into what DabPumps backend expects
        if code is None:
            code = self._encode_status_value(serial, key, value)
        else:
            (value,_) = self._decode_status_value(serial, key, code)
            
        if status.code == code:
            # Not changed
            return False
        
        _LOGGER.info(f"Set {serial}:{key} from {status.value} to {value} ({code})")
        
        # update the cached value in status_map
        status = status._replace(code=code, value=value, update_ts=datetime.now(timezone.utc))
        self._status_actual_map[status_key] = status
        
        # Update data via REST request
        context = f"set {status.serial}:{status.key}"
        request = {
            "method": "POST",
            "url": DABPUMPS_API_URL + f"/dum/{status.serial}",
            "headers": {
                'Content-Type': 'application/json',
            },
            "json": {
                'key': status.key, 
                'value': status.code
            },
        }
        
        _LOGGER.debug(f"DAB Pumps set device param for '{status.serial}:{status.key}' to '{value}' via {request["method"]} {request["url"]}")
        raw = await self._async_send_request(context, request)
        
        # If no exception was thrown then the operation was successfull
        return True
    

    async def async_fetch_strings(self, lang: str, raw: dict|None = None, ret: DabPumpsRet|None = DabPumpsRet.DATA):
        """Get string translations"""
    
        # Retrieve data via REST request
        if raw is None:
            context = f"localization_{lang}"
            request = {
                "method": "GET",
                "url": DABPUMPS_API_URL + f"/resources/js/localization_{lang}.properties?format=JSON",
            }
            
            _LOGGER.debug(f"DAB Pumps retrieve language info via {request["method"]} {request["url"]}")
            raw = await self._async_send_request(context, request)

        # Process the resulting raw data
        language = raw.get('bundle', '')
        messages = raw.get('messages', {})
        string_map = { k: v for k, v in messages.items() }
        
        # Sanity check. # Never overwrite a known string_map with empty lists
        if len(string_map) == 0:
            raise DabPumpsApiDataError(f"No strings found in data")

        _LOGGER.debug(f"DAB Pumps strings found: {len(string_map)} in language '{language}'")
        
        # Remember this data
        self._string_map_ts = datetime.now() if len(string_map) > 0 else datetime.min
        self._string_map_lang = language
        self._string_map = string_map

        # Return data or raw or both
        match ret:
            case DabPumpsRet.DATA: return string_map
            case DabPumpsRet.RAW: return raw
            case DabPumpsRet.BOTH: return (string_map, raw)


    def get_status_value(self, serial: str, key: str) -> DabPumpsStatus:
        """
        Resolve code, value and unit for a status
        """
        status_key = DabPumpsApi.create_id(serial, key)

        # Return status for this key; decoding and translation of code into value is already done.
        return self._status_actual_map.get(status_key, None) or self._status_static_map.get(status_key, None)


    def get_status_metadata(self, serial: str, key: str, translate:bool = True) -> DabPumpsParams:
        """
        Resolve meta params for a status
        """

        # Find the meta params for this status
        device = self._device_map.get(serial, None) if self._device_map else None
        config = self._config_map.get(device.config_id, None) if device is not None and self._config_map  else None
        params = config.meta_params.get(key, None) if config is not None and config.meta_params else None

        # Apply translations
        if translate and params is not None and params.values is not None:
            params_dict = params._asdict()
            params_dict['values'] = { k:self.translate_string(v) for k,v in params.values.items() }
            params = DabPumpsParams(**params_dict)

        return params


    def _decode_status_value(self, serial: str, key: str, code: str) -> Any:
        """
        Resolve the coded value into the real world value.
        Also returns the unit of measurement.
        """

        # Find the meta params for this status
        params = self.get_status_metadata(serial, key, translate=False)

        if params is None or code is None:
            return (code, '')
        
        # param:DabPumpsParam - 'key, type, unit, weight, values, min, max, family, group, view, change, log, report'
        match params.type:
            case 'enum':
                # Lookup value and translate
                value = self.translate_string(params.values.get(code, code))

            case 'measure':
                if params.weight and params.weight != 1 and params.weight != 0:
                    # Convert to float
                    precision = int(math.floor(math.log10(1.0 / params.weight)))
                    value = round(float(code) * params.weight, precision)
                else:
                    # Convert to int
                    value = int(code)
                    
            case 'label':
                # Convert to string; no translation
                value = str(code)

            case _:
                _LOGGER.warning(f"Encountered an unknown params type '{params.type}' for '{serial}:{params.key}'. Please contact the integration developer to have this resolved.")
                value = None

        return (value, params.unit)


    def _encode_status_value(self, serial: str, key: str, value: Any) -> Any:
        """
        Resolve the real world value into the coded value.
        """

        # Find the meta params for this status
        device = self._device_map.get(serial, None) if self._device_map else None
        config = self._config_map.get(device.config_id, None) if device is not None and self._config_map  else None
        params = config.meta_params.get(key, None) if config is not None and config.meta_params else None

        if params is None or value is None:
            return str(value)
        
        # param:DabPumpsParam - 'key, type, unit, weight, values, min, max, family, group, view, change, log, report'
        match params.type:
            case 'enum':
                code = next( (str(k) for k,v in params.values.items() if v==value), None)
                if code is None:
                    code = str(value)

            case 'measure':
                if params.weight and params.weight != 1 and params.weight != 0:
                    # Convert from float to int
                    code = str(int(round(value / params.weight)))
                else:
                    # Convert to int
                    code = str(int(value))
                    
            case 'label':
                # Convert to string
                code = str(value)

            case _:
                _LOGGER.warning(f"Encountered an unknown params type '{params.type}' for '{serial}:{params.key}'. Please contact the integration developer to have this resolved.")
                code = None
        
        return code
    

    def translate_string(self, str: str) -> str:
        """
        Return 'translated' string or original string if not found
        """
        return self._string_map.get(str, str) if self._string_map else str
    

    async def _async_send_request(self, context, request):
        """GET or POST a request for JSON data"""

        timestamp = datetime.now()

        # Always add certain headers
        if not "headers" in request:
            request["headers"] = {}

        request["headers"]['Cache-Control'] = 'no-cache'
        #request["headers"]['Connection'] = 'keep-alive'
        #request["headers"]['Accept'] = '*/*'

        # Perform the request
        (request,response) = await self._client.async_send_request(request)

        # Save the diagnostics if requested
        await self._async_update_diagnostics(timestamp, context, request, response)
        
        # Check response
        if not response["success"]:
            error = f"Unable to perform request, got response {response["status"]} while trying to reach {request["url"]}"
            _LOGGER.debug(error)    # logged as warning after last retry
            raise DabPumpsApiError(error)

        if "text" in response:
            return response["text"]
        
        elif "json" in response:
            # if the result structure contains a 'res' value, then check it
            json = response["json"]
            res = json.get('res', None)
            if res and res != 'OK':
                # BAD RESPONSE: { "res": "ERROR", "code": "FORBIDDEN", "msg": "Forbidden operation", "where": "ROUTE RULE" }
                code = json.get('code', '')
                msg = json.get('msg', '')
                
                if code in ['FORBIDDEN']:
                    error = f"Authorization failed: {res} {code} {msg}"
                    _LOGGER.debug(error)    # logged as warning after last retry

                    # Force a logout to so next login will be a real login, not a token reuse
                    await self.async_logout()
                    raise DabPumpsApiRightsError(error)
                else:
                    error = f"Unable to perform request, got response {res} {code} {msg} while trying to reach {request["url"]}"
                    _LOGGER.debug(error)    # logged as warning after last retry
                    raise DabPumpsApiError(error)

            return json
        
        else:
            return None
    

    async def _async_update_diagnostics(self, timestamp, context: str, request: dict|None, response: dict|None, token: dict|None = None):

        if self._diagnostics_callback:
            item = DabPumpsApiHistoryItem(timestamp, context, request, response, token)
            detail = DabPumpsApiHistoryDetail(timestamp, context, request, response, token)
            data = {
                "login_method": self._login_method,
            }

            self._diagnostics_callback(context, item, detail, data)
    

class DabPumpsApiAuthError(Exception):
    """Exception to indicate authentication failure."""

class DabPumpsApiRightsError(Exception):
    """Exception to indicate authorization failure"""

class DabPumpsApiError(Exception):
    """Exception to indicate generic error failure."""    
    
class DabPumpsApiDataError(Exception):
    """Exception to indicate generic data failure."""  

    
class DabPumpsApiHistoryItem(dict):
    def __init__(self, timestamp, context: str , request: dict|None, response: dict|None, token: dict|None):
        item = { 
            "ts": timestamp, 
            "op": context,
        }

        # If possible, add a summary of the response status and json res and code
        if response:
            rsp = []
            if "status_code" in response:
                rsp.append(response["status_code"])
            if "status" in response:
                rsp.append(response["status"])
            
            if json := response.get("json", None):
                if res := json.get('res', ''): rsp.append(f"res={res}")
                if code := json.get('code', ''): rsp.append(f"code={code}")
                if msg := json.get('msg', ''): rsp.append(f"msg={msg}")
                if details := json.get('details', ''): rsp.append(f"details={details}")

            item["rsp"] = ', '.join(rsp)

        # add as new history item
        super().__init__(item)


class DabPumpsApiHistoryDetail(dict):
    def __init__(self, timestamp, context: str, request: dict|None, response: dict|None, token: dict|None):
        item = { 
            "ts": timestamp, 
        }

        if request:
            item["req"] = request
        if response:
            item["rsp"] = response
        if token:
            item["token"] = token

        super().__init__(item)
